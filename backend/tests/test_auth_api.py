"""认证 API 集成测试：/api/auth/* 端点（走测试库）。"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_register_success(client):
    r = client.post(
        "/api/auth/register",
        json={"username": "carol_user", "email": "carol@example.com", "password": "password123"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "carol@example.com"
    assert body["username"] == "carol_user"
    assert "password" not in str(body)
    assert "code" in body


def test_register_duplicate_returns_409(client):
    client.post(
        "/api/auth/register",
        json={"username": "dave_user", "email": "dave@example.com", "password": "password123"},
    )
    r = client.post(
        "/api/auth/register",
        json={"username": "dave_user", "email": "dave@example.com", "password": "password123"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "USER_ALREADY_EXISTS"


def test_register_duplicate_username_returns_409(client):
    client.post(
        "/api/auth/register",
        json={"username": "same_name", "email": "s1@example.com", "password": "password123"},
    )
    r = client.post(
        "/api/auth/register",
        json={"username": "same_name", "email": "s2@example.com", "password": "password123"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "USER_ALREADY_EXISTS"


def test_register_missing_username_returns_422(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "no_name@example.com", "password": "password123"},
    )
    assert r.status_code == 422


def test_register_invalid_input_returns_422(client):
    r = client.post(
        "/api/auth/register",
        json={"username": "1bad", "email": "not-an-email", "password": "short"},
    )
    assert r.status_code == 422
    assert "error" in r.json()


def test_login_success(client):
    client.post(
        "/api/auth/register",
        json={"username": "erin_user", "email": "erin@example.com", "password": "password123"},
    )
    r = client.post(
        "/api/auth/login",
        json={"account": "erin@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "erin@example.com"
    assert body["user"]["username"] == "erin_user"


def test_login_with_username(client):
    client.post(
        "/api/auth/register",
        json={"username": "mou_talker", "email": "erin2@example.com", "password": "password123"},
    )
    r = client.post(
        "/api/auth/login",
        json={"account": "mou_talker", "password": "password123"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "mou_talker"


def test_login_wrong_password_returns_401(client):
    email = f"frank{uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"username": f"frank_{uuid4().hex[:6]}", "email": email, "password": "password123"},
    )
    r = client.post(
        "/api/auth/login",
        json={"account": email, "password": "wrongpass"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_verify_email_success(client):
    reg = client.post(
        "/api/auth/register",
        json={"username": "grace_user", "email": "grace@example.com", "password": "password123"},
    ).json()
    r = client.post(
        "/api/auth/verify",
        json={"email": "grace@example.com", "code": reg["code"]},
    )
    assert r.status_code == 200
    assert r.json()["verified"] is True


def test_verify_email_wrong_code_returns_400(client):
    reg = client.post(
        "/api/auth/register",
        json={"username": "heidi_user", "email": "heidi@example.com", "password": "password123"},
    ).json()
    assert reg["code"] != "000000"
    r = client.post(
        "/api/auth/verify",
        json={"email": "heidi@example.com", "code": "000000"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "WRONG_CODE"


def test_refresh_token(client):
    client.post(
        "/api/auth/register",
        json={"username": "ivan_user", "email": "ivan@example.com", "password": "password123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"account": "ivan@example.com", "password": "password123"},
    ).json()
    r = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_refresh_with_invalid_token_returns_401(client):
    r = client.post("/api/auth/refresh", json={"refresh_token": "garbage"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def test_me_requires_auth(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_token_returns_user(client):
    client.post(
        "/api/auth/register",
        json={"username": "judy_user", "email": "judy@example.com", "password": "password123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"account": "judy@example.com", "password": "password123"},
    ).json()
    r = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "judy@example.com"
    assert r.json()["username"] == "judy_user"
    assert "password_hash" not in r.json()
