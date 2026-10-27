# Kế hoạch dữ liệu camera để tiếp tục nhận diện

*Lập ngày 27/10/2026 từ kết quả [nghiên cứu nhận diện](recognition-autonomous-research-20261027.md). Cập nhật 28/10: đã có 19 ảnh điện thoại pilot trong `data/captured`, chưa có ảnh từ camera/buồng chụp dự kiến của máy.*

## Vì sao cần ảnh mới

Ứng viên tốt nhất trên VAIPE vẫn từ chối 28/28 ROI ID 46 và nhận nhầm 11/1.916 ROI thuốc lạ thuộc năm nhóm ảnh. Các lỗi tập trung ở viên nang hai màu và viên tròn sáng có dấu khắc mờ. Ảnh VAIPE không chứng minh được danh tính hoạt chất hoặc điều kiện chụp của máy. Nghiên cứu [ePillID](https://arxiv.org/abs/2005.14288) phân biệt hai mặt viên trong benchmark; nghiên cứu [nhận diện có đọc dấu khắc](https://www.jmir.org/2023/1/e41043/) cho thấy dấu khắc có thể bổ sung tín hiệu khi hình dạng/màu gần nhau. Đây là lý do thu cả hai mặt, không phải bảo đảm thuật toán sẽ nhận đúng.

## Cách thu và chia

1. Xác định **mã thuốc thật** mà máy phải nhận và thuốc lạ gần giống. Ghi mã bao bì/lô hoặc nguồn xác nhận danh tính vào `identity_evidence_ref`; không gán ID VAIPE thành tên thuốc thật.
2. Dùng đúng camera, ống kính, độ cao, khay, ánh sáng, phơi sáng và cơ cấu trước khi thả. Chụp riêng từng viên vật lý; nếu có thể chụp cả hai mặt, ghi cùng `pill_instance_id`, khác `view`. Ghi ảnh mờ, khuất, chồng viên như ca phải từ chối.
3. Chụp ở nhiều **phiên độc lập** và nhiều viên vật lý; thay đổi có chủ đích các điều kiện mà máy thật có thể gặp. Giữ toàn bộ ảnh của cùng viên và cùng phiên trong một split. Giữ **danh tính thuốc lạ** của tập đánh giá cuối ngoài train và calibration.
4. Điền [`manifest.template.csv`](../../data/captured/manifest.template.csv), sau đó chạy [`validate_camera_manifest.py`](../scripts/validate_camera_manifest.py). Chỉ chuyển `split` từ `unassigned` sau khi lập danh sách phiên và ID thuốc lạ; khóa tập test trước khi chọn mô hình hoặc ngưỡng.

## Hai giai đoạn đo

| Giai đoạn | Mục đích | Đầu ra cần xem |
|---|---|---|
| Pilot | Kiểm tra vùng chụp, nét, mặt viên, ánh sáng và danh tính nhãn; tìm cặp gần giống, đặc biệt viên tròn sáng và nang đỏ/vàng | Tỷ lệ ROI detector ghép đúng, confusion matrix từng thuốc, ảnh lỗi, tỷ lệ `WRONG_DRUG` |
| Đánh giá khóa | Chạy cấu hình đã chọn trên **phiên, viên vật lý và ID thuốc lạ chưa dùng để chỉnh** | Known đúng được thả theo từng thuốc, known sai được thả, unknown được thả, quyết định ảnh mờ, thời gian dừng trước cơ cấu |

Nếu mục tiêu vận hành là tỷ lệ thuốc lạ được thả dưới 1%, ngay cả trong giả định các quyết định độc lập, **0 lỗi trong 299 lần thử thuốc lạ** mới cho cận trên một phía 95% khoảng 1%. Các ảnh liên tiếp của cùng viên hoặc cùng phiên **không** tạo ra 299 phép thử độc lập; cần nhiều ID, viên vật lý và phiên. Đây là mốc thiết kế phép đo, chưa phải tiêu chí an toàn cuối cùng được nhóm chốt.

Cho đến khi có kết quả trên dữ liệu camera và kiểm tra phần cứng, mọi ảnh không đủ chắc chắn phải dừng trước khi thả và đi theo `WRONG_DRUG` để người vận hành kiểm tra.
