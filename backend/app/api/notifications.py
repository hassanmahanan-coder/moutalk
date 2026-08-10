"""离线通知 API（PRD 9.15 / 故事 7）：未读拉取 + 已读标记 + 列表 + 全局推送通道。"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.services import notification_service
from app.services.security import TokenType, decode_token
from app.services.ws_manager import get_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread: bool = False,
    type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拉取通知列表（unread=true 仅未读；type 按类型筛选，PRD 7.6）。"""
    items = notification_service.list_notifications(
        db, current_user.id, unread_only=unread, type_=type
    )
    return {"items": items}


@router.websocket("/ws")
async def notifications_ws(ws: WebSocket, token: str = Query("")) -> None:
    """全局通知推送通道（PRD 9.15 双写）：登录后建立，支付/报告事件实时推送。"""
    if not token:
        await ws.accept()
        await ws.send_json({"type": "error", "code": "UNAUTHORIZED", "message": "缺少访问令牌"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = decode_token(token, TokenType.ACCESS)
    except JWTError:
        await ws.accept()
        await ws.send_json({"type": "error", "code": "INVALID_TOKEN", "message": "访问令牌无效或已过期"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    user_id = payload["sub"]
    sid = f"notif:{user_id}"
    await ws.accept()
    get_ws_manager().register(sid, ws, user_id=user_id)
    try:
        while True:
            await ws.receive_text()  # 心跳/客户端消息忽略，仅保活
    except WebSocketDisconnect:
        pass
    finally:
        get_ws_manager().unregister(sid)


@router.patch("/{notification_id}")
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """标记已读（归属校验，幂等）。"""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "NOTIFICATION_NOT_FOUND", "message": "通知不存在"})
    ok = notification_service.mark_read(db, nid, current_user.id)
    if not ok:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "无权操作该通知"})
    return {"read": True}
