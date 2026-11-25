from pydantic import BaseModel, Field

from app.models.batch import BatchStatus


class CommandRequest(BaseModel):
    """Lenh tu dashboard. Dung tu ngu van hanh, khong phai ten trang thai."""

    command: str = Field(description='start | pause | stop | abort')
    batch_id: int


class CommandResponse(BaseModel):
    batch_id: int
    status: BatchStatus
