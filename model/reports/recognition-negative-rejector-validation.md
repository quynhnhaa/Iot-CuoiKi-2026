# Thử bộ từ chối thuốc lạ có học từ ví dụ âm

> **Đính chính về nhãn VAIPE 107:** Báo cáo lịch sử này đã tính nhãn 107 như một loại thuốc lạ; thực tế đây là nhãn ngoài đơn theo ngữ cảnh và có thể gồm viên thuộc ID đã biết. Hai ROI “unknown” lọt ở ngưỡng chung đều mang nhãn 107, nên không được diễn giải là hai danh tính thuốc lạ đã xác minh. Xem [đánh giá lại bằng CPU](recognition-vaipe-solution-review-cpu-20261027.md).

## Lý do và thiết kế

[Kiểm tra ảnh lỗi](recognition-error-audit.md) cho thấy xác suất và cosine của một số thuốc lạ gần 1,0; ID 107 rất đa dạng ngoại hình. Vì vậy thử một MLP nhỏ trên **embedding PIM đóng băng** để ước lượng mức “giống tập bảy ID đã chọn”. Điểm cổng = xác suất lớp cao nhất của PIM sau temperature scaling × điểm MLP. Lớp dự đoán vẫn phải trùng ID đang chọn trên máy; kết quả dưới đây chỉ đo cổng thị giác, chưa đo máy thật.

Nguồn known train: 5.782 ROI. Nguồn unknown train có 15.302 ROI từ 96 ID; thử hai chính sách:

1. **All-train:** dùng toàn bộ unknown train. Nhiều ID unknown cũng xuất hiện ở validation, nên phép thử này đo thuốc lạ **đã thấy dưới dạng âm**.
2. **Class-disjoint:** chỉ dùng **1.601 ROI thuộc 33 ID không có trong unknown validation** làm âm. Cả 68 ID unknown validation chưa từng dùng huấn luyện bộ từ chối. Đây là phép thử chính cho khả năng gặp ID lạ mới.

Validation được tách bằng parity của SHA-256(`group_id`): calibration gồm 1.216 known và 2.123 unknown; phần giữ riêng gồm 727 known và 1.710 unknown. Temperature, epoch tốt nhất và ngưỡng được chọn **chỉ trên calibration**. Mục tiêu ngưỡng: nhận nhầm unknown trên calibration ≤1%. Baseline SupCon cũ được chọn lại ngưỡng trên **cùng calibration** để so sánh công bằng. Split test VAIPE không được script thí nghiệm này đọc; test cũ đã từng được xem để chẩn đoán và không còn là phép thử mới độc lập cho thay đổi này.

Giới hạn của phép so sánh: trọng số SupCon cũ đã được chọn trong benchmark trước bằng **toàn bộ validation**. Do đó hàng baseline cùng nhóm chỉ là mốc tham chiếu, không phải đối chứng hoàn toàn độc lập với phần validation giữ riêng. Thí nghiệm MLP class-disjoint chọn epoch và ngưỡng chỉ từ nhóm calibration của lần này.

## Kết quả trên nhóm validation giữ riêng

| Cổng | Nhận đúng known | Nhận sai known | Nhận nhầm unknown |
|---|---:|---:|---:|
| SupCon cũ, chọn ngưỡng lại trên calibration | 9,90% | 0/727 | 13/1.710 (0,76%) |
| MLP, all-train unknown | 28,61% | 0/727 | 9/1.710 (0,53%) |
| **MLP, class-disjoint unknown, một ngưỡng chung** | **25,03%** | 0/727 | **2/1.710 (0,12%)** |
| MLP class-disjoint, ngưỡng theo lớp | 36,31% | 0/727 | 17/1.710 (0,99%) |

Best checkpoint class-disjoint ở **epoch 27/30** theo AUROC known/unknown trên calibration. Temperature từ calibration là **1,1351**. Với một ngưỡng chung **0,97367**, chỉ có hai ROI unknown lọt qua: cả hai mang ID 107 và bị dự đoán là 64. Tuy nhiên tỷ lệ nhận known theo lớp rất lệch:

| ID known | Đúng và được nhận / tổng ROI held-out, ngưỡng chung | Ngưỡng theo lớp |
|---:|---:|---:|
| 64 | 47/113 | 8/113 |
| 91 | 116/155 | 117/155 |
| 89 | 19/142 | 101/142 |
| 99 | 0/151 | 5/151 |
| 51 | 0/100 | 23/100 |
| 46 | 0/28 | 0/28 |
| 10 | 0/38 | 10/38 |

Ngưỡng theo lớp cải thiện tỷ lệ gộp nhưng vẫn thất bại ở ID 46 và gần như loại hết ID 99/64. Đây là phép khảo sát sau khi xem kết quả ngưỡng chung; **không dùng hàng này để công bố hiệu năng chọn mô hình độc lập**.

## Quyết định

**Chưa tích hợp để tự động thả viên.** Thử nghiệm cho thấy dữ liệu thuốc lạ làm ví dụ âm giúp cải thiện cổng từ chối, kể cả khi ID âm train không trùng ID validation. Tuy nhiên hai ROI lạ vẫn lọt qua ngưỡng chung, mức chấp nhận known thấp và không đều giữa bảy lớp. Không thể xem 0 lỗi known trong mẫu validation là bảo đảm an toàn. ID hình ảnh VAIPE không xác nhận hoạt chất, và dữ liệu camera/buồng chụp thực tế chưa có.

Bước kỹ thuật tiếp theo là cải thiện biểu diễn ảnh của các lớp 89/99, 51/46 và đánh giá theo từng lớp; cần một tập ảnh mới độc lập từ camera thật trước khi khóa quy tắc `ACCEPTED`/`WRONG_DRUG` cho máy. Các mẫu unknown đã lọt ngưỡng và ảnh audit cần dùng để tìm nguyên nhân, không dùng để chỉnh lại ngưỡng trên phần giữ riêng này.

## Tái lập

```bash
.venv/bin/python model/scripts/prepare_recognition_unknown.py
.venv/bin/python model/scripts/extract_recognition_features.py --device auto
.venv/bin/python model/scripts/train_recognition_rejector.py --unknown-policy class-disjoint --epochs 30 --device auto
```

Trainer lưu `last.pt` từng epoch với optimizer và RNG để resume đúng epoch; `best.pt` chọn theo AUROC calibration. Feature train unknown đã lưu trong `open_set_features_20261026`, nên lệnh trích sẽ bỏ qua file đã có. Kết quả chi tiết: [`validation-results.json`](../runs/recognition/negative_rejector_class_disjoint_20261026/validation-results.json), [`heldout-validation-predictions.csv`](../runs/recognition/negative_rejector_class_disjoint_20261026/heldout-validation-predictions.csv). Run all-train được giữ riêng ở [`negative_rejector_20261026`](../runs/recognition/negative_rejector_20261026/validation-results.json).
