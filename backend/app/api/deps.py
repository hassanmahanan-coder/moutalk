"""API 依赖：认证用户获取。"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import User
from app.services.security import TokenType, decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "缺少访问令牌"},
        )
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "访问令牌无效或已过期"},
        )
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "用户不存在"},
        )
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选登录用户（无/无效 token 返回 None，供公开端点叠加个人数据）。"""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except JWTError:
        return None
    return db.get(User, uuid.UUID(payload["sub"]))


def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """管理后台鉴权（PRD 9.16）：仅 is_admin=true 可访问。"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "需要管理员权限"},
        )
    return user
