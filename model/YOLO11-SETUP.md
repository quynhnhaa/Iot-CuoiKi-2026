# Thử YOLO11s trên VAIPE

Detector YOLO11s được train một lớp `pill` trên **cùng split VAIPE đã audit** với YOLOv7. Bản chạy chính dùng ảnh 640 px, 30 epoch, batch 8, seed 20261027, pretrained YOLO11s. Ultralytics 8.4.190 và trọng số tải từ [release chính thức](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt). Đây là phép so sánh model/pipeline thực tế; kiến trúc, số tham số và hyperparameter mặc định của hai họ khác nhau.

## Môi trường

Từ gốc dự án, chuẩn bị PyTorch/CUDA như [hướng dẫn detector](DETECTOR-SETUP.md). Trên môi trường hiện tại đã có OpenCV, NumPy, SciPy, Matplotlib, Torch/Torchvision; lượt này thêm:

```bash
.venv/bin/python -m pip install --no-deps 'ultralytics==8.4.190' 'ultralytics-thop==2.2.3'
.venv/bin/python -m pip install 'polars==2.1.0'
```

Môi trường mới có thể cài `ultralytics==8.4.190` với dependency bình thường. Cách `--no-deps` ở trên giữ nguyên các bản thư viện của môi trường YOLOv7 hiện có; smoke test đầu thất bại ở bước lưu checkpoint khi thiếu `polars`, sau khi cài đã chạy hết 1 epoch và lưu được trọng số. File tải về `model/checkpoints/yolo11s.pt` có SHA-256 `85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5`.

## Dữ liệu, train và resume

```bash
.venv/bin/python model/scripts/export_yolov7_detection.py
curl -L --fail -o model/checkpoints/yolo11s.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt
echo '85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5  model/checkpoints/yolo11s.pt' | sha256sum -c -

OMP_NUM_THREADS=4 .venv/bin/python model/scripts/train_yolo11_detector.py \
  --name yolo11s_pill_20261027 --epochs 30 --batch 8 --workers 4 --device cuda
```

Nếu run bị ngắt **sau khi lưu ít nhất một epoch**, chạy lại cùng tham số và thêm `--resume`. Script so manifest nguồn dữ liệu, phiên bản, batch, epoch, seed và file trọng số trước khi gọi resume từ `weights/last.pt`; Ultralytics khôi phục optimizer, lịch learning rate và epoch từ checkpoint. Epoch đang dở chạy lại. Sau khi run hoàn tất, checkpoint có thể bị strip optimizer và không dùng để kéo dài cùng run.

```bash
OMP_NUM_THREADS=4 .venv/bin/python model/scripts/train_yolo11_detector.py \
  --name yolo11s_pill_20261027 --epochs 30 --batch 8 --workers 4 --device cuda --resume
```

`--device auto|cuda|cpu` được hỗ trợ. Trên CPU, 30 epoch toàn bộ 6.633 ảnh sẽ chậm hơn rất nhiều. Run, checkpoint, manifest và log nằm trong `model/runs/detector/` và không đưa lên GitHub.

## So sánh

Chọn `best.pt` bằng validation, sau đó xuất dự đoán và chấm cùng `pycocotools.COCOeval`, bbox IoU 0.50:0.95, maxDets 100; thêm audit TP/FP/FN ở confidence 0,25 chỉ để chẩn đoán. Không dùng test để chọn ngưỡng hay checkpoint.

```bash
.venv/bin/python model/scripts/evaluate_yolo11_detector.py --split validation
.venv/bin/python model/scripts/evaluate_yolo11_detector.py --split test
```

Kết quả được ghi vào `model/runs/detector/yolo11s_pill_20261027/metrics-val.json` và `metrics-test.json`. Báo cáo tổng hợp và nhật ký công việc cập nhật sau khi chạy xong.
