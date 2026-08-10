"""认证安全原语：bcrypt 密码哈希 + JWT 签发/校验。"""

from __future__ import annotations

import enum
import time
import uuid

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

_ALGORITHM = "HS256"
_BCRYPT_ROUNDS = 12


class TokenType(str, enum.Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain: str) -> str:
    """bcrypt 哈希，自动加盐（每用户随机盐）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode(
        "ascii"
    )


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码，哈希非法时返回 False 而非抛错。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_token(
    subject: str,
    token_type: TokenType,
    ttl_seconds: int | None = None,
    secret: str | None = None,
) -> str:
    """签发 JWT。默认有效期：access 30 分钟，refresh 7 天。"""
    settings = get_settings()
    if ttl_seconds is None:
        ttl_seconds = {
            TokenType.ACCESS: settings.jwt_expire_minutes * 60,
            TokenType.REFRESH: settings.jwt_refresh_days * 86400,
        }[token_type]
    now = int(time.time())
    claims = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, secret or settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str, token_type: TokenType, secret: str | None = None) -> dict:
    """校验并解析 JWT；失败抛 JWTError。"""
    settings = get_settings()
    payload = jwt.decode(
        token,
        secret or settings.secret_key,
        algorithms=[_ALGORITHM],
    )
    if payload.get("type") != token_type.value:
        raise JWTError(f"token type mismatch: expected {token_type.value}")
    return payload
