"""Bam mat khau, ky token va sinh/kiem ma TOTP.

Hai loai token:
- `access`: dung cho moi API sau khi da qua ca hai lop.
- `mfa`: chi dung cho buoc nhap ma TOTP, song rat ngan, khong goi API khac duoc.

`token_version` cua nguoi dung duoc ky vao token. Doi mat khau hoac tat 2FA se
tang so nay, nen moi token da phat truoc do het hieu luc ngay.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt
import pyotp

from app.config import get_settings

ALGORITHM = 'HS256'
TokenKind = Literal['access', 'mfa']
TOTP_INTERVAL = 30


class TokenError(Exception):
    """Token khong hop le, sai loai hoac het han."""


# --- Mat khau -------------------------------------------------------------

def _salt() -> bytes:
    return bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)


def hash_password(password: str) -> str:
    # bcrypt chi dung 72 byte dau; cat truoc de khong am tham bo phan duoi.
    return bcrypt.hashpw(password.encode('utf-8')[:72], _salt()).decode('utf-8')


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8')[:72], password_hash.encode('utf-8'))
    except ValueError:
        return False


# --- API key cho tai khoan may -------------------------------------------

def generate_api_key() -> str:
    return f'pill_{secrets.token_urlsafe(32)}'


def hash_api_key(api_key: str) -> str:
    """API key la chuoi ngau nhien du dai nen bam SHA-256 la du, va nhanh.

    Khac mat khau: khong can lam cham vi khong co kho tu dien de thu.
    """
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def api_keys_match(api_key: str, api_key_hash: str | None) -> bool:
    if not api_key_hash:
        return False
    return secrets.compare_digest(hash_api_key(api_key), api_key_hash)


# --- Ma du phong ----------------------------------------------------------

def generate_recovery_code() -> str:
    # 16 chu so hex = 64 bit; du de mot ban sao co so du lieu bi lo khong the do duoc.
    raw = secrets.token_hex(8).upper()
    return f'{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:]}'


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().upper().replace('-', '')
    return bcrypt.hashpw(normalized.encode('utf-8'), _salt()).decode('utf-8')


def verify_recovery_code(code: str, code_hash: str) -> bool:
    normalized = code.strip().upper().replace('-', '')
    try:
        return bcrypt.checkpw(normalized.encode('utf-8'), code_hash.encode('utf-8'))
    except ValueError:
        return False


# --- TOTP -----------------------------------------------------------------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str) -> str:
    settings = get_settings()
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(
        name=username, issuer_name=settings.totp_issuer
    )


def current_timestep(at: datetime | None = None) -> int:
    moment = at or datetime.now(timezone.utc)
    return int(moment.timestamp()) // TOTP_INTERVAL


def find_totp_timestep(secret: str, code: str) -> int | None:
    """Tra ve buoc thoi gian ma `code` thuoc ve, hoac None neu khong khop.

    Tra ve chinh buoc da khop — khong phai buoc cua dong ho hien tai — vi cua
    so chap nhan lech dong ho rong hon mot buoc. Co buoc that moi chan phat lai
    dung mot ma ma khong chan luon ma ke tiep trong cung 30 giay.
    """
    settings = get_settings()
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    normalized = code.strip().replace(' ', '')
    now_step = current_timestep()
    window = settings.totp_valid_window
    for step in range(now_step - window, now_step + window + 1):
        if secrets.compare_digest(totp.at(step * TOTP_INTERVAL), normalized):
            return step
    return None


# --- JWT ------------------------------------------------------------------

def create_token(*, user_id: int, role: str, token_version: int, kind: TokenKind) -> str:
    settings = get_settings()
    minutes = settings.access_token_minutes if kind == 'access' else settings.mfa_token_minutes
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'role': role,
        'ver': token_version,
        'kind': kind,
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, *, expected_kind: TokenKind) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        raise TokenError('Token da het han') from error
    except jwt.PyJWTError as error:
        raise TokenError('Token khong hop le') from error
    if payload.get('kind') != expected_kind:
        # Khong cho dung token cua buoc MFA de goi API thuong, va nguoc lai.
        raise TokenError('Sai loai token')
    return payload
