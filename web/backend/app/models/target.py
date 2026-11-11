"""Mau chuan cua mot me dem."""
from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Target(Base):
    __tablename__ = 'targets'

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    # ID nhan anh cua nhanh AI (vi du VAIPE 64, 91...). Khong phai hoat chat thuoc that.
    recognition_label: Mapped[str | None] = mapped_column(String(64), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    batches: Mapped[list['Batch']] = relationship(back_populates='target')  # noqa: F821
