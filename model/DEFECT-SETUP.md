# PharmaVision `normal/defective` — chạy bằng CPU

## Dữ liệu và môi trường

- Manifest: `data/processed/pharmavision/manifest.csv`. Giữ split gốc: train 380, validation 60, test 200; mỗi split cân bằng `normal/defective`.
- Python: `.venv/bin/python`. Script cần `torch`, `torchvision`, `numpy`, `Pillow`; không cần CUDA hoặc `scikit-learn`.
- Trọng số ImageNet: `model/checkpoints/resnet50_imagenet1k_v1.pth` và `model/checkpoints/efficientnet_v2_s_imagenet1k_v1.pth`. Trọng số EfficientNetV2-S lấy từ `https://download.pytorch.org/models/efficientnet_v2_s-dd5fe13b.pth`.
- Tiền xử lý cố định theo backbone: sửa EXIF, RGB, resize và center crop, chuẩn hóa ImageNet. Không augmentation ở validation/test.

## Chạy lại

Từ thư mục gốc dự án:

```bash
.venv/bin/python -u model/scripts/train_pharmavision_cpu_baseline.py \
  --backbone resnet50 --run-name resnet50_frozen_cpu_20261027 \
  --threads 8 --batch-size 16

.venv/bin/python -u model/scripts/train_pharmavision_cpu_baseline.py \
  --backbone efficientnet_v2_s --run-name efficientnetv2s_frozen_cpu_20261027 \
  --threads 8 --batch-size 8
```

Thêm `--evaluate-test` **sau khi đã chốt lựa chọn trên validation**. Hai run ngày 27/10 đã được đánh giá test; chạy lại sẽ đọc kết quả test đã lưu, không đánh giá lại. Để thử cấu hình mới, dùng tên run mới và ghi rõ giao thức trước khi mở test.

Script dùng `torch.set_num_threads`; GPU không được sử dụng. Mỗi lô đặc trưng được ghi atomically vào `*-features.npz`. Chạy lại cùng lệnh sẽ tiếp tục từ số ảnh đã trích; `config.json` kiểm tra SHA-256 manifest và trọng số để không trộn dữ liệu khác. Đầu logistic dùng LBFGS xác định, không có epoch/LR scheduler cần khôi phục. Kết quả nằm trong `result.json`; `model-selection-20261027.json` lưu quyết định **trước** test.

## Giới hạn

Đây là baseline **đóng băng backbone, chỉ học đầu phân loại**, chưa phải fine-tune toàn bộ EfficientNetV2-S theo giao thức của bài báo. Tập PharmaVision nhỏ; split test chỉ đo trên miền công bố. Chưa có ảnh từ buồng chụp thật nên không dùng các ngưỡng này để điều khiển cơ cấu thả. Nếu điểm `normal/defective` không chắc chắn, logic hệ thống đưa viên vào `DEFECTIVE`.

## Fine-tune CPU trên train/validation

Lượt sau baseline cập nhật **hai block cuối** và classifier của EfficientNetV2-S tại 224 px, dùng train 380 ảnh và validation 60 ảnh; không đọc test. Tăng cường train: lật ngang/dọc, xoay tối đa 12°, thay sáng/tương phản tối đa 7%. Validation dùng ảnh gốc. Ngưỡng cố định 0,40; chọn checkpoint theo F2 lỗi rồi Recall lỗi.

```bash
.venv/bin/python -u model/scripts/finetune_pharmavision_cpu.py \
  --run-name efficientnetv2s_finalblocks_cpu_20261027 --threads 8
```

Nếu tiến trình bị ngắt giữa chừng, kiểm tra không còn tiến trình đang chạy cùng run, rồi:

```bash
.venv/bin/python -u model/scripts/finetune_pharmavision_cpu.py \
  --resume model/runs/defect/efficientnetv2s_finalblocks_cpu_20261027 --threads 8
```

Checkpoint `last.pt` chứa model, optimizer, scheduler, RNG Python/NumPy/Torch, best metric và số epoch không cải thiện. Resume bắt đầu từ epoch sau checkpoint và kiểm tra LR optimizer bằng LR scheduler. Nếu bị ngắt giữa epoch, epoch đó chạy lại từ đầu; `metrics.jsonl` chỉ ghi epoch hoàn tất. `best.pt` chứa checkpoint đạt validation tốt nhất. Run ngày 27/10 đã hoàn tất ở epoch 18 (dừng sớm), best epoch 12, nên không cần resume.

Đã kiểm thử resume bằng một run tạm bắt đầu từ checkpoint epoch 12: epoch 13 khởi động với LR `3,7725725642960056e-5`; toàn bộ bản ghi epoch 13–18 khớp chính xác run gốc. Thư mục run tạm đã được xóa sau đối chiếu.

Đây là fine-tune một phần phù hợp CPU, không tương đương giao thức full fine-tune 384 px của tác giả. Báo cáo: [defect-pharmavision-cpu-finetune-20261027.md](reports/defect-pharmavision-cpu-finetune-20261027.md).

## Đánh giá pillQC trên miền ảnh mới

Tải pillQC từ `https://github.com/matlab-deep-learning/pillQC` vào `data/external/pillQC`, kiểm tra commit `9c0a8ecdca0a3797e784412de077a30ae2c50b3c`. Script chặn ghi đè kết quả đã có, giữ checkpoint epoch 12/ngưỡng 0,40:

```bash
.venv/bin/python -u model/scripts/evaluate_pillqc_domain_shift.py
```

Kết quả gồm `summary.json`, `predictions.csv`, `errors.csv` và contact sheet ở `model/reports/defect-pillqc-cross-domain-20261027/`. Kết quả chạy ngày 27/10: Recall `chip` **26/43**, bỏ sót **17/43**. Xem [báo cáo chuyển miền](reports/defect-pillqc-cross-domain-20261027.md). Không chỉnh mô hình/ngưỡng bằng pillQC đã mở.
