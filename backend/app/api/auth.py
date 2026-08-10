"""认证 API：注册、登录、验证码校验、刷新令牌。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.services.auth import (
    AccountLockedError,
    AuthError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WrongCodeError,
    auth_service,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    account: str  # 邮箱或用户名
    password: str


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str


def _auth_error(exc: AuthError) -> HTTPException:
    mapping: dict[type[AuthError], tuple[int, str]] = {
        UserAlreadyExistsError: (status.HTTP_409_CONFLICT, "USER_ALREADY_EXISTS"),
        InvalidCredentialsError: (status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS"),
        UserNotFoundError: (status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS"),
        AccountLockedError: (status.HTTP_423_LOCKED, "ACCOUNT_LOCKED"),
        WrongCodeError: (status.HTTP_400_BAD_REQUEST, "WRONG_CODE"),
    }
    http_code, code = mapping[type(exc)]
    return HTTPException(status_code=http_code, detail={"code": code, "message": str(exc)})


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    try:
        user = auth_service.register(db, req.email, req.password, username=req.username)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc
    except AuthError as exc:
        raise _auth_error(exc) from exc
    db.commit()
    code = auth_service.issue_code(db, req.email)
    return {"id": str(user.id), "email": user.email, "username": user.username, "code": code}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return auth_service.login(db, req.account, req.password)
    except AuthError as exc:
        raise _auth_error(exc) from exc


@router.post("/verify")
def verify(req: VerifyRequest, db: Session = Depends(get_db)) -> dict:
    try:
        auth_service.verify_code(db, req.email, req.code)
    except AuthError as exc:
        raise _auth_error(exc) from exc
    return {"verified": True}


@router.post("/refresh")
def refresh(req: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return auth_service.refresh(db, req.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "role": user.role.value,
        "is_admin": user.is_admin,
    }
