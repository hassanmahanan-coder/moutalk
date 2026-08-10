"""离线通知服务（PRD 9.15 / 故事 7）：双写 + 幂等 + 未读/已读 + 30 天清理。

- create_notification：事件落库（(user_id, type, payload_hash) 唯一防重复）
- 双写策略：事件发生无论在线与否都落库；在线额外 WS 推送（调用方做）
- list_notifications：未读/全部，按时间倒序
- mark_read：归属校验 + 幂等
- cleanup_expired：删除 N 天前未读通知（Celery beat 每日调用）
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Notification, NotificationType

logger = logging.getLogger(__name__)

DEFAULT_EXPIRE_DAYS = 30  # PRD 9.15：通知保留 30 天


def _payload_hash(payload: dict | None) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def create_notification(
    db: Session,
    user_id: uuid.UUID,
    type_: NotificationType | str,
    title: str,
    payload: dict[str, Any] | None = None,
) -> Notification | None:
    """落库通知；同 (user_id, type, payload_hash) 已存在返回 None（幂等）。"""
    if isinstance(type_, str):
        type_ = NotificationType(type_)
    n = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        payload_json=payload,
        payload_hash=_payload_hash(payload),
    )
    db.add(n)
    try:
        db.flush()
        return n
    except IntegrityError:
        db.rollback()
        logger.info("通知重复事件已忽略: user=%s type=%s", user_id, type_.value)
        return None


def list_notifications(
    db: Session,
    user_id: uuid.UUID,
    unread_only: bool = False,
    type_: str | NotificationType | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    if type_ is not None:
        query = query.where(Notification.type == NotificationType(type_))
    rows = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(n.id),
            "type": n.type.value,
            "title": n.title,
            "payload": n.payload_json,
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


def mark_read(db: Session, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """标记已读（归属校验，幂等）。"""
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user_id:
        return False
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        db.commit()
    return True


def cleanup_expired(db: Session, days: int = DEFAULT_EXPIRE_DAYS) -> int:
    """删除 N 天前未读通知（Celery beat 每日调用，PRD 9.15）。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = db.execute(
        delete(Notification).where(
            Notification.created_at < cutoff,
            Notification.read_at.is_(None),
        )
    )
    return result.rowcount or 0
