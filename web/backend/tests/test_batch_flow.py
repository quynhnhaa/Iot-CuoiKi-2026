"""Kiem thu luong me dem. Cac rang buoc nay doc lap voi ai dang goi API."""
import pytest
from conftest import auth_headers

from app.models import Role

NORMAL_PILL = {
    'pill_count': 1,
    'image_usable': True,
    'identity_verified': True,
    'target_matches': True,
    'defect_status': 'normal',
}


@pytest.fixture
def roles(client):
    """Mot admin (tao mau chuan) va mot operator (van hanh va ghi ket qua)."""
    return {
        'admin': auth_headers(client, 'quan-tri', Role.ADMIN),
        'operator': auth_headers(client, 'van-hanh', Role.OPERATOR),
    }


def create_batch(client, roles, requested_count=None, start=True):
    target = client.post(
        '/api/targets',
        json={'code': 'KEO-TRANG-TRON', 'name': 'Vien mo phong trang tron'},
        headers=roles['admin'],
    ).json()
    payload = {'target_id': target['id']}
    if requested_count is not None:
        payload['requested_count'] = requested_count
    batch = client.post('/api/batches', json=payload, headers=roles['operator']).json()
    if start:
        client.patch(
            f'/api/batches/{batch["id"]}/status',
            json={'status': 'running'},
            headers=roles['operator'],
        )
    return batch


def test_uncertain_identity_routes_to_wrong_drug(client, roles):
    batch = create_batch(client, roles)
    response = client.post(
        f'/api/batches/{batch["id"]}/events',
        json={**NORMAL_PILL, 'identity_verified': False},
        headers=roles['operator'],
    )
    assert response.status_code == 201
    event = response.json()
    assert event['route'] == 'WRONG_DRUG'
    assert event['release_allowed'] is False


def test_counter_only_moves_after_drop_confirmation(client, roles):
    batch = create_batch(client, roles)
    event = client.post(
        f'/api/batches/{batch["id"]}/events',
        json={**NORMAL_PILL, 'identity_gate_validated': True, 'hardware_ready': True},
        headers=roles['operator'],
    ).json()
    assert event['route'] == 'ACCEPTED'
    assert event['requires_drop_confirmation'] is True

    counters = client.get(f'/api/batches/{batch["id"]}', headers=roles['operator']).json()[
        'counters'
    ]
    assert counters['observed']['ACCEPTED'] == 1
    assert counters['confirmed_total'] == 0

    client.patch(
        f'/api/batches/{batch["id"]}/events/{event["id"]}/drop',
        json={'drop_confirmed': True},
        headers=roles['operator'],
    )
    counters = client.get(f'/api/batches/{batch["id"]}', headers=roles['operator']).json()[
        'counters'
    ]
    assert counters['confirmed']['ACCEPTED'] == 1
    assert counters['confirmed_total'] == 1


def test_drop_cannot_be_confirmed_without_release(client, roles):
    batch = create_batch(client, roles)
    event = client.post(
        f'/api/batches/{batch["id"]}/events', json=NORMAL_PILL, headers=roles['operator']
    ).json()
    assert event['release_allowed'] is False
    response = client.patch(
        f'/api/batches/{batch["id"]}/events/{event["id"]}/drop',
        json={'drop_confirmed': True},
        headers=roles['operator'],
    )
    assert response.status_code == 409


def test_events_rejected_when_batch_not_running(client, roles):
    batch = create_batch(client, roles, start=False)
    response = client.post(
        f'/api/batches/{batch["id"]}/events', json=NORMAL_PILL, headers=roles['operator']
    )
    assert response.status_code == 409


def test_invalid_status_transition_rejected(client, roles):
    batch = create_batch(client, roles)
    client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'done'}, headers=roles['operator']
    )
    response = client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'running'}, headers=roles['operator']
    )
    assert response.status_code == 409


def test_defective_pill_drops_but_is_not_progress(client, roles):
    """Vien loai cung roi va cung duoc xac nhan, nhung khong phai mot vien da lay.

    `decision_simulator` tra accepted_count_increment = 0 cho vien loai, nen
    thanh tien do phai doc `accepted_total`, khong phai `confirmed_total`.
    """
    batch = create_batch(client, roles)
    ready = {'identity_gate_validated': True, 'hardware_ready': True}

    defective = client.post(
        f'/api/batches/{batch["id"]}/events',
        json={**NORMAL_PILL, **ready, 'defect_status': 'defective'},
        headers=roles['operator'],
    ).json()
    assert defective['route'] == 'DEFECTIVE'
    assert defective['release_allowed'] is True

    client.patch(
        f'/api/batches/{batch["id"]}/events/{defective["id"]}/drop',
        json={'drop_confirmed': True},
        headers=roles['operator'],
    )
    counters = client.get(f'/api/batches/{batch["id"]}', headers=roles['operator']).json()[
        'counters'
    ]
    assert counters['confirmed_total'] == 1
    assert counters['accepted_total'] == 0

    good = client.post(
        f'/api/batches/{batch["id"]}/events',
        json={**NORMAL_PILL, **ready},
        headers=roles['operator'],
    ).json()
    client.patch(
        f'/api/batches/{batch["id"]}/events/{good["id"]}/drop',
        json={'drop_confirmed': True},
        headers=roles['operator'],
    )
    counters = client.get(f'/api/batches/{batch["id"]}', headers=roles['operator']).json()[
        'counters'
    ]
    assert counters['confirmed_total'] == 2
    assert counters['accepted_total'] == 1


def test_batch_without_requested_count_is_an_open_count(client, roles):
    """Khong phai me nao cung biet truoc so vien; de trong phai la hop le."""
    batch = create_batch(client, roles)
    assert batch['requested_count'] is None

    detail = client.get(f'/api/batches/{batch["id"]}', headers=roles['operator']).json()
    assert detail['requested_count'] is None
    assert detail['counters']['accepted_total'] == 0


def test_paused_batch_can_be_finished_without_resuming(client, roles):
    """Tam dung roi thay da du thi phai ket thuc duoc ngay.

    Bat nguoi van hanh chay tiep roi moi dung duoc, hoac huy ca me de vut so da
    dem, deu la dua ho vao duong cut. Tam dung chi co nghia la may ngung nhan
    vien, khong phai la me chua duoc phep chot.
    """
    batch = create_batch(client, roles)
    status_url = f'/api/batches/{batch["id"]}/status'

    paused = client.patch(status_url, json={'status': 'paused'}, headers=roles['operator'])
    assert paused.status_code == 200

    done = client.patch(status_url, json={'status': 'done'}, headers=roles['operator'])
    assert done.status_code == 200
    assert done.json()['status'] == 'done'
    assert done.json()['finished_at'] is not None


def test_finished_batch_stays_finished(client, roles):
    """Hai cua cuoi phai dong han: me da chot khong mo lai duoc tu dau ca."""
    batch = create_batch(client, roles)
    status_url = f'/api/batches/{batch["id"]}/status'
    client.patch(status_url, json={'status': 'aborted'}, headers=roles['operator'])

    for target in ('running', 'paused', 'done'):
        response = client.patch(status_url, json={'status': target}, headers=roles['operator'])
        assert response.status_code == 409, target
