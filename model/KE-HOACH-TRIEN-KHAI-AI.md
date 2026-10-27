# Pill AI Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo nền dữ liệu có thể kiểm chứng cho VAIPE và PharmaVision trước khi huấn luyện bất kỳ mô hình nào.

**Architecture:** Chặng đầu đọc dữ liệu gốc ở chế độ chỉ đọc, chuẩn hóa thành manifest, kiểm tra ảnh–nhãn, tạo split theo nhóm ảnh cùng lần chụp và sinh báo cáo phân bố lớp. Các mô hình detection, recognition/open-set, defect và tích hợp sẽ có kế hoạch riêng sau khi báo cáo này xác định phạm vi dữ liệu thực tế.

**Tech Stack:** Python 3.11+, PyTorch ecosystem, Pillow, pandas, NumPy, scikit-learn, pytest, YAML/JSON.

**Spec:** `model/KIEN-TRUC-HE-THONG-AI.md`

## Global Constraints

- Không sửa, đổi tên hoặc ghi thêm file vào `data/external/`.
- VAIPE `public_test` không có nhãn và không được dùng để chọn mô hình hoặc ngưỡng.
- Các ảnh có cùng mã nhóm `VAIPE_P_<group>_<index>` phải nằm trong cùng một split.
- PharmaVision giữ nguyên split do tác giả công bố.
- Mọi artifact sinh ra đặt trong `data/processed/`; mọi báo cáo đặt trong `model/reports/`.
- Mọi lần chạy phải lưu cấu hình, seed, phiên bản split và thống kê đầu ra.

---

## Phân rã toàn dự án

Sau kế hoạch nền dữ liệu này, dự án được tách thành bốn kế hoạch độc lập:

1. Detector một lớp `pill` và chuẩn hóa ROI.
2. Fine-grained recognition kết hợp open-set recognition.
3. Phân loại `normal/defective` và thử nghiệm anomaly detection.
4. Tối ưu Raspberry Pi 4, tích hợp quyết định ba ô và đo end-to-end.

Chỉ viết kế hoạch huấn luyện cho từng nhánh sau khi hoàn thành báo cáo dữ liệu, vì số mẫu mỗi lớp và độ trùng giữa các nhóm quyết định kiến trúc, augmentation và metric phù hợp.

Mô hình được huấn luyện đầu tiên sau khi qua cổng nền dữ liệu là **YOLOv7 một lớp `pill`**. DINO/ResNet-50 được huấn luyện tiếp theo làm mốc chất lượng cho detector.

### Task 1: Khóa môi trường và kiểm thử đường dẫn dữ liệu

**Files:**
- Create: `model/requirements.txt`
- Create: `model/src/common/paths.py`
- Create: `model/tests/common/test_paths.py`

**Interfaces:**
- Produces: `DatasetPaths.from_project_root(root: Path) -> DatasetPaths`
- Produces: `DatasetPaths.validate() -> list[str]`, trả về danh sách lỗi; danh sách rỗng nghĩa là hợp lệ.

- [ ] **Step 1: Viết test thất bại cho cấu trúc dữ liệu bắt buộc**

Test phải kiểm tra đủ bốn vị trí: VAIPE train image, VAIPE train label, PharmaVision train và PharmaVision test.

- [ ] **Step 2: Chạy test và xác nhận thất bại**

Run: `cd model && pytest tests/common/test_paths.py -v`

Expected: FAIL vì `DatasetPaths` chưa tồn tại.

- [ ] **Step 3: Cài đặt `DatasetPaths` và danh sách dependency**

`paths.py` chỉ giải quyết đường dẫn và kiểm tra tồn tại; không đọc ảnh, không tự tải dữ liệu và không tạo symlink.

- [ ] **Step 4: Chạy test và kiểm tra trên dữ liệu thật**

Run: `cd model && pytest tests/common/test_paths.py -v`

Expected: PASS và không ghi file vào `data/external/`.

### Task 2: Parser nhãn VAIPE có kiểm tra schema

**Files:**
- Create: `model/src/common/vaipe_schema.py`
- Create: `model/tests/common/test_vaipe_schema.py`

**Interfaces:**
- Produces: `PillBox(x: int, y: int, w: int, h: int, label: int)`
- Produces: `parse_vaipe_label(path: Path, image_width: int, image_height: int) -> list[PillBox]`
- Raises: `LabelValidationError` khi thiếu trường, kích thước không dương, label ngoài `[0, 107]` hoặc box vượt ảnh.

- [ ] **Step 1: Viết test cho nhãn hợp lệ, thiếu trường và box vượt ảnh**
- [ ] **Step 2: Chạy test, xác nhận parser chưa tồn tại**
- [ ] **Step 3: Cài đặt dataclass, exception và parser**
- [ ] **Step 4: Chạy toàn bộ test parser**

Run: `cd model && pytest tests/common/test_vaipe_schema.py -v`

Expected: PASS.

### Task 3: Tạo manifest và audit VAIPE

**Files:**
- Create: `model/src/common/image_audit.py`
- Create: `model/scripts/build_vaipe_manifest.py`
- Create: `model/tests/common/test_image_audit.py`
- Generate: `data/processed/vaipe/manifest.csv`
- Generate: `model/reports/vaipe-data-audit.json`
- Generate: `model/reports/vaipe-class-distribution.csv`

**Interfaces:**
- Produces: `audit_image(path: Path) -> ImageAuditResult`
- Produces manifest columns: `image_path,label_path,group_id,image_id,width,height,box_count,labels,is_readable,validation_errors`.

- [ ] **Step 1: Viết test bằng ảnh RGB hợp lệ, file hỏng và ảnh không có nhãn**
- [ ] **Step 2: Chạy test và xác nhận thất bại**
- [ ] **Step 3: Cài đặt audit ảnh và script manifest**
- [ ] **Step 4: Chạy unit test**

Run: `cd model && pytest tests/common/test_image_audit.py -v`

- [ ] **Step 5: Audit toàn bộ VAIPE train**

Run: `cd model && python scripts/build_vaipe_manifest.py --seed 20261025`

Expected: manifest có đúng 9.502 dòng ảnh, báo cáo ghi số nhãn, box, lớp, ảnh lỗi và cặp ảnh–nhãn thiếu.

- [ ] **Step 6: Dừng pipeline nếu có lỗi nghiêm trọng**

Script trả exit code khác 0 khi ảnh không đọc được, thiếu label, label ngoài `[0,107]` hoặc bounding box không hợp lệ. Cảnh báo mất cân bằng lớp không làm script thất bại.

### Task 4: Tạo split VAIPE không rò rỉ nhóm

**Files:**
- Create: `model/src/common/group_split.py`
- Create: `model/scripts/split_vaipe.py`
- Create: `model/tests/common/test_group_split.py`
- Generate: `data/processed/vaipe/splits/train.csv`
- Generate: `data/processed/vaipe/splits/validation.csv`
- Generate: `data/processed/vaipe/splits/test.csv`
- Generate: `model/reports/vaipe-split-report.json`

**Interfaces:**
- Consumes: `data/processed/vaipe/manifest.csv`
- Produces: `make_group_split(records, ratios, seed) -> SplitResult`
- Invariant: một `group_id` chỉ xuất hiện trong một split.

- [ ] **Step 1: Viết test chống group leakage và kiểm tra tính lặp lại theo seed**
- [ ] **Step 2: Chạy test và xác nhận thất bại**
- [ ] **Step 3: Cài đặt greedy multilabel group split với tỷ lệ 70/15/15**
- [ ] **Step 4: Chạy unit test**
- [ ] **Step 5: Sinh split thật và báo cáo độ lệch phân bố lớp**

Run: `cd model && python scripts/split_vaipe.py --seed 20261025 --train 0.70 --validation 0.15 --test 0.15`

Expected: không có group leakage; báo cáo liệt kê số ảnh, số box và số mẫu từng lớp ở mỗi split.

### Task 5: Audit PharmaVision và giữ nguyên split chính thức

**Files:**
- Create: `model/scripts/build_pharmavision_manifest.py`
- Create: `model/tests/test_pharmavision_manifest.py`
- Generate: `data/processed/pharmavision/manifest.csv`
- Generate: `model/reports/pharmavision-data-audit.json`

**Interfaces:**
- Produces manifest columns: `image_path,split,label,width,height,is_readable,sha256`.

- [ ] **Step 1: Viết test ánh xạ thư mục `normal` và `defective`**
- [ ] **Step 2: Cài đặt script, bao gồm phát hiện file trùng theo SHA-256**
- [ ] **Step 3: Chạy test**
- [ ] **Step 4: Audit dữ liệu thật**

Run: `cd model && python scripts/build_pharmavision_manifest.py`

Expected: 640 ảnh; train 380, validation 60, test 200; mỗi split cân bằng hai lớp theo bộ dữ liệu gốc.

### Task 6: Chọn phạm vi lớp thuốc cho vòng thử nghiệm đầu

**Files:**
- Create: `model/scripts/rank_demo_classes.py`
- Create: `model/tests/test_rank_demo_classes.py`
- Generate: `model/reports/vaipe-demo-class-candidates.csv`
- Generate: `model/reports/data-foundation-summary.md`

**Interfaces:**
- Consumes: VAIPE manifest và split report.
- Produces candidate columns: `label,total_boxes,train_boxes,validation_boxes,test_boxes,group_count,median_box_area,eligible`.

- [ ] **Step 1: Viết test loại lớp thiếu mẫu ở một trong ba split**
- [ ] **Step 2: Cài đặt xếp hạng theo số nhóm, số box và độ phủ split**
- [ ] **Step 3: Chạy test và sinh báo cáo thật**
- [ ] **Step 4: Chọn 5–10 lớp sau khi xem ảnh đại diện và confusion risk**

Không tự động chọn lớp chỉ dựa vào số lượng. Danh sách cuối cần ưu tiên thuốc có đặc trưng nhìn thấy từ mặt camera và vẫn giữ ít nhất hai cặp gần giống nhau để bài toán đủ độ khó.

### Task 7: Cổng hoàn thành nền dữ liệu

**Files:**
- Modify: `model/reports/data-foundation-summary.md`

- [ ] **Step 1: Chạy toàn bộ test**

Run: `cd model && pytest -v`

Expected: PASS.

- [ ] **Step 2: Kiểm tra artifact bắt buộc**

Phải có manifest VAIPE, ba split, manifest PharmaVision, báo cáo lỗi dữ liệu, phân bố lớp và danh sách lớp demo ứng viên.

- [ ] **Step 3: Review trước khi viết kế hoạch train**

Chỉ chuyển sang detector khi không còn lỗi dữ liệu nghiêm trọng và split report xác nhận không có group leakage. Chỉ chốt recognition classes sau khi nhóm xem ảnh đại diện của các lớp ứng viên.

