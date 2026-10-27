# Model nhận diện loại viên và phát hiện lỗi

## Tài liệu kiến trúc

- [Kiến trúc hệ thống AI kiểm tra viên thuốc](KIEN-TRUC-HE-THONG-AI.md)
- [Kế hoạch triển khai chặng nền dữ liệu](KE-HOACH-TRIEN-KHAI-AI.md)
- [Báo cáo tổng hợp kết quả AI](reports/BAO-CAO-TIEN-DO-AI.md)
- [Nhật ký làm việc AI](reports/NHAT-KY-LAM-VIEC-AI.md)

## Chạy lại detector YOLOv7

Xem [hướng dẫn dựng môi trường và chọn CUDA/CPU](DETECTOR-SETUP.md). Lệnh train hỗ trợ `--device auto`, `--device cuda` và `--device cpu`; chạy `scripts/train_yolov7_detector.sh --help` để xem toàn bộ tham số, kể cả `--resume` để tiếp tục một run bị ngắt.

## Cấu trúc

- `configs/recognition/`: cấu hình các biến thể nhận diện viên có đúng loại được chọn cho mẻ hay không.
- `configs/defect/`: cấu hình các biến thể phát hiện viên nguyên, sứt hoặc vỡ.
- `src/common/`: đọc dữ liệu, tiền xử lý và đo lường dùng chung.
- `src/recognition/`, `src/defect/`: mã của từng bài toán; các mô hình khác nhau nằm trong từng nhánh này.
- `scripts/`: lệnh chuẩn bị dữ liệu, huấn luyện, đánh giá và chạy thử khi bắt đầu viết mã.
- `runs/recognition/`, `runs/defect/`: kết quả **từng lần chạy**; mỗi lần chạy tạo một thư mục riêng gồm cấu hình đã dùng, log, chỉ số, dự đoán và trọng số. Không ghi đè lần chạy cũ.
- `reports/`: bảng so sánh các lần thử trên cùng bộ kiểm tra.

## Quy ước thử nghiệm

Đặt tên lần chạy, ví dụ `runs/recognition/2026-10-24_mobilenetv3_v1/`. Lưu bản cấu hình, phiên bản dữ liệu/split, seed, metric và checkpoint vào cùng thư mục. Đánh giá các biến thể trên **cùng tập test**; không chọn mô hình bằng kết quả test. Trọng số lớn và dữ liệu không nên commit lên Git.

Đường dữ liệu dùng chung: `../data/`. VAIPE và PharmaVision đã được tải vào `../data/external/`; dữ liệu gốc được giữ ở chế độ chỉ đọc trong quá trình chuẩn bị manifest và split.
