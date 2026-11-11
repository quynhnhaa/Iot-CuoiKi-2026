"""Gop ket qua dem theo ngay, tuan, thang.

**Moc thoi gian tinh theo gio Viet Nam, khong phai UTC.** CSDL luu moc UTC;
mot me chay luc 06:00 ngay 28 theo gio Viet Nam duoc ghi la 23:00 ngay 27 theo
UTC. Gop theo UTC thi so lieu cua mot ca lam viec buoi sang se roi sang ngay
hom truoc — bang thong ke sai ma khong ai nhin ra.

Dung offset co dinh +07:00 chu khong dung `zoneinfo`: Viet Nam khong co gio mua
he va giu nguyen UTC+7 tu 1975, nen offset co dinh la dung tuyet doi o day, lai
khong keo theo goi `tzdata` — thu ma Windows khong co san va se lam
`ZoneInfo('Asia/Ho_Chi_Minh')` nem loi ngay tren may dev.

Viec dem tung nhan khong duoc viet lai o day: moi nhom su kien duoc dua cho
`counters.summarize`, dung ham ma trang chi tiet me va ThingsBoard dang dung.
Neu quy tac dem doi, no doi o mot cho.

Gop bang Python chu khong bang SQL: so su kien cua mot do an co quy mo nghin,
va mot cau `GROUP BY` co dich mui gio se khac nhau giua SQLite va Postgres. Neu
sau nay du lieu len hang trieu dong thi day la cho phai viet lai.
"""
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Batch, PillEvent
from app.services.counters import summarize

Period = Literal['day', 'week', 'month']
PERIODS: tuple[str, ...] = ('day', 'week', 'month')

# Gio Viet Nam. Xem phan dau file vi sao khong dung zoneinfo.
VN = timezone(timedelta(hours=7), 'ICT')

# So ky mac dinh khi nguoi dung khong chon khoang.
DEFAULT_SPAN: dict[str, int] = {'day': 30, 'week': 12, 'month': 12}


def _as_vn(moment: datetime) -> datetime:
    """Doi mot moc trong CSDL sang gio Viet Nam.

    SQLite tra ve datetime khong mang tzinfo; cac moc deu duoc ghi bang
    `utcnow`, nen moc tron la UTC chu khong phai gio may chu.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(VN)


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), VN)


def bucket_of(moment: datetime, period: str) -> date:
    """Ngay dai dien cho ky chua `moment`: chinh ngay do, thu Hai cua tuan, hoac
    ngay mung mot cua thang."""
    day = _as_vn(moment).date()
    return start_of(day, period)


def start_of(day: date, period: str) -> date:
    if period == 'day':
        return day
    if period == 'week':
        return day - timedelta(days=day.weekday())  # tuan bat dau thu Hai
    return day.replace(day=1)


def next_bucket(start: date, period: str) -> date:
    if period == 'day':
        return start + timedelta(days=1)
    if period == 'week':
        return start + timedelta(days=7)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def previous_bucket(start: date, period: str) -> date:
    if period == 'day':
        return start - timedelta(days=1)
    if period == 'week':
        return start - timedelta(days=7)
    if start.month == 1:
        return start.replace(year=start.year - 1, month=12)
    return start.replace(month=start.month - 1)


def label_of(start: date, period: str) -> str:
    if period == 'day':
        return start.strftime('%d/%m/%Y')
    if period == 'week':
        end = start + timedelta(days=6)
        week = start.isocalendar().week
        return f'Tuần {week}/{start.year} ({start:%d/%m} - {end:%d/%m})'
    return f'Tháng {start.month}/{start.year}'


def buckets_between(first: date, last: date, period: str) -> list[date]:
    """Moi ky tu `first` den `last`, **ke ca ky khong co so lieu**.

    Ky rong phai co mat: mot bang nhay tu ngay 12 sang ngay 15 khien nguoi doc
    tuong ngay 13, 14 khong co du lieu, trong khi that ra may khong chay.
    """
    out: list[date] = []
    cursor = start_of(first, period)
    stop = start_of(last, period)
    while cursor <= stop:
        out.append(cursor)
        cursor = next_bucket(cursor, period)
    return out


def default_range(period: str, today: date | None = None) -> tuple[date, date]:
    """Khoang mac dinh khi nguoi dung chua chon gi: DEFAULT_SPAN ky gan nhat."""
    today = today or datetime.now(VN).date()
    first = start_of(today, period)
    for _ in range(DEFAULT_SPAN[period] - 1):
        first = previous_bucket(first, period)
    return first, today


def _window_utc(first: date, last: date) -> tuple[datetime, datetime]:
    """Khoang can lay tu CSDL, doi sang UTC de so sanh voi cot `created_at`."""
    start = _midnight(start_of(first, 'day'))
    end = _midnight(last + timedelta(days=1))
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _group(items: Iterable, period: str, attr: str) -> dict[date, list]:
    grouped: dict[date, list] = {}
    for item in items:
        grouped.setdefault(bucket_of(getattr(item, attr), period), []).append(item)
    return grouped


def summarize_periods(session: Session, period: str, first: date, last: date) -> list[dict]:
    """Mot dong cho moi ky trong khoang, theo thu tu thoi gian."""
    # `first` co the roi vao giua mot ky; lay tu dau ky do de con so cua ky dau
    # bang khong thieu phan truoc do.
    span_first = start_of(first, period)
    start_utc, end_utc = _window_utc(span_first, last)
    naive_start = start_utc.replace(tzinfo=None)
    naive_end = end_utc.replace(tzinfo=None)

    events = list(
        session.scalars(
            select(PillEvent)
            .where(PillEvent.created_at >= naive_start)
            .where(PillEvent.created_at < naive_end)
        )
    )
    batches = list(
        session.scalars(
            select(Batch)
            .where(Batch.created_at >= naive_start)
            .where(Batch.created_at < naive_end)
        )
    )

    by_event = _group(events, period, 'created_at')
    by_batch = _group(batches, period, 'created_at')

    rows: list[dict] = []
    for bucket in buckets_between(span_first, last, period):
        counters = summarize(by_event.get(bucket, []))
        rows.append(
            {
                'key': bucket.isoformat(),
                'label': label_of(bucket, period),
                'batches': len(by_batch.get(bucket, [])),
                'observed': counters['observed'],
                'confirmed': counters['confirmed'],
                'observed_total': sum(counters['observed'].values()),
                'confirmed_total': counters['confirmed_total'],
                'accepted_total': counters['accepted_total'],
            }
        )
    return rows


def totals_of(rows: list[dict]) -> dict:
    """Tong ca khoang. Cong tu cac dong de bang va dong tong khong bao gio lech."""
    observed: dict[str, int] = {}
    confirmed: dict[str, int] = {}
    for row in rows:
        for route, count in row['observed'].items():
            observed[route] = observed.get(route, 0) + count
        for route, count in row['confirmed'].items():
            confirmed[route] = confirmed.get(route, 0) + count
    return {
        'batches': sum(row['batches'] for row in rows),
        'observed': observed,
        'confirmed': confirmed,
        'observed_total': sum(row['observed_total'] for row in rows),
        'confirmed_total': sum(row['confirmed_total'] for row in rows),
        'accepted_total': sum(row['accepted_total'] for row in rows),
    }
