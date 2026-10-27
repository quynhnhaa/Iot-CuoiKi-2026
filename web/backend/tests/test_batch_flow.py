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


def create_batch(client, roles, requested_count=10, start=True):
    target = client.post(
        '/api/targets',
        json={'code': 'KEO-TRANG-TRON', 'name': 'Vien mo phong trang tron'},
        headers=roles['admin'],
    ).json()
    batch = client.post(
        '/api/batches',
        json={'target_id': target['id'], 'requested_count': requested_count},
        headers=roles['operator'],
    ).json()
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
