"""Dich loi kiem tra truong cua pydantic sang tieng Viet.

FastAPI sinh loi 422 truoc khi request den duoc code cua minh, nen nhung loi
nay khong di qua `HTTPException` va khong duoc dich o day:

    {"detail":[{"type":"missing","loc":["body","recovery_code"],
                "msg":"Field required", ...}]}

Hai van de, khong phai mot:

1. Noi dung la tieng Anh va la cau truc may doc, khong phai cau nguoi doc.
2. `detail` la *mang*, trong khi moi cho khac trong API tra `detail` la *chuoi*.
   Frontend lam `new ApiError(body.detail)`, nen mot mang se hien ra man hinh
   thanh "[object Object]".

Handler nay gop ca hai: `detail` tro lai la mot cau tieng Viet, va mang goc
duoc giu nguyen o khoa `errors` cho ai can go roi.

Khong co y dich het pydantic. Nhung kieu loi thuong gap thi co cau rieng, con
lai roi ve `msg` goc — thieu dau con hon bia ra mot cau sai nghia.
"""
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Ten truong -> nhan nguoi doc hieu. Truong nao khong co trong day thi hien
# nguyen ten ky thuat, van tot hon la giau di.
FIELD_LABELS: dict[str, str] = {
    'username': 'Tên đăng nhập',
    'password': 'Mật khẩu',
    'current_password': 'Mật khẩu hiện tại',
    'new_password': 'Mật khẩu mới',
    'code': 'Mã xác thực',
    'recovery_code': 'Mã dự phòng',
    'mfa_token': 'Phiên xác thực',
    'api_key': 'API key',
    'full_name': 'Họ tên',
    'role': 'Vai trò',
    'is_active': 'Trạng thái hoạt động',
    'note': 'Ghi chú',
    'name': 'Tên',
    'recognition_label': 'Nhãn nhận ảnh',
    'target_id': 'Mẫu chuẩn',
    'requested_count': 'Số viên cần lấy',
    'operator': 'Người vận hành',
    'status': 'Trạng thái',
    'command': 'Lệnh',
    'batch_id': 'Mẻ đếm',
    'pill_count': 'Số viên trong khung',
    'image_usable': 'Ảnh dùng được',
    'identity_verified': 'Đã xác minh danh tính viên',
    'target_matches': 'Khớp mẫu chuẩn',
    'defect_status': 'Tình trạng hư hỏng',
    'identity_gate_validated': 'Cổng danh tính đã kiểm',
    'hardware_ready': 'Phần cứng sẵn sàng',
    'image_path': 'Đường dẫn ảnh',
    'drop_confirmed': 'Cảm biến rơi',
}

# Vi tri dau cua `loc` chi ra request o dau, khong phai ten truong.
_SECTIONS = {'body', 'query', 'path', 'header', 'cookie'}


def _reason(error: dict[str, Any]) -> str:
    kind = error.get('type', '')
    ctx = error.get('ctx') or {}
    match kind:
        case 'missing':
            return 'chưa điền'
        case 'string_too_short':
            return f'cần ít nhất {ctx.get("min_length")} ký tự'
        case 'string_too_long':
            return f'tối đa {ctx.get("max_length")} ký tự'
        case 'string_pattern_mismatch':
            return 'sai định dạng'
        case 'greater_than':
            return f'phải lớn hơn {ctx.get("gt")}'
        case 'greater_than_equal':
            return f'phải từ {ctx.get("ge")} trở lên'
        case 'less_than':
            return f'phải nhỏ hơn {ctx.get("lt")}'
        case 'less_than_equal':
            return f'tối đa {ctx.get("le")}'
        case 'int_parsing' | 'int_type':
            return 'phải là số nguyên'
        case 'float_parsing' | 'float_type':
            return 'phải là số'
        case 'bool_parsing' | 'bool_type':
            return 'phải là true hoặc false'
        case 'string_type':
            return 'phải là chuỗi chữ'
        case 'extra_forbidden':
            return 'không được gửi trường này'
        case 'json_invalid':
            return 'nội dung gửi lên không phải JSON hợp lệ'
        case 'enum' | 'literal_error':
            return f'chỉ nhận: {ctx.get("expected")}'
        case _:
            # Bao gom ca `value_error`, noi thong diep do chinh validator cua
            # minh viet ra va da la tieng Viet.
            return error.get('msg', 'không hợp lệ')


def _label(error: dict[str, Any]) -> str | None:
    # JSON hong thi `loc` la ['body', 12] — so 12 la vi tri ky tu loi, khong
    # phai phan tu thu 12 cua mot danh sach. Dat nhan o day se ra mot cau vo
    # nghia ("Muc thu 13: ..."), nen de ly do dung mot minh.
    if error.get('type') == 'json_invalid':
        return None
    parts = [p for p in error.get('loc', ()) if p not in _SECTIONS]
    if not parts:
        return None
    name = parts[-1]
    if isinstance(name, int):
        # Phan tu thu may trong mot danh sach; lay ten truong cha neu co.
        parent = parts[-2] if len(parts) > 1 else None
        label = FIELD_LABELS.get(parent, parent) if parent else 'Mục'
        return f'{label} thứ {name + 1}'
    return FIELD_LABELS.get(name, name)


def _sentence(error: dict[str, Any]) -> str:
    reason = _reason(error)
    label = _label(error)
    return f'{label}: {reason}' if label else reason


async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
    errors = error.errors()
    detail = '; '.join(dict.fromkeys(_sentence(item) for item in errors))
    return JSONResponse(
        # So nguyen thay vi hang cua starlette: ten hang nay dang doi
        # (UNPROCESSABLE_ENTITY -> UNPROCESSABLE_CONTENT) giua cac ban
        # trong khoang phien ban requirements cho phep.
        status_code=422,
        # `errors` giu nguyen cau truc goc cho viec go roi; `detail` la cau cho
        # nguoi dung. `jsonable_encoder` vi `ctx` co the chua Exception.
        content={
            'detail': detail or 'Dữ liệu gửi lên không hợp lệ',
            'errors': jsonable_encoder(errors),
        },
    )
