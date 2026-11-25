from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import Role


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginChallenge(BaseModel):
    """Buoc mot da qua. Chua phai access token."""

    stage: str  # 'totp_required' hoac 'enrollment_required'
    mfa_token: str
    expires_in_seconds: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in_seconds: int
    role: Role
    username: str


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class RecoveryLoginRequest(BaseModel):
    recovery_code: str


class EnrollmentResponse(BaseModel):
    secret: str
    otpauth_uri: str


class EnrollmentConfirmResponse(TokenResponse):
    # Chi hien dung mot lan, ngay sau khi ghi danh.
    recovery_codes: list[str]


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None
    role: Role
    totp_enabled: bool
    last_login_at: datetime | None
    unused_recovery_codes: int = 0
