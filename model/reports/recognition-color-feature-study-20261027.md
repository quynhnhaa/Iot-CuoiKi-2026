# Thử đặc trưng màu cho nhánh nhận diện — 27/10/2026

> **Đính chính về nhãn VAIPE 107:** Phép đo unknown lịch sử của thử nghiệm màu đã chứa nhãn 107 “ngoài đơn” theo ngữ cảnh. Không xem tỷ lệ đó là false acceptance của thuốc lạ có danh tính khác. Xem [đánh giá lại bằng CPU](recognition-vaipe-solution-review-cpu-20261027.md).

## Lý do và cách làm

Audit trước đó cho thấy PIM phân loại đúng toàn bộ 28 ROI ID 46 và 38 ROI ID 10 trong nhóm validation giữ riêng, nhưng verifier từ chối cả hai. Một số thuốc lạ giống ID 10 về hình dạng; vì vậy thử bổ sung thông tin màu để tách chúng. Thí nghiệm chạy trên CPU, không dùng ảnh camera thật.

Giữ embedding PIM gốc 256 chiều; trích 70 đặc trưng HSV và RGB từ vùng elip giữa ROI, chuẩn hóa bằng **train known và train unknown**, rồi ghép thành vector 326 chiều. Train unknown gồm 1.601 ROI từ 33 ID không xuất hiện trong unknown validation. Giữ cách chia nhóm và hiệu chỉnh ngưỡng như verifier gốc. Không dùng test để train hoặc chọn ngưỡng. Các kết quả trên nhóm validation giữ riêng đã được xem nhiều lần nên chỉ dùng để chẩn đoán, không xem là test độc lập mới.

## Kết quả

Trên cùng 727 ROI known và 1.710 ROI unknown của nhóm validation giữ riêng:

| Verifier | Known đúng được chấp nhận | Unknown bị nhận nhầm | ID 46 | ID 10 |
|---|---:|---:|---:|---:|
| PIM gốc | 39,75% | 14/1.710 (0,82%) | 0/28 | 0/38 |
| PIM + màu | 29,30% | 3/1.710 (0,18%) | 0/28 | 0/38 |

Ngưỡng riêng theo lớp chỉ được khảo sát để chẩn đoán: biến thể màu nhận đúng 40,17% known nhưng nhận nhầm 39/1.710 unknown (2,28%). Điều này không giải quyết được yêu cầu an toàn của cổng trước khi thả thuốc.

## Quyết định và bước tiếp

**Không chọn biến thể màu** cho điều khiển máy: giảm thuốc lạ lọt qua nhưng loại thêm 10,45 điểm phần trăm viên đúng, và ID 46/10 vẫn bị từ chối hoàn toàn. Nhánh nhận diện vẫn đang được cải thiện. Bước có giá trị nhất là thu ảnh từ camera, ánh sáng và cơ cấu thật với danh tính thuốc được đối chiếu; dùng một tập mới giữ riêng để đánh giá lại mức chồng lấn giữa thuốc đúng và thuốc lạ. Chưa bật `ACCEPTED` tự động.

## Tái lập

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/build_recognition_color_features.py --workers 4
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/train_recognition_verifier.py \
  --feature-dir model/runs/recognition/pim_color_features_20261027 \
  --run-name class_conditioned_verifier_color_20261027 \
  --epochs 30 --device cpu
```

Đầu ra: `model/runs/recognition/pim_color_features_20261027/manifest.json` và `model/runs/recognition/class_conditioned_verifier_color_20261027/validation-results.json`.
