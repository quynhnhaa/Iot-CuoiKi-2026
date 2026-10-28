from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.batch import BatchStatus


class BatchCreate(BaseModel):
    target_id: int
    # De trong = dem mo. Co so thi day chi la dich de nhin, khong phai mot
    # cai cua: cham den so do me van nhan tiep su kien.
    requested_count: int | None = Field(default=None, gt=0)
    operator: str | None = None
    note: str | None = None


class BatchCounters(BaseModel):
    """Hai bo dem tach biet de khong lan gi la quan sat voi gi da xac nhan."""

    observed: dict[str, int]
    confirmed: dict[str, int]
    # Moi vien da roi co xac nhan, ke ca vien loai.
    confirmed_total: int
    # Chi vien dat; day moi la tien do so voi requested_count.
    accepted_total: int


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_id: int
    requested_count: int | None
    status: BatchStatus
    operator: str | None
    note: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class BatchDetail(BatchRead):
    counters: BatchCounters


class BatchStatusUpdate(BaseModel):
    status: BatchStatus
