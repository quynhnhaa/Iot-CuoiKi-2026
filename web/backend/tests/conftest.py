import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
# Dat truoc khi import app: Settings doc bien moi truong luc khoi tao.
os.environ.setdefault('WEB_SECRET_KEY', 'khoa-chi-dung-cho-kiem-thu-dai-hon-32-byte')
# Ha chi phi bcrypt de bo test khong cham; ban chay that dung mac dinh 12.
os.environ.setdefault('WEB_BCRYPT_ROUNDS', '4')
os.environ.setdefault('WEB_DATABASE_URL', 'sqlite://')

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture
def session_factory():
    from app.models import Base

    engine = create_engine(
        'sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


@pytest.fixture
def client(session_factory):
    from app import db
    from app.db import get_session
    from app.main import app

    testing_session, engine = session_factory

    def override_session():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    original_engine = db.engine
    db.engine = engine
    with TestClient(app) as test_client:
        test_client.session_factory = testing_session
        yield test_client
    db.engine = original_engine
    app.dependency_overrides.clear()


def make_user(client, username, role, password='mat-khau-rat-dai-123'):
    """Tao tai khoan truc tiep trong DB, bo qua API de khong can admin san co."""
    from app.core.security import generate_api_key, hash_api_key, hash_password
    from app.models import Role, User

    session = client.session_factory()
    try:
        user = User(username=username, role=role)
        api_key = None
        if Role(role) is Role.MACHINE:
            api_key = generate_api_key()
            user.api_key_hash = hash_api_key(api_key)
        else:
            user.password_hash = hash_password(password)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id, api_key
    finally:
        session.close()


def enrol_and_login(client, username, password='mat-khau-rat-dai-123'):
    """Di tron ca hai lop: mat khau -> ghi danh TOTP -> access token."""
    challenge = client.post(
        '/api/auth/login', json={'username': username, 'password': password}
    ).json()
    assert challenge['stage'] == 'enrollment_required'
    mfa_headers = {'Authorization': f'Bearer {challenge["mfa_token"]}'}

    enrollment = client.post('/api/auth/totp/enroll', headers=mfa_headers).json()
    secret = enrollment['secret']
    confirmed = client.post(
        '/api/auth/totp/confirm',
        json={'code': pyotp.TOTP(secret).now()},
        headers=mfa_headers,
    ).json()
    return {
        'secret': secret,
        'token': confirmed['access_token'],
        'recovery_codes': confirmed['recovery_codes'],
        'headers': {'Authorization': f'Bearer {confirmed["access_token"]}'},
    }


def auth_headers(client, username, role, password='mat-khau-rat-dai-123'):
    make_user(client, username, role, password)
    return enrol_and_login(client, username, password)['headers']


def next_totp_code(secret):
    """Ma cua buoc thoi gian ke tiep.

    Dung khi vua xac thuc xong trong cung 30 giay: buoc hien tai da bi chiem,
    con buoc +1 nam trong cua so chap nhan.
    """
    from app.core.security import TOTP_INTERVAL, current_timestep

    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).at((current_timestep() + 1) * TOTP_INTERVAL)
