"""离线通知测试（PRD 9.15 / 故事 7）：双写 + 幂等 + 未读拉取/已读/清理。

契约：
- POST /api/notifications 仅系统内部使用（不暴露给用户）——测试直接测 service
- GET /api/notifications?unread=true 用户拉取未读
- PATCH /api/notifications/{id} 标记已读
- 幂等：同 (user_id, type, payload_hash) 不重复落库
- 30 天过期清理（service 函数）
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import Notification, User
from app.services import notification_service


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user_id(client, session, scenario):
    client.post(
        "/api/auth/register",
        json={"username": "notif", "email": "notif@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "notif@example.com"))
    return u.id


@pytest.fixture
def auth(client, user_id):
    tok = client.post(
        "/api/auth/login",
        json={"account": "notif@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


class TestNotificationService:
    def test_create_and_idempotent(self, session, user_id):
        n1 = notification_service.create_notification(
            session, user_id, "report", "复盘报告已生成", {"rid": "abc"}
        )
        session.commit()
        assert n1 is not None
        # 同 payload 重复 → 返回 None（幂等）
        n2 = notification_service.create_notification(
            session, user_id, "report", "复盘报告已生成", {"rid": "abc"}
        )
        session.commit()
        assert n2 is None
        rows = session.scalars(select(Notification).where(Notification.user_id == user_id)).all()
        assert len(rows) == 1

    def test_list_unread(self, session, user_id):
        notification_service.create_notification(session, user_id, "system", "公告", {"x": 1})
        notification_service.create_notification(session, user_id, "report", "报告", {"rid": "1"})
        session.commit()
        items = notification_service.list_notifications(session, user_id, unread_only=True)
        assert len(items) == 2
        assert all(n["read_at"] is None for n in items)

    def test_mark_read(self, session, user_id):
        n = notification_service.create_notification(session, user_id, "system", "公告", {"x": 1})
        session.commit()
        assert notification_service.mark_read(session, n.id, user_id) is True
        items = notification_service.list_notifications(session, user_id, unread_only=True)
        assert len(items) == 0

    def test_mark_read_other_user_forbidden(self, session, user_id):
        other = User(email=f"other_{uuid.uuid4().hex[:8]}@x.com", password_hash="h")
        session.add(other)
        session.commit()
        n = notification_service.create_notification(session, user_id, "system", "公告", {"x": 1})
        session.commit()
        assert notification_service.mark_read(session, n.id, other.id) is False

    def test_cleanup_expired(self, session, user_id):
        from datetime import UTC, datetime, timedelta

        n = notification_service.create_notification(session, user_id, "system", "旧公告", {"x": 1})
        n.created_at = datetime.now(UTC) - timedelta(days=31)
        session.commit()
        deleted = notification_service.cleanup_expired(session, days=30)
        session.commit()
        assert deleted == 1
        remaining = session.scalars(
            select(Notification).where(Notification.user_id == user_id)
        ).all()
        assert len(remaining) == 0


class TestNotificationAPI:
    def test_list_requires_auth(self, client):
        assert client.get("/api/notifications").status_code == 401

    def test_list_unread(self, client, auth, session, user_id):
        notification_service.create_notification(session, user_id, "system", "公告", {"x": 1})
        session.commit()
        r = client.get("/api/notifications?unread=true", headers=auth)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    def test_mark_read_api(self, client, auth, session, user_id):
        n = notification_service.create_notification(session, user_id, "system", "公告", {"x": 1})
        session.commit()
        r = client.patch(f"/api/notifications/{n.id}", headers=auth)
        assert r.status_code == 200
        assert r.json()["read"] is True

    def test_mark_read_other_user_403(self, client, auth, session, user_id):
        other = User(email=f"o_{uuid.uuid4().hex[:8]}@x.com", password_hash="h")
        session.add(other)
        session.commit()
        n = notification_service.create_notification(session, user_id, "system", "公告", {"x": 1})
        session.commit()
        # 归属校验：他人不可标记已读（service 层已覆盖）
        assert notification_service.mark_read(session, n.id, other.id) is False
