# DINO/ResNet-50 detector: chuẩn bị và resume

Nguồn: IDEA-Research/DINO commit `d84a491d41898b3befd8294d1cf2614661fc0953`. Patch `model/patches/dino-compat.patch` thêm EXIF transpose, lưu checkpoint nguyên tử, nạp checkpoint tương thích PyTorch 2.11 và khôi phục best validation từ `log.txt` khi resume.

## Dữ liệu

```bash
.venv/bin/python model/scripts/export_dino_detection.py
```

Tạo `data/processed/vaipe/dino_coco/` từ đúng VAIPE split đã audit: train 6.633 ảnh/21.103 box; validation 1.421/5.794; test 1.422/5.810. Ảnh là symlink, không sửa dữ liệu gốc. COCO bbox dùng kích thước **sau khi xoay EXIF**, và DINO loader đã vá để xoay ảnh cùng cách. Test giữ kín cho tới khi chọn checkpoint bằng validation.

## Môi trường

Dùng `.venv` PyTorch 2.11.0+cu128 hiện có. Các gói Python bổ sung đã cài: `pycocotools`, `termcolor`, `addict`, `yapf`, `timm`. DINO cần extension `MultiScaleDeformableAttention`. Đã tải `cuda_nvcc-linux-x86_64-12.8.93-archive.tar.xz` từ NVIDIA vào `model/toolchains/cuda-12.8/`, cài `nvidia-cuda-cccl-cu12==12.8.90`, ghép headers/libraries từ các gói NVIDIA trong `.venv`, rồi biên dịch extension cho `sm_120` (RTX 5060 Ti). Patch DINO cũng sửa API PyTorch 2.11 trong mã CUDA và API `yapf`. Smoke test so với bản PyTorch cho float/double đều đạt.

Extension `.so` phải được build lại nếu đổi Python, PyTorch, CUDA hay kiến trúc GPU. Mã nguồn và patch ở `model/vendor/DINO/` và `model/patches/dino-compat.patch`. Lệnh build đã dùng (từ gốc dự án):

```bash
project_root="$PWD"
cd model/vendor/DINO/models/dino/ops
nvidia_includes="$(find "$project_root/.venv/lib/python3.12/site-packages/nvidia" -mindepth 2 -maxdepth 2 -type d -name include -printf '%p:' )"
nvidia_libs="$(find "$project_root/.venv/lib/python3.12/site-packages/nvidia" -mindepth 2 -maxdepth 2 -type d -name lib -printf '%p:' )"
CUDA_HOME="$project_root/model/toolchains/cuda-12.8" CPATH="$nvidia_includes$project_root/model/toolchains/cuda-12.8/include" LIBRARY_PATH="$nvidia_libs$project_root/model/toolchains/cuda-12.8/lib64" LD_LIBRARY_PATH="$nvidia_libs$project_root/model/toolchains/cuda-12.8/lib64" TORCH_CUDA_ARCH_LIST='12.0' "$project_root/.venv/bin/python" setup.py build_ext --inplace
```

## Huấn luyện và resume

Cấu hình một lớp `pill`, ResNet-50 4-scale, 12 epoch, batch 1 tại `model/configs/dino_pill_4scale.py`. Run `dino_pill_baseline_20261025_v5` đang train từ đầu (ResNet-50 backbone tải ImageNet pretrained qua torchvision). Vì chưa dùng checkpoint DINO COCO pretrained, đây là baseline train từ đầu cho detector, không so trực tiếp với DINO fine-tune COCO nếu chưa ghi rõ điều kiện khởi tạo.

```bash
model/scripts/train_dino_detector.sh --run-name dino_pill_baseline_01 --device cuda --dry-run
model/scripts/train_dino_detector.sh --run-name dino_pill_baseline_01 --device cuda
model/scripts/train_dino_detector.sh --resume model/runs/detector/dino_pill_baseline_01 --device cuda
```

Script từ chối train khi extension chưa có. Resume đọc `checkpoint.pth`, kiểm tra đủ model/optimizer/lr_scheduler/epoch, xác nhận LR của optimizer khớp scheduler, khóa cấu hình bằng SHA-256 và giữ nguyên batch, tổng epoch, seed và thiết bị. DINO chỉ lưu cuối epoch: nếu dừng giữa epoch, batch của epoch đó chạy lại. RNG và AMP scaler chưa được lưu, nên resume đúng epoch/LR/optimizer nhưng không bảo đảm tái lập từng bit. Checkpoint ghi qua `.tmp` rồi thay thế nguyên tử.
