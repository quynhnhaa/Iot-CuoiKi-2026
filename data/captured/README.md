# Ảnh viên thuốc từ camera của máy

Thư mục hiện có **19 ảnh pilot chụp bằng điện thoại**, qua nhiều phiên, gồm nhiều ảnh của cùng viên vật lý. Chưa có ảnh từ **camera và buồng chụp dự kiến của máy**. Ảnh VAIPE và các ID số 46, 10, v.v. là nhãn hình ảnh nghiên cứu; **không dùng chúng làm tên thuốc thật**. Người chụp cho biết tên thuốc trên file đã đối chiếu với bao bì/lô; mã tham chiếu `identity_evidence_ref` cho từng nhóm chưa được ghi lại. Không lưu thông tin bệnh nhân trong đường dẫn hay manifest.

## Ảnh pilot hiện có (28/10/2026)

Tên file theo mẫu `<tên thuốc>_<o|x>_<số>.JPG`: `o` là viên bình thường, `x` là viên vỡ/sứt theo nhãn người chụp. Có **5 tên thuốc, 13 ảnh `o`, 6 ảnh `x`**; toàn bộ 19 ảnh giải mã được ở 3024×3024 và không có SHA-256 trùng nhau. Kết quả máy đọc được nằm trong `inventory.csv` và `inventory-summary.json` (chỉ lưu cục bộ, không đẩy ảnh/metadata này lên GitHub). Tạo lại bằng:

```bash
.venv/bin/python model/scripts/inventory_camera_captures.py
```

Nhãn trong inventory được **đọc từ tên file**, chưa phải manifest huấn luyện/đánh giá đã khóa. `split` vẫn là `unassigned` vì chưa có ánh xạ đầy đủ ảnh nào thuộc cùng viên vật lý và cùng phiên chụp. Ảnh chụp trên giấy ô ly và mặt bàn gỗ với ánh sáng/góc khác nhau; khi bổ sung dữ liệu cần chụp cả `o` và `x` trong cùng các điều kiện để tránh học nhầm nền. Không dùng 19 ảnh này để báo độ chính xác của máy hoặc để mở cổng `ACCEPTED`.

Chẩn đoán YOLOv7 CPU ở ngưỡng demo 0,25: **17 ảnh một hộp, 2 ảnh hai hộp**. Hai ảnh `betahistin24at_x_08/09` cho thấy một viên bị tách thành hai mảnh; detector đặt hộp lên từng mảnh. Logic hiện tại sẽ dừng ở `MULTIPLE_PILLS`, không thả. Đây là kiểm tra số hộp, **không phải độ chính xác detector** vì chưa có nhãn box đối chiếu. Tạo lại kết quả cục bộ `pilot-detector-results.json` bằng:

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/replay_camera_pilot_detector_cpu.py
```

Sau các thí nghiệm nhận diện ngày 27/10, [kế hoạch thu và đánh giá ảnh camera](../../model/reports/recognition-camera-evaluation-plan.md) nêu các cặp gần giống cần chú ý, cách giữ ID thuốc lạ chưa thấy, và cách tính số lần thử độc lập. Dùng kế hoạch đó trước khi chia tập ảnh thật.

## Chuẩn bị

1. Chọn các thuốc thật máy sẽ thử và đặt mã ổn định cho từng loại. Điền danh sách vào `model/configs/recognition/camera-known-drugs.json` bằng cách sao chép [`camera-known-drugs.template.json`](../../model/configs/recognition/camera-known-drugs.template.json). `known_drug_ids` phải có ít nhất một mã thật đã đối chiếu, không sao chép ID VAIPE.
2. Chụp ảnh vào `data/captured/images/<capture_session_id>/<sample_id>.jpg` bằng đúng camera, khoảng cách, buồng và cơ cấu của máy. Giữ một viên trong vùng nhận diện mỗi khung hình. Ghi `camera_id` và `lighting_id`; nếu đổi phơi sáng, cân bằng trắng, nguồn sáng hay vị trí camera, dùng mã điều kiện mới. Chụp cả hai mặt khi có thể, nhất là chữ, số và rãnh; giữ cùng `pill_instance_id` cho các góc của cùng viên.
3. Sao chép [`manifest.template.csv`](manifest.template.csv) thành `manifest.csv`, mỗi ảnh một hàng. Ban đầu dùng `split=unassigned`. Khi đủ nhiều phiên chụp độc lập, chia **theo `capture_session_id`**, giữ mọi ảnh của cùng `pill_instance_id` trong một split. Danh tính thuốc lạ dùng làm âm khi train phải khác toàn bộ danh tính thuốc lạ ở validation/test.

| Cột | Ý nghĩa |
|---|---|
| `sample_id`, `image_path` | Mã ảnh duy nhất và đường dẫn tương đối trong `data/captured/` |
| `capture_session_id` | Một phiên chụp độc lập; toàn bộ phiên ở cùng split |
| `pill_instance_id` | Mã **viên vật lý**, giữ nguyên qua nhiều mặt/góc |
| `verified_drug_id` | Danh tính từ nguồn đối chiếu, kể cả thuốc lạ; khác ID VAIPE |
| `target_drug_id` | Thuốc người vận hành chọn cho phép thử; phải thuộc `known_drug_ids` |
| `view` | `front`, `back`, `edge`, `other` |
| `condition` | `normal`, `defective`, `unknown`; nhánh nhận diện đầu tiên nên có `normal` rõ ràng |
| `identity_evidence_ref` | Mã bao bì/lô hoặc tham chiếu hồ sơ đối chiếu; không ghi dữ liệu bệnh nhân |
| `camera_id`, `lighting_id` | Mã thiết lập chụp để phát hiện thay đổi điều kiện |
| `split` | `unassigned`, `train`, `validation`, `test` |

## Kiểm tra trên CPU

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/validate_camera_manifest.py \
  --manifest data/captured/manifest.csv \
  --known-config model/configs/recognition/camera-known-drugs.json
```

Script kiểm tra ảnh đọc được, đường dẫn nằm trong `data/captured/`, cột bắt buộc, trùng SHA-256, rò rỉ phiên chụp/viên vật lý giữa split và **ID thuốc lạ xuất hiện ở hơn một split**. Kết quả nằm ở `model/reports/camera-data-audit.json`; có lỗi thì lệnh trả exit code 1. Các ảnh `unassigned` không được đưa vào đánh giá. Với ảnh pilot hiện tại, chỉ có inventory từ tên file; chưa thể chạy validator manifest đầy đủ cho đến khi ghi `capture_session_id`, `pill_instance_id`, mã tham chiếu bao bì/lô, camera và ánh sáng cho từng ảnh.

Sau khi có đủ ảnh, khóa tập test mới và không dùng nó để chỉnh model/ngưỡng. Đánh giá tỷ lệ nhận đúng **từng thuốc**, thuốc khác lọt vào `ACCEPTED`, ảnh mờ/che khuất bị chuyển `WRONG_DRUG`, và đo cả detector lẫn cơ cấu dừng trước khi thả.
