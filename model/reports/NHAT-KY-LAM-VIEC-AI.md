# Nhật ký triển khai AI

*Cập nhật: 27/10/2026. Ghi theo mạch kết quả → lý do → thay đổi → quyết định.*

> **Đính chính mới nhất:** nhãn VAIPE 107 là “ngoài đơn” theo ngữ cảnh, không phải một ID thuốc lạ. Các metric unknown lịch sử phía dưới có chứa 107 chỉ còn giá trị truy vết. Xem [đánh giá lại bằng CPU](recognition-vaipe-solution-review-cpu-20261027.md).

## Mạch quyết định: vì sao làm bước tiếp theo

| Kết quả quan sát được | Vì sao cần đổi hoặc làm thêm | Việc đã làm | Kết quả dẫn tới quyết định tiếp |
|---|---|---|---|
| 26/9.502 cặp VAIPE hỏng ảnh hoặc box sau EXIF | Ảnh và nhãn lỗi có thể làm sai split/training; bỏ một bên sẽ lệch cặp | Loại **cả ảnh lẫn nhãn** khỏi dữ liệu xử lý, rồi split 9.476 cặp hợp lệ theo nhóm | Không rò rỉ nhóm; đủ điều kiện train detector ([nền dữ liệu](data-foundation-summary.md)) |
| Cần tìm mọi viên trước khi biết loại thuốc | Detector bảy lớp sẽ bỏ qua các viên ngoài bảy ID | Train YOLOv7 **một lớp `pill`** trên toàn bộ VAIPE hợp lệ | Có baseline detector; cần so sánh chung với DINO ([YOLOv7](yolov7-pill-baseline-test.md)) |
| Metric in riêng của YOLOv7 và DINO không hoàn toàn ngang nhau | Không thể chọn nguồn ROI chỉ bằng hai báo cáo riêng | Chấm cùng COCOeval và so sánh validation | YOLOv7 AP validation 76,76% > DINO 73,31%; chọn YOLOv7 tạo ROI ([benchmark](pill-detector-common-benchmark.md)) |
| FGVC-PIM đạt 97,75% accuracy test trên **ROI bảy lớp đã biết** | Closed-set luôn ép thuốc lạ vào một lớp, nên không thể cho máy tự thả dựa trên accuracy này | Tạo unknown ROI và benchmark ArcFace/SupCon + ngưỡng validation | SupCon chỉ nhận đúng 16,35% known test, vẫn lọt 19/3.927 unknown; không triển khai ([open-set](recognition-open-set-benchmark.md)) |
| 38 unknown validation lọt SupCon; nhiều điểm gần 1,0 | Ngưỡng của embedding PIM đóng băng không tách đủ thuốc lạ | Xem ảnh lỗi; học MLP với ví dụ âm từ ID train **khác ID unknown validation** | Nhận đúng 25,03% known, lọt 2/1.710 unknown; nhưng bốn ID known bị loại hết ([MLP](recognition-negative-rejector-validation.md)) |
| Một điểm MLP chung loại sạch ID 99/51/46/10 | Cổng cần biết đang xác minh ID nào, thay vì “giống bảy ID” nói chung | Train verifier bảy đầu theo ID | Nhận đúng 39,75% known nhưng lọt 14/1.710 unknown; ID 46/10 vẫn 0 mẫu được nhận ([thuật toán](recognition-algorithm-improvement-20261027.md)) |
| Verifier theo ID vẫn không nhận ID 46/10 | Có thể embedding PIM chưa tách được lớp gần giống | Fine-tune PIM bằng lấy mẫu cân bằng + ArcFace, rồi train lại verifier | Macro F1 closed-set tăng 97,72→97,88% nhưng unknown lọt tăng 14→29/1.710; **không chọn checkpoint mới** ([thuật toán](recognition-algorithm-improvement-20261027.md)) |
| Sau fine-tune, ID 46/10 vẫn bị loại | Cần phân biệt lỗi classifier với lỗi cổng trước khi train thêm | Audit bằng CPU từng điểm và ảnh ROI trên nhóm validation giữ riêng | PIM đúng 28/28 ID 46 và 38/38 ID 10; điểm verifier/unknown chồng lấn, không hạ ngưỡng ([audit](recognition-id46-id10-audit.md)) |
| Audit cho thấy một số thuốc lạ giống ID 10 về hình dạng và màu | Thử xem đặc trưng màu có giúp verifier tách chúng không, trong lúc GPU bận | Trích màu HSV/RGB trên CPU, ghép embedding PIM và train verifier mới | Unknown lọt giảm 14→3/1.710 nhưng known đúng được nhận giảm 39,75→29,30%, ID 46/10 vẫn 0; không chọn ([thử màu](recognition-color-feature-study-20261027.md)) |
| Màu đơn giản giảm known; kNN và đầu tám trạng thái có thể tận dụng feature theo cách khác | Người dùng cho phép dùng GPU và yêu cầu tự thử | Chạy kNN, đầu tám trạng thái, fine-tune PIM bằng outlier exposure, feature đa tầng và DINOv2 | kNN, đầu tám trạng thái, outlier exposure, DINOv2 đều không vượt mốc; feature đa tầng tăng độ phủ nhưng vẫn còn thuốc lạ lọt ([nghiên cứu tiếp](recognition-autonomous-research-20261027.md)) |
| Validation giữ riêng theo nhóm vẫn chứa cùng ID thuốc lạ ở calibration | Cần biết cổng xử lý được **loại thuốc lạ mới** hay chỉ ảnh mới của loại đã thấy | Chia unknown validation theo ID không giao nhau, đánh giá lại các phương án | Feature không gian đạt 41,27% known và lọt 11/1.916 unknown; ID 46 vẫn 0. Ngưỡng riêng theo ID vọt lên 82/1.916 unknown; loại chính sách đó ([nghiên cứu tiếp](recognition-autonomous-research-20261027.md)) |
| Nghiên cứu mã cuộc thi cho thấy ID 107 là thuốc ngoài đơn theo từng đơn | Trộn nhãn ngữ cảnh với ID ngoại hình có thể làm sai tập âm và tỷ lệ thuốc lạ lọt | Lọc 107 khỏi unknown train/validation, giữ dữ liệu cũ để truy vết; đánh giá lại cổng và ngưỡng thuốc mục tiêu trên CPU | Cổng gốc lọt 26/1.414 ID lạ mới, cổng không gian 25/1.414; cả hai vượt 1%. Không chọn cổng mới ([đính chính](recognition-vaipe-solution-review-cpu-20261027.md)) |
| Sau khi sửa 107, cổng gốc vẫn lọt 26/1.414 ID lạ mới | Chưa thử các điểm OOD hậu kiểm phổ biến, không cần train | Thử MSP, energy, Mahalanobis, relative Mahalanobis, kNN, ViM và Mahalanobis so với tâm thuốc lạ train trên đặc trưng PIM, CPU | Không vượt cổng gốc; biến thể so với tâm âm lọt 3/1.414 nhưng chỉ nhận 28,47% known. Một lần chạy rò rỉ ID âm bị loại ([hậu kiểm](recognition-posthoc-ood-cpu-20261027.md)) |
| Bộ phân loại 7 lớp ít thông tin về thuốc lạ | Theo Vaze et al. 2022, bộ phân loại closed-set mạnh trên nhiều danh tính có thể cho điểm open-set tốt hơn | Fine-tune DINOv2 ViT-S/14 phân loại 7 ID mục tiêu + các ID âm (CosFace) trên GPU | Closed-set 98,76%. Khi tập âm chứa ID calibration: known 93–97% nhưng lọt 127–224/1.414. Khi loại mọi ID validation khỏi tập âm: 48,56% known, lọt 32. Không chọn ([DINOv2 toàn ID](recognition-fullid-dinov2-gpu-20261027.md)) |
| Không có ảnh nào trong `data/captured` | VAIPE chưa chứng minh máy thật nhận đúng thuốc, màu và mặt viên thay đổi theo cách chụp | Chuẩn bị quy trình chụp, manifest và validator CPU chống rò rỉ | Chờ ảnh camera với danh tính thuốc thật được đối chiếu; chưa bật `ACCEPTED` ([hướng dẫn](../../data/captured/README.md)) |

Các số liệu sau khi nhóm validation giữ riêng đã được xem chỉ phục vụ **so sánh nghiên cứu**; chúng không phải test độc lập mới. Test VAIPE cũ không được dùng để chỉnh mô hình hoặc ngưỡng mới. Trạng thái hiện tại: **không có train đang chạy; chưa bật thả tự động**.

## 27/10/2026 — Điểm OOD hậu kiểm (CPU) và DINOv2 phân loại toàn ID (GPU)

Người dùng yêu cầu tìm thêm phương pháp để tăng độ chính xác, dùng dữ liệu hiện có và GPU. Giao thức giữ như bản sửa 107: ngưỡng chọn trên calibration (unknown FAR ≤ 1%), báo trên 727 known và 1.414 unknown thuộc ID chưa thấy; không đọc test. Mốc là cổng gốc: nhận 55,57% known, lọt 26.

- **Hậu kiểm trên đặc trưng PIM, CPU** (`scripts/benchmark_posthoc_ood_cpu.py`): MSP 19,94%/36 lọt, energy 15,82%/41, Mahalanobis 25,72%/26 (ID 46 lần đầu nhận 6/28), relative Mahalanobis 6,74%/28, kNN k=1 8,25%/7, ViM 20,77%/38. Mahalanobis so với tâm thuốc lạ train lúc đầu cho 60,66%/27, nhưng tập âm có cùng ID với phía đánh giá. Sau khi loại mọi ID unknown validation (còn 33 ID âm), kết quả còn 28,47% known, lọt 3/1.414, chỉ phủ tốt ID 91/89. Không chọn. [Báo cáo](recognition-posthoc-ood-cpu-20261027.md).
- **DINOv2 ViT-S/14 phân loại toàn ID, GPU** (`scripts/train_fullid_dinov2_gpu.py`, CosFace m=0.2, 12 epoch, 224 px, trọng số chính thức trên máy). Closed-set 7 ID đạt 98,76% validation.
  - Lần 1: tập âm gồm cả ID thuốc lạ của calibration. Known nhận 93–97% (ID 46 25/28, ID 10 38/38) nhưng lọt 127–224/1.414 vì ngưỡng bị lỏng. Khi đặt ngưỡng ngay trên phía đánh giá (chỉ để chẩn đoán), lọt 14 thì known nhận 70,3%.
  - Lần 2 (`--strict`): loại mọi ID unknown validation khỏi tập âm (40 ID train, 7.383 ROI). Điểm cos margin nhận 48,56% known, lọt 32/1.414. Không vượt cổng gốc. [Báo cáo](recognition-fullid-dinov2-gpu-20261027.md).
- **Quyết định:** không thay cổng vận hành, chưa bật `ACCEPTED` tự động. Model tách tốt các loại thuốc lạ **đã có trong train**, nhưng chưa tổng quát sang loại mới. Với demo có 1–2 loại viên lạ biết trước, bước tiếp theo là chụp ảnh camera của chính các viên đó làm lớp âm, rồi đánh giá trên phiên chụp tách riêng. Không chỉnh thêm trên validation VAIPE đã xem nhiều lần.

## 27/10/2026 — Xem giải pháp VAIPE và sửa nhãn 107, chỉ dùng CPU

Theo yêu cầu người dùng, dừng dùng GPU và đọc thể lệ VAIPE cùng mã công khai của các đội. Baseline và các đội dùng thông tin đơn thuốc để quyết định “ngoài đơn”; mã Pill Gates biến ID dự đoán thành 107 khi ID đó không nằm trong đơn. Điều này chứng minh 107 là nhãn **phụ thuộc ngữ cảnh**, không phải một ngoại hình viên cố định. Trước đây nhánh open-set đã gộp 107 vào unknown; lỗi thiết kế dữ liệu cần sửa trước khi train tiếp.

- Đếm và loại **6.458 ROI 107 ở train unknown**, **1.005 ROI 107 ở validation unknown** trong một bản manifest/feature mới; không sửa dữ liệu cũ, không đọc test. Kiểm tra lại từng hàng theo `image_id`, `annotation_index`, `class_id`.
- Chia 2.828 ROI unknown validation còn lại theo 67 ID thành 1.414 calibration/1.414 ID lạ chưa thấy. Đánh giá checkpoint đã có hoàn toàn trên CPU: cổng gốc nhận đúng 404/727 known và lọt 26/1.414 unknown; cổng không gian nhận đúng 387/727 known và lọt 25/1.414 unknown. Cả hai vượt mục tiêu khảo sát 1% trên phía ID mới.
- Thử quy tắc có **ID thuốc mục tiêu do người vận hành chọn**, tương ứng việc giải pháp VAIPE dùng đơn thuốc giới hạn ứng viên. Ngưỡng nghiêm ngặt không cho lọt unknown hoặc wrong-known trên calibration vẫn cho lọt unknown thuộc ID mới ở các mục tiêu 89/10; ID 46 vẫn 0/28. ID 91 chỉ là ca nghiên cứu khả quan trong VAIPE, chưa đủ cho máy thật. Không bật thả tự động. Xem [báo cáo và lệnh tái lập](recognition-vaipe-solution-review-cpu-20261027.md).
- Vì mới chỉ đánh giá lại các verifier cũ, thử train bảy đầu tuyến tính **theo thuốc mục tiêu** trên embedding PIM gốc, tăng trọng số âm gần mục tiêu bằng cosine tính từ train. Môi trường thiếu `sklearn`, nên dùng PyTorch CPU có sẵn, 200 epoch. Mẫu âm vẫn chỉ 33 ID tách khỏi validation; ngưỡng vẫn yêu cầu 0 lỗi trên calibration. Đầu mới cho ID 91 đạt 132/155, ID 46 0/28, ID 89 lọt 14/1.414 unknown; nhìn chung kém cổng cũ. Không chọn và không cài thêm thư viện. Chi tiết trong [báo cáo CPU](recognition-vaipe-solution-review-cpu-20261027.md).

## 27/10/2026 — Nghiên cứu tiếp nhánh nhận diện với GPU

Người dùng cho phép dùng GPU và yêu cầu tự nghiên cứu, thử, ghi nhật ký. Audit trước chỉ ra PIM phân loại đúng ID 46/10 nhưng cổng từ chối; thí nghiệm màu giảm viên lạ lọt đồng thời làm giảm tỷ lệ nhận đúng. Vì vậy kiểm tra lần lượt giả thuyết về khoảng cách embedding, đầu học trạng thái lạ, đặc trưng backbone, và nguồn đặc trưng tự giám sát.

- kNN cosine trên embedding PIM: độ phủ calibration ở FAR 1% chỉ 8–10%, nên không tiếp tục.
- Đầu tám trạng thái trên GPU nhận đúng 36,59% known và cho lọt 10/1.916 unknown ID chưa thấy. Fine-tune PIM với outlier exposure bốn epoch làm macro F1 known giảm còn 93,78% ở best epoch, cổng nhận 30,54% known và lọt 7/1.916 unknown; hai hướng không vượt mốc gốc theo tiêu chí tổng hợp.
- Trích thêm ResNet layer4, ghép với embedding PIM và train verifier: trên ID lạ chưa thấy nhận đúng 40,44% known, lọt 14/1.916 unknown; ID 10 nhận 7/38, ID 46 vẫn 0/28. Đây là ứng viên nghiên cứu tốt nhất **theo calibration**, chưa được đưa vào máy.
- Thử ngưỡng riêng theo ID với ngân sách lỗi chung 1% trên calibration: known tăng đến 50,21% ở nhóm còn lại nhưng thuốc lạ mới lọt 82/1.916. Loại vì không tổng quát. Trung bình điểm 50/50 giữa cổng gốc và đa tầng cho 39,20% known, 7/1.916 unknown ở phép đo thăm dò; không dùng nhóm đã xem để chọn triển khai.
- Tải trọng số DINOv2 ViT-S/14 chính thức, trích đặc trưng train/validation trên GPU. Ghép PIM+DINOv2 nhận 34,39% known, lọt 8/1.916 unknown; linear probe DINOv2 macro F1 94,40% known validation và cổng riêng kém hơn. Không chọn.
- Thử tăng đa dạng âm: 62 ID/10.664 ROI train không chứa ID lạ đánh giá, lấy mẫu cân bằng theo ID. Calibration known đạt 42,76%, nhưng ID lạ mới lọt 46/1.916 (2,40%); ID 10 được nhận 30/38 với đổi lại rủi ro này. Không chọn. Các ID calibration trùng một phần ID âm train, nên không dùng điểm calibration để tuyên bố tổng quát hóa.
- Kiến trúc dự án nêu đặc trưng bậc hai cho viên khó; vì ảnh audit có dấu khắc mờ, trích thêm độ lệch chuẩn không gian của feature map layer4 và train verifier. Kết quả trên ID lạ chưa thấy: **41,27%** known, **11/1.916** unknown lọt, ID 10 nhận 8/38 nhưng ID 46 vẫn 0/28. 11 ROI lỗi thuộc 5/115 nhóm ảnh. Đây là ứng viên nghiên cứu tốt nhất theo calibration, vẫn chưa đủ để tự thả.
- 14 ROI lạ lọt cổng đa tầng thuộc sáu nhóm ảnh, chủ yếu ID 2→10 và ID 3→89. Không dùng test cũ để điều chỉnh. Kết quả chi tiết, mã và nguồn nghiên cứu: [báo cáo nghiên cứu](recognition-autonomous-research-20261027.md). Trước bước học máy tiếp theo cần ảnh camera thật, danh tính thuốc đối chiếu và một tập đánh giá mới khóa trước; vẫn trả `WRONG_DRUG` khi không chắc chắn.

## 27/10/2026 — Thử đặc trưng màu trên CPU

Kết quả audit cho thấy classifier nhận đúng ID 46/10, trong khi verifier không cho qua; một số ROI thuốc lạ có hình dạng gần giống. Vì vậy thử thêm histogram HSV và thống kê RGB từ tâm ROI vào embedding PIM, giữ train unknown tách ID với unknown validation. Không dùng GPU và không trích test cho biến thể này.

- Train verifier màu 30 epoch; best epoch 7. Trên nhóm validation giữ riêng, unknown lọt giảm từ 14 xuống 3/1.710, nhưng known đúng được nhận giảm từ 39,75% xuống 29,30%; ID 46/10 vẫn 0 mẫu được nhận.
- Thử ngưỡng riêng từng lớp để chẩn đoán: known đúng 40,17%, unknown lọt 39/1.710. Không chọn biến thể màu hay ngưỡng riêng cho máy. Cần dữ liệu camera thật và tập đánh giá mới. Xem [báo cáo thí nghiệm](recognition-color-feature-study-20261027.md).

## 25/10/2026 — Nền dữ liệu

- Đọc đề tài, kế hoạch triển khai và kiến trúc AI. Thống nhất ảnh không đủ chắc chắn phải dừng trước khi thả, quyết định `WRONG_DRUG` và kiểm tra thủ công.
- Audit VAIPE: 9.502 cặp. Phát hiện 1 JPEG bị cắt đuôi, 25 nhãn vượt biên EXIF. Đối chiếu các tệp với nguồn Kaggle, kết luận lỗi có trong nguồn. Theo quyết định của người dùng, loại **cả ảnh và nhãn** của 26 cặp khỏi dữ liệu xử lý; không sửa nguồn.
- Tạo manifest, split VAIPE theo nhóm, xác nhận không leakage; giữ split gốc PharmaVision. Tạo notebook EDA `model/notebooks/kham-pha-du-lieu-ai.ipynb`.
- Xem ảnh đại diện và chốt 7 ID nhận diện: 64, 91, 89, 99, 51, 46, 10.

## 25/10/2026 — YOLOv7 `pill`

- Xuất 9.476 ảnh/32.707 box thành một lớp `pill`; kiểm tra overlay và hướng EXIF. Chuẩn bị `.venv`, PyTorch CUDA 12.8 và trọng số YOLOv7 gốc.
- Vá tương thích NumPy, đường dẫn checkpoint phân biệt chữ hoa/thường, resume và ghi `last.pt` nguyên tử. Chạy smoke, sau đó baseline 30 epoch.
- Dừng theo yêu cầu người dùng tại epoch 19/30; xác thực checkpoint có optimizer, EMA, epoch và LR rồi resume chạy nền. Run hoàn thành 30/30, best epoch 29.
- Test giữ riêng 1.422 ảnh/5.810 box: mAP@0.5:0.95 74,8% theo bộ đo YOLOv7.

## 25–26/10/2026 — DINO/ResNet-50

- Tải mã DINO chính thức. Xuất cùng VAIPE split sang COCO; vá loader để xoay ảnh theo EXIF trước khi áp dụng bbox.
- Cài CUDA `nvcc` 12.8.93 trong dự án; bổ sung headers/thư viện từ `.venv`, vá API CUDA/PyTorch và `yapf`; biên dịch `MultiScaleDeformableAttention` cho RTX 5060 Ti, smoke test float/double đạt.
- Lỗi khởi chạy ban đầu được xử lý theo thứ tự: thiếu `PYTHONPATH` extension, nhãn COCO `category_id=1` vượt index của mô hình một lớp, và API cũ. Các run khởi động lỗi được giữ riêng; run chính là `dino_pill_baseline_20261025_v5`.
- DINO hoàn thành 12/12 epoch, best epoch 12, COCO AP@0.5:0.95 test 71,47%. Checkpoint và manifest đã lưu.

## 26/10/2026 — Benchmark chung và ROI

- Xuất dự đoán YOLOv7/DINO trên cùng test, chấm bằng một COCOeval. YOLOv7 AP@0.5:0.95 **74,22%**, DINO **71,47%**; DINO AR@100 cao hơn nhưng chứa nhiều ứng viên score thấp.
- Chấm YOLOv7 trên validation bằng COCOeval: AP@0.5:0.95 **76,76%**, so với DINO **73,31%**. Chọn YOLOv7 làm nguồn ROI dựa trên validation, không chỉnh ngưỡng bằng test.
- Kiểm tra overlay và ghép hộp một-một với nhãn. Xuất **9.590 crop** thuộc bảy ID (train 5.782, validation 1.943, test 1.865); ghi riêng 10 nhãn không ghép được. Xác nhận crop đọc được, EXIF đúng, không rò rỉ nhóm.

## 26/10/2026 — FGVC-PIM: lỗi khởi động và kiểm tra resume

YOLOv7 đã tạo được ROI bảy ID, nên bước kế là học đặc trưng để phân biệt các viên gần giống. Trước khi tin một lượt train dài, cần bảo đảm scheduler và checkpoint có thể tiếp tục đúng sau khi bị ngắt.

- Tải mã FGVC-PIM chính thức; tạo trainer riêng dùng loss base/drop/combiner, chọn best bằng macro F1 validation, khởi tạo ResNet-50 bằng ImageNet V1.
- Run khởi đầu bị dừng sớm để sửa tình huống AMP bỏ qua optimizer step nhưng scheduler vẫn tiến; chưa có checkpoint từ run này. Khởi chạy lại run `pim_resnet50_7class_20261026_v2` ở chế độ nền.
- Kiểm tra checkpoint epoch đầu có model, optimizer, scheduler, scaler, RNG; LR optimizer khớp scheduler. Kiểm tra `--resume` từ chối khi tiến trình đang chạy để tránh ghi đè.
- **Mốc lịch sử lúc run còn chạy:** sau 4/20 epoch, best macro F1 validation 87,08% ở epoch 2. Mốc này đã được thay bằng kết quả 20/20 epoch bên dưới; hiện không có run PIM này đang chạy.

## Quy trình resume đã dùng tại thời điểm đó

- Đọc `model/runs/recognition/pim_resnet50_7class_20261026_v2/metrics.jsonl` và `*.console.log` trước khi resume; không chạy hai tiến trình cùng run. Checkpoint được kiểm tra epoch, optimizer, scheduler, scaler và RNG để LR không lệch. Run này **đã hoàn tất**, không cần resume nữa.
- Sau khi hoàn tất đã đánh giá test một lần. Lỗi cặp 89/99 và giới hạn closed-set là lý do chuyển sang open-set/`WRONG_DRUG`.

## 26/10/2026 — FGVC-PIM hoàn tất và đánh giá test

Kết quả detector chỉ nói tìm đúng vị trí, nên sau khi PIM hoàn tất cần đo riêng khả năng phân biệt ID trên ROI mà detector ghép được.

- Run `pim_resnet50_7class_20261026_v2` hoàn thành 20/20 epoch. Best macro F1 validation 97,72% ở epoch 17.
- Đánh giá `best.pt` một lần trên 1.865 ROI test: macro F1 97,79%, accuracy 97,75%. Confusion matrix cho thấy 30 ROI ID 89 bị đoán là ID 99; hai nhãn thuộc bảy lớp không có ROI detector ghép đúng.
- Lưu `test-results.json`, cập nhật manifest và tạo [báo cáo nhận diện test](recognition-pim-7class-test.md). Bước tiếp theo là open-set/`WRONG_DRUG`; chưa thử lớp lạ.

## 26/10/2026 — Benchmark open-set bước đầu

Vì classifier bảy lớp luôn trả về một trong bảy ID, dù ảnh thuộc thuốc khác, accuracy closed-set 97,75% không thể là cổng `ACCEPTED`. Đây là lý do tạo ROI thuốc lạ và hiệu chỉnh ngưỡng từ chối.

- Tạo manifest thuốc lạ từ ID ngoài bảy lớp, ghép detector–nhãn một-một; validation có 3.833 ROI/68 ID, test có 3.927 ROI/69 ID. Không chép ảnh, lưu tọa độ crop và đường dẫn ảnh gốc.
- Trích logits và embedding từ PIM epoch 17 trên train/validation/test. Validation closed-set sai 29/1.943 ROI, trong đó 89→99 có 17 ROI.
- Huấn luyện đầu ArcFace và SupCon trên embedding PIM đóng băng, 25 epoch; checkpoint sau mỗi epoch gồm optimizer và RNG để resume. Hiệu chỉnh nhiệt độ và chọn ngưỡng xác suất/cosine trên validation với mục tiêu unknown false acceptance ≤1%.
- Chọn SupCon trên validation: nhận đúng known 16,06%, nhận nhầm unknown 0,99%. Test giữ nguyên ngưỡng: nhận đúng known 16,35%, nhận nhầm unknown 0,48% (19/3.927). Đánh dấu **chưa đủ triển khai tự động**, cần kiểm tra ảnh sai và cải thiện trước khi tích hợp. Chi tiết ở [báo cáo open-set](recognition-open-set-benchmark.md).

## 26/10/2026 — Kiểm tra ảnh lỗi và thử rejector có ví dụ âm

SupCon vẫn cho lọt 19 ROI thuốc lạ test và loại phần lớn viên đúng. Trước khi thêm mô hình mới, cần xem **loại ảnh nào** lọt và liệu xác suất/cosine có thực sự tách được thuốc lạ.

- Xuất CSV và ảnh ghép của 29 lỗi known validation, 38 unknown validation lọt ngưỡng, cùng kết quả test cũ để chẩn đoán. Lỗi 89→99 chiếm 17 ROI known validation; unknown lọt ngưỡng tập trung ở ID 107 và 2. Tạo [báo cáo ảnh lỗi](recognition-error-audit.md).
- Mở rộng manifest unknown sang train: 15.302 ROI thuộc 96 ID ghép đúng detector; trích feature PIM đóng băng. Dùng 1.601 ROI từ 33 ID **không xuất hiện trong unknown validation** để train MLP rejector class-disjoint.
- Tách validation theo `group_id` thành calibration 1.216 known/2.123 unknown và phần giữ riêng 727 known/1.710 unknown. Best epoch 27/30 theo calibration AUROC; ngưỡng chung calibration 0,97367. Trên phần giữ riêng nhận đúng known 25,03%, nhận nhầm unknown 2/1.710, nhận nhầm known 0/727. Baseline SupCon trên cùng nhóm: 9,90%, 13/1.710, 0/727.
- Phát hiện ngưỡng chung không chấp nhận ID 99, 51, 46, 10 trong phần giữ riêng. Khảo sát ngưỡng theo lớp đạt 36,31% nhận đúng gộp nhưng ID 46 vẫn 0/28, unknown lọt 17/1.710. Giữ kết luận **chưa được tự động thả viên**; không đánh giá mô hình mới trên test cũ. Chi tiết ở [báo cáo rejector](recognition-negative-rejector-validation.md).

## 27/10/2026 — Verifier theo ID và fine-tune PIM ArcFace

MLP nhị phân giảm thuốc lạ lọt nhưng không nhận mẫu nào của bốn ID known. Vì cổng đang học một điểm chung cho cả bảy ID, thử verifier theo ID; khi ID 46/10 vẫn bị loại, thử fine-tune embedding PIM để xem đặc trưng có cải thiện không.

- Train verifier bảy đầu trên embedding PIM gốc với 1.601 ROI thuốc lạ thuộc 33 ID tách biệt unknown validation. Trên 727 known/1.710 unknown validation giữ riêng: nhận đúng 39,75%, unknown lọt 14 mẫu, ID 46 và 10 không được chấp nhận ở ngưỡng chung.
- Fine-tune PIM từ best epoch 17, lấy mẫu cân bằng, thêm ArcFace loss, 6 epoch. Lần khởi động đầu gặp lỗi dtype trong `scatter` dưới AMP trước checkpoint; sửa float32 và giữ run lỗi riêng. Tiến trình chính bị môi trường dừng giữa epoch 5; xác nhận `--resume` tiếp tục từ epoch 5 với LR `5,03767778e-6`, hoàn tất 6/6. Best epoch 4, macro F1 validation 97,88%.
- Trích feature mới chỉ trên train/validation, giữ 33 ID âm train không trùng unknown validation; train lại verifier theo ID. Nhóm validation giữ riêng: known đúng 42,78%, unknown lọt 29/1.710 (1,70%), ID 46/10 vẫn 0 mẫu được nhận. Không chọn checkpoint fine-tune cho hệ thống. Chi tiết ở [báo cáo thuật toán](recognition-algorithm-improvement-20261027.md).

## 27/10/2026 — Audit ID 46/10 và nền tảng ảnh camera thật

Macro F1 tăng sau fine-tune nhưng thuốc lạ lọt nhiều hơn và ID 46/10 vẫn bị loại. Do đó cần truy nguyên **tầng nào** gây từ chối trước khi tiếp tục train hoặc hạ ngưỡng.

- Dùng checkpoint PIM gốc + verifier theo ID trên CPU, nối feature với manifest validation theo `image_id`/`annotation_index`. PIM dự đoán đúng 28/28 ROI ID 46 và 38/38 ROI ID 10 ở nhóm giữ riêng; cả 66 bị cổng verifier từ chối. Xuất [bảng điểm và ảnh sát ranh giới](recognition-id46-id10-audit.md). Thuốc lạ cạnh tranh có hình dạng/màu tương tự; không hạ ngưỡng trên nhóm đã xem.
- Kiểm tra `data/captured`: chưa có ảnh camera thật. Tạo [hướng dẫn chụp và manifest template](../../data/captured/README.md), template mã thuốc thật và `validate_camera_manifest.py`. Validator kiểm tra ảnh, đường dẫn, trùng ảnh, nhóm phiên/viên vật lý và ID thuốc lạ giữa các split; kiểm thử bằng ảnh giả tạm thời cho trường hợp hợp lệ, rò rỉ phiên và rò rỉ ID lạ.

## 27/10/2026 — Baseline CPU cho nhánh viên lỗi PharmaVision

Vì các lần cải tiến nhận diện tiếp tục gặp unknown lọt và chưa có ảnh camera thật để tạo bằng chứng mới, chuyển sang nhánh lỗi còn thiếu trong kiến trúc. PharmaVision đã qua audit, nên dùng split gốc 380/60/200, không chia lại.

- Viết `train_pharmavision_cpu_baseline.py` dùng ResNet-50 ImageNet đã có để trích đặc trưng đóng băng bằng CPU, học đầu logistic và chọn `C`/ngưỡng theo F2 lỗi trên validation. Lưu đặc trưng sau từng lô để chạy tiếp khi ngắt, khóa bằng SHA-256 manifest/trọng số. Không có scheduler epoch vì đầu logistic tối ưu bằng LBFGS xác định.
- ResNet-50 validation nhận **30/30 viên lỗi**, nhưng báo nhầm **24/30 viên bình thường**. Đây là dấu hiệu ngưỡng bảo thủ làm giảm khả năng sử dụng thực tế, nên tải trọng số EfficientNetV2-S chính thức của PyTorch và chạy cùng giao thức làm đối chứng.
- EfficientNetV2-S validation nhận **29/30 viên lỗi**, báo nhầm **19/30 viên bình thường**; F2 86,31% so với ResNet-50 86,21%. Theo ưu tiên Recall lỗi, ghi quyết định chọn ResNet-50 vào `model-selection-20261027.json` trước khi mở test EfficientNetV2-S.
- Test với ngưỡng đã khóa: ResNet-50 nhận **96/100 viên lỗi**, bỏ sót 4 và báo nhầm 56/100 viên bình thường; EfficientNetV2-S cũng nhận 96/100, bỏ sót 4 và báo nhầm 62/100 viên bình thường. Không chỉnh ngưỡng hoặc đổi lựa chọn dựa trên test. Cả hai chỉ là baseline; chưa đủ cho cơ cấu thả.
- Viết [báo cáo kết quả](defect-pharmavision-cpu-baseline-20261027.md) và [hướng dẫn môi trường/chạy tiếp](../DEFECT-SETUP.md). Bước tiếp theo là fine-tune hoặc phân tích lỗi chỉ trên train/validation; ảnh camera thật vẫn cần để kiểm tra chuyển miền.

## 27/10/2026 — Xem ảnh sai và fine-tune EfficientNetV2-S bằng CPU

Baseline đóng băng bỏ sót 4/100 viên lỗi trên test đã mở và báo nhầm quá nhiều viên bình thường; **test này không còn phù hợp để chọn điều chỉnh mới**. Vì vậy chỉ xem ảnh sai validation và huấn luyện trên train/validation gốc.

- Xuất [44 dòng lỗi validation](defect-validation-audit/errors.csv) và hai contact sheet: ResNet-50 có 24 báo nhầm viên bình thường; EfficientNetV2-S có 19 báo nhầm và một viên lỗi xám sứt nhỏ bị bỏ sót. Nhiều ảnh bình thường màu xanh/trắng bị báo lỗi. Đây là quan sát giúp chọn thí nghiệm, chưa kết luận nguyên nhân chắc chắn.
- Dùng EfficientNetV2-S đã tải, cập nhật hai block cuối và classifier ở 224 px bằng CPU để giảm chi phí so với full fine-tune 384 px. Thêm lật, xoay nhẹ, điều chỉnh sáng/tương phản chỉ trên train. Giữ ngưỡng validation 0,40 cố định, chọn best theo F2 lỗi; không dò ngưỡng nhiều lần trên 60 ảnh.
- Viết `finetune_pharmavision_cpu.py` lưu checkpoint atomically mỗi epoch gồm model, optimizer, scheduler, RNG và best metric; resume kiểm tra SHA-256 manifest/trọng số và LR. Run hoàn tất 18/20 epoch do dừng sớm sau sáu epoch không cải thiện. Best epoch **12**: validation nhận **30/30 viên lỗi**, báo nhầm **8/30 viên bình thường**, F2 **94,94%**. Baseline EfficientNetV2-S cùng validation là 29/30 lỗi, 19/30 báo nhầm, F2 86,31%.
- Kiểm tra `best.pt` epoch 12, `last.pt` epoch 18; LR optimizer = LR scheduler = `2,7091379149682626e-6` ở checkpoint cuối. Không mở lại test cũ và chưa dùng mô hình để điều khiển thả. Ghi [báo cáo fine-tune](defect-pharmavision-cpu-finetune-20261027.md) và cập nhật [cách chạy/resume](../DEFECT-SETUP.md).
- Để kiểm chứng resume thực tế, tạo run tạm từ checkpoint epoch 12 rồi chạy lại epoch 13–18. LR epoch 13 là `3,7725725642960056e-5`; từng dòng metric/loss/LR sau resume khớp chính xác run gốc. Xóa run tạm sau đối chiếu.

## 27/10/2026 — Đánh giá pillQC độc lập và mô phỏng dừng trước khi thả

Fine-tune đạt 30/30 lỗi trên validation PharmaVision nhưng tập này nhỏ và đã dùng để chọn checkpoint. Chưa có ảnh camera thật, nên cần một miền ảnh khác để kiểm tra khả năng chuyển miền mà không tối ưu thêm vào đó.

- Tải pillQC chính thức tại commit `9c0a8ecdca0a3797e784412de077a30ae2c50b3c`; xác nhận 43 `chip`, 149 `normal`, 138 `dirt`. Theo giao thức tác giả PharmaVision, chỉ dùng `chip`/`normal` cho phép đo chính, vì `dirt` là lỗi nhiễm bẩn có định nghĩa khác. Kiểm tra ảnh đọc được và không trùng SHA-256 với PharmaVision.
- Khóa checkpoint EfficientNetV2-S epoch 12, ngưỡng 0,40, CPU; không train hay chỉnh ngưỡng trên pillQC. Kết quả: nhận **26/43 viên sứt**, bỏ sót **17/43**, báo lỗi nhầm **2/149 viên bình thường**, F2 **65,00%**. Một số vết sứt rõ trong contact sheet vẫn bị nhận là bình thường. Điều này phủ nhận việc dùng metric validation PharmaVision làm bằng chứng đủ cho máy thật. Ghi [báo cáo và dự đoán từng ảnh](defect-pillqc-cross-domain-20261027.md).
- Vì lỗi nhận diện thuốc và lỗi chất lượng đều chưa đủ vững, viết `decision_simulator.py` chỉ mô phỏng quyết định, mặc định không cho release. Thử các trường hợp không viên, nhiều viên, ảnh mờ, ID không chắc, ID sai, lỗi không chắc, viên lỗi và viên bình thường. **16/16 kiểm thử đạt**; bộ đếm chỉ được tăng sau cảm biến xác nhận rơi trong tích hợp thực tế, nên hàm mô phỏng luôn trả `accepted_count_increment=0`.
- Giữ trạng thái chưa triển khai; không dùng pillQC đã mở để hạ ngưỡng. Bước còn thiếu là dữ liệu camera/buồng chụp thật được gán nhãn và kiểm thử phần cứng end-to-end.

## 27/10/2026 — Replay pipeline CPU và kiểm tra dừng trước khi thả

Sau đánh giá pillQC cho thấy nhánh lỗi chưa bền và cổng danh tính vẫn chưa an toàn, cần nối các thành phần để phát hiện lỗi giao diện/luồng trước khi có ảnh camera thật. Bản replay chỉ đọc ảnh validation VAIPE và ghi log, không gửi lệnh cơ cấu hay tăng bộ đếm.

- Tạo `replay_ai_pipeline_cpu.py`: YOLOv7 → crop lề 10% → FGVC-PIM 7 ID → verifier chẩn đoán → EfficientNetV2-S defect → `decision_simulator.py`. Với ảnh nhiều viên/không có viên, bỏ qua các tầng sau detector. Mọi ảnh một viên đều có `identity_verified=False` vì verifier hiện không được dùng để cấp quyền thả.
- Cách tải YOLOv7 cũ bằng cách tắt `weights_only` bị cổng kiểm duyệt tự động từ chối vì checkpoint pickle có thể thực thi mã. Kiểm kê global trong checkpoint, dùng `weights_only=True` với allowlist giới hạn các lớp YOLOv7/NumPy. Do YOLOv7 và FGVC-PIM cùng dùng tên package `models`, đặt YOLOv7 trong `infer_yolov7_cpu_safe.py` làm worker riêng; PIM/verifier/defect cũng tải bằng `weights_only=True` với allowlist NumPy tối thiểu. Trước khi có worker, đã chạy một lượt dùng JSON hộp YOLOv7 đã xuất; giữ run này để đối chiếu kết quả.
- Phát lại ba ảnh VAIPE validation (hai ảnh một viên, một ảnh hai viên) và một ảnh trống giả lập. Run detector thật trên CPU trả `WRONG_DRUG` 2, `MULTIPLE_PILLS` 1, `EMPTY_FRAME` 1; **không có lệnh thả, không tăng bộ đếm**. Số hộp và route của ba ảnh VAIPE khớp replay từ JSON đã xuất. Kiểm tra log từng ảnh và chạy lại 16 kiểm thử quyết định đều đạt.
- Thời gian tổng quan sát 181–528 ms/ảnh trên laptop CPU, gồm đọc ảnh hai lần qua hai tiến trình nhưng không gồm tải model. Vì chỉ bốn mẫu, không diễn giải như benchmark hoặc tốc độ Raspberry Pi. Ghi [báo cáo](pipeline-cpu-dry-run-20261027.md) và [hướng dẫn chạy lại](../PIPELINE-REPLAY-SETUP.md). Còn thiếu ảnh camera thật, kiểm tra chất lượng ảnh, đánh giá hai cổng độc lập và cơ cấu/cảm biến thật.

## 27/10/2026 — Thử kiến trúc nhận diện bổ sung trên CPU

- Cổng theo ID mục tiêu cũ nhận 337/727 ROI đúng nhưng lọt 24 trường hợp thuốc lạ trên 1.414 ROI ID mới. Vì lỗi tập trung ở các cặp rất giống (ID 3 → 89, ID 2 → 10), thử thêm kiểm tra xoay 90°/180° trên 927 ứng viên đã qua cổng. Tất cả giữ nguyên nhãn; không loại được trường hợp thuốc lạ nào.
- Kiểm tra đặc trưng bilinear covariance của layer4 với 336 ROI gallery train để tìm dấu hiệu cục bộ ngoài embedding PIM. So centroid và ảnh gallery gần nhất đều không loại được 24 trường hợp lạ; biến thể gần nhất còn loại một mẫu đúng ở nhóm hiệu chỉnh. Không dùng các bộ lọc này.
- Vì đầu xác minh tuyến tính cũ yếu, huấn luyện MLP 256–128–7 trên 5.782 known train và các ID âm train tách khỏi unknown validation, loại nhãn ngữ cảnh 107. CPU 40 epoch. Trên nhóm ảnh/ID giữ riêng, số đúng được nhận tăng từ 337 lên 368/727 nhưng trường hợp lạ lọt tăng 24 → 25. ID 46 vẫn 0/28; ID 89 vẫn lọt 17. Không thay cổng máy và không chọn riêng ID dựa trên validation đã xem.
- Ghi [báo cáo đầy đủ](recognition-architecture-trials-cpu-20261027.md), script và kết quả từng ID. Đây là thêm bằng chứng rằng đổi loss/đầu nhận diện trên cùng dữ liệu chưa giải quyết được thuốc gần giống; cần ảnh camera thật với ID thuốc được đối chiếu và tập mới giữ riêng trước khi quyết định cho thả.

## 27–28/10/2026 — Thử YOLO11s và so với YOLOv7

Người dùng hỏi vì sao dùng YOLOv7 thay vì YOLO11; repo trước đó chỉ có đối chứng DINO. Để kiểm tra bằng dữ liệu dự án thay vì suy đoán theo phiên bản model, tôi chọn **YOLO11s** vì nhẹ hơn và có ý nghĩa cho hướng Raspberry Pi. Giữ đúng split VAIPE đã audit, một lớp `pill`, ảnh 640 px, 30 epoch và batch 8 như lượt YOLOv7; các hyperparameter/kiến trúc mặc định của hai framework vẫn khác nhau.

- Cài Ultralytics 8.4.190 và `ultralytics-thop` vào `.venv` hiện có, tải trọng số YOLO11s chính thức và ghi SHA-256. Smoke 1 epoch đầu đọc ảnh/CUDA thành công nhưng dừng khi lưu checkpoint vì thiếu `polars`; cài bổ sung `polars==2.1.0`, chạy smoke lần hai hoàn tất và lưu `best.pt`/`last.pt`. Đây là lỗi setup, không phải kết quả mô hình.
- Viết `train_yolo11_detector.py`: khóa cấu hình và SHA-256 nguồn trong manifest trước khi train, chặn ghi đè run, hỗ trợ `--resume` từ `last.pt` với kiểm tra split, batch, epoch, phiên bản thư viện và seed. Lưu `pip-freeze.txt` và checksum script trong run. Train trên RTX 5060 Ti hoàn tất **30/30 epoch**, khoảng **3.365 giây (56 phút)**; best **epoch 30**, mAP@0.5:0.95 validation do Ultralytics ghi **76,669%**.
- Khi xuất COCO validation, script ban đầu truyền danh sách toàn bộ 1.421 ảnh độ phân giải lớn và bị hệ điều hành kill do RAM. Sửa sang **stream theo thư mục**, kiểm tra tên, số lượng, trùng lặp và hướng ảnh; không train lại hoặc thay checkpoint. Kiểm tra mẫu 102 ảnh không lệch kích thước/hướng EXIF. Đánh giá validation bằng cùng COCOeval: YOLOv7 **76,76%**, YOLO11s **76,31%** AP@0.5:0.95. Ở cutoff 0,25, YOLOv7 **5.771 TP / 42 FP / 23 FN**, YOLO11s **5.769 / 57 / 25**.
- Khóa `best.pt` theo validation rồi chấm test **một lần**: YOLOv7 **74,22%**, YOLO11s **73,09%** AP@0.5:0.95. Ở cutoff 0,25, YOLOv7 **5.791 TP / 32 FP / 19 FN**, YOLO11s **5.777 / 66 / 33**. YOLO11s khoảng 9,4 triệu tham số so với YOLOv7 khoảng 36,5 triệu; số đo inference YOLO11s trên GPU ~3,71 ms/ảnh chưa tương đương số YOLOv7 ~5,2 ms gồm inference+NMS.
- **Quyết định:** giữ YOLOv7 cấp ROI vì validation AP nhỉnh hơn và test cho ít hộp sai/bỏ sót hơn. Chưa đổi pipeline hoặc huấn luyện lại nhánh nhận diện theo ROI YOLO11s. YOLO11s vẫn là ứng viên nhẹ để đo riêng trên Raspberry Pi và ảnh camera thật; kết quả này không khái quát cho mọi kích thước YOLO11. Cập nhật [báo cáo tổng hợp](BAO-CAO-TIEN-DO-AI.md) và [hướng dẫn tái lập](../YOLO11-SETUP.md).

## 28/10/2026 — Nhận ảnh pilot thuốc thật từ điện thoại

Trước đó `data/captured` trống nên không thể khảo sát ảnh ngoài VAIPE/PharmaVision. Người dùng đã đưa 19 ảnh `.JPG` theo mẫu `<tên thuốc>_<o|x>_<số>` và xác nhận `o` là bình thường, `x` là vỡ/sứt; tên thuốc đã đối chiếu với bao bì/lô. Ảnh chụp bằng **điện thoại, qua nhiều phiên**, và có nhiều ảnh của cùng một viên vật lý. Đây là dữ liệu pilot, chưa phải ảnh từ camera/buồng chụp của máy.

- Viết `inventory_camera_captures.py` để đọc toàn bộ ảnh, kiểm tra EXIF/giải mã, SHA-256 và nhãn từ tên file mà không sửa ảnh gốc. Kết quả: **19/19 ảnh đọc được**, tất cả 3024×3024, **0 cặp trùng SHA-256**, 5 tên thuốc, **13 `o` và 6 `x`**. Inventory cục bộ đặt tại `data/captured/inventory.csv` và `inventory-summary.json`, mọi hàng `split=unassigned`; ảnh/metadata này không push lên GitHub.
- Xem mẫu trực quan: vết sứt của `Pracetam800_x_03` thấy rõ; nền giấy ô ly và mặt bàn gỗ, ánh sáng/góc khác nhau. Đây là dấu hiệu cần chụp cả bình thường và vỡ trong cùng điều kiện để mô hình không học nhầm nền. Chưa gán lại nhãn chỉ từ quan sát hình ảnh.
- **Chưa chia train/validation/test và chưa train/đánh giá độ chính xác**, vì chưa có ánh xạ chính xác file nào thuộc cùng viên vật lý và phiên chụp; chia từng file ngẫu nhiên sẽ rò rỉ. Mã tham chiếu bao bì/lô, camera và ánh sáng cũng chưa được ghi theo từng ảnh. Cập nhật [hướng dẫn thư mục ảnh](../../data/captured/README.md) và [báo cáo tổng hợp](BAO-CAO-TIEN-DO-AI.md). Cổng `ACCEPTED` vẫn khóa.
- Để xem detector VAIPE phản ứng với ảnh điện thoại ra sao, chạy `replay_camera_pilot_detector_cpu.py` bằng checkpoint YOLOv7 và loader `weights_only=True` hiện có. Ở ngưỡng demo 0,25, 17 ảnh có một hộp, hai ảnh `betahistin24at_x_08/09` có hai hộp. Quan sát ảnh cho thấy mỗi hộp nằm trên một **mảnh của cùng viên vỡ**, không phải hai viên nguyên. Pipeline hiện dừng an toàn ở `MULTIPLE_PILLS`; cần nghiên cứu nhánh mảnh vỡ để báo đúng nguyên nhân, nhưng chưa thay quyết định hoặc cấp quyền thả. Không tính accuracy vì chưa có box thật gán nhãn.

