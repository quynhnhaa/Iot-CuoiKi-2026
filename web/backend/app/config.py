"""Cau hinh backend; doc tu bien moi truong hoac file .env o web/."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# web/backend/app/config.py -> web/backend -> web -> repo root
BACKEND_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BACKEND_DIR.parent
PROJECT_ROOT = WEB_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=WEB_DIR / '.env',
        env_prefix='WEB_',
        extra='ignore',
    )

    app_name: str = 'Quan ly may dem va loai vien thuoc'
    database_url: str = f'sqlite:///{BACKEND_DIR / "quanly.db"}'
    cors_origins: str = 'http://localhost:5173'

    # Khoa ky JWT. Khong co gia tri mac dinh: thieu thi backend khong khoi dong,
    # de khong ai vo tinh chay that voi mot khoa doan duoc.
    secret_key: str

    access_token_minutes: int = 30
    # Token trung gian giua buoc mat khau va buoc ma TOTP; co doi song ngan.
    mfa_token_minutes: int = 5

    # Ten hien o ung dung sinh ma (Google Authenticator, Aegis...).
    totp_issuer: str = 'May dem vien thuoc'
    # So buoc thoi gian 30 giay chap nhan lech dong ho hai phia.
    totp_valid_window: int = 1

    # Chi phi bam mat khau. Ha xuong trong kiem thu de bo test khong cham.
    bcrypt_rounds: int = 12

    max_failed_attempts: int = 5
    lockout_minutes: int = 15
    recovery_code_count: int = 8

    # --- ThingsBoard ---
    # Tat mac dinh: khong co instance thi backend van chay binh thuong.
    thingsboard_enabled: bool = False
    thingsboard_base_url: str = ''
    thingsboard_device_token: str = ''
    thingsboard_timeout_seconds: float = 3.0
    # Bi mat chia se cho endpoint nhan lenh tu dashboard. De trong = tat han.
    thingsboard_command_secret: str = ''

    # Duong dan sang nhanh AI trong cung repo.
    model_dir: Path = PROJECT_ROOT / 'model'
    pipeline_runs_dir: Path = PROJECT_ROOT / 'model' / 'runs' / 'pipeline'

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def decision_simulator_path(self) -> Path:
        return self.model_dir / 'src' / 'common' / 'decision_simulator.py'


@lru_cache
def get_settings() -> Settings:
    return Settings()
