"""Gui email cho nguoi quan ly khi co mau can train lai."""
import smtplib
from email.message import EmailMessage

from app.config import get_settings


class TrainingEmailUnavailable(RuntimeError):
    """SMTP hoac danh sach nguoi quan ly chua duoc cau hinh."""


def _settings_or_raise():
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise TrainingEmailUnavailable(
            'Chua cau hinh WEB_SMTP_HOST hoac WEB_SMTP_FROM'
        )
    return settings


def request_retraining(*, target_count: int, image_count: int, recipients: list[str]) -> None:
    """Gui yeu cau train toan bo du lieu; quan ly chu dong chay pipeline."""
    settings = _settings_or_raise()
    if not recipients:
        raise TrainingEmailUnavailable('Chua co email cua tai khoan quan tri dang hoat dong')
    message = EmailMessage()
    message['Subject'] = '[May dem vien] Yeu cau train lai toan bo du lieu mau'
    message['From'] = settings.smtp_from
    message['To'] = ', '.join(recipients)
    message.set_content(
        'Co yeu cau train lai toan bo du lieu mau trong he thong.\n\n'
        f'So mau chuan: {target_count}.\n'
        f'Tong so anh mau: {image_count}.\n\n'
        'Vui long kiem tra du lieu va chay pipeline train lai theo quy trinh cua nhom AI.'
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
