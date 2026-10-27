# FGVC-PIM: nhận diện 7 ID VAIPE từ ROI YOLOv7

Run `pim_resnet50_7class_20261026_v2` hoàn thành **20/20 epoch** trong khoảng 33 phút trên RTX 5060 Ti. Chọn `best.pt` theo **macro F1 validation**: epoch **17**, macro F1 **97.72%**, accuracy **98.56%**.

Đánh giá một lần trên **1.865 ROI test** đã ghép detector với nhãn gốc:

| Chỉ số | Kết quả |
|---|---:|
| Macro F1 | **97.79%** |
| Accuracy | **97.75%** |
| ROI có nhãn hợp lệ được detector ghép | 1.865/1.867 |

| ID | F1 test |
|---:|---:|
| 64 | 99.88% |
| 91 | 99.25% |
| 89 | 95.03% |
| 99 | 93.99% |
| 51 | 98.88% |
| 46 | 97.53% |
| 10 | 100.00% |

Nhầm lẫn đáng chú ý: **30 ROI của ID 89 bị dự đoán thành ID 99**, và 4 ROI ID 99 thành ID 89. Đây là cặp viên trắng tương tự nhau. Cặp 51/46 có 3 ROI ID 51 bị đoán thành 46.

**Giới hạn:** Chỉ số trên là closed-set **có điều kiện ROI đã được detector ghép đúng với nhãn ở IoU ≥ 0,5**. Hai viên thuộc bảy lớp mà detector không ghép được không nằm trong 1.865 mẫu test này. Mô hình chưa kiểm tra thuốc lạ, không được dùng xác suất closed-set để tự động `ACCEPTED`. ID VAIPE không xác nhận hoạt chất. Cần làm open-set và đặt ngưỡng `WRONG_DRUG` bằng validation trước khi tích hợp cơ cấu thả.

- [Checkpoint tốt nhất](../runs/recognition/pim_resnet50_7class_20261026_v2/best.pt)
- [Số liệu và confusion matrix](../runs/recognition/pim_resnet50_7class_20261026_v2/test-results.json)
- [Hướng dẫn train/resume](../RECOGNITION-SETUP.md)
