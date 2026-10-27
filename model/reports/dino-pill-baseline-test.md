# DINO/ResNet-50 một lớp `pill` trên VAIPE

Run `dino_pill_baseline_20261025_v5` hoàn thành 12/12 epoch. Chọn `checkpoint_best_regular.pth` theo COCO AP@0.5:0.95 trên validation; checkpoint tốt nhất là epoch **12**. Tập test giữ riêng gồm **1.422 ảnh, 5.810 hộp**; không dùng để chọn checkpoint.

| Tập | COCO AP@0.5 | COCO AP@0.5:0.95 |
|---|---:|---:|
| Validation | 0,9865 | 0,7331 |
| Test | 0,9868 | 0,7147 |

Trên test, COCO AP@0.75 là 0,8448; COCO AR@maxDets100 là 0,817. Số test được đo bằng DINO `main.py --eval` với tập test ánh xạ vào nhánh `val` mà mã nguồn dùng để đánh giá; `log.txt` và `eval.pth` được lưu ở `model/runs/detector/dino_pill_baseline_20261025_v5_test/`.

YOLOv7 baseline có mAP@0.5:0.95 test 0,748 theo bộ đo của YOLOv7; DINO có COCO AP@0.5:0.95 test 0,7147. **Hai con số chưa là so sánh tuyệt đối** vì mã đánh giá, giới hạn detections, ngưỡng và hậu xử lý khác nhau. Muốn chọn detector theo Recall/ROI và tốc độ trên máy thật, cần xuất dự đoán hai model rồi tính cùng một evaluator và cùng chính sách ngưỡng. DINO này train detector từ đầu, chỉ backbone ResNet-50 dùng trọng số ImageNet pretrained.

- [Checkpoint tốt nhất](../runs/detector/dino_pill_baseline_20261025_v5/checkpoint_best_regular.pth)
- [Log test](../runs/detector/dino_pill_baseline_20261025_v5_test.console.log)
