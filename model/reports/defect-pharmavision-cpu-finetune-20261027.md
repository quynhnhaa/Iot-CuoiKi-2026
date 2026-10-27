# Fine-tune CPU nhánh viên lỗi — 27/10/2026

## Lý do và kiểm tra lỗi ban đầu

Baseline ResNet-50 đóng băng nhận 30/30 viên lỗi validation nhưng báo nhầm 24/30 viên bình thường. EfficientNetV2-S đóng băng nhận 29/30 viên lỗi và báo nhầm 19/30 viên bình thường. Ảnh sai và điểm số validation được xuất ở [defect-validation-audit](defect-validation-audit/errors.csv); contact sheet cho [ResNet-50](defect-validation-audit/resnet50_frozen_cpu_20261027.jpg) và [EfficientNetV2-S](defect-validation-audit/efficientnetv2s_frozen_cpu_20261027.jpg). Nhiều ảnh bình thường màu xanh/trắng bị đánh dấu lỗi. Mẫu lỗi duy nhất EfficientNetV2-S bỏ sót trên validation là viên xám có vết sứt nhỏ. Nhận xét này dựa trên quan sát ảnh, chưa chứng minh nguyên nhân thống kê.

## Giao thức lượt mới

- Split PharmaVision gốc: **380 train, 60 validation**; **không đọc 200 ảnh test** đã mở trong lượt baseline.
- EfficientNetV2-S ImageNet1K V1; đóng băng các block đầu, fine-tune block 6–7 và classifier bằng CPU, ảnh 224 px, batch 8, AdamW, learning rate 1e-4 với epoch đầu 1e-5, cosine decay, weight decay 1e-4.
- Tăng cường nhẹ chỉ ở train: lật, xoay ±12°, brightness/contrast ±7%. Validation cố định ngưỡng 0,40 theo giao thức nghiên cứu, không dò ngưỡng trên 60 ảnh. Chọn checkpoint theo F2 lớp `defective`, sau đó Recall/Precision. Tối đa 20 epoch, dừng khi 6 epoch không cải thiện.
- Checkpoint mỗi epoch lưu model, optimizer, scheduler, RNG và kiểm tra LR khi resume. File: `model/runs/defect/efficientnetv2s_finalblocks_cpu_20261027/`.

## Kết quả validation

| Mô hình | Epoch | Recall lỗi | Precision lỗi | F2 lỗi | Ma trận `[[TN,FP],[FN,TP]]` |
|---|---:|---:|---:|---:|---|
| EfficientNetV2-S đóng băng, baseline | — | 29/30 = 96,67% | 60,42% | 86,31% | `[[11,19],[1,29]]` |
| **EfficientNetV2-S fine-tune block cuối** | **12/18** | **30/30 = 100%** | **78,95%** | **94,94%** | **`[[22,8],[0,30]]`** |

Checkpoint tốt nhất ở epoch 12; dừng sớm sau epoch 18. So với baseline cùng backbone, validation có thêm 1 viên lỗi được phát hiện và giảm 11 viên bình thường bị báo nhầm. File `best.pt` mang epoch 12, `last.pt` mang epoch 18; LR optimizer và scheduler trong `last.pt` đều là `2,7091379149682626e-6`.

Đã nạp lại `best.pt` và tái tính metric validation, khớp báo cáo. Kiểm thử resume từ checkpoint epoch 12 trong run tạm cho kết quả epoch 13–18 **trùng chính xác từng bản ghi** với run gốc, gồm learning rate, loss và metric; run tạm đã được xóa.

Đây chỉ là cải thiện **trên validation nhỏ đã dùng để chọn checkpoint**. Không có số liệu test mới độc lập cho mô hình fine-tune. Không chọn lại ngưỡng hoặc checkpoint bằng test đã xem, và không đưa mô hình này vào cơ cấu thả. Cần ảnh camera/buồng chụp thật được gán nhãn độc lập để kiểm tra Recall lỗi và tỷ lệ loại nhầm trong điều kiện vận hành.

## Tái lập

Script: [finetune_pharmavision_cpu.py](../scripts/finetune_pharmavision_cpu.py). Lệnh chạy và resume: [DEFECT-SETUP.md](../DEFECT-SETUP.md). Giao thức nguồn tham khảo: [mã PharmaVision của tác giả](https://github.com/tahirlee/pharmaceutical-tablet-defect-detection); lượt này chỉ fine-tune block cuối ở 224 px để phù hợp CPU, không nhận là tái lập kết quả full fine-tune của bài báo.
