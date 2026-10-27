# Thử cải thiện thuật toán nhận diện và cổng `WRONG_DRUG` — 27/10/2026

> **Đính chính về nhãn VAIPE 107:** Các phép đo unknown lịch sử trong báo cáo này đã chứa nhãn 107, vốn là “ngoài đơn” theo ngữ cảnh chứ không phải một danh tính viên thuốc lạ. Kết quả này không còn là phép đo an toàn open-set hợp lệ. Xem [đánh giá lại bằng CPU](recognition-vaipe-solution-review-cpu-20261027.md).

## Mục tiêu và dữ liệu

Thử tăng tỷ lệ chấp nhận đúng của bảy ID VAIPE, đặc biệt các ID bị cổng cũ từ chối nhiều, trong khi giữ mục tiêu **unknown false acceptance ≤1% trên nhóm calibration**. Mọi phép thử ở đây chỉ dùng train và validation; **không đọc split test**. PIM gốc, ROI YOLOv7 và bảy ID đã chọn giữ nguyên.

Các bộ xác minh học trên 5.782 ROI known train và 1.601 ROI unknown train thuộc 33 ID **không xuất hiện trong unknown validation**. Validation được tách theo SHA-256(`group_id`): calibration 1.216 known/2.123 unknown; nhóm giữ riêng 727 known/1.710 unknown. Temperature và ngưỡng chỉ chọn bằng calibration. Nhóm giữ riêng đã được xem trong các thí nghiệm trước, nên số liệu này là **so sánh nghiên cứu**, chưa phải test độc lập mới.

## Hai thay đổi đã thử

1. **Verifier theo ID:** bảy đầu sigmoid trên embedding PIM đóng băng. Mỗi ROI known có một ID dương và sáu ID âm; ROI unknown âm cho cả bảy ID. Khi suy luận lấy điểm đầu ứng với ID PIM dự đoán, nhân với xác suất PIM đã calibration rồi so với ngưỡng. Best epoch **9/30** được chọn trên calibration.
2. **PIM fine-tune:** bắt đầu từ checkpoint PIM gốc epoch 17, lấy mẫu cân bằng bảy ID, thêm ArcFace loss trên đặc trưng trước classifier. Chạy **6/6 epoch**, best ở **epoch 4** theo macro F1 validation. Sau đó trích feature mới và huấn luyện lại verifier theo ID trên cùng dữ liệu và quy tắc split; best verifier ở epoch **4/30**.

PIM fine-tune tăng macro F1 closed-set validation từ **97,72% lên 97,88%**. F1 của ID 51 tăng từ 98,25% lên 98,91%, ID 46 từ 92,45% lên 94,34%; ID 89 và 99 giảm nhẹ. Đây chỉ là điểm phân loại bảy lớp đã biết.

## Kết quả cổng từ chối trên nhóm validation giữ riêng

| PIM + verifier | Nhận đúng known | Nhận sai known | Thuốc lạ lọt | Đạt mục tiêu ≤1% trên nhóm này? |
|---|---:|---:|---:|---|
| PIM gốc + verifier theo ID | **39,75%** | 0/727 | **14/1.710 (0,82%)** | Có, trong mẫu này |
| PIM fine-tune + verifier theo ID | 42,78% | 0/727 | **29/1.710 (1,70%)** | Không |

| ID known | PIM gốc: đúng và chấp nhận | PIM fine-tune: đúng và chấp nhận | Tổng ROI |
|---:|---:|---:|---:|
| 64 | 48 | 19 | 113 |
| 91 | 138 | 139 | 155 |
| 89 | 87 | 104 | 142 |
| 99 | 14 | 49 | 151 |
| 51 | 2 | 0 | 100 |
| 46 | 0 | 0 | 28 |
| 10 | 0 | 0 | 38 |

Ngưỡng riêng theo ID cũng được tính như một khảo sát: với PIM gốc, nhóm giữ riêng có 43,33% known được nhận đúng nhưng **39/1.710** unknown lọt; với PIM fine-tune, 40,03% known được nhận đúng và **29/1.710** unknown lọt. ID 46 vẫn **0/28** ở cả hai. Các hàng này không phải chính sách được chọn.

Ảnh đối chiếu [ID 10 và unknown ID 2](recognition-class10-vs-unknown2.jpg) cho thấy cả hai là viên nang hai màu đỏ/vàng hoặc cam/vàng dưới các điều kiện chụp khác nhau. PIM gốc cho xác suất trung vị khoảng **0,9999** trên ID 10 đúng và **0,9998** trên ROI ID 2 bị dự đoán thành 10. Chỉ tăng ngưỡng xác suất không tách được cặp này; nhãn hình ảnh VAIPE không chứng minh hoạt chất.

## Quyết định

**Không thay mô hình đang dùng bằng PIM fine-tune, không bật `ACCEPTED` tự động.** Tăng macro F1 closed-set không chuyển thành cải thiện an toàn open-set: số thuốc lạ lọt tăng và vài ID known vẫn bị từ chối hoàn toàn. Verifier theo ID trên PIM gốc là mốc nghiên cứu tốt hơn bộ từ chối nhị phân cũ về tỷ lệ chấp nhận gộp, nhưng vẫn không đủ để vận hành do độ phủ từng ID rất lệch và vẫn có unknown lọt. Mọi trường hợp không đủ chắc chắn tiếp tục dừng trước khi thả và chuyển `WRONG_DRUG`.

Bước tiếp theo cần dữ liệu từ đúng camera/buồng chụp và danh tính thuốc đã xác minh. Trước khi thử thuật toán khác, cần xem khả năng tách các cặp gần giống bằng màu chuẩn, ảnh nhiều góc hoặc dấu khắc; nếu ảnh đơn không mang đủ thông tin, ngưỡng hay loss mới không thể tự tạo ra bằng chứng nhận diện.

## Tái lập

```bash
.venv/bin/python model/scripts/train_recognition_verifier.py --epochs 30 --device auto
.venv/bin/python model/scripts/finetune_recognition_pim_arcface.py --device auto
.venv/bin/python model/scripts/finetune_recognition_pim_arcface.py --resume --device auto
.venv/bin/python model/scripts/extract_recognition_features.py \
  --checkpoint model/runs/recognition/pim_arcface_balanced_20261027/best.pt \
  --output-dir model/runs/recognition/pim_arcface_features_20261027 \
  --development-only --class-disjoint-unknown-train --device auto
.venv/bin/python model/scripts/train_recognition_verifier.py \
  --feature-dir model/runs/recognition/pim_arcface_features_20261027 \
  --run-name class_conditioned_verifier_pim_arcface_20261027 --epochs 30 --device auto
```

Fine-tune checkpoint lưu model, optimizer, cosine scheduler, AMP scaler và RNG mỗi epoch; đã kiểm tra resume sau khi môi trường dừng giữa epoch 5, tiếp tục đúng LR `5,03767778e-6`. Checkpoint tốt nhất và số liệu: [PIM fine-tune](../runs/recognition/pim_arcface_balanced_20261027/run-manifest.json), [verifier PIM gốc](../runs/recognition/class_conditioned_verifier_20261027/validation-results.json), [verifier PIM fine-tune](../runs/recognition/class_conditioned_verifier_pim_arcface_20261027/validation-results.json). Run khởi động lỗi dtype trước epoch đầu được giữ riêng với hậu tố `_failed_start`.
