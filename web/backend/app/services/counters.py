"""Tinh bo dem cua mot me tu cac su kien da luu.

`observed` la so lan camera ket luan tung nhan. `confirmed` chi tinh nhung su
kien da co cam bien duong roi xac nhan, dung quy tac cua nhanh AI: bo dem chi
tang sau khi cam bien bao vien da roi dung o.
"""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PillEvent

ROUTES = ('EMPTY_FRAME', 'MULTIPLE_PILLS', 'WRONG_DRUG', 'DEFECTIVE', 'ACCEPTED')


def summarize(events: Iterable[PillEvent]) -> dict:
    observed = dict.fromkeys(ROUTES, 0)
    confirmed = dict.fromkeys(ROUTES, 0)
    for event in events:
        if event.route in observed:
            observed[event.route] += 1
            if event.drop_confirmed:
                confirmed[event.route] += 1
    return {
        'observed': observed,
        'confirmed': confirmed,
        'confirmed_total': sum(confirmed.values()),
    }


def load_events(session: Session, batch_id: int) -> list[PillEvent]:
    """Doc su kien thang tu DB.

    Quan he `batch.events` co the da duoc nap truoc khi them su kien moi trong
    cung mot request, nen dem tu do se thieu. Truy van lai cho chac.
    """
    return list(
        session.scalars(
            select(PillEvent).where(PillEvent.batch_id == batch_id).order_by(PillEvent.sequence)
        )
    )
