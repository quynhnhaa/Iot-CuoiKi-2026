# Chạy thử pipeline AI bằng CPU, không điều khiển cơ cấu

Script `model/scripts/replay_ai_pipeline_cpu.py` phát lại ảnh VAIPE validation qua YOLOv7 → crop ROI → FGVC-PIM → verifier (chỉ để chẩn đoán) → EfficientNetV2-S defect → bộ quyết định. Mọi kết quả nhận diện đều bị chặn ở `identity_verified=False` vì cổng open-set chưa đạt. Không có giao tiếp động cơ, cảm biến hoặc bộ đếm thật.

## Lệnh chạy

Từ thư mục gốc dự án, trong `.venv` đã dùng cho detector/recognition:

```bash
.venv/bin/python -u model/scripts/replay_ai_pipeline_cpu.py \
  --live-detector --include-empty-frame \
  --run-name validation_model_replay_with_empty_cpu_20261027 \
  --target-id 91 \
  --image-id VAIPE_P_306_0 \
  --image-id VAIPE_P_102_14 \
  --image-id VAIPE_P_1027_0 \
  --threads 8
```

Dùng tên run khác nếu chạy mới; script từ chối ghi đè. `--image-id` phải thuộc split validation VAIPE. `--include-empty-frame` thêm một ảnh xám trống **giả lập** để kiểm tra nhánh không có viên. Tùy chọn bỏ `--live-detector` để dùng JSON dự đoán YOLOv7 đã xuất; thời gian detector khi đó chỉ là thời gian đọc/tra cứu artifact, không phải suy luận.

Output trong `model/runs/pipeline/<run-name>/`: `run-manifest.json` lưu checksum nguồn, `events.jsonl` lưu từng tầng và lý do từ chối, `summary.json` đếm route, `detector-stderr.log` lưu cảnh báo của worker. Run bốn ảnh ngày 27/10 đã hoàn tất.

## Cách nạp checkpoint và giới hạn thời gian

Checkpoint YOLOv7 kiểu cũ chứa object Python. Cổng kiểm duyệt tự động từ chối cách ép PyTorch tắt `weights_only` vì nạp pickle có thể thực thi mã. Worker `infer_yolov7_cpu_safe.py` chạy tiến trình riêng, chỉ cho phép đúng các lớp YOLOv7/NumPy đã kiểm kê và gọi `torch.load(..., weights_only=True)`. PIM/verifier/defect cũng dùng `weights_only=True` với allowlist NumPy tối thiểu. Tiến trình riêng giải quyết xung đột package `models` giữa YOLOv7 và FGVC-PIM.

Thời gian `detector_model_preprocess_inference_nms` là tính trên worker CPU; `detector_worker_wall` bao gồm đọc ảnh và trao đổi giữa hai tiến trình. `total_from_image_decode` gồm cả việc đọc ảnh hai lần ở hai tiến trình, không gồm thời gian khởi tạo model. Đây không phải latency trên camera hoặc Raspberry Pi 4.

Ngưỡng lọc hộp 0,25 chỉ dùng cho demo theo mặc định YOLOv7; không phải ngưỡng vận hành đã hiệu chỉnh. Ngưỡng verifier lịch sử trong log chỉ là chẩn đoán và **không có quyền mở cổng** vì phép đánh giá VAIPE 107 cũ sai ngữ nghĩa. Xác suất defect trên ảnh VAIPE cũng chỉ là chẩn đoán vì ảnh này không có nhãn chất lượng tương ứng.

Báo cáo: [pipeline-cpu-dry-run-20261027.md](reports/pipeline-cpu-dry-run-20261027.md).
