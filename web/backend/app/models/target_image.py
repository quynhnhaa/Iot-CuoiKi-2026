"""Anh mau duoc dinh kem de quan ly co du lieu train lai."""
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class TargetImage(Base):
    __tablename__ = 'target_images'

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey('targets.id'))
    stored_name: Mapped[str] = mapped_column(String(128), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    target: Mapped['Target'] = relationship(back_populates='images')  # noqa: F821
