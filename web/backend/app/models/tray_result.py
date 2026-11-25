"""Snapshot ket qua AI cua mot khay trong me dem."""
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class TrayResult(Base):
    """Moi khay chi giu ket qua AI moi nhat.

    ``counts_json`` la mang ``[{"label": "...", "count": n}]`` do AI gui.
    Khong luu ket luan dung/sai o day vi ket luan phu thuoc mau duoc chon
    cua me va duoc giao dien tu tinh.
    """

    __tablename__ = 'tray_results'
    __table_args__ = (UniqueConstraint('batch_id', 'tray_number', name='uq_tray_result_batch_tray'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'))
    tray_number: Mapped[int] = mapped_column(Integer)
    counts_json: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    batch: Mapped['Batch'] = relationship(back_populates='tray_results')  # noqa: F821
