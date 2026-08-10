"""认证服务测试：注册、登录、验证码、失败锁定、刷新。"""

import pytest
from sqlalchemy import select

from app.models import User
from app.services.auth import (
    AccountLockedError,
    AuthError,
    CodeStore,
    InvalidCredentialsError,
    TokenStore,
    UserAlreadyExistsError,
    UserNotFoundError,
    WrongCodeError,
    auth_service,
)
from app.services.security import TokenType, decode_token, verify_password


@pytest.fixture
def code_store():
    return CodeStore(prefix="test:verify:")


@pytest.fixture
def fail_store():
    return TokenStore(prefix="test:login_fail:")


@pytest.fixture(autouse=True)
def clean_redis(fail_store):
    import redis

    from app.core.config import get_settings

    r = redis.from_url(get_settings().redis_url)
    r.delete("test:verify:*", "test:login_fail:*")
    keys = r.keys("test:*")
    if keys:
        r.delete(*keys)
    yield


def test_register_creates_user_with_hashed_password(session):
    user = auth_service.register(session, "bob@example.com", "password123")

    assert user.id is not None
    fetched = session.scalar(select(User).where(User.email == "bob@example.com"))
    assert fetched is not None
    assert fetched.password_hash != "password123"
    assert verify_password("password123", fetched.password_hash)


def test_register_duplicate_email_raises(session):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    with pytest.raises(UserAlreadyExistsError):
        auth_service.register(session, "bob@example.com", "otherpass")


def test_register_invalid_email_raises(session):
    with pytest.raises(ValueError):
        auth_service.register(session, "not-an-email", "password123")


def test_register_short_password_raises(session):
    with pytest.raises(ValueError):
        auth_service.register(session, "bob@example.com", "short")


def test_register_with_username(session):
    user = auth_service.register(session, "bob@example.com", "password123", username="bob_speaks")
    assert user.username == "bob_speaks"
    assert user.email == "bob@example.com"


def test_register_duplicate_username_raises(session):
    auth_service.register(session, "a@example.com", "password123", username="bob")
    session.commit()
    with pytest.raises(UserAlreadyExistsError):
        auth_service.register(session, "b@example.com", "password123", username="BOB")


def test_register_invalid_username_raises(session):
    with pytest.raises(ValueError):
        auth_service.register(session, "b@example.com", "password123", username="1bad")
    with pytest.raises(ValueError):
        auth_service.register(session, "b@example.com", "password123", username="ab")
    with pytest.raises(ValueError):
        auth_service.register(session, "b@example.com", "password123", username="bad name")
    with pytest.raises(ValueError):
        auth_service.register(
            session, "b@example.com", "password123", username="x" * 21
        )


def test_login_by_username(session):
    auth_service.register(session, "bob@example.com", "password123", username="bob")
    session.commit()

    tokens = auth_service.login(session, "bob", "password123")
    assert tokens["user"]["username"] == "bob"
    assert tokens["user"]["email"] == "bob@example.com"


def test_login_by_email_case_insensitive_still_works(session):
    auth_service.register(session, "bob@example.com", "password123", username="bob")
    session.commit()

    tokens = auth_service.login(session, "BOB@Example.com", "password123")
    assert tokens["user"]["email"] == "bob@example.com"


def test_login_by_unknown_username_raises(session):
    with pytest.raises(UserNotFoundError):
        auth_service.login(session, "ghost_user", "password123")


def test_login_returns_is_admin_flag(session):
    """登录响应须含 is_admin（前端管理后台导航依赖）。"""
    user = auth_service.register(session, "admin@x.com", "password123", username="admin_x")
    session.commit()
    user.is_admin = True
    session.commit()
    tokens = auth_service.login(session, "admin_x", "password123")
    assert tokens["user"]["is_admin"] is True
    auth_service.register(session, "plain@x.com", "password123", username="plain_u")
    session.commit()
    t2 = auth_service.login(session, "plain_u", "password123")
    assert t2["user"]["is_admin"] is False


def test_login_banned_user_rejected(session):
    """封禁用户禁止登录（管理后台封禁能力）。"""
    user = auth_service.register(session, "banned@x.com", "password123", username="banned_u")
    session.commit()
    user.banned = True
    session.commit()
    with pytest.raises(AccountLockedError):
        auth_service.login(session, "banned@x.com", "password123")


class TestChangePassword:
    def test_change_password_success(self, session):
        auth_service.register(session, "cp@x.com", "password123", username="cp_u")
        session.commit()
        auth_service.change_password(session, "cp@x.com", "password123", "newpass456")
        # 旧密码失效、新密码可登录
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(session, "cp@x.com", "password123")
        tokens = auth_service.login(session, "cp@x.com", "newpass456")
        assert tokens["user"]["email"] == "cp@x.com"

    def test_change_password_wrong_old_rejected(self, session):
        auth_service.register(session, "cp2@x.com", "password123", username="cp2_u")
        session.commit()
        with pytest.raises(InvalidCredentialsError):
            auth_service.change_password(session, "cp2@x.com", "wrong-old", "newpass456")

    def test_change_password_unknown_user_rejected(self, session):
        with pytest.raises(UserNotFoundError):
            auth_service.change_password(session, "ghost@x.com", "x", "newpass456")

    def test_reset_password_with_code(self, session, code_store):
        """忘记密码：验证码 + 新密码重置。"""
        auth_service.register(session, "fp@x.com", "password123", username="fp_u")
        session.commit()
        code = auth_service.issue_code(session, "fp@x.com", code_store=code_store)
        auth_service.reset_password(session, "fp@x.com", code, "resetpass789", code_store=code_store)
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(session, "fp@x.com", "password123")
        assert auth_service.login(session, "fp@x.com", "resetpass789")["user"]["email"] == "fp@x.com"

    def test_reset_password_wrong_code_rejected(self, session, code_store):
        auth_service.register(session, "fp2@x.com", "password123", username="fp2_u")
        session.commit()
        auth_service.issue_code(session, "fp2@x.com", code_store=code_store)
        with pytest.raises(WrongCodeError):
            auth_service.reset_password(session, "fp2@x.com", "000000", "resetpass789", code_store=code_store)


def test_login_success_returns_tokens(session):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    tokens = auth_service.login(session, "bob@example.com", "password123")

    access = decode_token(tokens["access_token"], TokenType.ACCESS)
    refresh = decode_token(tokens["refresh_token"], TokenType.REFRESH)
    assert access["sub"] == str(auth_service._user(session, "bob@example.com").id)
    assert refresh["type"] == "refresh"


def test_login_wrong_password_raises(session):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    with pytest.raises(InvalidCredentialsError):
        auth_service.login(session, "bob@example.com", "wrong-password")


def test_login_unknown_user_raises(session):
    with pytest.raises(UserNotFoundError):
        auth_service.login(session, "ghost@example.com", "password123")


def test_login_locks_after_5_failures(session, fail_store):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(
                session, "bob@example.com", "wrong", fail_store=fail_store
            )

    with pytest.raises(AccountLockedError):
        auth_service.login(session, "bob@example.com", "password123", fail_store=fail_store)


def test_failed_login_resets_after_success(session, fail_store):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    with pytest.raises(InvalidCredentialsError):
        auth_service.login(
            session, "bob@example.com", "wrong", fail_store=fail_store
        )
    auth_service.login(session, "bob@example.com", "password123", fail_store=fail_store)

    # 成功后计数清零：再错 4 次仍不应锁定
    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(
                session, "bob@example.com", "wrong", fail_store=fail_store
            )


def test_issue_verification_code(session, code_store):
    code = auth_service.issue_code(session, "bob@example.com", code_store=code_store)
    assert len(code) == 6
    assert code.isdigit()


def test_verify_code_success(session, code_store):
    code = auth_service.issue_code(session, "bob@example.com", code_store=code_store)
    auth_service.verify_code(session, "bob@example.com", code, code_store=code_store)


def test_verify_code_wrong_raises(session, code_store):
    auth_service.issue_code(session, "bob@example.com", code_store=code_store)
    with pytest.raises(WrongCodeError):
        auth_service.verify_code(session, "bob@example.com", "000000", code_store=code_store)


def test_verify_code_expired_raises(session, code_store):
    auth_service.issue_code(session, "bob@example.com", code_store=code_store)
    code_store.client.expire(
        f"{code_store.prefix}bob@example.com", -1
    )
    with pytest.raises(WrongCodeError):
        auth_service.verify_code(session, "bob@example.com", "123456", code_store=code_store)


def test_refresh_token_flow(session):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    tokens = auth_service.login(session, "bob@example.com", "password123")
    new_tokens = auth_service.refresh(session, tokens["refresh_token"])

    access = decode_token(new_tokens["access_token"], TokenType.ACCESS)
    assert access["sub"] == str(auth_service._user(session, "bob@example.com").id)


def test_refresh_with_access_token_raises(session):
    auth_service.register(session, "bob@example.com", "password123")
    session.commit()

    tokens = auth_service.login(session, "bob@example.com", "password123")
    with pytest.raises(AuthError):
        auth_service.refresh(session, tokens["access_token"])
