"""Hinh dang cua bang thong ke theo ngay, tuan, thang."""
from datetime import date

from pydantic import BaseModel, Field


class StatsTotals(BaseModel):
    """Tong cua ca khoang."""

    batches: int
    observed: dict[str, int]
    confirmed: dict[str, int]
    # Tong so lan camera soi, ke ca lan bi loai ngay tu anh.
    observed_total: int
    # Vien da roi co cam bien xac nhan, ke ca vien loai.
    confirmed_total: int
    # Chi vien dat; day moi la so vien lay duoc.
    accepted_total: int


class StatsRow(StatsTotals):
    """Mot ky: mot ngay, mot tuan hoac mot thang."""

    # Ngay dau ky, dang ISO — dung lam khoa, khong phai de hien.
    key: date
    # Chuoi de hien cho nguoi doc: '28/10/2026', 'Tuần 44/2026 (26/10 - 01/11)'.
    label: str


class StatsResponse(BaseModel):
    period: str
    first: date = Field(serialization_alias='from')
    last: date = Field(serialization_alias='to')
    rows: list[StatsRow]
    totals: StatsTotals

    model_config = {'populate_by_name': True}
