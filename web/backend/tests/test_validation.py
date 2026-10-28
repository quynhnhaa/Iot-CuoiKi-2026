"""Loi kiem tra truong phai la mot cau tieng Viet, khong phai mang cua pydantic.

Hai tinh chat duoc khoa o day. Mot la ngon ngu. Hai la *kieu* cua `detail`:
frontend lam `new ApiError(body.detail)`, nen neu `detail` tro lai thanh mang
thi man hinh se hien "[object Object]" — hong nhung khong he bao hong.
"""
from conftest import auth_headers

from app.api import validation


def test_missing_field_reads_as_a_sentence(client):
    response = client.post('/api/auth/login', json={'username': 'ai-do'})

    assert response.status_code == 422
    body = response.json()
    assert isinstance(body['detail'], str)
    assert body['detail'] == 'Mật khẩu: chưa điền'


def test_several_problems_are_joined(client):
    response = client.post('/api/auth/login', json={})

    detail = response.json()['detail']
    assert 'Tên đăng nhập: chưa điền' in detail
    assert 'Mật khẩu: chưa điền' in detail


def test_constraint_message_names_the_limit(client):
    headers = auth_headers(client, 'van-hanh-kiem-tra', 'operator')
    target = client.post(
        '/api/targets',
        json={'code': 'MC-KIEM-TRA', 'name': 'Vien kiem tra'},
        headers=auth_headers(client, 'quan-tri-kiem-tra', 'admin'),
    ).json()

    response = client.post(
        '/api/batches',
        json={'target_id': target['id'], 'requested_count': 0},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'Số viên cần lấy: phải lớn hơn 0'


def test_original_pydantic_errors_are_kept_for_debugging(client):
    body = client.post('/api/auth/login', json={'username': 'ai-do'}).json()

    assert [item['type'] for item in body['errors']] == ['missing']
    assert body['errors'][0]['loc'] == ['body', 'password']


def test_field_is_named_by_its_label_not_its_column(client):
    response = client.post('/api/batches', json={}, headers=auth_headers(client, 'vh2', 'operator'))

    assert 'Mẫu chuẩn: chưa điền' in response.json()['detail']


def test_unlabelled_field_keeps_its_own_name(client):
    """Truong khong co trong bang nhan thi hien ten ky thuat, khong bi giau di.

    Gia mot loi thay vi tim mot endpoint co truong chua duoc dat nhan: bang
    nhan se day len theo thoi gian, con tinh chat nay thi khong doi.
    """
    assert validation._label({'loc': ['body', 'khong_co_trong_bang']}) == 'khong_co_trong_bang'
    assert validation._label({'loc': ['body']}) is None


def test_unknown_error_type_keeps_the_original_message(client):
    """Khong bia ra mot cau sai nghia khi chua dich duoc kieu loi do."""
    error = {'type': 'mot_kieu_chua_dich', 'msg': 'Field required', 'loc': ['body', 'code']}

    assert validation._sentence(error) == 'Mã xác thực: Field required'


def test_broken_json_does_not_pretend_to_name_a_field(client):
    """`loc` cua loi JSON la vi tri ky tu, khong phai so thu tu trong danh sach.

    Dat nhan theo so do se ra "Muc thu 13: ...", tro nguoi doc den mot truong
    khong ton tai.
    """
    response = client.post(
        '/api/auth/login',
        content=b'{khong-phai-json',
        headers={'Content-Type': 'application/json'},
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'nội dung gửi lên không phải JSON hợp lệ'
