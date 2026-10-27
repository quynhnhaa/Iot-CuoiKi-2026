from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.batch import BatchStatus


class BatchCreate(BaseModel):
    target_id: int
    requested_count: int = Field(gt=0)
    operator: str | None = None
    note: str | None = None


class BatchCounters(BaseModel):
    """Hai bo dem tach biet de khong lan gi la quan sat voi gi da xac nhan."""

    observed: dict[str, int]
    confirmed: dict[str, int]
    confirmed_total: int


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_id: int
    requested_count: int
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
