"""Mot lan camera soi mot vien, kem quyet dinh va xac nhan cam bien roi."""
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class PillEvent(Base):
    __tablename__ = 'pill_events'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'))
    sequence: Mapped[int]

    # Quan sat tu pipeline AI.
    pill_count: Mapped[int]
    image_usable: Mapped[bool]
    identity_verified: Mapped[bool]
    target_matches: Mapped[bool]
    defect_status: Mapped[str] = mapped_column(String(16))
    identity_gate_validated: Mapped[bool] = mapped_column(default=False)
    hardware_ready: Mapped[bool] = mapped_column(default=False)

    # Ket qua tu decision_simulator cua nhanh AI; khong tinh lai o day.
    route: Mapped[str] = mapped_column(String(32))
    release_allowed: Mapped[bool]
    requires_drop_confirmation: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(Text)

    # Chi cam bien duong roi moi dat co nay; bo dem chi tinh su kien da xac nhan.
    drop_confirmed: Mapped[bool] = mapped_column(default=False)
    image_path: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    batch: Mapped['Batch'] = relationship(back_populates='events')  # noqa: F821
