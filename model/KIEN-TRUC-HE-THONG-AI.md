# Kiến trúc hệ thống AI kiểm tra viên thuốc

## 1. Mục tiêu

Hệ thống xử lý từng viên thuốc đi qua vùng camera và trả về đúng một trong ba kết quả:

1. `ACCEPTED`: đúng loại thuốc đã chọn và viên còn nguyên vẹn.
2. `DEFECTIVE`: đúng loại thuốc nhưng viên bị sứt, nứt, vỡ hoặc có bất thường bề mặt.
3. `WRONG_DRUG`: sai loại thuốc hoặc hệ thống không đủ chắc chắn để chấp nhận.

Hệ thống không ép một ảnh không rõ ràng vào lớp gần nhất. Các trường hợp độ tin cậy thấp được chuyển sang `WRONG_DRUG` để kiểm tra thủ công.

## 2. Pipeline chính thức

```text
Ảnh camera
    ↓
Tầng 1: Phát hiện viên thuốc và cắt ROI
    ↓
Tầng 2: Fine-grained recognition nhận diện loại thuốc
    ↓
Tầng 3: Open-set recognition xác nhận đúng loại hoặc thuốc lạ
    ↓
Tầng 4: Kiểm tra normal/defective
    ↓
ACCEPTED / DEFECTIVE / WRONG_DRUG
```

Hai nhánh nhận diện loại thuốc và kiểm tra lỗi được huấn luyện bằng hai bộ dữ liệu riêng. Chúng chỉ được ghép lại ở pipeline suy luận.

## 3. Tầng 1 — Phát hiện viên thuốc và cắt ROI

### Nhiệm vụ

- Tìm vị trí viên thuốc trong ảnh camera.
- Cắt vùng chứa viên và loại bỏ phần lớn nền, máng dẫn và cơ cấu máy.
- Phát hiện các trạng thái không hợp lệ: không có viên, có nhiều hơn một viên hoặc viên bị che quá nhiều.

### Đầu vào và đầu ra

- Đầu vào: một ảnh RGB từ camera.
- Đầu ra: bounding box, ảnh ROI đã chuẩn hóa và độ tin cậy phát hiện.

### Nguyên tắc

Mô hình chỉ cần một lớp `pill`. Chất lượng của tầng này được đánh giá chủ yếu bằng Recall, vì bỏ sót viên sẽ khiến các tầng sau không thể xử lý.

## 4. Tầng 2 — Fine-grained recognition

### Nhiệm vụ

Nhận diện loại thuốc từ ROI bằng các đặc trưng nhỏ như:

- Hình dạng và tỷ lệ viên.
- Màu sắc và phân bố màu.
- Rãnh chia thuốc.
- Chữ, số hoặc ký hiệu in/dập trên bề mặt.
- Các vùng đặc trưng cục bộ giúp phân biệt những viên gần giống nhau.

### Đầu vào và đầu ra

- Đầu vào: ROI của một viên thuốc.
- Đầu ra: vector đặc trưng, xác suất các lớp và lớp dự đoán tốt nhất.

### Hướng mô hình

Nhóm sẽ benchmark các kiến trúc fine-grained thay vì chọn trước một mô hình duy nhất. Mô hình mạnh có thể làm teacher; mô hình nhẹ hơn được distillation để triển khai trên Raspberry Pi 4. Việc lựa chọn cuối cùng dựa trên chất lượng nhận diện, khả năng phân biệt các lớp dễ nhầm và thời gian suy luận thực tế.

## 5. Tầng 3 — Open-set recognition

### Nhiệm vụ

Ngăn hệ thống nhận nhầm thuốc lạ thành một lớp đã biết. Đây là tầng quyết định viên có đủ điều kiện để đi tiếp sang kiểm tra lỗi hay phải đưa vào ô thuốc sai loại.

### Cách quyết định

Tầng này kết hợp:

- Loại thuốc người vận hành đã chọn cho mẻ đếm.
- Xác suất dự đoán của mô hình fine-grained.
- Khoảng cách giữa embedding của ảnh và đại diện của lớp thuốc mục tiêu.
- Ngưỡng từ chối được hiệu chỉnh trên tập validation có các lớp thuốc lạ.

```text
Dự đoán đúng lớp
AND xác suất đạt ngưỡng
AND khoảng cách embedding đạt ngưỡng
    → chuyển sang tầng kiểm tra lỗi

Ngược lại
    → WRONG_DRUG
```

Các hướng huấn luyện embedding cần được benchmark gồm ArcFace và supervised contrastive learning. Ngưỡng từ chối phải được xác định bằng dữ liệu validation, không đặt tùy ý.

## 6. Tầng 4 — Kiểm tra viên bình thường hoặc lỗi

### Nhiệm vụ

Phân loại ROI của viên đã được xác nhận đúng loại thành:

- `normal`: viên đạt yêu cầu.
- `defective`: viên sứt, nứt, vỡ hoặc có bất thường bề mặt thuộc phạm vi dữ liệu huấn luyện.

### Dữ liệu

- PharmaVision dùng để huấn luyện và tạo mốc đánh giá ban đầu.
- Ảnh tự chụp bằng camera, ánh sáng, nền và cơ cấu thật dùng để fine-tune và đánh giá khả năng triển khai.

### Nguyên tắc

Ưu tiên Recall của lớp `defective`. Nếu tầng này không đủ chắc chắn, viên được đưa vào `DEFECTIVE` để tránh cho viên nghi lỗi vào ô đạt.

## 7. Luồng ra quyết định

```text
Không phát hiện viên
    → EMPTY_FRAME, máy không tăng bộ đếm

Phát hiện nhiều viên
    → MULTIPLE_PILLS, máy dừng hoặc cấp lại

Thuốc sai loại hoặc không chắc chắn
    → WRONG_DRUG

Đúng loại và bị lỗi
    → DEFECTIVE

Đúng loại và bình thường
    → ACCEPTED, tăng bộ đếm viên đạt
```

Chỉ kết quả `ACCEPTED` được tính vào số lượng cần đóng lọ.

## 8. Ranh giới giữa các thành phần

Mỗi tầng cung cấp một giao diện độc lập:

```text
detect(image) -> detection_result
recognize(pill_roi) -> identity_result
verify_open_set(identity_result, selected_drug) -> verification_result
inspect_defect(pill_roi) -> defect_result
decide(all_results) -> routing_command
```

Nhờ đó nhóm có thể thay một mô hình mà không phải sửa toàn bộ pipeline. Mỗi kết quả phải chứa nhãn, confidence, thời gian xử lý và lý do từ chối nếu có.

## 9. Dữ liệu và cách chia tập

- VAIPE dùng cho phát hiện và nhận diện loại thuốc.
- PharmaVision dùng cho phân loại `normal/defective`.
- Dữ liệu từ camera thật dùng để kiểm tra domain shift và fine-tune.
- Các ảnh cùng đơn thuốc hoặc cùng phiên chụp phải nằm trong cùng một split để tránh rò rỉ dữ liệu.
- `public_test` của VAIPE không có nhãn nên không dùng để báo cáo accuracy nội bộ.
- Phải tạo train, validation và test có nhãn từ `public_train`; test chỉ được dùng để đánh giá cuối cùng.

## 10. Chiến lược mô hình ưu tiên chất lượng

Không chọn một mô hình nhẹ ngay từ đầu rồi xem đó là kết quả cuối. Với mỗi tầng, nhóm huấn luyện một mô hình chất lượng cao làm mốc, một hoặc nhiều mô hình đối chứng, sau đó mới tối ưu mô hình triển khai trên Raspberry Pi 4. Nếu cần distillation, mô hình chất lượng cao đóng vai trò teacher và mô hình triển khai đóng vai trò student.

### Thứ tự thử nghiệm đã chốt

Sau khi hoàn thành audit và chia dữ liệu, nhóm thử mô hình theo thứ tự:

1. **YOLOv7 một lớp `pill`:** detector đầu tiên và là ứng viên chính thức, dùng để tạo ROI.
2. **DINO với ResNet-50:** mốc chất lượng cao để đo YOLOv7 làm giảm bao nhiêu Recall và chất lượng bounding box.
3. **FGVC-PIM:** nhận diện chi tiết loại thuốc từ ROI.
4. **ArcFace và supervised contrastive learning:** benchmark khả năng từ chối thuốc lạ.
5. **EfficientNetV2-S:** mô hình chính đầu tiên cho `normal/defective`.
6. **Xception và PatchCore:** đối chứng cho chất lượng chuyển miền và khả năng phát hiện bất thường.

Không chuyển sang tầng sau chỉ vì model đã train xong. Kết quả của mỗi tầng phải vượt qua cổng benchmark ở Mục 11 trước khi tích hợp.

### 10.1. Phát hiện viên và cắt ROI

| Vai trò | Mô hình | Lý do thử nghiệm |
|---|---|---|
| Teacher/chất lượng cao | DINO với backbone ResNet-50 | Detector Transformer mạnh, phù hợp làm mốc chất lượng và tạo ROI ổn định. |
| Mô hình theo cuộc thi | YOLOv7 | Được sử dụng trong giải pháp Pill Gates hạng nhất và pipeline UIT4meow của VAIPE 2022. |
| Ứng viên triển khai | YOLOv7-tiny | Nhẹ hơn để chạy trên Pi; chỉ được chọn nếu Recall và độ ổn định ROI đạt yêu cầu. |

Detector chỉ học một lớp `pill`. DINO không mặc định là mô hình chạy trên Pi; vai trò chính của nó là mốc chất lượng để biết mô hình nhẹ làm giảm bao nhiêu Recall và chất lượng bounding box.

Trong buồng chụp cố định, nhóm cũng phải đo một baseline thị giác máy tính truyền thống bằng phân đoạn nền. Baseline này không thay detector chính, nhưng giúp xác định mô hình học sâu có thực sự mang lại cải thiện hay không.

### 10.2. Fine-grained recognition

| Vai trò | Mô hình | Lý do thử nghiệm |
|---|---|---|
| Mô hình chính | FGVC-PIM với backbone ConvNeXt-Tiny hoặc EfficientNet | Tập trung vào vùng đặc trưng nhỏ, phù hợp với chữ dập, rãnh và dấu hiệu cục bộ trên viên thuốc. |
| Đối chứng mạnh | ConvNeXt-Tiny classifier | Đo mức cải thiện thật sự của module fine-grained so với backbone thông thường. |
| Đối chứng gọn | EfficientNet-B0/B2 | Cân bằng chất lượng, kích thước và khả năng triển khai. |
| Student triển khai | EfficientNet-B0 hoặc mô hình nhẹ được distillation | Chỉ dùng sau khi so sánh với teacher trên cùng tập kiểm tra. |

FGVC-PIM được ưu tiên vì bài toán nhận diện thuốc có khoảng cách giữa các lớp rất nhỏ. Tuy nhiên, nó chỉ được chọn chính thức nếu tăng Macro F1 và giảm nhầm lẫn ở các cặp thuốc khó so với classifier backbone.

Ảnh đầu vào của classifier phải là ROI độ phân giải đủ cao để giữ chữ và ký hiệu. Không resize quá nhỏ trước khi thực hiện thí nghiệm độ phân giải 224, 320 và 384 pixel.

### 10.3. Open-set recognition

Classifier closed-set luôn chọn một lớp đã biết, kể cả khi ảnh là thuốc lạ. Vì vậy tầng open-set là bắt buộc, không phải tính năng bổ sung.

Nhóm benchmark hai hướng embedding:

1. ArcFace: ép các mẫu cùng lớp gần nhau và các lớp khác nhau cách xa nhau theo biên góc.
2. Supervised contrastive learning: học không gian embedding từ nhiều cặp dương và âm trong một batch.

Tham khảo ePillID cho thấy metric learning với nhiều nhánh đặc trưng và bilinear features phù hợp với nhận diện viên thuốc ít mẫu. Với phạm vi của nhóm, triển khai ArcFace và supervised contrastive trước; chỉ thêm multi-head/bilinear khi hai hướng trên chưa tách được các lớp khó.

Quyết định `WRONG_DRUG` phải dựa trên cả xác suất classifier và khoảng cách embedding. Confidence sau huấn luyện cần được calibration bằng temperature scaling trên validation set. Ngưỡng từ chối được chọn bằng đường cong Precision–Recall của tập unknown, không chọn bằng quan sát vài ảnh.

### 10.4. Phát hiện viên lỗi

| Vai trò | Mô hình | Bằng chứng và mục đích |
|---|---|---|
| Mô hình chính | EfficientNetV2-S | Benchmark PharmaVision báo cáo F1 cao nhất 88,56% và khả năng chuyển sang pillQC thuộc nhóm tốt nhất. |
| Đối chứng mạnh | Xception | F1 87,08% trên PharmaVision và Recall lỗi cao; dùng để kiểm tra kết quả EfficientNetV2-S có ổn định không. |
| Đối chứng triển khai | MobileNetV3-small | Rất nhẹ nhưng chỉ được chọn nếu chất lượng trên dữ liệu camera thật đủ tốt; benchmark gốc cho thấy khả năng chuyển miền yếu. |
| Nhánh anomaly | PatchCore | Học từ vùng bình thường và có khả năng phát hiện bất thường chưa được gán nhãn; dùng làm thí nghiệm bổ sung và bản đồ vị trí lỗi. |

Mô hình lỗi chính vẫn là supervised classifier từ PharmaVision kết hợp dữ liệu tự chụp. PatchCore không thay thế classifier ngay; nó được đánh giá như một nhánh bổ sung vì memory bank có thể tốn bộ nhớ trên Pi và điểm anomaly cần được hiệu chỉnh riêng.

Nếu EfficientNetV2-S quá chậm trên Pi, ưu tiên distillation hoặc giảm độ phân giải có kiểm soát. Không chuyển thẳng sang MobileNetV3-small chỉ vì số tham số thấp.

### 10.5. Teacher, student và ensemble

- Ensemble chỉ dùng để xác lập mốc chất lượng trên máy huấn luyện, không mặc định chạy trên Pi.
- Teacher có thể là FGVC-PIM/ConvNeXt cho nhận diện và EfficientNetV2-S kết hợp Xception cho kiểm tra lỗi.
- Student học từ nhãn thật và soft target của teacher.
- Chỉ chấp nhận student nếu mức giảm chất lượng nằm trong giới hạn đã công bố trước và tốc độ trên Pi cải thiện rõ ràng.
- Quantization được thực hiện sau khi có checkpoint tốt; phải đo lại toàn bộ metric sau INT8 hoặc FP16.

## 11. Quy trình benchmark và cổng chất lượng

### 11.1. Nguyên tắc benchmark

- Mọi mô hình trong cùng một tầng dùng đúng một phiên bản dữ liệu và cùng train/validation/test split.
- Cố định seed và lưu cấu hình, checkpoint, log, dự đoán cùng từng lần chạy.
- Chọn checkpoint và ngưỡng bằng validation set; không chọn bằng test set.
- Báo cáo trung bình và độ lệch qua ít nhất ba lần chạy khi chi phí huấn luyện cho phép.
- Đánh giá riêng trên dữ liệu công khai và tập ảnh camera thật chưa xuất hiện khi huấn luyện.
- Ghi nhận số tham số, kích thước model, RAM cực đại và thời gian suy luận trực tiếp trên Raspberry Pi 4.

### 11.2. Metric bắt buộc

| Tầng | Metric quyết định |
|---|---|
| Phát hiện ROI | Recall, mAP50, tỷ lệ `EMPTY_FRAME` và `MULTIPLE_PILLS` đúng |
| Nhận diện loại | Macro F1, per-class Recall, confusion matrix, Top-1 và Top-3 accuracy |
| Open-set | AUROC unknown, AUPR unknown, Recall `WRONG_DRUG`, false acceptance rate |
| Kiểm tra lỗi | Recall `defective`, F2, F1, confusion matrix và cross-domain F1 |
| Toàn pipeline | Tỷ lệ đưa đúng ba ô, tỷ lệ thuốc sai lọt vào `ACCEPTED`, thời gian mỗi viên |

Trong bài toán này, accuracy tổng không đủ để chọn mô hình. Một mô hình có accuracy cao vẫn bị loại nếu bỏ sót nhiều thuốc lạ hoặc viên lỗi.

### 11.3. Cổng lựa chọn cuối cùng

Mô hình chỉ được đưa vào pipeline chính khi:

1. Tốt hơn hoặc tương đương baseline trên tập test có nhãn.
2. Không suy giảm nghiêm trọng trên tập camera thật.
3. Confidence đã được calibration và ngưỡng từ chối được lưu cùng checkpoint.
4. Kết quả có thể tái lập từ cấu hình và seed đã lưu.
5. Chạy được trong giới hạn RAM và thời gian xử lý chấp nhận được của một viên trên Pi 4.

Các ngưỡng số cụ thể sẽ được chốt sau lần baseline đầu tiên. Không đặt mục tiêu phần trăm khi chưa đo độ khó thật của các lớp thuốc được chọn.

## 12. Giới hạn đã biết

- Một camera nhìn từ trên xuống chỉ quan sát được một mặt viên thuốc.
- Hai loại thuốc giống nhau ở mặt trên nhưng khác ở mặt dưới không thể được phân biệt đáng tin cậy từ ảnh hiện có.
- Bản demo cần chọn các loại thuốc có đặc trưng quan sát được từ mặt camera, hoặc bổ sung cơ cấu chụp hai mặt nếu muốn mở rộng phạm vi.
- PharmaVision gộp nhiều dạng lỗi vào lớp `defective`; hệ thống hiện chỉ kết luận viên lỗi, không kết luận chính xác từng loại lỗi.

## 13. Cơ sở nghiên cứu

- [VAIPE Challenge 2022](https://aihub.ml/competitions/230): bài toán phát hiện, nhận diện thuốc và thuốc ngoài đơn; tiêu chí weighted mAP.
- [Baseline chính thức VAIPE](https://github.com/VAIPE-Challenge-2022/ai4vn-vaipe-baseline): YOLOv6s đạt khoảng 44% wmAP trên public test.
- [Pill Gates](https://github.com/huyenbui117/pill-yolov7): giải pháp hạng nhất public và private test, sử dụng ensemble YOLOv7, dữ liệu sinh, OCR và hậu xử lý theo đơn thuốc.
- [UIT4meow](https://github.com/hungcao0402/UIT4meow_VAIPE): pipeline tách phát hiện, DINO, FGVC-PIM và VietOCR.
- [PGPNet](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0291865): kết hợp đặc trưng thị giác với quan hệ đồng xuất hiện và kích thước tương đối giữa các viên thuốc.
- [DINO](https://arxiv.org/abs/2203.03605): detector Transformer dùng denoising anchor boxes, mixed query selection và box refinement.
- [FGVC-PIM](https://arxiv.org/abs/2202.03822): module fine-grained tìm và hợp nhất các vùng phân biệt cục bộ.
- [ePillID](https://www.microsoft.com/en-us/research/publication/epillid-dataset-a-low-shot-fine-grained-benchmark-for-pill-identification/): benchmark nhận diện thuốc ít mẫu với multi-head metric learning và bilinear features.
- [PharmaVision benchmark](https://www.mdpi.com/1999-4923/18/10/1287): so sánh 12 kiến trúc cho phân loại viên bình thường/lỗi và đánh giá chuyển miền sang pillQC.
- [PatchCore](https://arxiv.org/abs/2106.08265): anomaly detection dựa trên memory bank của đặc trưng patch bình thường.

