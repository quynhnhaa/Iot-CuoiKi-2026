"""Me dem: mot loai vien chuan va so vien can lay."""
from datetime import datetime
from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class BatchStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    PAUSED = 'paused'
    DONE = 'done'
    ABORTED = 'aborted'


class Batch(Base):
    __tablename__ = 'batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey('targets.id'))
    requested_count: Mapped[int]
    status: Mapped[BatchStatus] = mapped_column(String(16), default=BatchStatus.PENDING)
    operator: Mapped[str | None] = mapped_column(String(128), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    target: Mapped['Target'] = relationship(back_populates='batches')  # noqa: F821
    events: Mapped[list['PillEvent']] = relationship(  # noqa: F821
        back_populates='batch', cascade='all, delete-orphan', order_by='PillEvent.sequence'
    )
