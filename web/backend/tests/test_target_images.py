"""Anh mau va yeu cau train lai cua mau chuan."""
import pytest

from conftest import auth_headers

from app.models import Role

PNG = b'\x89PNG\r\n\x1a\nminimal-image-content'


@pytest.fixture
def admin(client):
    return auth_headers(client, 'quan-tri-anh-mau', Role.ADMIN)


def test_target_with_multiple_images_is_created(client, admin, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), 'target_images_dir', tmp_path)
    response = client.post(
        '/api/targets/with-images',
        data={'code': 'THUOC-ANH', 'name': 'Thuoc co anh', 'recognition_label': 'drug_image'},
        files=[
            ('images', ('goc-1.png', PNG, 'image/png')),
            ('images', ('goc-2.png', PNG, 'image/png')),
        ],
        headers=admin,
    )
    assert response.status_code == 201
    target = response.json()
    assert target['image_count'] == 2
    assert len(list((tmp_path / str(target['id'])).iterdir())) == 2


def test_target_with_only_one_image_is_rejected(client, admin):
    response = client.post(
        '/api/targets/with-images',
        data={'code': 'THUOC-MOT-ANH', 'name': 'Khong du anh'},
        files=[('images', ('goc-1.png', PNG, 'image/png'))],
        headers=admin,
    )
    assert response.status_code == 422


def test_train_request_sends_notification_for_all_images(client, admin, tmp_path, monkeypatch):
    from app.api import targets
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), 'target_images_dir', tmp_path)
    created = client.post(
        '/api/targets/with-images',
        data={'code': 'THUOC-TRAIN', 'name': 'Thuoc can train'},
        files=[
            ('images', ('goc-1.png', PNG, 'image/png')),
            ('images', ('goc-2.png', PNG, 'image/png')),
        ],
        headers=admin,
    ).json()
    called = []
    monkeypatch.setattr(targets, 'request_retraining', lambda **kwargs: called.append(kwargs))

    response = client.post('/api/targets/train-request', headers=admin)
    assert response.status_code == 200
    assert called == [{'target_count': 1, 'image_count': 2, 'recipients': []}]
