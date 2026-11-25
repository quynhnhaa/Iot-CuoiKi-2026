"""Thong ke theo ngay, tuan, thang — xem tren web hoac tai ve dang CSV."""
import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_reader
from app.db import get_session
from app.models import User
from app.schemas.stats import StatsResponse
from app.services import stats

router = APIRouter(prefix='/stats', tags=['stats'])

PERIOD_LABELS = {'day': 'ngày', 'week': 'tuần', 'month': 'tháng'}

# Nhan nam duong dich bang tieng Viet cho file CSV.
#
# Frontend giu ban cua rieng no trong `components/ui.tsx` (`ROUTE_LOOK`), vi o
# do nhan con di kem mau va icon. Hai noi, cung nam cai ten: doi ten o day thi
# phai doi ca ben kia, neu khong file tai ve se goi khac man hinh.
ROUTE_LABELS = {
    'ACCEPTED': 'Đúng, nguyên',
    'DEFECTIVE': 'Sứt, vỡ',
    'WRONG_DRUG': 'Sai thuốc',
    'MULTIPLE_PILLS': 'Nhiều viên',
    'EMPTY_FRAME': 'Khung trống',
}

# Chi hai duong nay tung duoc tha xuong o, nen chi hai duong nay co so "da xac
# nhan". Ba duong con lai luon bang 0 — dua chung vao file la tao ra ba cot so
# khong vinh vien, dung cai loi ma giao dien vua phai sua.
DROPPABLE = ('ACCEPTED', 'DEFECTIVE')

# Chan truy van qua rong: mot bang vai nghin dong khong ai doc, ma van bat may
# chu gop het tung ky mot.
MAX_BUCKETS = 400

PeriodQuery = Annotated[str, Query(pattern='^(day|week|month)$')]


def _resolve_range(period: str, first: date | None, last: date | None) -> tuple[date, date]:
    if first is None or last is None:
        default_first, default_last = stats.default_range(period)
        first = first or default_first
        last = last or default_last
    if first > last:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc'
        )
    count = len(stats.buckets_between(first, last, period))
    if count > MAX_BUCKETS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Khoảng này có {count} {PERIOD_LABELS[period]}, quá {MAX_BUCKETS}.'
            ' Thu hẹp khoảng lại hoặc đổi sang kỳ dài hơn.',
        )
    return first, last


@router.get('', response_model=StatsResponse, response_model_by_alias=True)
def read_stats(
    period: PeriodQuery = 'day',
    first: Annotated[date | None, Query(alias='from')] = None,
    last: Annotated[date | None, Query(alias='to')] = None,
    session: Session = Depends(get_session),
    _: User = Depends(require_reader),
) -> StatsResponse:
    first, last = _resolve_range(period, first, last)
    rows = stats.summarize_periods(session, period, first, last)
    return StatsResponse(
        period=period,
        first=first,
        last=last,
        rows=rows,
        totals=stats.totals_of(rows),
    )


def _csv_rows(rows: list[dict], totals: dict) -> list[list]:
    header = ['Kỳ', 'Số mẻ', 'Camera soi']
    header += [f'{ROUTE_LABELS[route]} (camera)' for route in ROUTE_LABELS]
    header += [f'{ROUTE_LABELS[route]} (đã xác nhận)' for route in DROPPABLE]
    header += ['Đã xác nhận rơi', 'Viên đạt']

    def line(label: str, row: dict) -> list:
        return [
            label,
            row['batches'],
            row['observed_total'],
            *[row['observed'].get(route, 0) for route in ROUTE_LABELS],
            *[row['confirmed'].get(route, 0) for route in DROPPABLE],
            row['confirmed_total'],
            row['accepted_total'],
        ]

    return [header, *(line(row['label'], row) for row in rows), line('Tổng', totals)]


@router.get('/export.csv')
def export_stats_csv(
    period: PeriodQuery = 'day',
    first: Annotated[date | None, Query(alias='from')] = None,
    last: Annotated[date | None, Query(alias='to')] = None,
    session: Session = Depends(get_session),
    _: User = Depends(require_reader),
) -> Response:
    first, last = _resolve_range(period, first, last)
    rows = stats.summarize_periods(session, period, first, last)

    buffer = io.StringIO()
    # `\r\n` va dau nhay kep la quy uoc CSV; de csv.writer lo, dung tu noi chuoi.
    csv.writer(buffer, lineterminator='\r\n').writerows(_csv_rows(rows, stats.totals_of(rows)))

    # BOM o dau file. Excel tren Windows khong tu doan ra UTF-8: thieu BOM thi
    # "Sứt, vỡ" mo ra thanh "Sá»©t, vá»¡". Trinh doc khac bo qua BOM nay.
    body = ('﻿' + buffer.getvalue()).encode('utf-8')
    name = f'thong-ke-{period}-{first.isoformat()}-den-{last.isoformat()}.csv'
    return Response(
        content=body,
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{name}"'},
    )
