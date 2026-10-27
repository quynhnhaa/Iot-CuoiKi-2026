# Baseline CPU kiểm tra viên lỗi trên PharmaVision — 27/10/2026

## Vì sao làm bước này

Nhận diện loại thuốc còn cho lọt thuốc ngoài danh sách, trong khi chưa có ảnh camera thật để đánh giá độc lập. Nhánh `normal/defective` của kiến trúc có dữ liệu PharmaVision đã qua audit nhưng chưa có mô hình. Vì vậy chạy hai baseline có trọng số ImageNet sẵn/được tải chính thức để đo mức khả thi trên CPU, không đổi cổng nhận diện hay bật `ACCEPTED`.

## Giao thức

- Giữ split tác giả: **380 train (190/190), 60 validation (30/30), 200 test (100/100)**. Không phát hiện ảnh lỗi hoặc trùng SHA-256 trong audit.
- ResNet-50 và EfficientNetV2-S ImageNet1K V1, backbone đóng băng. Trích đặc trưng ảnh sau EXIF transpose và tiền xử lý ImageNet; học đầu logistic với `C` trong `{0.01, 0.1, 1, 10}`.
- Chọn `C` và ngưỡng theo **F2 lớp defective** trên validation. Quyết định chọn giữa hai backbone được ghi trong `model/runs/defect/model-selection-20261027.json` **trước khi đánh giá test của EfficientNetV2-S**: ưu tiên Recall defective, rồi F2. ResNet-50 được chọn vì validation nhận 30/30 viên lỗi, còn EfficientNetV2-S nhận 29/30; F2 chỉ lệch khoảng 0,001.
- Test chỉ dùng với cấu hình đã khóa. Ma trận nhầm lẫn có hàng nhãn thật `[normal, defective]`, cột dự đoán `[normal, defective]`.

| Backbone | Split | Ngưỡng | Recall lỗi | Precision lỗi | F2 lỗi | Ma trận nhầm lẫn |
|---|---|---:|---:|---:|---:|---|
| ResNet-50 | Validation | 0,12078 | 100% (30/30) | 55,56% | 86,21% | `[[6,24],[0,30]]` |
| EfficientNetV2-S | Validation | 0,16797 | 96,67% (29/30) | 60,42% | 86,31% | `[[11,19],[1,29]]` |
| **ResNet-50 được chọn** | **Test** | **0,12078** | **96% (96/100)** | **63,16%** | **86,96%** | **`[[44,56],[4,96]]`** |
| EfficientNetV2-S, đối chứng | Test | 0,16797 | 96% (96/100) | 60,76% | 86,02% | `[[38,62],[4,96]]` |

Test xác nhận cả hai vẫn bỏ sót **4/100 viên lỗi**. Ngưỡng thiên về Recall cũng loại nhầm hơn nửa số viên bình thường. Do đó ResNet-50 chỉ là mốc nghiên cứu, **chưa đạt để tự động phân loại/thả viên**. Không chọn lại mô hình hoặc sửa ngưỡng bằng test.

## Kết quả lưu và bước tiếp

- Script: `model/scripts/train_pharmavision_cpu_baseline.py`; hướng dẫn chạy lại: `model/DEFECT-SETUP.md`.
- Run: `model/runs/defect/resnet50_frozen_cpu_20261027/` và `model/runs/defect/efficientnetv2s_frozen_cpu_20261027/`, gồm cấu hình, đặc trưng tiếp tục được, kết quả validation/test và đầu logistic.
- Bước tiếp theo của nhánh lỗi là **fine-tune có kiểm soát trên train/validation hoặc thử phân tích lỗi**, tuyệt đối không chỉnh theo test đã xem. Sau đó cần ảnh camera/buồng chụp thật để đo chuyển miền. Nhánh nhận diện `WRONG_DRUG` vẫn chưa đạt; hai nhánh chưa được ghép để điều khiển máy.

Nguồn giao thức dữ liệu: [bài báo PharmaVision](https://www.mdpi.com/1999-4923/18/10/1287), [mã tác giả](https://github.com/tahirlee/pharmaceutical-tablet-defect-detection).
