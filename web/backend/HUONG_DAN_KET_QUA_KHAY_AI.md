# Kết quả AI theo ba khay

Tài liệu này mô tả cách nâng cấp cơ sở dữ liệu và cách pipeline AI gửi kết quả
đếm theo từng khay. API chỉ nhận nhãn AI cùng số lượng; web tự đối chiếu với
mẫu thuốc đã chọn trong mẻ để phân loại **Đúng thuốc**, **Sai thuốc** và
**Viên bể**.

## 1. Chạy migration

Từ thư mục `web/backend`, với môi trường ảo đã được tạo:

```powershell
.venv\Scripts\python.exe migrations\003_create_tray_results.py
```

Migration này tạo bảng `tray_results`. Mỗi mẻ có tối đa một snapshot mới nhất
cho mỗi khay 1, 2 và 3. Có thể chạy lại lệnh an toàn vì bảng được tạo với
`CREATE TABLE IF NOT EXISTS`.

Khởi động hoặc kiểm tra lại backend sau migration:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## 2. Quy ước nhãn AI

Pipeline AI trả về số lượng theo từng nhãn nhận dạng. Nhãn thuốc đúng nên bằng
`recognition_label` của mẫu chuẩn trong mẻ. Nếu mẫu chưa có nhãn này, web mới
thử đối chiếu tiếp với `code` và `name` của mẫu.

Các nhãn được web hiểu là viên bể/lỗi gồm:

- `broken`
- `defective`
- `cracked`
- `vien be`
- `sut vo`
- `be vo`

Mọi nhãn còn lại không khớp mẫu chuẩn đều được hiển thị là **Sai thuốc**.
Nên cấu hình pipeline dùng cố định `broken` cho viên bể để tránh sai khác tên
nhãn giữa các phiên bản model.

Ví dụ, nếu mẫu chuẩn có `recognition_label = "drug_a"`, kết quả dưới đây có
2 viên đúng, 3 viên sai thuốc và 4 viên bể:

```json
[
  { "label": "drug_a", "count": 2 },
  { "label": "drug_b", "count": 3 },
  { "label": "broken", "count": 4 }
]
```

## 3. API cho pipeline AI

### Ghi hoặc thay thế kết quả của một khay

```http
PUT /api/batches/{batch_id}/tray-results/{tray_number}
X-API-Key: <machine_api_key>
Content-Type: application/json
```

`tray_number` phải là `1`, `2` hoặc `3`. Mẻ phải ở trạng thái `running`.
Tài khoản gọi API phải là `machine` (qua `X-API-Key`) hoặc `operator` (qua
access token). Gửi lại kết quả cho cùng một khay sẽ **thay thế** snapshot cũ,
không cộng dồn số lượng; điều này giúp AI retry request an toàn.

Body mẫu:

```json
{
  "counts": [
    { "label": "drug_a", "count": 2 },
    { "label": "drug_b", "count": 3 },
    { "label": "broken", "count": 4 }
  ],
  "image_path": "/images/batch-18/tray-1.jpg"
}
```

- `counts`: bắt buộc, là mảng không rỗng gồm `{ "label": string, "count": integer > 0 }`.
- `image_path`: tùy chọn; web dùng ảnh này ở phần ảnh theo khay.

Ví dụ PowerShell:

```powershell
$headers = @{ "X-API-Key" = "<machine_api_key>" }
$body = @{
  counts = @(
    @{ label = "drug_a"; count = 2 },
    @{ label = "drug_b"; count = 3 },
    @{ label = "broken"; count = 4 }
  )
  image_path = "/images/batch-18/tray-1.jpg"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8000/api/batches/18/tray-results/1" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

### Đọc kết quả ba khay

```http
GET /api/batches/{batch_id}/tray-results
Authorization: Bearer <access_token>
```

Response là danh sách snapshot đã có, sắp theo số khay. Web gọi endpoint này
và tự tạo các tổng đúng/sai/bể cho từng khay cũng như toàn bộ ba khay.

## 4. Lệnh Git để tự commit

Từ thư mục gốc repository, kiểm tra thay đổi trước:

```powershell
git status
```

Các file mới có thể stage trực tiếp:

```powershell
git add web/backend/app/api/tray_results.py web/backend/app/models/tray_result.py web/backend/app/schemas/tray_result.py web/backend/migrations/003_create_tray_results.py web/backend/tests/test_tray_results.py web/backend/HUONG_DAN_KET_QUA_KHAY_AI.md
```

Các file dưới đây đang có thể chứa thay đổi khác chưa commit. Dùng chế độ chọn
từng hunk để chỉ stage phần kết quả AI theo khay:

```powershell
git add -p web/backend/app/api/__init__.py web/backend/app/models/__init__.py web/backend/app/models/batch.py web/frontend/src/lib/api.ts web/frontend/src/pages/BatchDetailPage.tsx web/frontend/src/styles/components.css
```

Xem lại phần đã stage rồi tự commit:

```powershell
git diff --cached
git commit -m "feat: show AI tray count summaries"
```
