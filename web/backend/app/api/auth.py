"""Dang nhap hai lop, ghi danh TOTP va doi mat khau."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_mfa_user
from app.config import get_settings
from app.core import security
from app.db import get_session
from app.models import User
from app.schemas.auth import (
    EnrollmentConfirmResponse,
    EnrollmentResponse,
    LoginChallenge,
    LoginRequest,
    MeResponse,
    PasswordChangeRequest,
    RecoveryLoginRequest,
    TokenResponse,
    TotpVerifyRequest,
)
from app.services import auth as service

router = APIRouter(prefix='/auth', tags=['auth'])


def _auth_error(error: service.AuthError) -> HTTPException:
    code = (
        status.HTTP_423_LOCKED
        if isinstance(error, service.AccountLocked)
        else status.HTTP_401_UNAUTHORIZED
    )
    return HTTPException(code, str(error))


def _access_token(user: User) -> TokenResponse:
    settings = get_settings()
    token = security.create_token(
        user_id=user.id, role=user.role, token_version=user.token_version, kind='access'
    )
    return TokenResponse(
        access_token=token,
        expires_in_seconds=settings.access_token_minutes * 60,
        role=user.role,
        username=user.username,
    )


@router.post('/login', response_model=LoginChallenge)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginChallenge:
    """Lop thu nhat. Khong bao gio tra access token o buoc nay."""
    settings = get_settings()
    user = session.scalar(select(User).where(User.username == payload.username))
    try:
        user = service.authenticate_password(user, payload.password, session)
    except service.AuthError as error:
        raise _auth_error(error) from error

    token = security.create_token(
        user_id=user.id, role=user.role, token_version=user.token_version, kind='mfa'
    )
    return LoginChallenge(
        stage='totp_required' if user.totp_enabled else 'enrollment_required',
        mfa_token=token,
        expires_in_seconds=settings.mfa_token_minutes * 60,
    )


@router.post('/login/verify', response_model=TokenResponse)
def verify_totp(
    payload: TotpVerifyRequest,
    user: User = Depends(get_mfa_user),
    session: Session = Depends(get_session),
) -> TokenResponse:
    """Lop thu hai. Chi den day moi co access token."""
    try:
        service.consume_totp(user, payload.code, session)
    except service.AuthError as error:
        raise _auth_error(error) from error
    service.mark_login(user, session)
    return _access_token(user)


@router.post('/login/recovery', response_model=TokenResponse)
def verify_recovery_code(
    payload: RecoveryLoginRequest,
    user: User = Depends(get_mfa_user),
    session: Session = Depends(get_session),
) -> TokenResponse:
    """Thay the lop thu hai khi mat thiet bi sinh ma."""
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, 'Tai khoan chua bat xac thuc hai lop')
    try:
        service.consume_recovery_code(user, payload.recovery_code, session)
    except service.AuthError as error:
        raise _auth_error(error) from error
    service.mark_login(user, session)
    return _access_token(user)


@router.post('/totp/enroll', response_model=EnrollmentResponse)
def enroll(
    user: User = Depends(get_mfa_user), session: Session = Depends(get_session)
) -> EnrollmentResponse:
    """Sinh secret cho lan ghi danh dau. Tai khoan da bat 2FA phai tat truoc."""
    if user.totp_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            'Tai khoan da bat xac thuc hai lop; nho quan tri vien dat lai',
        )
    secret, uri = service.start_enrollment(user, session)
    return EnrollmentResponse(secret=secret, otpauth_uri=uri)


@router.post('/totp/confirm', response_model=EnrollmentConfirmResponse)
def confirm_enrollment(
    payload: TotpVerifyRequest,
    user: User = Depends(get_mfa_user),
    session: Session = Depends(get_session),
) -> EnrollmentConfirmResponse:
    try:
        recovery_codes = service.confirm_enrollment(user, payload.code, session)
    except service.AuthError as error:
        raise _auth_error(error) from error
    service.mark_login(user, session)
    token = _access_token(user)
    return EnrollmentConfirmResponse(**token.model_dump(), recovery_codes=recovery_codes)


@router.get('/me', response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    response = MeResponse.model_validate(user)
    response.unused_recovery_codes = sum(1 for code in user.recovery_codes if code.used_at is None)
    return response


@router.post('/password', status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Doi mat khau; moi token da phat bi thu hoi, ke ca token dang dung."""
    if not security.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Mat khau hien tai khong dung')
    user.password_hash = security.hash_password(payload.new_password)
    service.revoke_tokens(user, session)
