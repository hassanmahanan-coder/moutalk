"""认证服务：注册、登录、邮箱验证码、失败锁定、令牌刷新。

存储约定：
- 验证码：Redis `verify_code:{email}`（TTL 10 分钟）
- 登录失败计数：Redis `login_fail:{email}`（5 次锁 15 分钟）
"""

from __future__ import annotations

import logging
import random
import re
from collections.abc import Callable

import redis as redis_lib
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from app.services.security import (
    TokenType,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 600          # 验证码 10 分钟有效
LOCK_TTL_SECONDS = 900          # 锁定 15 分钟
MAX_LOGIN_FAILURES = 5
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,19}$")  # 3-20 位，字母开头


class AuthError(Exception):
    pass


class UserAlreadyExistsError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class UserNotFoundError(AuthError):
    pass


class AccountLockedError(AuthError):
    pass


class WrongCodeError(AuthError):
    pass


class CodeStore:
    """验证码存取（Redis）。prefix 便于测试隔离。"""

    def __init__(self, prefix: str = "verify_code:"):
        self.prefix = prefix
        self.client = redis_lib.from_url(get_settings().redis_url)

    def set(self, email: str, code: str) -> None:
        self.client.set(f"{self.prefix}{email}", code, ex=CODE_TTL_SECONDS)

    def get(self, email: str) -> str | None:
        value = self.client.get(f"{self.prefix}{email}")
        return value.decode() if value else None

    def delete(self, email: str) -> None:
        self.client.delete(f"{self.prefix}{email}")


class TokenStore:
    """登录失败计数（Redis）。"""

    def __init__(self, prefix: str = "login_fail:"):
        self.prefix = prefix
        self.client = redis_lib.from_url(get_settings().redis_url)

    def increment(self, email: str) -> int:
        key = f"{self.prefix}{email}"
        count = self.client.incr(key)
        if count == 1:
            self.client.expire(key, LOCK_TTL_SECONDS)
        return count

    def reset(self, email: str) -> None:
        self.client.delete(f"{self.prefix}{email}")

    def is_locked(self, email: str) -> bool:
        count = self.client.get(f"{self.prefix}{email}")
        return count is not None and int(count) >= MAX_LOGIN_FAILURES


class AuthService:
    def __init__(self, code_store: CodeStore | None = None, fail_store: TokenStore | None = None):
        self._code_store = code_store or CodeStore()
        self._fail_store = fail_store or TokenStore()

    @staticmethod
    def _user(db: Session, email: str) -> User | None:
        return db.scalar(select(User).where(User.email == email.lower()))

    @staticmethod
    def _user_by_username(db: Session, username: str) -> User | None:
        return db.scalar(select(User).where(User.username == username.lower()))

    def register(
        self, db: Session, email: str, password: str, username: str | None = None
    ) -> User:
        email = email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("邮箱格式不合法")
        if len(password) < 8:
            raise ValueError("密码长度至少 8 位")
        if username is not None:
            username = username.strip().lower()
            if not _USERNAME_RE.match(username):
                raise ValueError("用户名需 3-20 位，字母开头，可含数字与下划线")
            if self._user_by_username(db, username):
                raise UserAlreadyExistsError("该用户名已被使用")
        if self._user(db, email):
            raise UserAlreadyExistsError("该邮箱已注册")
        user = User(email=email, password_hash=hash_password(password), username=username)
        db.add(user)
        db.flush()
        logger.info("新用户注册: %s (%s)", email, username)
        return user

    def issue_code(
        self,
        db: Session,
        email: str,
        code_store: CodeStore | None = None,
        sender: Callable[[str, str], None] | None = None,
    ) -> str:
        """生成 6 位数字验证码并存入 Redis，同时发送邮件（PRD 邮箱验证）。

        sender 未注入时用默认 send_verification_email（SMTP 未配置降级日志）。
        """
        from app.services.email_sender import send_verification_email

        store = code_store or self._code_store
        code = f"{random.randint(0, 999999):06d}"
        store.set(email.strip().lower(), code)
        try:
            (sender or send_verification_email)(email.strip().lower(), code)
        except Exception as exc:  # noqa: BLE001 邮件发送失败不阻断验证码生成
            logger.warning("验证码邮件发送失败，仅 Redis 存码: %s (%s)", email, exc)
        logger.info("验证码已生成（开发环境打印）：%s -> %s", email, code)
        return code

    def verify_code(self, db: Session, email: str, code: str, code_store: CodeStore | None = None) -> None:
        store = code_store or self._code_store
        expected = store.get(email.strip().lower())
        if expected is None or expected != code:
            raise WrongCodeError("验证码错误或已过期")

    def change_password(
        self, db: Session, email: str, old_password: str, new_password: str
    ) -> None:
        """登录态改密码：校验旧密码后更新（新密码 >= 8 位）。"""
        email = email.strip().lower()
        if len(new_password) < 8:
            raise ValueError("密码长度至少 8 位")
        user = self._user(db, email)
        if user is None:
            raise UserNotFoundError("用户不存在")
        if not verify_password(old_password, user.password_hash):
            raise InvalidCredentialsError("旧密码错误")
        user.password_hash = hash_password(new_password)
        db.commit()
        logger.info("密码已修改: %s", email)

    def reset_password(
        self,
        db: Session,
        email: str,
        code: str,
        new_password: str,
        code_store: CodeStore | None = None,
    ) -> None:
        """忘记密码：邮箱验证码校验通过后重置密码。"""
        email = email.strip().lower()
        if len(new_password) < 8:
            raise ValueError("密码长度至少 8 位")
        user = self._user(db, email)
        if user is None:
            raise UserNotFoundError("用户不存在")
        self.verify_code(db, email, code, code_store=code_store)
        user.password_hash = hash_password(new_password)
        db.commit()
        logger.info("密码已重置: %s", email)

    def login(
        self,
        db: Session,
        account: str,
        password: str,
        fail_store: TokenStore | None = None,
    ) -> dict:
        """账号密码登录：account 支持邮箱或用户名（大小写不敏感）。"""
        account = account.strip().lower()
        store = fail_store or self._fail_store
        if store.is_locked(account):
            raise AccountLockedError("密码错误次数过多，账号已临时锁定")
        user = (
            self._user(db, account)
            if "@" in account
            else self._user_by_username(db, account)
        )
        if user is None:
            raise UserNotFoundError("用户不存在")
        if getattr(user, "banned", False):
            raise AccountLockedError("账号已被封禁，请联系管理员")
        if not verify_password(password, user.password_hash):
            store.increment(account)
            raise InvalidCredentialsError("密码错误")
        store.reset(account)
        return {
            "access_token": create_token(str(user.id), TokenType.ACCESS),
            "refresh_token": create_token(str(user.id), TokenType.REFRESH),
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "role": user.role.value,
                "is_admin": bool(user.is_admin),
            },
        }

    def refresh(self, db: Session, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except JWTError as exc:
            raise AuthError("刷新令牌无效或已过期") from exc
        user = db.get(User, payload["sub"])
        if user is None:
            raise AuthError("用户不存在")
        return {
            "access_token": create_token(str(user.id), TokenType.ACCESS),
            "token_type": "bearer",
        }


auth_service = AuthService()
