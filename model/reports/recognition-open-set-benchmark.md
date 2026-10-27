# Benchmark nhận diện thuốc lạ và quyết định `WRONG_DRUG`

> **Đính chính về nhãn VAIPE 107:** Các chỉ số thuốc lạ trong báo cáo lịch sử này có chứa nhãn 107, vốn là “ngoài đơn” theo ngữ cảnh, không phải ID thuốc lạ cố định. Không dùng các chỉ số đó để quyết định thả thuốc. Xem [đánh giá lại bằng CPU](recognition-vaipe-solution-review-cpu-20261027.md).

## Dữ liệu và quy trình

- Mô hình FGVC-PIM bảy ID dùng `best.pt` ở epoch 17. Trích logits và đặc trưng trước lớp phân loại; **đóng băng toàn bộ PIM**, chỉ huấn luyện hai đầu chiếu embedding ArcFace và supervised contrastive (SupCon). Đây là benchmark bước đầu, chưa phải fine-tune end-to-end.
- Tập thuốc lạ là các ID VAIPE nằm ngoài `[64, 91, 89, 99, 51, 46, 10]`. Ghép hộp YOLOv7 với nhãn gốc một-một ở IoU ≥ 0,5, crop lề 10%, giữ split theo nhóm. Validation: 3.833/3.848 ROI, 68 ID; test: 3.927/3.943 ROI, 69 ID. ROI không ghép được không đưa vào metric.
- Embedding chỉ học từ 5.782 ROI **known train**; thuốc lạ validation chỉ dùng chọn ngưỡng. Temperature scaling học từ 1.943 ROI known validation; nhiệt độ **1,1709**. Chọn phương pháp và hai ngưỡng trên validation; đánh giá test sau khi lựa chọn đã được lưu.
- Quy tắc nhận: lớp dự đoán phải trùng ID đang chọn trên máy, xác suất sau calibration ≥ ngưỡng, cosine tới tâm lớp dự đoán ≥ ngưỡng. Mọi trường hợp khác chuyển `WRONG_DRUG` và dừng trước khi thả. Chỉ số dưới đây đo cổng xác suất + cosine; chưa đo cơ cấu máy.

## Kết quả

Validation của PIM đóng tập có **29/1.943** ROI sai: 89→99 là 17, 99→89 là 3, 51→46 là 6, 46→51 là 2, 91→89 là 1.

Mục tiêu chọn ngưỡng là tỷ lệ nhận nhầm thuốc lạ trên validation ≤ **1%**. Đây là mục tiêu thử nghiệm để so sánh, chưa phải chỉ tiêu an toàn đã được xác nhận cho máy thật.

| Đầu embedding | Validation nhận đúng known | Validation nhận nhầm known | Validation nhận nhầm unknown | AUROC unknown |
|---|---:|---:|---:|---:|
| ArcFace | 15,95% | 0% | 0,91% | 0,8767 |
| SupCon | **16,06%** | 0% | 0,99% | **0,8786** |

Chọn **SupCon** theo tỷ lệ nhận đúng known trên validation. Ngưỡng đã khóa: xác suất **0,9999211**, cosine **0,9993737**.

| Phép đo giữ lại | Kết quả test |
|---|---:|
| ROI known / unknown | 1.865 / 3.927 |
| Nhận đúng known | **16,35%** |
| Nhận nhầm known | 0% trên tập này |
| Nhận nhầm unknown | **0,48%** (19/3.927) |
| Recall chuyển unknown sang `WRONG_DRUG` | 99,52% |
| AUROC unknown / AUPR unknown | 0,8823 / 0,9323 |

## Kết luận sử dụng

**Chưa đủ để tự động thả viên.** Với ngưỡng hiện tại, khoảng 84% ROI known test không được chấp nhận; đồng thời vẫn có 19 ROI thuốc lạ bị nhận nhầm. Số 0% nhận nhầm known chỉ là quan sát trên tập test này, không chứng minh rủi ro bằng 0. Chỉ số cũng có điều kiện detector đã ghép ROI đúng, chưa gồm false positive/miss của detector và ảnh từ camera thật. ID VAIPE là nhãn hình ảnh, không xác minh hoạt chất.

Việc tiếp theo: xem trực tiếp các mẫu 89/99 và 19 unknown bị nhận nhầm; tăng độ phân biệt bằng huấn luyện embedding cùng backbone trên crop đủ nét, và thu ảnh đúng camera/buồng chụp trước khi đặt ngưỡng vận hành. Sau khi cải thiện, khóa phương pháp và ngưỡng trên validation mới, rồi đánh giá trên test mới độc lập; không tiếp tục chỉnh theo test hiện tại.

## Tái lập

```bash
.venv/bin/python model/scripts/prepare_recognition_unknown.py
.venv/bin/python model/scripts/extract_recognition_features.py --device auto
.venv/bin/python model/scripts/benchmark_recognition_open_set.py --device auto --epochs 25
```

Lệnh trích feature bỏ qua `.npz` đã tồn tại; benchmark lưu `arcface-last.pt` và `supcon-last.pt` sau mỗi epoch để resume đúng optimizer/RNG khi chạy lại **cùng số epoch và dữ liệu**. Kết quả lựa chọn và test: [`selection-validation.json`](../runs/recognition/open_set_benchmark_20261026/selection-validation.json), [`test-results.json`](../runs/recognition/open_set_benchmark_20261026/test-results.json). Để làm benchmark mới với cấu hình khác, dùng thư mục run khác; không ghi đè run này.
