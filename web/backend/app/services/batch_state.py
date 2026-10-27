"""Chuyen trang thai cua mot me dem.

Dat o day vi co hai duong vao: nguoi van hanh bam tren web, va lenh
start/pause/stop gui tu dashboard ThingsBoard. Hai duong phai di qua dung mot
bang chuyen trang thai, neu khong thi mot hom nao do chung se lech nhau.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Batch, BatchStatus

# Chuyen trang thai hop le; khong cho nhay tuy y tu bat ky dashboard nao.
ALLOWED_TRANSITIONS: dict[BatchStatus, set[BatchStatus]] = {
    BatchStatus.PENDING: {BatchStatus.RUNNING, BatchStatus.ABORTED},
    BatchStatus.RUNNING: {BatchStatus.PAUSED, BatchStatus.DONE, BatchStatus.ABORTED},
    BatchStatus.PAUSED: {BatchStatus.RUNNING, BatchStatus.ABORTED},
    BatchStatus.DONE: set(),
    BatchStatus.ABORTED: set(),
}


class InvalidTransition(Exception):
    """Trang thai dich khong di duoc tu trang thai hien tai."""


def apply_status(batch: Batch, target: BatchStatus, session: Session) -> Batch:
    current = BatchStatus(batch.status)
    if target != current and target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(
            f'Khong the chuyen trang thai {current.value} -> {target.value}'
        )

    now = datetime.now(timezone.utc)
    if target is BatchStatus.RUNNING and batch.started_at is None:
        batch.started_at = now
    if target in (BatchStatus.DONE, BatchStatus.ABORTED):
        batch.finished_at = now
    batch.status = target
    session.commit()
    session.refresh(batch)
    return batch
