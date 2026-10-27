"""Xac dinh ai dang goi API va vai tro nao duoc phep.

Hai duong vao:
- `Authorization: Bearer <access token>` cho nguoi dung da qua hai lop.
- `X-API-Key: <key>` cho tai khoan may.
"""
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import TokenError, api_keys_match, decode_token
from app.db import get_session
from app.models import Role, User

bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHENTICATED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    'Can dang nhap',
    headers={'WWW-Authenticate': 'Bearer'},
)


def _active_user_from_token(token: str, session: Session, *, expected_kind: str) -> User:
    try:
        payload = decode_token(token, expected_kind=expected_kind)
    except TokenError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(error), headers={'WWW-Authenticate': 'Bearer'}
        ) from error
    user = session.get(User, int(payload['sub']))
    if user is None or not user.is_active:
        raise UNAUTHENTICATED
    if payload.get('ver') != user.token_version:
        # Mat khau da doi hoac 2FA da bi tat sau khi token nay duoc phat.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Token da bi thu hoi')
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    session: Session = Depends(get_session),
) -> User:
    if credentials is not None and credentials.credentials:
        user = _active_user_from_token(credentials.credentials, session, expected_kind='access')
        if user.requires_totp and not user.totp_enabled:
            raise HTTPException(status.HTTP_403_FORBIDDEN, 'Tai khoan chua ghi danh xac thuc hai lop')
        return user

    if x_api_key:
        # So khop theo bam; chi tai khoan may co api_key_hash.
        for candidate in session.scalars(select(User).where(User.api_key_hash.is_not(None))):
            if candidate.is_active and api_keys_match(x_api_key, candidate.api_key_hash):
                return candidate
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'API key khong hop le')

    raise UNAUTHENTICATED


def get_mfa_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Nguoi dung da qua lop mat khau, dang o buoc nhap ma."""
    if credentials is None or not credentials.credentials:
        raise UNAUTHENTICATED
    return _active_user_from_token(credentials.credentials, session, expected_kind='mfa')


def require_roles(*roles: Role):
    """Cho phep cac vai tro duoc liet ke; admin khong duoc mac dinh di qua het.

    Vi du `POST /events` chi mo cho `machine` va `operator`: admin quan tri tai
    khoan, khong phai nguoi ghi ket qua soi vien.
    """
    allowed = frozenset(roles)

    def guard(user: User = Depends(get_current_user)) -> User:
        if Role(user.role) not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f'Vai tro "{Role(user.role).value}" khong duoc thuc hien viec nay',
            )
        return user

    return guard


# Doc du lieu nghiep vu: moi tai khoan nguoi dang nhap duoc.
require_reader = require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER)
# Van hanh me dem.
require_operator = require_roles(Role.ADMIN, Role.OPERATOR)
# Ghi ket qua soi vien: thiet bi, hoac nguoi van hanh khi nhap tay.
require_recorder = require_roles(Role.MACHINE, Role.OPERATOR)
# Quan tri tai khoan va mau chuan.
require_admin = require_roles(Role.ADMIN)
