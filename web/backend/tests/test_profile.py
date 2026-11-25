"""Nguoi dung tu cap nhat email lien he cua minh."""
from conftest import auth_headers

from app.models import Role


def test_user_can_update_own_email(client):
    headers = auth_headers(client, 'quan-tri-email', Role.ADMIN)
    response = client.patch('/api/auth/me', json={'email': 'manager@example.com'}, headers=headers)
    assert response.status_code == 200
    assert response.json()['email'] == 'manager@example.com'

    me = client.get('/api/auth/me', headers=headers)
    assert me.json()['email'] == 'manager@example.com'


def test_user_cannot_save_invalid_email(client):
    headers = auth_headers(client, 'van-hanh-email', Role.OPERATOR)
    response = client.patch('/api/auth/me', json={'email': 'khong-phai-email'}, headers=headers)
    assert response.status_code == 422
