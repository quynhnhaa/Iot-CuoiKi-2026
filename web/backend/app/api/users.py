"""Quan tri tai khoan. Chi vai tro admin vao duoc."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core import security
from app.db import get_session
from app.models import Role, User
from app.schemas.user import UserCreate, UserCreated, UserRead, UserUpdate
from app.services import auth as auth_service

router = APIRouter(prefix='/users', tags=['users'], dependencies=[Depends(require_admin)])


@router.get('', response_model=list[UserRead])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return list(session.scalars(select(User).order_by(User.id)))


@router.post('', response_model=UserCreated, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> UserCreated:
    """Tài khoản người cần mật khẩu; tai khoan may duoc phat API key mot lan."""
    user = User(username=payload.username, role=payload.role, full_name=payload.full_name, note=payload.note)
    api_key: str | None = None

    if payload.role is Role.MACHINE:
        if payload.password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Tài khoản máy không dùng mật khẩu')
        api_key = security.generate_api_key()
        user.api_key_hash = security.hash_api_key(api_key)
    else:
        if not payload.password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Tài khoản người cần mật khẩu')
        user.password_hash = security.hash_password(payload.password)

    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f'Tên đăng nhập "{payload.username}" đã tồn tại'
        ) from None
    session.refresh(user)
    return UserCreated(**UserRead.model_validate(user).model_dump(), api_key=api_key)


def _get_user_or_404(user_id: int, session: Session) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy tài khoản')
    return user


@router.patch('/{user_id}', response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> User:
    user = _get_user_or_404(user_id, session)
    changes = payload.model_dump(exclude_unset=True)

    # Admin khong tu ha vai tro hoac tu vo hieu minh, de khong khoa het duong vao.
    if user.id == admin.id:
        if changes.get('role') not in (None, Role.ADMIN):
            raise HTTPException(status.HTTP_409_CONFLICT, 'Không thể tự hạ vai trò của chính mình')
        if changes.get('is_active') is False:
            raise HTTPException(status.HTTP_409_CONFLICT, 'Không thể tự vô hiệu tài khoản của mình')

    for field, value in changes.items():
        setattr(user, field, value)
    if 'is_active' in changes and changes['is_active'] is False:
        auth_service.revoke_tokens(user, session)
    session.commit()
    session.refresh(user)
    return user


@router.post('/{user_id}/reset-totp', response_model=UserRead)
def reset_totp(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> User:
    """Dat lai 2FA khi nguoi dung mat thiet bi va het ma du phong.

    Sau khi dat lai, nguoi dung phai ghi danh lai o lan dang nhap sau; token cu
    het hieu luc ngay.
    """
    user = _get_user_or_404(user_id, session)
    if user.id == admin.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            'Không tự đặt lại 2FA của mình; nhờ một admin khác thực hiện',
        )
    user.totp_secret = None
    user.totp_enabled = False
    user.last_totp_timestep = None
    user.recovery_codes.clear()
    auth_service.revoke_tokens(user, session)
    session.refresh(user)
    return user


@router.post('/{user_id}/rotate-api-key', response_model=UserCreated)
def rotate_api_key(user_id: int, session: Session = Depends(get_session)) -> UserCreated:
    """Phat API key moi cho tai khoan may; key cu het hieu luc ngay."""
    user = _get_user_or_404(user_id, session)
    if Role(user.role) is not Role.MACHINE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Chỉ tài khoản máy có API key')
    api_key = security.generate_api_key()
    user.api_key_hash = security.hash_api_key(api_key)
    session.commit()
    session.refresh(user)
    return UserCreated(**UserRead.model_validate(user).model_dump(), api_key=api_key)
