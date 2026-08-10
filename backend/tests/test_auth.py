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
