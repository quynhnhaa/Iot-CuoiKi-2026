from datetime import datetime

from pydantic import BaseModel, Field


class TrayCount(BaseModel):
    """Mot nhan AI va so vien cua nhan do trong mot khay."""

    label: str = Field(min_length=1, max_length=128)
    count: int = Field(gt=0)


class TrayResultIn(BaseModel):
    """Snapshot day du cua mot khay; gui lai se thay the snapshot cu."""

    counts: list[TrayCount] = Field(min_length=1, max_length=100)
    image_path: str | None = Field(default=None, max_length=512)


class TrayResultRead(TrayResultIn):
    tray_number: int
    created_at: datetime
    updated_at: datetime
