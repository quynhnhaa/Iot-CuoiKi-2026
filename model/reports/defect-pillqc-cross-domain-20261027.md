# Đánh giá chuyển miền pillQC và luồng quyết định — 27/10/2026

## Vì sao làm

Fine-tune EfficientNetV2-S đạt 30/30 viên lỗi trên validation PharmaVision, nhưng validation chỉ có 60 ảnh và đã dùng để chọn checkpoint. Chưa có ảnh từ buồng chụp thật. Vì vậy dùng một bộ công khai khác để kiểm tra khả năng nhận diện lỗi trên miền mới, với checkpoint/ngưỡng giữ nguyên, và kiểm thử riêng quy tắc dừng trước khi thả bằng dữ liệu giả lập.

## Giao thức pillQC

- Nguồn: [pillQC chính thức](https://github.com/matlab-deep-learning/pillQC), commit `9c0a8ecdca0a3797e784412de077a30ae2c50b3c`. Bộ dữ liệu có 43 `chip`, 149 `normal`, 138 `dirt`.
- Phép đo chính dùng **43 `chip` → defective** và **149 `normal` → normal**. Loại `dirt` vì [giao thức đối chiếu PharmaVision](https://github.com/tahirlee/pharmaceutical-tablet-defect-detection) chỉ đánh giá lỗi sứt cùng khái niệm với lớp lỗi được huấn luyện. Kết quả không đo khả năng phát hiện bụi/bẩn.
- Kiểm tra tất cả ảnh đọc được, 192 ảnh đánh giá không trùng SHA-256 nội bộ và không trùng SHA-256 với manifest PharmaVision.
- Checkpoint `efficientnetv2s_finalblocks_cpu_20261027/best.pt`, epoch 12, ngưỡng **0,40** đã chốt trên PharmaVision. CPU, resize cạnh ngắn 224, center crop 224, chuẩn hóa ImageNet. **Không fine-tune, không chọn lại ngưỡng và không dùng pillQC để chọn checkpoint.**

## Kết quả

| Chỉ số | pillQC |
|---|---:|
| Recall lỗi `chip` | **26/43 = 60,47%** |
| Viên sứt bị nhận thành bình thường | **17/43 = 39,53%** |
| Precision lỗi | 26/28 = 92,86% |
| F2 lỗi | 65,00% |
| Viên bình thường bị báo lỗi | 2/149 = 1,34% |
| Ma trận `[[TN,FP],[FN,TP]]` | `[[147,2],[17,26]]` |

So với validation PharmaVision (30/30 lỗi, F2 94,94%), Recall lỗi giảm mạnh trên pillQC. Ảnh [contact sheet lỗi](defect-pillqc-cross-domain-20261027/errors.jpg) cho thấy một số viên sứt rõ vẫn được dự đoán là bình thường. Đây là bằng chứng mô hình hiện **không đáng tin để điều khiển thả viên trên miền ảnh mới**. pillQC chỉ có một sản phẩm, một kiểu lỗi `chip` và một cấu hình chụp nên cũng không thay thế được ảnh buồng chụp thật.

Chi tiết từng ảnh: [predictions.csv](defect-pillqc-cross-domain-20261027/predictions.csv), [errors.csv](defect-pillqc-cross-domain-20261027/errors.csv), [summary.json](defect-pillqc-cross-domain-20261027/summary.json). Script chỉ cho phép tạo kết quả một lần và từ chối ghi đè: [evaluate_pillqc_domain_shift.py](../scripts/evaluate_pillqc_domain_shift.py).

## Kiểm thử luồng quyết định giả lập

Thêm [decision_simulator.py](../src/common/decision_simulator.py) làm hàm thuần, không gửi lệnh cơ cấu. Mặc định `identity_gate_validated=False` và `hardware_ready=False`, vì nhánh nhận diện chưa đạt và cơ cấu chưa được xác minh. Trạng thái ảnh không tin cậy/ID không chắc/không khớp thuốc mục tiêu đều trả `WRONG_DRUG`, `release_allowed=False`; không có viên hoặc nhiều viên đều giữ lại. Lỗi chưa chắc chuyển nhánh `DEFECTIVE` nhưng vẫn giữ lại để xem xét. Chỉ trường hợp được xác minh và phần cứng sẵn sàng mới có thể đủ điều kiện release; bộ đếm vẫn chờ cảm biến xác nhận rơi.

Chạy `model/tests/common/test_decision_simulator.py`: **16/16 ca đạt**. Đây là kiểm thử logic thuần, chưa kiểm thử camera, cảm biến, động cơ hay độ trễ end-to-end.

## Quyết định sau đánh giá

Giữ mô hình defect ở trạng thái **nghiên cứu**, không bật `ACCEPTED` tự động. Không hạ ngưỡng theo pillQC vì bộ này vừa được dùng để đánh giá độc lập. Bước tiếp theo cần ảnh/viên thật từ buồng chụp của máy và nhãn lỗi được kiểm chứng; nếu chưa có, có thể hoàn thiện giao diện dữ liệu và mô phỏng phần cứng nhưng không tuyên bố an toàn vận hành.
