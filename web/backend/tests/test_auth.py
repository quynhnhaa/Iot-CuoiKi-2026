"""Kiem thu luong hai lop. Trong tam: lop thu nhat mot minh khong mo duoc gi."""
import pyotp
from conftest import auth_headers, enrol_and_login, make_user, next_totp_code

from app.models import Role

PASSWORD = 'mat-khau-rat-dai-123'


def test_login_alone_returns_no_access_token(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    response = client.post('/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD})
    assert response.status_code == 200
    body = response.json()
    # Buoc mat khau chi tra ve thach thuc, khong bao gio tra access token.
    assert 'access_token' not in body
    assert body['stage'] == 'enrollment_required'


def test_mfa_token_cannot_call_business_api(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    headers = {'Authorization': f'Bearer {challenge["mfa_token"]}'}
    # Token cua buoc giua khong duoc dung thay access token.
    assert client.get('/api/batches', headers=headers).status_code == 401


def test_access_token_cannot_be_used_for_mfa_step(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    session = enrol_and_login(client, 'van-hanh')
    response = client.post('/api/auth/totp/enroll', headers=session['headers'])
    assert response.status_code == 401


def test_full_two_factor_login(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    first = enrol_and_login(client, 'van-hanh')

    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    assert challenge['stage'] == 'totp_required'
    verified = client.post(
        '/api/auth/login/verify',
        json={'code': next_totp_code(first['secret'])},
        headers={'Authorization': f'Bearer {challenge["mfa_token"]}'},
    )
    assert verified.status_code == 200
    assert verified.json()['role'] == 'operator'


def test_wrong_totp_code_is_rejected(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    enrol_and_login(client, 'van-hanh')
    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    response = client.post(
        '/api/auth/login/verify',
        json={'code': '000000'},
        headers={'Authorization': f'Bearer {challenge["mfa_token"]}'},
    )
    assert response.status_code == 401


def test_totp_code_cannot_be_replayed(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    session = enrol_and_login(client, 'van-hanh')
    code = pyotp.TOTP(session['secret']).now()

    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    first = client.post(
        '/api/auth/login/verify',
        json={'code': code},
        headers={'Authorization': f'Bearer {challenge["mfa_token"]}'},
    )
    # Ma dung o buoc xac nhan ghi danh da chiem buoc thoi gian nay.
    assert first.status_code == 401
    assert 'đã được dùng' in first.json()['detail']


def test_recovery_code_works_once(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    session = enrol_and_login(client, 'van-hanh')
    code = session['recovery_codes'][0]
    assert len(session['recovery_codes']) == 8

    def login_with_recovery():
        challenge = client.post(
            '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
        ).json()
        return client.post(
            '/api/auth/login/recovery',
            json={'recovery_code': code},
            headers={'Authorization': f'Bearer {challenge["mfa_token"]}'},
        )

    assert login_with_recovery().status_code == 200
    # Lan thu hai voi cung ma du phong phai bi tu choi.
    assert login_with_recovery().status_code == 401


def test_account_locks_after_repeated_password_failures(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    for _ in range(5):
        client.post('/api/auth/login', json={'username': 'van-hanh', 'password': 'sai'})
    response = client.post('/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD})
    assert response.status_code == 423


def test_password_change_revokes_existing_tokens(client):
    make_user(client, 'van-hanh', Role.OPERATOR)
    session = enrol_and_login(client, 'van-hanh')
    assert client.get('/api/auth/me', headers=session['headers']).status_code == 200

    changed = client.post(
        '/api/auth/password',
        json={'current_password': PASSWORD, 'new_password': 'mat-khau-moi-dai-456'},
        headers=session['headers'],
    )
    assert changed.status_code == 204
    # Token cu phai het hieu luc ngay, khong doi den luc het han.
    assert client.get('/api/auth/me', headers=session['headers']).status_code == 401


def test_admin_reset_totp_forces_re_enrollment(client):
    admin_headers = auth_headers(client, 'quan-tri', Role.ADMIN)
    user_id, _ = make_user(client, 'van-hanh', Role.OPERATOR)
    enrol_and_login(client, 'van-hanh')

    reset = client.post(f'/api/users/{user_id}/reset-totp', headers=admin_headers)
    assert reset.status_code == 200
    assert reset.json()['totp_enabled'] is False

    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    assert challenge['stage'] == 'enrollment_required'


def test_user_without_enrollment_cannot_be_granted_access_token(client):
    """Khong co duong nao phat access token cho tai khoan chua bat 2FA."""
    make_user(client, 'van-hanh', Role.OPERATOR)
    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    headers = {'Authorization': f'Bearer {challenge["mfa_token"]}'}
    # Khong co secret thi khong verify duoc, va /login/verify doi secret.
    assert client.post('/api/auth/login/verify', json={'code': '123456'}, headers=headers).status_code == 401
    assert client.post('/api/auth/login/recovery', json={'recovery_code': 'X'}, headers=headers).status_code == 409


def test_next_code_in_same_window_still_works(client):
    """Chan phat lai khong duoc chan luon ma ke tiep trong cung 30 giay."""
    make_user(client, 'van-hanh', Role.OPERATOR)
    session = enrol_and_login(client, 'van-hanh')
    challenge = client.post(
        '/api/auth/login', json={'username': 'van-hanh', 'password': PASSWORD}
    ).json()
    response = client.post(
        '/api/auth/login/verify',
        json={'code': next_totp_code(session['secret'])},
        headers={'Authorization': f'Bearer {challenge["mfa_token"]}'},
    )
    assert response.status_code == 200
