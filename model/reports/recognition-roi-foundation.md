# Nền ROI nhận diện 7 lớp VAIPE

Detector được chọn bằng validation là YOLOv7; xem [benchmark chung](pill-detector-common-benchmark.md). ROI xuất từ checkpoint `best.pt` đã dùng cho test, giữ ba split VAIPE không rò rỉ nhóm. Mỗi hộp YOLO được ghép một-một với nhãn VAIPE bằng IoU ≥ 0,5. Crop thêm lề 10% và giữ độ phân giải gốc; không dùng test trong train hoặc chọn checkpoint.

| Split | Nhãn 7 lớp gốc | Crop khớp detector | Không khớp |
|---|---:|---:|---:|
| Train | 5.787 | 5.782 | 5 |
| Validation | 1.946 | 1.943 | 3 |
| Test | 1.867 | 1.865 | 2 |

Tổng **9.590 crop** đã kiểm tra đọc được; kích thước cạnh ngắn trung vị **499 px** (nhỏ nhất 21 px). Không có group leakage giữa ba split. Mười nhãn không ghép được nằm trong `*-excluded.csv`; không gán sang ROI khác. [Contact sheet](recognition-roi-contact-sheet.jpg) cho thấy ID 89/99 và 51/46 gần giống nhau, đúng với phạm vi lớp được duyệt. ID là nhãn hình ảnh VAIPE, không xác thực hoạt chất thuốc.

Nguồn dữ liệu và báo cáo chi tiết: `data/processed/vaipe/recognition/yolov7_rois/`. Script tái lập: `model/scripts/export_recognition_rois.py`. Nhánh closed-set FGVC-PIM đang huấn luyện trên train và chọn checkpoint bằng macro F1 validation. Open-set và ngưỡng `WRONG_DRUG` chưa được đánh giá.
