from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PillObservationIn(BaseModel):
    """Quan sat tu pipeline AI. Backend khong tu suy ra quyet dinh nao khac."""

    pill_count: int = Field(ge=0)
    image_usable: bool
    identity_verified: bool
    target_matches: bool
    defect_status: Literal['normal', 'defective', 'uncertain']
    identity_gate_validated: bool = False
    hardware_ready: bool = False
    image_path: str | None = None


class DropConfirmation(BaseModel):
    drop_confirmed: bool


class PillEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    sequence: int
    pill_count: int
    image_usable: bool
    identity_verified: bool
    target_matches: bool
    defect_status: str
    identity_gate_validated: bool
    hardware_ready: bool
    route: str
    release_allowed: bool
    requires_drop_confirmation: bool
    reason: str
    drop_confirmed: bool
    image_path: str | None
    created_at: datetime
