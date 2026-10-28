"""Tinh bo dem cua mot me tu cac su kien da luu.

`observed` la so lan camera ket luan tung nhan. `confirmed` chi tinh nhung su
kien da co cam bien duong roi xac nhan, dung quy tac cua nhanh AI: bo dem chi
tang sau khi cam bien bao vien da roi dung o.

Hai tong so **khac nhau** va khong duoc dung lan:

* `confirmed_total` — moi vien da roi co xac nhan, ke ca vien loai da roi vao o
  loai. Dung de doi chieu voi so vien thuc su da di qua may.
* `accepted_total` — chi vien dat. Day moi la tien do so voi so vien can lay:
  `decision_simulator` tra `accepted_count_increment = 0` cho vien loai, nen
  vien loai roi vao o loai khong duoc tinh la da lay duoc mot vien.
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
        'accepted_total': confirmed['ACCEPTED'],
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
