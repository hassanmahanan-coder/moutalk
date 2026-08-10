"""认证与安全原语测试：密码哈希、JWT 签发/校验。"""

import pytest
from jose import JWTError

from app.services.security import (
    TokenType,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_password_never_returns_plaintext():
    h = hash_password("secret123")
    assert h != "secret123"
    assert h.startswith("$2")


def test_hash_password_is_salted():
    h1 = hash_password("secret123")
    h2 = hash_password("secret123")
    assert h1 != h2


def test_verify_password_correct():
    h = hash_password("secret123")
    assert verify_password("secret123", h) is True


def test_verify_password_wrong():
    h = hash_password("secret123")
    assert verify_password("wrong-pass", h) is False


def test_verify_password_malformed_hash_returns_false():
    assert verify_password("x", "not-a-hash") is False


def test_access_token_roundtrip():
    token = create_token("user-1", TokenType.ACCESS)
    payload = decode_token(token, TokenType.ACCESS)
    assert payload["sub"] == "user-1"
    assert payload["type"] == TokenType.ACCESS.value


def test_refresh_token_roundtrip():
    token = create_token("user-1", TokenType.REFRESH)
    payload = decode_token(token, TokenType.REFRESH)
    assert payload["sub"] == "user-1"
    assert payload["type"] == TokenType.REFRESH.value


def test_access_token_rejected_as_refresh():
    token = create_token("user-1", TokenType.ACCESS)
    with pytest.raises(JWTError):
        decode_token(token, TokenType.REFRESH)


def test_tampered_token_rejected():
    token = create_token("user-1", TokenType.ACCESS)
    tampered = token[:-4] + "AAAA"
    with pytest.raises(JWTError):
        decode_token(tampered, TokenType.ACCESS)


def test_expired_token_rejected():
    token = create_token("user-1", TokenType.ACCESS, ttl_seconds=-1)
    with pytest.raises(JWTError):
        decode_token(token, TokenType.ACCESS)


def test_access_token_contains_expected_claims():
    token = create_token("user-1", TokenType.ACCESS, ttl_seconds=600)
    payload = decode_token(token, TokenType.ACCESS)
    assert payload["type"] == "access"
    assert payload["iat"] is not None
    assert payload["exp"] - payload["iat"] == 600
