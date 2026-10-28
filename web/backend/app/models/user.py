"""Nguoi van hanh va tai khoan may.

Nguoi dung dang nhap hai lop: mat khau roi ma TOTP. Tai khoan `machine` la
thiet bi (Raspberry Pi day quan sat len), khong the go ma luan phien nen dung
API key thay vi TOTP — doi lai no bi gioi han o dung mot viec: ghi su kien.
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Role(str, Enum):
    ADMIN = 'admin'
    OPERATOR = 'operator'
    VIEWER = 'viewer'
    MACHINE = 'machine'


# Vai tro la nguoi that thi buoc phai co lop thu hai.
HUMAN_ROLES = frozenset({Role.ADMIN, Role.OPERATOR, Role.VIEWER})


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(128), default=None)
    role: Mapped[Role] = mapped_column(String(16), default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)

    # Tai khoan may khong co mat khau; tai khoan nguoi khong co api key.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    # TOTP. Secret duoc sinh khi ghi danh va chi bat sau khi xac nhan dung ma.
    totp_secret: Mapped[str | None] = mapped_column(String(64), default=None)
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    # Chong dung lai dung mot ma trong cung mot buoc thoi gian.
    last_totp_timestep: Mapped[int | None] = mapped_column(default=None)

    # Han che do mat khau.
    failed_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(default=None)

    # Moi lan doi mat khau hoac tat 2FA se tang so nay, lam het hieu luc token cu.
    token_version: Mapped[int] = mapped_column(default=1)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    recovery_codes: Mapped[list['RecoveryCode']] = relationship(
        back_populates='user', cascade='all, delete-orphan'
    )

    @property
    def requires_totp(self) -> bool:
        return Role(self.role) in HUMAN_ROLES


class RecoveryCode(Base):
    """Ma du phong dung mot lan khi mat thiet bi sinh ma. Chi luu dang bam."""

    __tablename__ = 'recovery_codes'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    code_hash: Mapped[str] = mapped_column(String(255))
    used_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped['User'] = relationship(back_populates='recovery_codes')
