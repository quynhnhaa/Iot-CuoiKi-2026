"""Kiem thu phan quyen: ai lam duoc viec gi, va ai thi khong."""
from conftest import auth_headers, enrol_and_login, make_user

from app.models import Role

PASSWORD = 'mat-khau-rat-dai-123'

OBSERVATION = {
    'pill_count': 1,
    'image_usable': True,
    'identity_verified': False,
    'target_matches': True,
    'defect_status': 'normal',
}


def running_batch(client, operator_headers, admin_headers):
    target = client.post(
        '/api/targets', json={'code': 'KEO-TRANG', 'name': 'Vien mo phong'}, headers=admin_headers
    ).json()
    batch = client.post(
        '/api/batches',
        json={'target_id': target['id'], 'requested_count': 10},
        headers=operator_headers,
    ).json()
    client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'running'}, headers=operator_headers
    )
    return batch


def test_every_endpoint_rejects_anonymous_calls(client):
    cases = [
        ('get', '/api/targets'),
        ('post', '/api/targets'),
        ('get', '/api/batches'),
        ('post', '/api/batches'),
        ('get', '/api/ai-runs'),
        ('get', '/api/users'),
        ('get', '/api/auth/me'),
    ]
    for method, path in cases:
        kwargs = {'json': {}} if method == 'post' else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, f'{method.upper()} {path} khong doi xac thuc'


def test_health_stays_public(client):
    # Can goi duoc truoc khi dang nhap de biet backend con song.
    assert client.get('/api/health').status_code == 200


def test_viewer_cannot_write(client):
    viewer = auth_headers(client, 'nguoi-xem', Role.VIEWER)
    assert client.get('/api/batches', headers=viewer).status_code == 200
    created_batch = client.post(
        '/api/batches', json={'target_id': 1, 'requested_count': 5}, headers=viewer
    )
    assert created_batch.status_code == 403
    created_target = client.post('/api/targets', json={'code': 'X', 'name': 'X'}, headers=viewer)
    assert created_target.status_code == 403


def test_operator_cannot_manage_users(client):
    operator = auth_headers(client, 'van-hanh', Role.OPERATOR)
    assert client.get('/api/users', headers=operator).status_code == 403


def test_operator_cannot_create_targets(client):
    operator = auth_headers(client, 'van-hanh', Role.OPERATOR)
    response = client.post('/api/targets', json={'code': 'X', 'name': 'X'}, headers=operator)
    assert response.status_code == 403


def test_admin_cannot_record_pill_events(client):
    """Admin quan tri tai khoan, khong phai nguoi ghi ket qua soi vien."""
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    operator = auth_headers(client, 'van-hanh', Role.OPERATOR)
    batch = running_batch(client, operator, admin)
    response = client.post(
        f'/api/batches/{batch["id"]}/events', json=OBSERVATION, headers=admin
    )
    assert response.status_code == 403


def test_machine_account_uses_api_key_and_only_records(client):
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    operator = auth_headers(client, 'van-hanh', Role.OPERATOR)
    batch = running_batch(client, operator, admin)

    created = client.post(
        '/api/users', json={'username': 'may-dem-01', 'role': 'machine'}, headers=admin
    ).json()
    api_key = created['api_key']
    assert api_key
    machine = {'X-API-Key': api_key}

    recorded = client.post(
        f'/api/batches/{batch["id"]}/events', json=OBSERVATION, headers=machine
    )
    assert recorded.status_code == 201
    # Thiet bi khong duoc tao me, khong doc danh sach me, khong vao quan tri.
    created_batch = client.post(
        '/api/batches', json={'target_id': 1, 'requested_count': 5}, headers=machine
    )
    assert created_batch.status_code == 403
    assert client.get('/api/batches', headers=machine).status_code == 403
    assert client.get('/api/users', headers=machine).status_code == 403


def test_machine_account_cannot_log_in_with_password(client):
    make_user(client, 'may-dem-01', Role.MACHINE)
    response = client.post(
        '/api/auth/login', json={'username': 'may-dem-01', 'password': PASSWORD}
    )
    assert response.status_code == 401


def test_wrong_api_key_rejected(client):
    response = client.get('/api/batches', headers={'X-API-Key': 'pill_khong-ton-tai'})
    assert response.status_code == 401


def test_rotating_api_key_invalidates_the_old_one(client):
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    created = client.post(
        '/api/users', json={'username': 'may-dem-01', 'role': 'machine'}, headers=admin
    ).json()
    old_key = created['api_key']
    rotated = client.post(f'/api/users/{created["id"]}/rotate-api-key', headers=admin).json()
    assert rotated['api_key'] != old_key
    # Key cu phai het hieu luc ngay sau khi phat key moi.
    assert client.get('/api/auth/me', headers={'X-API-Key': old_key}).status_code == 401


def test_deactivated_user_loses_access_immediately(client):
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    user_id, _ = make_user(client, 'nguoi-xem', Role.VIEWER)
    session = enrol_and_login(client, 'nguoi-xem')
    assert client.get('/api/auth/me', headers=session['headers']).status_code == 200

    client.patch(f'/api/users/{user_id}', json={'is_active': False}, headers=admin)
    assert client.get('/api/auth/me', headers=session['headers']).status_code == 401


def test_admin_cannot_lock_itself_out(client):
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    me = client.get('/api/auth/me', headers=admin).json()
    demoted = client.patch(f'/api/users/{me["id"]}', json={'role': 'viewer'}, headers=admin)
    assert demoted.status_code == 409
    disabled = client.patch(f'/api/users/{me["id"]}', json={'is_active': False}, headers=admin)
    assert disabled.status_code == 409
    assert client.post(f'/api/users/{me["id"]}/reset-totp', headers=admin).status_code == 409


def test_machine_account_rejects_password_field(client):
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    response = client.post(
        '/api/users',
        json={'username': 'may-02', 'role': 'machine', 'password': PASSWORD},
        headers=admin,
    )
    assert response.status_code == 400


def test_human_account_requires_password(client):
    admin = auth_headers(client, 'quan-tri', Role.ADMIN)
    response = client.post(
        '/api/users', json={'username': 'nguoi-moi', 'role': 'operator'}, headers=admin
    )
    assert response.status_code == 400
