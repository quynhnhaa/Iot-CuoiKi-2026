# Chạy thử pipeline AI bằng CPU — 27/10/2026

## Mục tiêu

Kiểm tra giao diện và thứ tự xử lý từ ảnh đến quyết định trước khi có camera/viên thật. Hai cổng an toàn chưa đạt: verifier danh tính VAIPE vẫn cho lọt thuốc khác, mô hình lỗi bỏ sót 17/43 viên sứt trên pillQC. Do đó bản này **không cấp lệnh thả** và **không tăng bộ đếm**, bất kể điểm mô hình.

## Cách chạy

- Ba ảnh từ validation VAIPE: hai ảnh một viên (`VAIPE_P_306_0`, `VAIPE_P_102_14`) và một ảnh hai viên (`VAIPE_P_1027_0`). Thuốc mục tiêu của lần phát lại là ID hình ảnh 91; ID này không xác nhận hoạt chất thuốc thật.
- Một ảnh xám trống 640×640 **giả lập** để đi qua nhánh không có viên.
- YOLOv7 một lớp `pill` chạy CPU ở 640 px, NMS IoU 0,45, lọc score 0,25 chỉ cho demo. Với đúng một hộp, crop thêm 10% lề, đưa qua FGVC-PIM 7 lớp, verifier và EfficientNetV2-S lỗi.
- Cổng `identity_verified` cố định `False`; score verifier và xác suất defect chỉ để ghi log. Logic quyết định chạy qua `decision_simulator.py`, `identity_gate_validated=False`, `hardware_ready=False`. Không có mã gửi lệnh động cơ.
- Checkpoint được nạp bằng `weights_only=True` và allowlist kiểu dữ liệu giới hạn. YOLOv7 chạy worker riêng vì mã YOLOv7 và FGVC-PIM cùng đặt tên package `models`.

## Kết quả bốn ảnh

| Ảnh | Hộp YOLOv7 | Nhánh đã chạy | Quyết định | Thời gian toàn lượt trên CPU |
|---|---:|---|---|---:|
| `VAIPE_P_306_0` | 1 | PIM dự đoán ID 91; defect chạy | `WRONG_DRUG`: danh tính chưa được xác minh an toàn | 528 ms |
| `VAIPE_P_102_14` | 1 | PIM dự đoán ID 89; defect chạy | `WRONG_DRUG`: danh tính chưa được xác minh an toàn | 384 ms |
| `VAIPE_P_1027_0` | 2 | Bỏ qua PIM/defect | `MULTIPLE_PILLS` | 307 ms |
| Ảnh xám trống giả lập | 0 | Bỏ qua PIM/defect | `EMPTY_FRAME` | 181 ms |

**0 lệnh thả, 0 tăng bộ đếm.** Bất biến này được kiểm tra từ `events.jsonl`, cùng [16 kiểm thử quyết định](../tests/common/test_decision_simulator.py) đã đạt. Với ảnh một viên, detector preprocess/inference/NMS khoảng 132–208 ms, PIM 68–71 ms, defect 25–30 ms trong lượt bốn ảnh này. Thời gian tổng còn gồm đọc ảnh hai lần ở hai tiến trình và giao tiếp nội bộ; không gồm khởi tạo model. Mẫu quá nhỏ để suy ra phân phối độ trễ, và không phải benchmark Raspberry Pi 4.

## Giới hạn và bước sau

Đây là **replay ảnh VAIPE đã dùng trong nghiên cứu**, không phải phép đo accuracy mới. Xác suất defect trên VAIPE không có nhãn chất lượng để đối chiếu. Frame trống là ảnh nhân tạo. Ngưỡng YOLO score 0,25 chưa được hiệu chỉnh cho cơ cấu; điểm verifier lịch sử không được dùng để quyết định vì vấn đề ngữ nghĩa nhãn 107. `image_usable` hiện chỉ nghĩa là ảnh đọc được, chưa có bộ kiểm tra mờ/che khuất của camera.

Run chính: [events.jsonl](../runs/pipeline/validation_model_replay_with_empty_cpu_20261027/events.jsonl), [summary.json](../runs/pipeline/validation_model_replay_with_empty_cpu_20261027/summary.json), [run-manifest.json](../runs/pipeline/validation_model_replay_with_empty_cpu_20261027/run-manifest.json). Có thêm run dùng JSON hộp YOLOv7 đã xuất để đối chiếu; số hộp và route của ba ảnh VAIPE khớp run detector thật, nhưng thời gian tra JSON không được tính là suy luận.

Bước thiếu để tiến tới máy thật: chụp và gán nhãn viên từ đúng camera/buồng chụp, đánh giá độc lập cả nhận diện/open-set lẫn lỗi, sau đó đo độ trễ và cảm biến xác nhận rơi trên Raspberry Pi/cơ cấu. Giữ `ACCEPTED` tự động tắt cho đến khi hai cổng và phần cứng qua kiểm tra.
