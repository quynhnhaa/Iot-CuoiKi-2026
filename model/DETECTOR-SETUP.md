# Dựng lại môi trường YOLOv7 detector

Tài liệu này ghi đúng môi trường dùng cho baseline ngày 2026-10-25. Detector chỉ có một lớp `pill`; các ID thuốc được dùng ở nhánh nhận diện riêng. Dữ liệu gốc nằm trong `data/external/` và không được ghi đè.

## 1. Điều kiện và phiên bản

- Linux x86_64, Python 3.12.3; GPU baseline: NVIDIA RTX 5060 Ti (compute capability 12.0), driver 595.91.07.
- PyTorch 2.11.0 và torchvision 0.26.0. Dùng bản `+cu128` trên máy có CUDA phù hợp, hoặc `+cpu` trên máy không có CUDA.
- Các thư viện còn lại được ghim trong `model/requirements-detector.txt`. Toàn bộ bản cài của lần baseline GPU nằm trong `model/runs/detector/yolov7_pill_baseline_20261025_v2/pip-freeze.txt`.
- YOLOv7 chính thức tại commit `a207844b1ce82d204ab36d87d496728d3d2348e7`. Các sửa đổi tương thích NumPy/đường dẫn và hỗ trợ resume được lưu trong `model/patches/yolov7-compat.patch`.
- Checkpoint huấn luyện gốc `yolov7_training.pt` từ [release YOLOv7 v0.1](https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7_training.pt), SHA-256: `54c0651ef2d866584f9dcdcbd2a60c9f8fb0ee9e444af3dfd67b8c1e023f75f4`.

## 2. Tạo môi trường ảo

Chạy từ thư mục gốc của dự án:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

Chọn **một** trong hai lệnh PyTorch:

```bash
# Máy có NVIDIA CUDA phù hợp:
.venv/bin/python -m pip install 'torch==2.11.0+cu128' 'torchvision==0.26.0+cu128' --index-url https://download.pytorch.org/whl/cu128

# Máy không dùng CUDA:
.venv/bin/python -m pip install 'torch==2.11.0+cpu' 'torchvision==0.26.0+cpu' --index-url https://download.pytorch.org/whl/cpu
```

Sau đó cài các phụ thuộc còn lại:

```bash
.venv/bin/python -m pip install -r model/requirements-detector.txt
.venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
```

Đừng cài trực tiếp `model/vendor/yolov7/requirements.txt`: tệp upstream ghim NumPy `<1.24`, không phù hợp với môi trường Python/NumPy đã kiểm tra ở đây. `requirements-detector.txt` và patch là cấu hình của đồ án.

## 3. Mã YOLOv7 và checkpoint

Nếu `model/vendor/yolov7/` chưa có, lấy mã chính thức rồi áp dụng patch:

```bash
git clone https://github.com/WongKinYiu/yolov7.git model/vendor/yolov7
git -C model/vendor/yolov7 checkout --detach a207844b1ce82d204ab36d87d496728d3d2348e7
git -C model/vendor/yolov7 apply ../../patches/yolov7-compat.patch
```

Nếu repo đã có, kiểm tra `git -C model/vendor/yolov7 rev-parse HEAD` và `git -C model/vendor/yolov7 diff` trước khi áp dụng patch để tránh áp dụng hai lần. Tải checkpoint vào `model/checkpoints/` rồi kiểm tra checksum:

```bash
mkdir -p model/checkpoints
curl -L --fail -o model/checkpoints/yolov7_training.pt https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7_training.pt
printf '%s  %s\n' '54c0651ef2d866584f9dcdcbd2a60c9f8fb0ee9e444af3dfd67b8c1e023f75f4' 'model/checkpoints/yolov7_training.pt' | sha256sum -c -
```

YOLOv7 lưu cả đối tượng Python trong checkpoint cũ. Script train đặt `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` để PyTorch tải checkpoint này. Chỉ dùng checkpoint đã kiểm tra từ nguồn tin cậy; đừng dùng tùy tiện với tệp `.pt` khác.

## 4. Chuẩn bị dữ liệu

Bộ VAIPE đã audit và chia nhóm được xuất bằng:

```bash
.venv/bin/python model/scripts/export_yolov7_detection.py
```

Lệnh tạo `data/processed/vaipe/yolov7/pill.yaml`, liên kết ảnh gốc trong `images/` và tạo TXT một lớp trong `labels/`. Nếu chuyển dự án sang thư mục khác, **chạy lại lệnh này** để cập nhật đường dẫn tuyệt đối trong `pill.yaml`. Nó cần các split ở `data/processed/vaipe/splits/` và danh sách cặp bị loại ở `data/processed/vaipe/excluded-invalid-pairs.csv`.

## 5. Chọn CUDA hoặc CPU khi train

```bash
# Tự chọn CUDA nếu PyTorch dùng được; nếu không thì CPU:
model/scripts/train_yolov7_detector.sh --device auto --dry-run

# Bắt buộc CUDA; lỗi rõ ràng nếu GPU không dùng được:
model/scripts/train_yolov7_detector.sh --device cuda --dry-run

# Bắt buộc CPU, kể cả trên máy có GPU:
model/scripts/train_yolov7_detector.sh --device cpu --dry-run
```

Bỏ `--dry-run` để chạy thật. Ví dụ:

```bash
model/scripts/train_yolov7_detector.sh --device cuda --epochs 30 --batch-size 8 --run-name yolov7_pill_cuda_01
model/scripts/train_yolov7_detector.sh --device cpu --epochs 1 --batch-size 1 --workers 0 --run-name yolov7_pill_cpu_smoke
```

Mặc định: 30 epoch, ảnh 640 px; batch 8/workers 4 trên CUDA, batch 1/workers 0 trên CPU. CPU dùng được về chức năng nhưng train toàn bộ 30 epoch sẽ lâu hơn nhiều. Mỗi lệnh tạo thư mục chạy mới trong `model/runs/detector/`; script từ chối ghi đè thư mục đã tồn tại.

Baseline GPU đang chạy được khởi động bằng phiên bản script trước khi có tùy chọn `--device`; lệnh và bản cài chính xác đã lưu trong `model/runs/detector/yolov7_pill_baseline_20261025_v2/`.

## 6. Chạy tiếp sau khi bị ngắt

Nếu tiến trình đã dừng **trước khi hoàn thành** toàn bộ epoch, dùng thư mục của chính run đó:

```bash
model/scripts/train_yolov7_detector.sh --resume model/runs/detector/yolov7_pill_baseline_20261025_v2 --device auto --dry-run
model/scripts/train_yolov7_detector.sh --resume model/runs/detector/yolov7_pill_baseline_20261025_v2 --device auto
```

Lệnh dùng `weights/last.pt` và `opt.yaml`/`hyp.yaml` của run cũ. Trước khi chạy, `check_yolov7_resume.py` kiểm tra checkpoint còn optimizer và EMA, đọc `epoch`, rồi đối chiếu LR đã lưu với lịch cosine hoặc linear của run. Script **không cho thay đổi** `--epochs`, `--batch-size`, `--workers`, `--img-size` hay `--run-name` khi resume. `--device auto|cuda|cpu` được phép đổi thiết bị; mã YOLOv7 đã vá giữ lựa chọn thiết bị từ lệnh mới, còn lịch và batch gốc được nạp từ `opt.yaml`. Run đang hoạt động bị chặn resume song song.

Checkpoint được lưu **cuối mỗi epoch**. Nếu bị ngắt giữa epoch, các batch của epoch đó sẽ chạy lại từ đầu; epoch trước đó, trọng số, EMA, optimizer và LR được nạp lại. YOLOv7 tái tạo scheduler từ cấu hình đã lưu và đặt `last_epoch = start_epoch - 1`; đây là tiếp tục đúng mốc epoch/LR, nhưng **không phải tái lập từng bit** vì trạng thái bộ sinh số ngẫu nhiên và AMP GradScaler không được lưu. Sau khi run hoàn thành bình thường, YOLOv7 bỏ optimizer khỏi `last.pt`/`best.pt`, nên chúng dùng để suy luận hoặc fine-tune mới, không dùng để resume cùng run.

Patch hiện tại còn ghi `last.pt` qua tệp tạm rồi thay thế nguyên tử, để lần lưu bị ngắt không làm hỏng checkpoint trước đó. Tiến trình baseline đã khởi chạy trước khi bổ sung patch này nên không nhận thay đổi đó giữa chừng.
