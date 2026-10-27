# Data foundation summary

## Source audit
- VAIPE: 9502 original images and labels. The original source has 1 truncated JPEG and 25 labels with out-of-bounds boxes. All 26 affected source files match Kaggle dataset version 1 byte for byte.
- Both image and label from each invalid pair are excluded from processed splits. The source under `data/external/` is unchanged.
- PharmaVision: 640 images, balanced by class in train (380), validation (60), and test (200); no unreadable images or duplicate SHA-256 groups.

## Processed VAIPE split
- Valid image-label pairs: 9476; excluded pairs: 26.
- train: 6633 images, 829 groups, 21103 boxes.
- validation: 1421 images, 172 groups, 5794 boxes.
- test: 1422 images, 172 groups, 5810 boxes.
- Group leakage: none. Seed: 20261025. Split version: group split over valid pairs with ratios 70/15/15.
- Excluded pair paths and reasons: `data/processed/vaipe/excluded-invalid-pairs.csv`.

## Approved recognition classes (first benchmark)
The user approved the following seven IDs for the first recognition benchmark on 2026-10-25. They occur in all splits and were reviewed using crops from distinct groups (`model/reports/vaipe-demo-contact-sheet.jpg`). The machine-readable list is `model/configs/recognition/selected-classes.json`. These visual IDs do not prove chemical identity.

| Class ID | Boxes | Train | Validation | Test | Visual note |
|---:|---:|---:|---:|---:|---|
| 64 | 2597 | 1831 | 352 | 414 | dark round |
| 91 | 1344 | 763 | 382 | 199 | pink oblong |
| 89 | 1611 | 842 | 374 | 395 | white oblong, similar to 99 |
| 99 | 880 | 367 | 243 | 270 | white oblong, similar to 89 |
| 51 | 1008 | 597 | 230 | 181 | light round, similar to 46 |
| 46 | 507 | 375 | 52 | 80 | light round, similar to 51 |
| 10 | 1653 | 1012 | 313 | 328 | red and yellow capsule |

Class 107 is excluded from the selected recognition classes because it is the VAIPE **out-of-prescription context label**, not one fixed pill identity; its representative crops are visually heterogeneous. It must also be excluded from appearance-based unknown-class evaluation unless the underlying pill identity is verified separately. See [the CPU VAIPE correction](recognition-vaipe-solution-review-cpu-20261027.md). IDs 89/99 and 51/46 are intentional near-lookalike pairs. Open-set evaluation must use held-out unknown identities; these seven are the known classes for the first benchmark.

## Gate and next step
- Data gate for one-class `pill` detector: passed for the 9,476 valid matched pairs. Train only from the processed split; the original manifest still records all 9,502 source images.
- Recognition class selection: approved for the first benchmark (IDs 64, 91, 89, 99, 51, 46, 10).
- The three-class hardware demo still needs images taken with its actual camera and lighting for domain-shift evaluation.
- First planned model after this gate: YOLOv7 one-class `pill`.

## YOLOv7 detector export
- Prepared one-class `pill` labels at `data/processed/vaipe/yolov7/`; each exported image is a relative symlink to its original, and each label is a new TXT in the matching split.
- Dataset configuration: `data/processed/vaipe/yolov7/pill.yaml`. Export counts: train 6,633 images / 21,103 boxes; validation 1,421 / 5,794; test 1,422 / 5,810.
- All 9,476 image links and label files were checked; the four EXIF orientations sampled matched OpenCV dimensions, and representative converted boxes were reviewed in `model/reports/vaipe-yolov7-label-preview.jpg`.
- Training has not started. The current Python environment has no PyTorch installation; set up a compatible environment and verify YOLOv7 dependencies before launching a run.

## Detector baseline in progress
- YOLOv7 official source commit `a207844b1ce82d204ab36d87d496728d3d2348e7`, with three local compatibility edits recorded by `git diff` in `model/vendor/yolov7/`.
- PyTorch 2.11.0+cu128 was verified on the RTX 5060 Ti (SM 12.0). The official `yolov7_training.pt` checkpoint initializes the model.
- Smoke run completed one train/validation epoch on 16/8 images and wrote checkpoints under `model/runs/detector/smoke_fixed_20261025/`. Its metrics are only a pipeline check, not a model-quality estimate.
- The 30-epoch baseline is running in the background under `model/runs/detector/yolov7_pill_baseline_20261025_v2/`; train uses 6,633 images, validation uses 1,421, and the 1,422-image test split remains untouched.
- Run command: `model/scripts/train_yolov7_detector.sh`. Progress: `console.log`; process ID: `pid`; settings and versions: `run-manifest.json` and `pip-freeze.txt`.

- Hướng dẫn dựng lại môi trường và tùy chọn CPU/CUDA: `model/DETECTOR-SETUP.md`; các phiên bản phụ thuộc: `model/requirements-detector.txt`; patch YOLOv7: `model/patches/yolov7-compat.patch`.

- Resume: `model/scripts/train_yolov7_detector.sh --resume RUN_DIR --device auto`; checkpoint được kiểm tra epoch, optimizer, EMA và LR trước khi chạy. Chi tiết và giới hạn ở `model/DETECTOR-SETUP.md`.
