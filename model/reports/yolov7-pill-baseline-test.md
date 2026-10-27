# Kết quả YOLOv7 một lớp `pill` trên VAIPE

- Run: `yolov7_pill_baseline_20261025_v2`; hoàn thành 30/30 epoch.
- Chọn `best.pt` theo fitness trên validation (0,1 × mAP@0.5 + 0,9 × mAP@0.5:0.95); epoch tốt nhất: **29**.
- Tập test giữ riêng: **1.422 ảnh, 5.810 hộp nhãn**, không dùng khi train hoặc chọn checkpoint.
- Đánh giá bằng `model/vendor/yolov7/test.py --task test --img-size 640 --batch-size 8 --device 0 --no-trace`; mặc định `conf_thres=0.001`, `iou_thres=0.65`.

| Tập | Precision | Recall | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|
| Validation, epoch 29 | 0,9953 | 0,9959 | 0,9976 | 0,7734 |
| Test, `best.pt` | 0,996 | 0,997 | 0,997 | 0,748 |

YOLOv7 in các số test đến 3 chữ số thập phân. mAP@0.5:0.95 của test thấp hơn validation **0,0254** (2,54 điểm phần trăm). Đây là metric **phát hiện hộp viên thuốc** trên VAIPE, chưa phản ánh nhận diện ID thuốc, phát hiện viên lỗi, hay độ chính xác trên camera/máng thực tế.

- Checkpoint: `model/runs/detector/yolov7_pill_baseline_20261025_v2/weights/best.pt`
- Log test: `model/runs/detector/yolov7_pill_baseline_20261025_v2/test-console.log`
- Ảnh kiểm tra và biểu đồ: `model/runs/detector/yolov7_pill_baseline_20261025_v2_test/`
