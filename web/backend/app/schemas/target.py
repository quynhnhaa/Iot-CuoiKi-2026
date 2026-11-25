from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TargetCreate(BaseModel):
    code: str
    name: str
    recognition_label: str | None = None
    note: str | None = None


class TargetRead(TargetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
