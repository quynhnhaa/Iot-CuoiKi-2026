# Web quản lý — máy đếm và loại viên thuốc lỗi

Giao diện và API quản lý **dữ liệu nghiệp vụ và lịch sử** của đồ án: tài khoản, mẫu chuẩn, mẻ đếm, kết quả từng viên và bộ đếm từng ô. Nhánh AI nằm ở [`../model`](../model/README.md).

> Nguyên mẫu kỹ thuật. Không dùng để nhận dạng, đếm hoặc cấp phát thuốc thật cho bệnh nhân.

## Ranh giới với ThingsBoard

Hệ thống dùng **cả hai**. ThingsBoard lo telemetry thời gian thực và màn hình điều khiển; web này giữ dữ liệu nghiệp vụ, lịch sử và bộ đếm chính thức. Phân chia để tránh hai nơi cùng giữ một bộ đếm rồi lệch nhau:

| | ThingsBoard | Web này |
|---|---|---|
| Telemetry thời gian thực, trạng thái máy, lỗi phần cứng | ✅ | ❌ |
| Nút start/pause/stop trên màn hình vận hành | ✅ | ✅ |
| Tài khoản, mẫu chuẩn, mẻ đếm, kết quả từng viên, lịch sử | ❌ | ✅ |
| Bộ đếm **chính thức** của một mẻ | ❌ | ✅ (chỉ tính viên đã được cảm biến xác nhận) |

### Dữ liệu chảy thế nào

```
                 telemetry (bộ đếm, trạng thái mẻ)
Web  ──────────────────────────────────────────────▶  ThingsBoard
     ◀──────────────────────────────────────────────
                 lệnh start / pause / stop
```

**Chiều ra** — sau mỗi lần đổi trạng thái mẻ, ghi kết quả soi viên hoặc xác nhận cảm biến rơi, web đẩy telemetry lên ThingsBoard. Payload tách tên rõ hai nhóm: `confirmed_*` (bộ đếm chính thức) và `observed_*` (camera thấy), để không ai đọc nhầm trên dashboard.

Việc đẩy chạy **ở nền sau khi request đã trả lời**, và mọi lỗi mạng đều bị nuốt rồi ghi log. ThingsBoard sập thì dashboard trễ số, còn mẻ đang chạy vẫn chạy — có kiểm thử riêng cho điều này.

**Chiều vào** — dashboard gọi `POST /api/thingsboard/commands` với `X-Command-Secret`. Đường này không dùng tài khoản người dùng: lệnh đến từ một máy chủ, không từ trình duyệt đã đăng nhập hai lớp. Nó chỉ làm được đúng một việc — đổi trạng thái một mẻ — và **đi qua đúng bảng chuyển trạng thái** mà nút bấm trên web dùng ([`services/batch_state.py`](backend/app/services/batch_state.py)), nên dashboard không có đường tắt nào mà web không có.

`WEB_THINGSBOARD_COMMAND_SECRET` để trống nghĩa là **tắt hẳn** endpoint (trả 503), không phải chấp nhận mọi lời gọi — một cấu hình thiếu không được biến thành cánh cửa mở.

### Bật ThingsBoard

1. Trong ThingsBoard tạo một device cho web này, lấy **access token** của nó.
2. Điền vào `web/.env`:

```bash
WEB_THINGSBOARD_ENABLED=true
WEB_THINGSBOARD_BASE_URL=http://localhost:8080
WEB_THINGSBOARD_DEVICE_TOKEN=<access token của device>
WEB_THINGSBOARD_COMMAND_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(32))">
```

3. Trên dashboard, dựng widget đọc các khoá `confirmed_total`, `batch_status`, `confirmed_accepted`… và nút gọi `POST /api/thingsboard/commands` kèm header bí mật.

Mặc định `WEB_THINGSBOARD_ENABLED=false`, nên không có ThingsBoard backend vẫn chạy bình thường và không gửi gì.

## Xác thực hai lớp

Mọi tài khoản người dùng đều phải qua **hai lớp**: mật khẩu, rồi mã TOTP 6 số từ ứng dụng xác thực (Google Authenticator, Aegis, 1Password…).

```
POST /api/auth/login            mật khẩu  → mfa_token (5 phút), KHÔNG có access token
POST /api/auth/login/verify     mã TOTP   → access token (30 phút)
POST /api/auth/login/recovery   mã dự phòng → access token
```

Các tính chất được ràng buộc bằng kiểm thử:

- **Bước mật khẩu không bao giờ trả access token.** Nó trả `mfa_token` mang `kind="mfa"`, và `mfa_token` bị từ chối ở mọi API nghiệp vụ. Ngược lại access token không dùng được cho bước ghi danh.
- **Một mã TOTP chỉ dùng được một lần.** Backend lưu *bước thời gian mà mã thật sự thuộc về* (không phải bước của đồng hồ hiện tại), nên mã bị nhìn thấy không phát lại được, mà mã kế tiếp trong cùng 30 giây vẫn dùng bình thường.
- **Chưa ghi danh 2FA thì không vào được gì.** Tài khoản mới đăng nhập lần đầu bị đưa vào luồng ghi danh; không có đường nào phát access token trước khi `totp_enabled` bật.
- **8 mã dự phòng**, mỗi mã một lần, chỉ hiện đúng một lần lúc ghi danh, trong DB chỉ lưu dạng bcrypt.
- **Sai mật khẩu 5 lần** → khoá tạm 15 phút (HTTP 423).
- **Đổi mật khẩu hoặc bị vô hiệu → token cũ hết hiệu lực ngay**, không đợi hết hạn (`token_version` được ký vào token).
- Mất thiết bị và hết mã dự phòng: admin khác gọi `POST /api/users/{id}/reset-totp`. Admin **không tự** đặt lại 2FA, tự hạ vai trò hay tự vô hiệu tài khoản của mình — để không ai khoá hết đường vào hệ thống.

### Tài khoản máy dùng API key, không dùng TOTP

Thiết bị đẩy kết quả soi viên (Raspberry Pi) không gõ được mã luân phiên. Nên vai trò `machine` xác thực bằng `X-API-Key` thay vì hai lớp. Đánh đổi được bù lại bằng phạm vi hẹp: **tài khoản máy chỉ ghi được kết quả soi viên**, không đọc danh sách mẻ, không tạo mẻ, không vào quản trị. Key chỉ hiện một lần lúc phát; phát key mới làm key cũ hết hiệu lực ngay.

## Phân quyền

| | viewer | operator | machine | admin |
|---|:--:|:--:|:--:|:--:|
| Xem mẻ, mẫu chuẩn, lần chạy AI | ✅ | ✅ | ❌ | ✅ |
| Tạo mẻ, đổi trạng thái mẻ | ❌ | ✅ | ❌ | ✅ |
| Ghi kết quả soi viên, xác nhận cảm biến rơi | ❌ | ✅ | ✅ | ❌ |
| Tạo mẫu chuẩn | ❌ | ❌ | ❌ | ✅ |
| Quản trị tài khoản | ❌ | ❌ | ❌ | ✅ |

Admin **không** mặc định đi qua mọi cổng: admin quản trị tài khoản, không phải người ghi kết quả soi viên. Giao diện có ẩn nút theo vai trò, nhưng đó chỉ để bớt rối mắt — quyết định thật nằm ở guard của từng route trong backend.

## Hai bộ đếm, cố ý tách riêng

Mỗi mẻ có hai bộ số:

- **`observed`** — camera kết luận viên thuộc ô nào.
- **`confirmed`** — cảm biến đường rơi đã báo viên vào ô. Đây mới là bộ đếm của mẻ, theo đúng quy tắc của nhánh AI: bộ đếm chỉ tăng sau khi cảm biến xác nhận.

API từ chối xác nhận rơi cho một sự kiện mà `release_allowed=false`, nên không thể cộng bộ đếm cho viên mà hệ thống chưa cho phép thả.

## Logic ba nhãn không được viết lại ở đây

`ACCEPTED` / `DEFECTIVE` / `WRONG_DRUG` do [`model/src/common/decision_simulator.py`](../model/src/common/decision_simulator.py) quyết định. Backend nạp đúng file đó theo đường dẫn ([`app/services/decision.py`](backend/app/services/decision.py)) và chỉ gọi `decide`. Bản sao thứ hai của logic này sẽ lệch khỏi bản đã có kiểm thử, nên không có bản sao nào.

Hệ quả: `GET /api/health` trả `decision_logic` khác `"ok"` nếu không tìm thấy file, và API ghi sự kiện trả **503** thay vì tự đoán một nhãn.

## Cấu trúc

```
web/
├── .env.example
├── backend/            FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── api/        routes + deps.py (xác định người gọi, guard theo vai trò)
│   │   ├── core/       security.py: bcrypt, JWT, TOTP, API key
│   │   ├── models/     ORM: User, RecoveryCode, Target, Batch, PillEvent
│   │   ├── schemas/    pydantic request/response
│   │   ├── services/   auth, decision (nạp từ nhánh AI), counters, ai_runs
│   │   ├── config.py
│   │   ├── db.py
│   │   └── main.py
│   ├── scripts/        create_admin.py
│   ├── migrations/     để trống; thêm Alembic khi schema ổn định
│   └── tests/
└── frontend/           Vite + React + TypeScript
    └── src/
        ├── styles/     tokens.css (màu, khoảng cách, bóng), base, layout,
        │               components — không có hex rời rạc ngoài tokens.css
        ├── components/ Icon, UserMenu, ui.tsx (Card, Badge, Tile, Alert…)
        ├── lib/        api.ts, auth.tsx (AuthProvider, RoleGate)
        └── pages/      LoginPage, BatchesPage, BatchDetailPage, TargetsPage,
                        UsersPage
```

## Giao diện

Menu bên trái chia hai nhóm — **Vận hành** (Mẻ đếm, Mẫu chuẩn) và **Quản trị** (Tài khoản, chỉ admin thấy). Dưới 880px menu thu thành ngăn trượt mở bằng nút ở thanh trên. Tài khoản và nút đăng xuất nằm trong menu người dùng ở góc phải.

Màu lấy từ bảng đã kiểm định cho trực quan hoá dữ liệu: bốn màu trạng thái (good / warning / serious / critical) dùng cho năm ô đích và trạng thái mẻ, **mỗi màu luôn đi kèm icon và nhãn chữ** nên không bao giờ để màu tự mang nghĩa. Chế độ tối là một bộ giá trị chọn riêng cho nền tối, không phải đảo ngược tự động.

Dòng «Nguyên mẫu kỹ thuật — không dùng cho thuốc thật» không hiện trong giao diện; nó nằm ở README này và ở [đề tài gốc](../DeTai/de-tai-may-dem-va-loai-vien-loi-ai.md).

## Chạy backend

```bash
cd web/backend
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Tạo `web/.env` với khoá ký. **Bước này bắt buộc** — thiếu `WEB_SECRET_KEY` thì backend không khởi động, cố ý như vậy để không ai chạy thật với một khoá đoán được:

```bash
cp web/.env.example web/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # dán vào WEB_SECRET_KEY
```

Tạo admin đầu tiên (mật khẩu nhập ẩn, không qua tham số dòng lệnh để không vào history của shell):

```bash
cd web/backend && .venv/Scripts/python scripts/create_admin.py --username admin
```

Chạy:

```bash
cd web/backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Kiểm tra nạp được logic AI: http://127.0.0.1:8000/api/health

Lần đăng nhập đầu của admin sẽ vào luồng ghi danh TOTP và trả về 8 mã dự phòng — lưu lại ngay, chúng không hiện lại.

Bảng được tạo lúc khởi động cho bản demo. Khi schema ổn định thì chuyển sang Alembic trong `migrations/`.

## Chạy frontend

```bash
cd web/frontend
npm install
npm run dev
```

Mở http://localhost:5173. Vite proxy `/api` sang `http://127.0.0.1:8000`, nên không cần cấu hình CORS khi phát triển.

## Kiểm thử

```bash
cd web/backend
.venv/Scripts/python -m pytest
```

Các kiểm thử bám vào những ràng buộc dễ bị phá khi sửa về sau:

- **Xác thực** (`test_auth.py`): mật khẩu một mình không mở được gì, `mfa_token` không gọi được API nghiệp vụ, mã TOTP không phát lại được nhưng mã kế tiếp vẫn dùng được, mã dự phòng chỉ một lần, khoá tài khoản sau 5 lần sai, đổi mật khẩu thu hồi token cũ.
- **Phân quyền** (`test_authorization.py`): mọi endpoint từ chối gọi vô danh, viewer không ghi được, operator không quản trị tài khoản, admin không ghi kết quả soi viên, tài khoản máy chỉ ghi được kết quả, key cũ hết hiệu lực sau khi phát key mới, admin không tự khoá mình ra ngoài.
- **ThingsBoard** (`test_thingsboard.py`): tắt mặc định thì không gửi gì, telemetry tách tên `confirmed_*`/`observed_*`, ThingsBoard sập không làm hỏng mẻ đang chạy, thiếu bí mật thì kênh lệnh đóng chứ không mở, lệnh từ dashboard theo đúng bảng chuyển trạng thái của web.
- **Luồng mẻ đếm** (`test_batch_flow.py`): danh tính chưa xác minh ra `WRONG_DRUG`, bộ đếm chỉ tăng sau xác nhận rơi, không xác nhận rơi khi chưa được phép thả, không ghi sự kiện khi mẻ không `running`, không nhảy trạng thái tuỳ ý.

## API

| Method | Đường dẫn | Quyền | Việc |
|---|---|---|---|
| GET | `/api/health` | công khai | trạng thái backend và việc nạp logic AI |
| POST | `/api/auth/login` | công khai | lớp một; trả `mfa_token` |
| POST | `/api/auth/login/verify` | `mfa_token` | lớp hai; trả access token |
| POST | `/api/auth/login/recovery` | `mfa_token` | lớp hai bằng mã dự phòng |
| POST | `/api/auth/totp/enroll` | `mfa_token` | sinh secret để ghi danh |
| POST | `/api/auth/totp/confirm` | `mfa_token` | bật 2FA, trả mã dự phòng |
| GET | `/api/auth/me` | đã đăng nhập | thông tin tài khoản hiện tại |
| POST | `/api/auth/password` | đã đăng nhập | đổi mật khẩu, thu hồi token cũ |
| GET POST | `/api/users` | admin | danh sách / tạo tài khoản |
| PATCH | `/api/users/{id}` | admin | đổi vai trò, vô hiệu |
| POST | `/api/users/{id}/reset-totp` | admin | buộc ghi danh 2FA lại |
| POST | `/api/users/{id}/rotate-api-key` | admin | phát API key mới cho tài khoản máy |
| GET | `/api/targets` | đã đăng nhập | danh sách mẫu chuẩn |
| POST | `/api/targets` | admin | thêm mẫu chuẩn |
| GET POST | `/api/batches` | xem / operator | danh sách / tạo mẻ |
| GET | `/api/batches/{id}` | đã đăng nhập | chi tiết mẻ kèm hai bộ đếm |
| PATCH | `/api/batches/{id}/status` | operator | start / pause / done / abort |
| GET | `/api/batches/{id}/events` | đã đăng nhập | kết quả từng viên |
| POST | `/api/batches/{id}/events` | machine / operator | ghi quan sát; chạy `decide` |
| PATCH | `/api/batches/{id}/events/{event_id}/drop` | machine / operator | cảm biến xác nhận viên đã rơi |
| POST | `/api/thingsboard/commands` | bí mật chia sẻ | lệnh start/pause/stop từ dashboard |
| GET | `/api/ai-runs` | đã đăng nhập | các lần chạy trong `model/runs/pipeline/` |
| GET | `/api/ai-runs/{name}/events` | đã đăng nhập | `events.jsonl` của một lần chạy |

`/api/ai-runs` **không có trang giao diện** — hai endpoint này còn đó để gọi trực tiếp khi cần, nhưng không hiện trong menu. Chúng đọc `model/runs/`, thư mục không commit lên Git, nên trên máy chưa chạy thí nghiệm kết quả sẽ trống.

## Giới hạn đã biết

- **Token nằm trong `localStorage`.** Đủ cho bản demo, nhưng một lỗi XSS trên trang này sẽ đọc được token. Chạy thật nên chuyển sang cookie `HttpOnly` kèm chống CSRF.
- **Không có refresh token.** Hết 30 phút là phải đăng nhập lại cả hai lớp.
- **Chưa có QR code** cho lúc ghi danh; giao diện hiện khoá dạng chữ và đường dẫn `otpauth://` để dán vào ứng dụng xác thực.
- **Giới hạn số lần thử tính theo tài khoản**, chưa tính theo IP, nên chưa chặn được việc rải mật khẩu qua nhiều tài khoản.
- **Chưa có nhật ký kiểm toán** (ai đăng nhập lúc nào, ai đổi gì) ngoài `last_login_at`.
- **Tích hợp ThingsBoard chưa chạy thử với một ThingsBoard thật.** Kiểm thử dùng transport giả, nên hình dạng payload và luồng lệnh đã được khoá lại, nhưng việc dashboard hiển thị đúng thì phải dựng instance mới biết.
- Telemetry đẩy theo từng sự kiện, chưa có hàng đợi hay gửi lại khi hỏng — mất mạng lúc nào thì dashboard thiếu nhịp đó cho tới sự kiện kế tiếp.
- Chưa nhận ảnh trực tiếp từ camera, chưa có Alembic.
- Giao diện chưa có kiểm thử tự động; các màn hình được xem bằng tay ở cả chế độ sáng, tối và bề rộng điện thoại.
