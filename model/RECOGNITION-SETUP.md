# Nhận diện 7 ID bằng FGVC-PIM

> **Lưu ý dữ liệu:** Nhãn VAIPE `107` là thuốc ngoài đơn theo ngữ cảnh, không phải một ID ngoại hình thuốc lạ. Các run open-set lịch sử có 107 trong tập unknown đã được [đánh giá lại trên CPU](reports/recognition-vaipe-solution-review-cpu-20261027.md). Khi nghiên cứu tiếp, dùng manifest/feature đã loại 107 và giữ tập test riêng.

## Dữ liệu

Detector ROI được chọn là YOLOv7 sau [benchmark chung](reports/pill-detector-common-benchmark.md). Exporter `model/scripts/export_recognition_rois.py` ghép hộp detector với nhãn gốc VAIPE theo IoU ≥ 0,5, chỉ lấy bảy ID đã duyệt và giữ split theo nhóm. Crop dùng kích thước ảnh sau khi xoay EXIF, thêm lề 10%, lưu ở độ phân giải gốc. Những hộp không khớp được ghi trong `*-excluded.csv` cùng ảnh và nhãn, không được gán sang lớp khác. Train 5.782 crop, validation 1.943, test 1.865; test chỉ dùng đánh giá cuối.

## Mô hình và cách chạy

Trainer `model/scripts/train_recognition_pim.py` dùng mã PIM chính thức ở commit `348edd983d0007a0cbbce65979aa2fbaade068c8`, backbone ResNet-50 khởi tạo từ torchvision ImageNet V1 (`model/checkpoints/resnet50_imagenet1k_v1.pth`, SHA-256 `0676ba61b6795bbe1773cffd859882e5e297624d384b6993f7c9e683e722fb8a`). Ảnh đầu vào 320 px, batch 4, tích lũy gradient 2, 20 epoch, AdamW, cosine LR. Loss giữ các thành phần base/drop/combiner của PIM. Chọn `best.pt` theo **macro F1 trên validation**, đồng thời lưu `last.pt` cuối mỗi epoch.

```bash
.venv/bin/python model/scripts/train_recognition_pim.py --run-name pim_resnet50_7class_20261026_v2 --device cuda --dry-run
.venv/bin/python model/scripts/train_recognition_pim.py --run-name NEW_NAME --device cuda
.venv/bin/python model/scripts/train_recognition_pim.py --resume model/runs/recognition/NEW_NAME --device cuda
```

Không chạy `--resume` khi PID của run còn sống. Checkpoint có model, optimizer, scheduler, AMP scaler, epoch, best macro F1 và RNG của Python/NumPy/PyTorch/CUDA. Script đối chiếu cấu hình, checksum của manifest ROI và backbone, và LR optimizer với scheduler trước khi tiếp tục. Nếu dừng giữa epoch, chỉ phần epoch đó chạy lại từ đầu. File `last.pt` và `best.pt` được ghi qua `.tmp` rồi thay thế nguyên tử.

Đây là **closed-set 7 lớp**. Chưa dùng xác suất của nó làm quyết định `ACCEPTED`; cần hiệu chỉnh open-set trên validation, thêm lớp thuốc lạ và đặt ngưỡng `WRONG_DRUG` sau benchmark nhận diện. ID ảnh là nhãn hình ảnh VAIPE, không xác thực thành phần hóa học.

## Benchmark `WRONG_DRUG` và rejector

Các phép thử và kết quả hiện có ở [open-set](reports/recognition-open-set-benchmark.md), [kiểm tra ảnh lỗi](reports/recognition-error-audit.md) và [rejector có ví dụ âm](reports/recognition-negative-rejector-validation.md). Mọi kết quả hiện tại vẫn **chưa đủ để cho máy tự động thả viên**.

```bash
.venv/bin/python model/scripts/prepare_recognition_unknown.py
.venv/bin/python model/scripts/extract_recognition_features.py --device auto
.venv/bin/python model/scripts/audit_recognition_errors.py
.venv/bin/python model/scripts/train_recognition_rejector.py --unknown-policy class-disjoint --epochs 30 --device auto
```

`--device auto` chọn CUDA nếu có, còn lại CPU. Có thể chỉ định `--device cuda` hoặc `--device cpu`. Feature extractor bỏ qua `.npz` đã tồn tại; khi thay đổi checkpoint hoặc manifest nguồn phải tạo run feature mới, không tái dùng file cũ. Rejector lưu `last.pt` từng epoch với optimizer, RNG và hash dữ liệu; chạy lại cùng lệnh để resume đúng epoch. Đổi số epoch hoặc dữ liệu cần run mới. `class-disjoint` chỉ dùng ID thuốc lạ train không xuất hiện trong validation; đây là chính sách đáng tin hơn `all-train`. Script rejector **không đọc test**.

## Thử cải thiện thuật toán 27/10/2026

Xem [báo cáo verifier theo ID và PIM fine-tune](reports/recognition-algorithm-improvement-20261027.md). Hai run chỉ dùng train/validation, chưa thay checkpoint PIM gốc cho ứng dụng.

```bash
.venv/bin/python model/scripts/train_recognition_verifier.py --epochs 30 --device auto
.venv/bin/python model/scripts/finetune_recognition_pim_arcface.py --device auto
.venv/bin/python model/scripts/finetune_recognition_pim_arcface.py --resume --device auto
```

Fine-tune mặc định dùng run `pim_arcface_balanced_20261027`; `--run-name` chọn run mới khi thư mục chưa tồn tại, còn `--resume` chỉ tiếp tục từ `last.pt` sau epoch hoàn chỉnh. Trình train đối chiếu hash checkpoint gốc, manifest ROI, cấu hình, optimizer LR và scheduler; lưu model, optimizer, scheduler, AMP scaler và RNG. File lock ngăn hai tiến trình cùng ghi một run. Khi bị dừng giữa epoch, epoch đó chạy lại. Feature của checkpoint mới phải đặt ở một output directory mới và dùng `--development-only` để không đọc test.

### Chạy chỉ bằng CPU khi GPU đang bận

Các script nhận diện hỗ trợ `--device cpu`. Dùng `CUDA_VISIBLE_DEVICES=''` để tiến trình không nhìn thấy GPU; `--device auto` sẽ chọn CUDA nếu máy có GPU. Fine-tune mới cần `--run-name` khác run CUDA đã hoàn tất. Resume chính xác chỉ được phép trên cùng loại thiết bị với run lúc tạo.

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/finetune_recognition_pim_arcface.py \
  --run-name pim_arcface_cpu_20261027 --device cpu
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/finetune_recognition_pim_arcface.py \
  --run-name pim_arcface_cpu_20261027 --resume --device cpu

CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/extract_recognition_features.py \
  --checkpoint model/runs/recognition/pim_arcface_cpu_20261027/best.pt \
  --output-dir model/runs/recognition/pim_arcface_cpu_features_20261027 \
  --development-only --class-disjoint-unknown-train --device cpu

CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/train_recognition_verifier.py \
  --feature-dir model/runs/recognition/pim_arcface_cpu_features_20261027 \
  --run-name verifier_pim_arcface_cpu_20261027 --epochs 30 --device cpu
```

Chỉ chạy bước trích feature sau khi fine-tune CPU đã hoàn tất và có `best.pt`. Chạy CPU trên ảnh 320 px sẽ chậm hơn GPU đáng kể; checkpoint và quy tắc chọn theo validation giữ nguyên.

## Kiểm tra ID khó và dữ liệu camera thật

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/audit_recognition_id46_id10.py
```

Kết quả tại [audit ID 46/10](reports/recognition-id46-id10-audit.md) giải thích vì sao cổng hiện từ chối hai ID này. Ảnh camera thật sẽ đi vào `data/captured/`, tách hoàn toàn khỏi VAIPE. Đọc [hướng dẫn chụp và manifest](../data/captured/README.md); điền mã thuốc thật và manifest trước khi chạy `validate_camera_manifest.py`. Validator chỉ dùng CPU và chưa thể chạy trên dữ liệu thật khi thư mục ảnh còn trống.

## Nghiên cứu thêm bằng GPU ngày 27/10/2026

Kết quả và quyết định ở [báo cáo nghiên cứu nhận diện](reports/recognition-autonomous-research-20261027.md). Các run này **chỉ là thí nghiệm**, không thay checkpoint vận hành và không đọc test để chọn model. Đánh giá thuốc lạ mới phải chia theo **ID thuốc lạ**, ngoài việc chia ảnh theo phiên/nhóm.

```bash
.venv/bin/python model/scripts/evaluate_recognition_knn.py --device cuda
.venv/bin/python model/scripts/train_recognition_unknown_head.py --device cuda --epochs 30
.venv/bin/python model/scripts/finetune_recognition_pim_oe.py --device cuda
.venv/bin/python model/scripts/finetune_recognition_pim_oe.py --device cuda --resume
.venv/bin/python model/scripts/extract_recognition_features.py --device cuda \
  --checkpoint model/runs/recognition/pim_resnet50_7class_20261026_v2/best.pt \
  --output-dir model/runs/recognition/pim_multilayer_raw_20261027 \
  --development-only --class-disjoint-unknown-train --extra-layer4
.venv/bin/python model/scripts/build_recognition_multilayer_features.py
.venv/bin/python model/scripts/train_recognition_verifier.py --device cuda --epochs 30 \
  --feature-dir model/runs/recognition/pim_multilayer_features_20261027 \
  --run-name class_conditioned_verifier_multilayer_20261027
.venv/bin/python model/scripts/evaluate_recognition_unseen_ids.py
.venv/bin/python model/scripts/extract_recognition_features.py --device cuda \
  --checkpoint model/runs/recognition/pim_resnet50_7class_20261026_v2/best.pt \
  --output-dir model/runs/recognition/pim_spatial_raw_20261027 \
  --development-only --class-disjoint-unknown-train --extra-layer4 --extra-layer4-std
.venv/bin/python model/scripts/build_recognition_spatial_features.py
.venv/bin/python model/scripts/train_recognition_verifier.py --device cuda --epochs 30 \
  --feature-dir model/runs/recognition/pim_spatial_features_20261027 \
  --run-name class_conditioned_verifier_spatial_20261027
.venv/bin/python model/scripts/evaluate_recognition_unseen_ids.py
```

Các script ghi feature đã có sẽ bỏ qua file cũ; muốn đổi checkpoint/transform thì dùng thư mục output mới. `finetune_recognition_pim_oe.py --resume` khôi phục đúng epoch, optimizer và LR scheduler từ `last.pt`; chuỗi augmentation/ảnh do DataLoader sau khi khởi động lại không được bảo đảm trùng bit với run liền mạch. Run OE hiện đã hoàn tất 4/4 epoch.

DINOv2 ViT-S/14 chính thức được tải vào `model/.cache/torch/hub/checkpoints/`. Script trích xuất yêu cầu source code Torch Hub `facebookresearch_dinov2_main`; dùng `--source` và `--weights` để chỉ đến bản đã tải khi tái lập ở máy khác. Các lệnh dùng cho nhánh này là `extract_recognition_dinov2.py`, `build_recognition_dinov2_features.py`, `train_recognition_dinov2_probe.py` và `train_recognition_verifier.py` với feature directory tương ứng. Checksum trọng số và transform lưu trong `model/runs/recognition/dinov2_vits14_features_20261027/manifest.json`.

## Sửa nhãn 107 và đánh giá có thuốc mục tiêu trên CPU

Tài liệu VAIPE định nghĩa 107 là “ngoài đơn”, nên không dùng nó làm mẫu thuốc lạ có danh tính khác khi tính cổng nhận diện ngoại hình. Giữ manifest/feature cũ để đối chiếu; tạo bản train/validation mới đã loại 107 và chấm lại checkpoint đã có bằng CPU:

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/filter_vaipe_context_unknown.py
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/evaluate_vaipe_target_gate_cpu.py
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 .venv/bin/python model/scripts/train_vaipe_target_logistic_cpu.py
```

Kết quả và giới hạn ở [báo cáo VAIPE CPU](reports/recognition-vaipe-solution-review-cpu-20261027.md). Script không tải hay đọc test; GPU không được sử dụng.
