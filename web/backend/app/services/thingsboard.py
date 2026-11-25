"""Đẩy telemetry của mẻ lên ThingsBoard.

Ranh giới cố ý: **web này là nguồn sự thật của bộ đếm**, ThingsBoard chỉ hiển
thị. Dữ liệu chảy một chiều ra ngoài. Chiều ngược lại — lệnh start/pause/stop
từ dashboard — đi qua [app/api/thingsboard.py](../api/thingsboard.py) và vẫn
phải qua đúng bảng chuyển trạng thái của web.

Mọi lỗi mạng ở đây đều bị nuốt và chỉ ghi log: dashboard không hiện số mới là
phiền, còn một mẻ đang chạy mà hỏng vì ThingsBoard sập thì tệ hơn nhiều.
"""
import logging
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.models import Batch

logger = logging.getLogger(__name__)


class Transport(Protocol):
    """Tách phần gửi ra ngoài để kiểm thử không cần một ThingsBoard thật."""

    def send(self, url: str, payload: dict[str, Any], timeout: float) -> None: ...


class HttpTransport:
    def send(self, url: str, payload: dict[str, Any], timeout: float) -> None:
        response = httpx.post(url, json=payload, timeout=timeout)
        response.raise_for_status()


class RecordingTransport:
    """Dùng trong kiểm thử và khi chạy thử không có ThingsBoard."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, url: str, payload: dict[str, Any], timeout: float) -> None:  # noqa: ARG002
        self.sent.append((url, payload))


_transport: Transport = HttpTransport()


def set_transport(transport: Transport) -> Transport:
    """Thay transport (kiểm thử dùng). Trả về cái cũ để khôi phục."""
    global _transport
    previous = _transport
    _transport = transport
    return previous


def is_enabled() -> bool:
    return get_settings().thingsboard_enabled


def build_batch_telemetry(batch: Batch, counters: dict[str, Any]) -> dict[str, Any]:
    """Payload telemetry của một mẻ.

    Khoá `confirmed_*` là bộ đếm chính thức (cảm biến đã xác nhận);
    `observed_*` là kết luận của camera trước khi viên rơi. Hai nhóm được đặt
    tên tách bạch để không ai đọc nhầm trên dashboard.

    Widget tiến độ trên dashboard phải đọc `accepted_total`, không phải
    `confirmed_total`: viên loại cũng rơi và cũng được cảm biến xác nhận, nhưng
    không được tính là đã lấy được một viên.

    Nhận `counters` từ bên ngoài thay vì tự đọc `batch.events`: hàm này chạy
    trong lúc request còn phiên DB, rồi payload mới được gửi đi ở nền.
    """
    payload: dict[str, Any] = {
        'batch_id': batch.id,
        'batch_status': str(batch.status),
        'confirmed_total': counters['confirmed_total'],
        'accepted_total': counters['accepted_total'],
    }
    # Me dem mo khong co so dich; khong gui khoa rong de widget khong ve
    # mot thanh tien do khong co mau so.
    if batch.requested_count is not None:
        payload['requested_count'] = batch.requested_count
    for route, count in counters['confirmed'].items():
        payload[f'confirmed_{route.lower()}'] = count
    for route, count in counters['observed'].items():
        payload[f'observed_{route.lower()}'] = count
    return payload


def publish(payload: dict[str, Any]) -> None:
    """Gửi một payload đã dựng sẵn. Không bao giờ ném lỗi ra ngoài.

    Chạy ở nền sau khi request đã trả lời, nên không được chạm vào ORM hay
    phiên DB — chỉ có dict thuần đi vào đây.
    """
    settings = get_settings()
    if not settings.thingsboard_enabled:
        return
    if not settings.thingsboard_base_url or not settings.thingsboard_device_token:
        logger.warning('ThingsBoard bật nhưng thiếu base URL hoặc device token; bỏ qua telemetry')
        return

    url = (
        f'{settings.thingsboard_base_url.rstrip("/")}'
        f'/api/v1/{settings.thingsboard_device_token}/telemetry'
    )
    try:
        _transport.send(url, payload, settings.thingsboard_timeout_seconds)
    except Exception:
        # Dashboard trễ số thì phiền; mẻ đang chạy mà hỏng thì tệ hơn nhiều.
        logger.exception(
            'Không đẩy được telemetry của mẻ %s lên ThingsBoard', payload.get('batch_id')
        )
