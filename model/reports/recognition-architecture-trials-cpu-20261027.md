# Thử cải thiện kiến trúc nhận diện trên CPU — 27/10/2026

## Vì sao thử

Cổng PIM gốc theo ID mục tiêu nhận đúng 337/727 ROI của bảy ID ở nhóm ảnh giữ riêng, nhưng vẫn chấp nhận nhầm 24 ROI thuốc lạ thuộc ID chưa có trong nhóm hiệu chỉnh. ID 46 không có ROI nào được nhận. Các lỗi nổi bật: thuốc lạ ID 3 bị đoán thành 89 và ID 2 bị đoán thành 10. Đây là kết quả VAIPE, không phải tỷ lệ an toàn của máy thật. Nhãn VAIPE 107 biểu thị thuốc ngoài đơn theo ngữ cảnh, nên không dùng nó như một danh tính thuốc lạ.

## Hai phép kiểm tra đặc trưng bổ sung

1. [Kiểm tra xoay ảnh](../runs/recognition/rotation_consistency_cpu_20261027/results.json): yêu cầu nhãn PIM không đổi khi xoay ROI 90° và 180°, sau cổng gốc. Cả 903 ROI thuốc đúng và 24 ROI thuốc lạ đã qua cổng gốc đều giữ nguyên nhãn. Kết quả cổng không đổi: 337/727 đúng và 24/1.414 thuốc lạ lọt ở nhóm đánh giá. Không chọn vì không tạo thêm khả năng phân biệt.
2. [Đặc trưng bilinear](../runs/recognition/bilinear_local_cpu_20261027/results.json): lấy covariance của feature map layer4, chiếu cố định 64 chiều, so với 48 ảnh train khác nhóm cho mỗi ID. Cổng yêu cầu ID của centroid bilinear trùng ID mục tiêu. Nó cũng giữ nguyên 337/727 đúng và 24/1.414 thuốc lạ lọt. Biến thể so với ảnh gallery gần nhất loại một mẫu đúng ở nhóm hiệu chỉnh, không loại được thuốc lạ. Không chọn.

Hai thử nghiệm này chỉ **lọc tiếp các ứng viên đã qua cổng gốc**, nên không thể giúp ID 46 vốn đang bị từ chối hoàn toàn.

## Đầu xác minh phi tuyến mới

Đầu tuyến tính theo thuốc mục tiêu đã thử trước đó không đủ khả năng tách các cặp gần giống. Vì vậy, tôi huấn luyện MLP nhỏ `256 → 128 → ReLU → 7` trên embedding PIM đóng băng. Train gồm 5.782 ROI thuộc bảy ID biết trước và 1.601 ROI âm từ 33 ID thuốc **không xuất hiện trong unknown validation**; loại 107. Mỗi đầu dùng binary cross entropy cân hai phía dương/âm; AdamW 40 epoch, seed 20261027, CPU. Cổng vẫn đòi PIM dự đoán đúng ID mục tiêu, nhân xác suất PIM với xác suất đầu mới. Ngưỡng từng mục tiêu chọn trên phần hiệu chỉnh để có 0 ROI known sai và 0 ROI thuốc lạ được nhận tại đó; không dùng test.

| ID mục tiêu | Cổng gốc: đúng / thuốc lạ lọt | MLP: đúng / thuốc lạ lọt |
|---:|---:|---:|
| 64 | 70/113 · 0 | 73/113 · 0 |
| 91 | 135/155 · 0 | 137/155 · 0 |
| 89 | 114/142 · 17 | 114/142 · 17 |
| 99 | 7/151 · 1 | 33/151 · 5 |
| 51 | 1/100 · 0 | 4/100 · 0 |
| 46 | 0/28 · 0 | 0/28 · 0 |
| 10 | 10/38 · 6 | 7/38 · 3 |
| **Gộp bảy tình huống mục tiêu** | **337/727 · 24** | **368/727 · 25** |

Mẫu thuốc lạ được dùng lại trong bảy tình huống mục tiêu giả định; số 24/25 là tổng trường hợp được nhận sai, không phải tỷ lệ của một mẻ có một ID mục tiêu. MLP cải thiện độ phủ của một số ID nhưng **không cải thiện đồng thời độ phủ và nhận nhầm thuốc lạ**. ID 89 và 46 vẫn là điểm nghẽn. Không chọn MLP làm cổng vận hành và không ghép chọn từng ID theo nhóm đánh giá đã xem.

## Giới hạn và quyết định

Toàn bộ validation VAIPE này đã được xem ở các lượt nghiên cứu trước. Kết quả là chẩn đoán, không phải kiểm chứng độc lập. Chưa có ảnh từ camera/buồng chụp thật và danh tính thuốc thật đã đối chiếu; ảnh một mặt có thể thiếu dấu khắc hoặc thông tin đủ phân biệt. Không thay checkpoint/cổng điều khiển, không mở `ACCEPTED`; trường hợp danh tính không chắc phải dừng trước khi thả với `WRONG_DRUG`.

Tiếp theo cần thu ảnh viên thật theo [quy trình camera](recognition-camera-evaluation-plan.md), có các cặp gần giống và cả hai mặt khi khả thi; khóa trước tập đánh giá tách theo viên vật lý, phiên chụp và ID thuốc lạ. Chỉ khi có phép đo độc lập mới đánh giá model/kiến trúc và ngưỡng cho từng thuốc thật.

## Tái lập

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 .venv/bin/python model/scripts/evaluate_recognition_rotation_consistency_cpu.py
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 .venv/bin/python model/scripts/evaluate_recognition_bilinear_cpu.py
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 .venv/bin/python model/scripts/train_vaipe_target_mlp_cpu.py
```

Kết quả MLP và checkpoint nghiên cứu: [`validation-results.json`](../runs/recognition/vaipe_target_mlp_cpu_20261027/validation-results.json), [`model.pt`](../runs/recognition/vaipe_target_mlp_cpu_20261027/model.pt). Không dùng GPU hay test trong ba phép thử.
