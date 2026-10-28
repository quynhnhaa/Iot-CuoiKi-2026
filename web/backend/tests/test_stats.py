"""Thong ke theo ngay, tuan, thang.

Tinh chat quan trong nhat o day la **mui gio**. CSDL luu UTC, nguoi doc bang
song o UTC+7, va mot ca lam viec buoi sang nam vat qua ranh gioi ngay cua UTC.
Gop nham thi bang van day so, van cong dung tong, chi co dieu so cua ngay 28
nam o dong ngay 27 — kieu sai khong ai phat hien bang mat.
"""
from datetime import datetime, timedelta, timezone

from conftest import auth_headers

from app.models import Batch, BatchStatus, PillEvent

# Mot quan sat da qua `decide`, luu san ket qua nhu API van ghi.
ACCEPTED = {
    'pill_count': 1,
    'image_usable': True,
    'identity_verified': True,
    'target_matches': True,
    'defect_status': 'normal',
    'identity_gate_validated': True,
    'hardware_ready': True,
    'route': 'ACCEPTED',
    'release_allowed': True,
    'requires_drop_confirmation': True,
    'reason': 'normal pill; await drop sensor',
}
WRONG_DRUG = {**ACCEPTED, 'target_matches': False, 'route': 'WRONG_DRUG', 'release_allowed': False}


def seed(client, moments, *, observation=None, drop_confirmed=True, batch_at=None):
    """Dat san mot me va cac su kien vao dung moc UTC can kiem.

    Ghi thang vao CSDL chu khong qua API: API dat `created_at` la bay gio, ma
    bai kiem nay can moc cu the.
    """
    from app.models import Target

    session = client.session_factory()
    try:
        target = Target(code='MC-TK', name='Viên kiểm thử', recognition_label='64')
        session.add(target)
        session.flush()
        batch = Batch(
            target_id=target.id,
            status=BatchStatus.DONE,
            created_at=batch_at or moments[0],
        )
        session.add(batch)
        session.flush()
        for index, moment in enumerate(moments, start=1):
            session.add(
                PillEvent(
                    batch_id=batch.id,
                    sequence=index,
                    created_at=moment,
                    drop_confirmed=drop_confirmed,
                    **(observation or ACCEPTED),
                )
            )
        session.commit()
        return batch.id
    finally:
        session.close()


def fetch(client, headers, **params):
    response = client.get('/api/stats', params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def row_for(body, key):
    return next(row for row in body['rows'] if row['key'] == key)


def test_an_event_late_in_utc_belongs_to_the_next_vietnamese_day(client):
    """23:30 UTC ngay 27 la 06:30 sang ngay 28 o Viet Nam.

    Day la ca duy nhat phan biet "gop theo gio Viet Nam" voi "gop theo UTC", va
    cung la ca xay ra moi sang that.
    """
    headers = auth_headers(client, 'vh-mui-gio', 'operator')
    seed(client, [datetime(2026, 10, 27, 23, 30)])

    body = fetch(client, headers, period='day', **{'from': '2026-10-26', 'to': '2026-10-29'})

    assert row_for(body, '2026-10-28')['observed_total'] == 1
    assert row_for(body, '2026-10-27')['observed_total'] == 0


def test_an_event_early_in_utc_stays_on_the_same_day(client):
    """Doi xung voi bai tren: 02:00 UTC ngay 28 la 09:00 sang 28, khong nhay."""
    headers = auth_headers(client, 'vh-mui-gio-2', 'operator')
    seed(client, [datetime(2026, 10, 28, 2, 0)])

    body = fetch(client, headers, period='day', **{'from': '2026-10-27', 'to': '2026-10-29'})

    assert row_for(body, '2026-10-28')['observed_total'] == 1


def test_periods_with_no_data_are_still_listed(client):
    """Bang nhay tu ngay 1 sang ngay 4 khien nguoi doc tuong ngay 2, 3 mat du
    lieu, trong khi that ra may khong chay."""
    headers = auth_headers(client, 'vh-ky-rong', 'operator')
    seed(client, [datetime(2026, 10, 1, 5, 0), datetime(2026, 10, 4, 5, 0)])

    body = fetch(client, headers, period='day', **{'from': '2026-10-01', 'to': '2026-10-04'})

    assert [row['key'] for row in body['rows']] == [
        '2026-10-01',
        '2026-10-02',
        '2026-10-03',
        '2026-10-04',
    ]
    assert row_for(body, '2026-10-02')['observed_total'] == 0


def test_a_week_starts_on_monday(client):
    headers = auth_headers(client, 'vh-tuan', 'operator')
    # 29/10/2026 la thu Nam; tuan cua no bat dau thu Hai 26/10.
    seed(client, [datetime(2026, 10, 29, 5, 0)])

    body = fetch(client, headers, period='week', **{'from': '2026-10-26', 'to': '2026-11-01'})

    assert [row['key'] for row in body['rows']] == ['2026-10-26']
    assert row_for(body, '2026-10-26')['observed_total'] == 1
    assert 'Tuần' in body['rows'][0]['label']


def test_months_are_grouped_by_their_first_day(client):
    headers = auth_headers(client, 'vh-thang', 'operator')
    seed(client, [datetime(2026, 9, 30, 20, 0), datetime(2026, 10, 15, 5, 0)])

    body = fetch(client, headers, period='month', **{'from': '2026-09-01', 'to': '2026-10-31'})

    assert [row['key'] for row in body['rows']] == ['2026-09-01', '2026-10-01']
    # 30/09 20:00 UTC = 01/10 03:00 gio Viet Nam, nen no thuoc thang 10.
    assert row_for(body, '2026-09-01')['observed_total'] == 0
    assert row_for(body, '2026-10-01')['observed_total'] == 2


def test_rejected_pills_count_as_seen_but_not_as_collected(client):
    """Cung mot quy tac nhu trang chi tiet me: `accepted_total` khong tinh vien
    bi loai, va duong khong duoc tha thi khong co so da xac nhan."""
    headers = auth_headers(client, 'vh-nhan', 'operator')
    seed(client, [datetime(2026, 10, 28, 5, 0)], observation=WRONG_DRUG, drop_confirmed=False)

    row = row_for(
        fetch(client, headers, period='day', **{'from': '2026-10-28', 'to': '2026-10-28'}),
        '2026-10-28',
    )

    assert row['observed']['WRONG_DRUG'] == 1
    assert row['observed_total'] == 1
    assert row['confirmed_total'] == 0
    assert row['accepted_total'] == 0


def test_totals_are_the_sum_of_the_rows(client):
    headers = auth_headers(client, 'vh-tong', 'operator')
    seed(client, [datetime(2026, 10, 1, 5, 0), datetime(2026, 10, 2, 5, 0), datetime(2026, 10, 2, 6, 0)])

    body = fetch(client, headers, period='day', **{'from': '2026-10-01', 'to': '2026-10-03'})

    assert body['totals']['observed_total'] == sum(row['observed_total'] for row in body['rows'])
    assert body['totals']['observed_total'] == 3
    assert body['totals']['accepted_total'] == 3
    assert body['totals']['batches'] == 1


def test_default_range_covers_the_recent_periods(client):
    """Khong truyen khoang thi van phai ra bang, va bang do phai chua hom nay."""
    headers = auth_headers(client, 'vh-mac-dinh', 'operator')
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seed(client, [now - timedelta(hours=1)])

    body = fetch(client, headers, period='day')

    assert len(body['rows']) == 30
    assert body['totals']['observed_total'] == 1


def test_a_backwards_range_is_refused(client):
    headers = auth_headers(client, 'vh-nguoc', 'operator')

    response = client.get(
        '/api/stats', params={'from': '2026-10-28', 'to': '2026-10-01'}, headers=headers
    )

    assert response.status_code == 400
    assert 'trước' in response.json()['detail']


def test_a_range_too_wide_is_refused_with_a_way_out(client):
    """Tu choi thi phai noi lam gi tiep, khong chi noi khong."""
    headers = auth_headers(client, 'vh-rong', 'operator')

    response = client.get(
        '/api/stats', params={'from': '2020-01-01', 'to': '2026-12-31'}, headers=headers
    )

    assert response.status_code == 400
    assert 'kỳ dài hơn' in response.json()['detail']


def test_an_unknown_period_is_refused(client):
    headers = auth_headers(client, 'vh-ky-la', 'operator')

    assert client.get('/api/stats', params={'period': 'quy'}, headers=headers).status_code == 422


def test_reading_stats_needs_a_login(client):
    assert client.get('/api/stats').status_code == 401


def test_a_viewer_can_read_stats(client):
    """Xem thong ke la viec doc; tai khoan chi xem phai lam duoc."""
    headers = auth_headers(client, 'nguoi-xem', 'viewer')

    assert client.get('/api/stats', headers=headers).status_code == 200


# --- Xuat CSV ---------------------------------------------------------------


def export(client, headers, **params):
    response = client.get('/api/stats/export.csv', params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response


def test_csv_starts_with_a_bom_so_excel_reads_vietnamese(client):
    """Thieu BOM thi Excel tren Windows mo ra "Sứt, vỡ" thanh rac."""
    headers = auth_headers(client, 'vh-csv', 'operator')
    seed(client, [datetime(2026, 10, 28, 5, 0)])

    response = export(client, headers, period='day', **{'from': '2026-10-28', 'to': '2026-10-28'})

    assert response.content.startswith(b'\xef\xbb\xbf')
    assert 'Sứt, vỡ (camera)' in response.content.decode('utf-8-sig')


def test_csv_is_offered_as_a_download_with_the_range_in_its_name(client):
    headers = auth_headers(client, 'vh-ten-file', 'operator')

    response = export(client, headers, period='week', **{'from': '2026-10-01', 'to': '2026-10-28'})

    disposition = response.headers['content-disposition']
    assert disposition.startswith('attachment;')
    assert 'thong-ke-week-2026-10-01-den-2026-10-28.csv' in disposition


def test_csv_has_no_confirmed_column_for_routes_that_never_drop(client):
    """Ba duong nay luon tra `release_allowed=false`, nen cot "da xac nhan" cua
    chung se vinh vien bang 0 — dung cai loi ma giao dien vua phai sua."""
    headers = auth_headers(client, 'vh-cot', 'operator')

    text = export(client, headers, period='day').content.decode('utf-8-sig')
    header = text.splitlines()[0]

    assert 'Đúng, nguyên (đã xác nhận)' in header
    assert 'Sai thuốc (đã xác nhận)' not in header
    assert 'Khung trống (đã xác nhận)' not in header


def test_csv_ends_with_a_total_row(client):
    headers = auth_headers(client, 'vh-dong-tong', 'operator')
    seed(client, [datetime(2026, 10, 28, 5, 0), datetime(2026, 10, 28, 6, 0)])

    text = export(
        client, headers, period='day', **{'from': '2026-10-28', 'to': '2026-10-28'}
    ).content.decode('utf-8-sig')
    rows = [line for line in text.splitlines() if line.strip()]

    assert rows[-1].startswith('Tổng,')
    assert rows[-1].split(',')[2] == '2'  # cot "Camera soi"
