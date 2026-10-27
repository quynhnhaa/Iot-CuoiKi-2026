# Ảnh viên thuốc từ camera của máy

Thư mục này hiện **chưa có ảnh camera thật**. Ảnh VAIPE và các ID số 46, 10, v.v. là nhãn hình ảnh nghiên cứu; **không dùng chúng làm tên thuốc thật**. Chỉ đưa ảnh vào đánh giá khi danh tính viên đã được đối chiếu với bao bì/lô hoặc hồ sơ nguồn đáng tin cậy và ghi mã tham chiếu `identity_evidence_ref`. Không lưu thông tin bệnh nhân trong đường dẫn hay manifest.

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

Script kiểm tra ảnh đọc được, đường dẫn nằm trong `data/captured/`, cột bắt buộc, trùng SHA-256, rò rỉ phiên chụp/viên vật lý giữa split và **ID thuốc lạ xuất hiện ở hơn một split**. Kết quả nằm ở `model/reports/camera-data-audit.json`; có lỗi thì lệnh trả exit code 1. Các ảnh `unassigned` không được đưa vào đánh giá. Template chưa có danh tính thuốc hay ảnh nên chưa thể chạy kiểm tra dữ liệu thật.

Sau khi có đủ ảnh, khóa tập test mới và không dùng nó để chỉnh model/ngưỡng. Đánh giá tỷ lệ nhận đúng **từng thuốc**, thuốc khác lọt vào `ACCEPTED`, ảnh mờ/che khuất bị chuyển `WRONG_DRUG`, và đo cả detector lẫn cơ cấu dừng trước khi thả.
