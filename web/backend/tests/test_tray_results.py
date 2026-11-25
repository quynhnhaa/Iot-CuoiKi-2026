"""Kiem thu API snapshot dem theo khay tu AI."""
import pytest

from conftest import auth_headers

from app.models import Role


@pytest.fixture
def roles(client):
    return {
        'admin': auth_headers(client, 'quan-tri-khay', Role.ADMIN),
        'operator': auth_headers(client, 'van-hanh-khay', Role.OPERATOR),
    }


def running_batch(client, roles):
    target = client.post(
        '/api/targets',
        json={'code': 'THUOC-A', 'name': 'Thuoc A', 'recognition_label': 'drug_a'},
        headers=roles['admin'],
    ).json()
    batch = client.post('/api/batches', json={'target_id': target['id']}, headers=roles['operator']).json()
    client.patch(
        f'/api/batches/{batch["id"]}/status', json={'status': 'running'}, headers=roles['operator']
    )
    return batch


def test_tray_result_is_replaced_instead_of_accumulated(client, roles):
    batch = running_batch(client, roles)
    url = f'/api/batches/{batch["id"]}/tray-results/1'

    first = client.put(url, json={'counts': [{'label': 'drug_a', 'count': 2}]}, headers=roles['operator'])
    assert first.status_code == 200
    assert first.json()['counts'] == [{'label': 'drug_a', 'count': 2}]

    replacement = client.put(
        url,
        json={'counts': [{'label': 'drug_a', 'count': 3}, {'label': 'broken', 'count': 1}]},
        headers=roles['operator'],
    )
    assert replacement.status_code == 200

    results = client.get(f'/api/batches/{batch["id"]}/tray-results', headers=roles['operator'])
    assert results.status_code == 200
    body = results.json()
    assert len(body) == 1
    assert body[0]['tray_number'] == 1
    assert body[0]['counts'] == [{'label': 'drug_a', 'count': 3}, {'label': 'broken', 'count': 1}]
    assert body[0]['image_path'] is None


def test_tray_result_requires_a_running_batch(client, roles):
    target = client.post(
        '/api/targets', json={'code': 'T', 'name': 'T'}, headers=roles['admin']
    ).json()
    batch = client.post('/api/batches', json={'target_id': target['id']}, headers=roles['operator']).json()
    response = client.put(
        f'/api/batches/{batch["id"]}/tray-results/4',
        json={'counts': [{'label': 'drug_a', 'count': 1}]},
        headers=roles['operator'],
    )
    assert response.status_code == 422
