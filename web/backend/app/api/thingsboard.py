"""Nhận lệnh start/pause/stop gửi từ dashboard ThingsBoard.

Đường này **không** dùng tài khoản người dùng: lệnh đến từ một máy chủ, không
từ một trình duyệt đã đăng nhập hai lớp. Nó xác thực bằng một bí mật chia sẻ
và chỉ làm được đúng một việc — đổi trạng thái một mẻ, qua đúng bảng chuyển
trạng thái mà nút bấm trên web dùng.

Bí mật để trống nghĩa là **tắt hẳn** endpoint, không phải là chấp nhận mọi lời
gọi: một cấu hình thiếu không được biến thành một cánh cửa mở.
"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import Batch, BatchStatus
from app.schemas.thingsboard import CommandRequest, CommandResponse
from app.services.batch_state import InvalidTransition, apply_status

router = APIRouter(prefix='/thingsboard', tags=['thingsboard'])

# Lệnh trên dashboard nói bằng ngôn ngữ người vận hành, không phải tên trạng thái.
COMMAND_TO_STATUS: dict[str, BatchStatus] = {
    'start': BatchStatus.RUNNING,
    'pause': BatchStatus.PAUSED,
    'stop': BatchStatus.DONE,
    'abort': BatchStatus.ABORTED,
}


def verify_command_secret(x_command_secret: str | None = Header(default=None)) -> None:
    configured = get_settings().thingsboard_command_secret
    if not configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            'Kênh lệnh ThingsBoard chưa được cấu hình',
        )
    if not x_command_secret or not secrets.compare_digest(x_command_secret, configured):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Bí mật lệnh không hợp lệ')


@router.post('/commands', response_model=CommandResponse, dependencies=[Depends(verify_command_secret)])
def handle_command(
    payload: CommandRequest,
    session: Session = Depends(get_session),
) -> CommandResponse:
    target = COMMAND_TO_STATUS.get(payload.command)
    if target is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f'Lệnh không hiểu: {payload.command}')

    batch = session.get(Batch, payload.batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy mẻ đếm')

    try:
        batch = apply_status(batch, target, session)
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return CommandResponse(batch_id=batch.id, status=BatchStatus(batch.status))
