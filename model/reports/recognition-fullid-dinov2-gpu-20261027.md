# Fine-tune DINOv2 ViT-S/14 phân loại toàn bộ ID (GPU, 27/10/2026)

Script: `scripts/train_fullid_dinov2_gpu.py` (CosFace m=0.2, 12 epoch, 224 px, lấy mẫu cân bằng theo ID, trọng số DINOv2 chính thức trên máy). Giao thức đánh giá như [báo cáo sửa VAIPE](recognition-vaipe-solution-review-cpu-20261027.md): bỏ 107, ngưỡng chọn trên calibration với FAR ≤ 1%, báo trên 727 known và 1.414 unknown thuộc ID chưa thấy. Không đọc test.

| Lần chạy | Tập âm khi train | Điểm | Known nhận đúng | Unknown lọt |
|---|---|---|---:|---:|
| Cổng gốc (mốc) | — | verifier | 55,57% | 26 |
| 1 | 7 ID mục tiêu + ID thuốc lạ của calibration | cos margin | 96,97% | 224 |
| 1 | như trên | cos target | 93,12% | 127 |
| 1, ngưỡng đặt trên phía đánh giá (chỉ chẩn đoán) | như trên | cos margin | 70,3% | 14 |
| 2 (`--strict`) | 33 ID không thuộc validation | cos margin | 48,56% | 32 |
| 2 (`--strict`) | như trên | p toàn ID | 20,08% | 15 |

Độ chính xác closed-set của 7 ID là 98,76% ở cả hai lần chạy. ID 46/10 lần đầu được nhận nhiều (25/28, 38/38 ở lần 1).

**Kết luận:** lần 1 có ngưỡng bị lỏng vì các ID thuốc lạ dùng để chỉnh ngưỡng đã được học làm âm. Khi giao thức chặt (lần 2), kết quả không vượt cổng gốc. Không thay cổng vận hành.

**Hàm ý cho demo:** model tách rất tốt những loại thuốc lạ **đã có trong train**. Máy demo chỉ dùng 1–2 loại viên lạ biết trước, nên cần chụp ảnh chính các viên lạ đó và đưa vào làm lớp âm. Khi đó cần đo lại trên ảnh camera của các phiên chụp tách riêng.
