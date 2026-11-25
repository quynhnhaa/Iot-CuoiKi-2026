from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import Role


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    role: Role
    full_name: str | None = None
    note: str | None = None
    # Bat buoc voi tai khoan nguoi, bo trong voi tai khoan may.
    password: str | None = Field(default=None, min_length=12)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None
    role: Role
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    last_login_at: datetime | None
    locked_until: datetime | None
    note: str | None


class UserCreated(UserRead):
    # Chi tra ve dung mot lan, luc tao tai khoan may.
    api_key: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    note: str | None = None
