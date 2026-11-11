"""Kiểm thử cầu nối ThingsBoard, cả hai chiều.

Không cần một ThingsBoard thật: chiều ra dùng transport ghi lại, chiều vào là
HTTP bình thường.
"""
import pytest
from conftest import auth_headers

from app.config import get_settings
from app.models import Role
from app.services import thingsboard

NORMAL_PILL = {
    'pill_count': 1,
    'image_usable': True,
    'identity_verified': True,
    'target_matches': True,
    'defect_status': 'normal',
    'identity_gate_validated': True,
    'hardware_ready': True,
}
COMMAND_SECRET = 'bi-mat-lenh-dung-cho-kiem-thu'


@pytest.fixture
def recorder():
    """Bắt mọi lần gửi ra ngoài, và bật ThingsBoard trong lúc test."""
    settings = get_settings()
    previous = (
        settings.thingsboard_enabled,
        settings.thingsboard_base_url,
        settings.thingsboard_device_token,
    )
    settings.thingsboard_enabled = True
    settings.thingsboard_base_url = 'https://tb.example.test'
    settings.thingsboard_device_token = 'token-thiet-bi'

    transport = thingsboard.RecordingTransport()
    old_transport = thingsboard.set_transport(transport)
    yield transport
    thingsboard.set_transport(old_transport)
    (
        settings.thingsboard_enabled,
        settings.thingsboard_base_url,
        settings.thingsboard_device_token,
    ) = previous


@pytest.fixture
def command_secret():
    settings = get_settings()
    previous = settings.thingsboard_command_secret
    settings.thingsboard_command_secret = COMMAND_SECRET
    yield COMMAND_SECRET
    settings.thingsboard_command_secret = previous


@pytest.fixture
def roles(client):
    return {
        'admin': auth_headers(client, 'quan-tri', Role.ADMIN),
        'operator': auth_headers(client, 'van-hanh', Role.OPERATOR),
    }


def make_running_batch(client, roles):
    target = client.post(
        '/api/targets', json={'code': 'KEO-TRANG', 'name': 'Vien mo phong'}, headers=roles['admin']
    ).json()
    batch = client.post(
        '/api/batches',
        json={'target_id': target['id'], 'requested_count': 10},
        headers=roles['operator'],
    ).json()
    client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'running'}, headers=roles['operator']
    )
    return batch


# --- Chiều ra: telemetry -----------------------------------------------------


def test_disabled_by_default_sends_nothing(client, roles):
    """Không cấu hình ThingsBoard thì backend chạy bình thường và im lặng."""
    transport = thingsboard.RecordingTransport()
    old = thingsboard.set_transport(transport)
    try:
        make_running_batch(client, roles)
    finally:
        thingsboard.set_transport(old)
    assert transport.sent == []


def test_status_change_publishes_telemetry(client, roles, recorder):
    make_running_batch(client, roles)
    url, payload = recorder.sent[-1]
    assert url == 'https://tb.example.test/api/v1/token-thiet-bi/telemetry'
    assert payload['batch_status'] == 'running'
    assert payload['requested_count'] == 10


def test_counters_are_named_apart_in_telemetry(client, roles, recorder):
    """Dashboard phải không thể lẫn 'camera thấy' với 'đã xác nhận'."""
    batch = make_running_batch(client, roles)
    event = client.post(
        f'/api/batches/{batch["id"]}/events', json=NORMAL_PILL, headers=roles['operator']
    ).json()

    _, after_event = recorder.sent[-1]
    assert after_event['observed_accepted'] == 1
    assert after_event['confirmed_accepted'] == 0
    assert after_event['confirmed_total'] == 0

    client.patch(
        f'/api/batches/{batch["id"]}/events/{event["id"]}/drop',
        json={'drop_confirmed': True},
        headers=roles['operator'],
    )
    _, after_drop = recorder.sent[-1]
    assert after_drop['confirmed_accepted'] == 1
    assert after_drop['confirmed_total'] == 1


def test_thingsboard_failure_does_not_break_the_batch(client, roles, recorder):
    """ThingsBoard sập thì mẻ vẫn chạy — đây là điểm quan trọng nhất ở đây."""

    class BrokenTransport:
        def send(self, url, payload, timeout):
            raise RuntimeError('ThingsBoard khong phan hoi')

    old = thingsboard.set_transport(BrokenTransport())
    try:
        batch = make_running_batch(client, roles)
        response = client.post(
            f'/api/batches/{batch["id"]}/events', json=NORMAL_PILL, headers=roles['operator']
        )
        assert response.status_code == 201
        assert response.json()['route'] == 'ACCEPTED'
    finally:
        thingsboard.set_transport(old)


def test_missing_token_skips_sending(client, roles, recorder):
    get_settings().thingsboard_device_token = ''
    recorder.sent.clear()
    make_running_batch(client, roles)
    assert recorder.sent == []


# --- Chiều vào: lệnh từ dashboard --------------------------------------------


def test_command_channel_is_off_when_no_secret_configured(client, roles):
    """Thiếu cấu hình phải là cửa đóng, không phải cửa mở."""
    batch = make_running_batch(client, roles)
    response = client.post(
        '/api/thingsboard/commands', json={'command': 'pause', 'batch_id': batch['id']}
    )
    assert response.status_code == 503


def test_command_requires_the_secret(client, roles, command_secret):
    batch = make_running_batch(client, roles)
    body = {'command': 'pause', 'batch_id': batch['id']}

    assert client.post('/api/thingsboard/commands', json=body).status_code == 401
    wrong = client.post(
        '/api/thingsboard/commands', json=body, headers={'X-Command-Secret': 'sai'}
    )
    assert wrong.status_code == 401


def test_command_changes_batch_status(client, roles, command_secret):
    batch = make_running_batch(client, roles)
    response = client.post(
        '/api/thingsboard/commands',
        json={'command': 'pause', 'batch_id': batch['id']},
        headers={'X-Command-Secret': command_secret},
    )
    assert response.status_code == 200
    assert response.json()['status'] == 'paused'

    detail = client.get(f'/api/batches/{batch["id"]}', headers=roles['operator']).json()
    assert detail['status'] == 'paused'


def test_command_obeys_the_same_transition_table_as_the_web(client, roles, command_secret):
    """Dashboard không được phép đi đường tắt mà nút trên web không đi được."""
    batch = make_running_batch(client, roles)
    client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'done'}, headers=roles['operator']
    )
    response = client.post(
        '/api/thingsboard/commands',
        json={'command': 'start', 'batch_id': batch['id']},
        headers={'X-Command-Secret': command_secret},
    )
    assert response.status_code == 409


def test_unknown_command_rejected(client, roles, command_secret):
    batch = make_running_batch(client, roles)
    response = client.post(
        '/api/thingsboard/commands',
        json={'command': 'tha-het-vien', 'batch_id': batch['id']},
        headers={'X-Command-Secret': command_secret},
    )
    assert response.status_code == 400


def test_command_on_missing_batch(client, command_secret):
    response = client.post(
        '/api/thingsboard/commands',
        json={'command': 'pause', 'batch_id': 9999},
        headers={'X-Command-Secret': command_secret},
    )
    assert response.status_code == 404


def test_open_batch_sends_no_requested_count(client, roles, recorder):
    """Me dem mo khong co mau so, nen dashboard khong duoc nhan mot khoa rong."""
    target = client.post(
        '/api/targets', json={'code': 'KEO-MO', 'name': 'Dem mo'}, headers=roles['admin']
    ).json()
    batch = client.post(
        '/api/batches', json={'target_id': target['id']}, headers=roles['operator']
    ).json()
    client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'running'}, headers=roles['operator']
    )
    _, payload = recorder.sent[-1]
    assert 'requested_count' not in payload
