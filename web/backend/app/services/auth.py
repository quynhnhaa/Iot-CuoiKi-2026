"""Luong dang nhap hai lop va cac thao tac quanh TOTP."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import security
from app.models import RecoveryCode, User


class AuthError(Exception):
    """Dang nhap that bai; thong diep duoc giu chung chung co y."""


class AccountLocked(AuthError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(moment: datetime | None) -> datetime | None:
    """SQLite tra ve datetime khong co tzinfo; gan lai UTC de so sanh duoc."""
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def is_locked(user: User) -> bool:
    locked_until = _as_utc(user.locked_until)
    return locked_until is not None and locked_until > _now()


def register_failure(user: User, session: Session) -> None:
    settings = get_settings()
    user.failed_attempts += 1
    if user.failed_attempts >= settings.max_failed_attempts:
        user.locked_until = _now() + timedelta(minutes=settings.lockout_minutes)
        user.failed_attempts = 0
    session.commit()


def clear_failures(user: User, session: Session) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    session.commit()


def authenticate_password(user: User | None, password: str, session: Session) -> User:
    """Lop thu nhat. Khong tiet lo tai khoan co ton tai hay khong."""
    if user is None or not user.is_active or not user.requires_totp:
        raise AuthError('Ten dang nhap hoac mat khau khong dung')
    if is_locked(user):
        raise AccountLocked('Tai khoan dang bi tam khoa; thu lai sau')
    if not security.verify_password(password, user.password_hash):
        register_failure(user, session)
        raise AuthError('Ten dang nhap hoac mat khau khong dung')
    clear_failures(user, session)
    return user


def consume_totp(user: User, code: str, session: Session) -> None:
    """Lop thu hai. Mot ma chi dung duoc mot lan."""
    if not user.totp_secret:
        raise AuthError('Tai khoan chua ghi danh xac thuc hai lop')
    if is_locked(user):
        raise AccountLocked('Tai khoan dang bi tam khoa; thu lai sau')
    timestep = security.find_totp_timestep(user.totp_secret, code)
    if timestep is None:
        register_failure(user, session)
        raise AuthError('Ma xac thuc khong dung')
    if user.last_totp_timestep is not None and timestep <= user.last_totp_timestep:
        # Ma dung nhung da duoc dung roi: chan phat lai ma bi nhin thay.
        register_failure(user, session)
        raise AuthError('Ma nay da duoc dung; cho ma tiep theo')
    user.last_totp_timestep = timestep
    clear_failures(user, session)


def consume_recovery_code(user: User, code: str, session: Session) -> None:
    """Dung khi mat thiet bi sinh ma. Moi ma chi co gia tri mot lan."""
    if is_locked(user):
        raise AccountLocked('Tai khoan dang bi tam khoa; thu lai sau')
    for stored in user.recovery_codes:
        if stored.used_at is None and security.verify_recovery_code(code, stored.code_hash):
            stored.used_at = _now()
            clear_failures(user, session)
            return
    register_failure(user, session)
    raise AuthError('Ma du phong khong dung hoac da duoc dung')


def start_enrollment(user: User, session: Session) -> tuple[str, str]:
    """Sinh secret moi. Chua bat 2FA cho tới khi nguoi dung xac nhan dung ma."""
    user.totp_secret = security.generate_totp_secret()
    user.totp_enabled = False
    session.commit()
    return user.totp_secret, security.totp_uri(user.totp_secret, user.username)


def confirm_enrollment(user: User, code: str, session: Session) -> list[str]:
    """Xac nhan ghi danh, bat 2FA va phat bo ma du phong moi."""
    if not user.totp_secret:
        raise AuthError('Chua co phien ghi danh nao; bat dau lai')
    timestep = security.find_totp_timestep(user.totp_secret, code)
    if timestep is None:
        register_failure(user, session)
        raise AuthError('Ma xac thuc khong dung')

    settings = get_settings()
    user.totp_enabled = True
    user.last_totp_timestep = timestep
    user.recovery_codes.clear()
    plain_codes = [security.generate_recovery_code() for _ in range(settings.recovery_code_count)]
    for plain in plain_codes:
        user.recovery_codes.append(RecoveryCode(code_hash=security.hash_recovery_code(plain)))
    clear_failures(user, session)
    session.commit()
    return plain_codes


def mark_login(user: User, session: Session) -> None:
    user.last_login_at = _now()
    session.commit()


def revoke_tokens(user: User, session: Session) -> None:
    """Lam het hieu luc moi token da phat cho nguoi dung nay."""
    user.token_version += 1
    session.commit()
