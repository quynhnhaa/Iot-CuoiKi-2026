# Báo cáo tổng hợp AI — máy đếm và loại viên

*Cập nhật: 27/10/2026. Đây là báo cáo chính để đọc kết quả hiện tại. Các báo cáo thí nghiệm cũ được giữ làm hồ sơ truy vết; số liệu lịch sử dùng định nghĩa “thuốc lạ” khác không thay thế kết quả đã sửa dưới đây.*

## 1. Kết luận hiện tại

Pipeline nghiên cứu đã chạy được trên ảnh VAIPE: **YOLOv7 phát hiện viên → cắt ROI → FGVC-PIM nhận diện ID → đầu xác minh → EfficientNetV2-S kiểm tra lỗi → quyết định**. Detector và bộ nhận diện 7 lớp có kết quả tốt khi đánh giá đúng phạm vi của chúng. **Hệ thống chưa đủ căn cứ để tự động thả viên**: bộ xác minh còn nhận nhầm một số ID thuốc lạ, mô hình lỗi bỏ sót nhiều viên sứt trên bộ ảnh khác miền, và chưa có ảnh từ camera/buồng chụp thật.

Trong bản replay hiện tại, `identity_verified=False`, `identity_gate_validated=False`, `hardware_ready=False`. Ảnh hoặc danh tính không đủ chắc chắn trả `WRONG_DRUG` và dừng trước khi thả. Chưa có kết nối động cơ/cảm biến thật; bộ đếm chỉ có thể tăng sau cảm biến xác nhận viên rơi trong bản tích hợp sau này.

| Thành phần | Trạng thái | Kết quả cần nhớ |
|---|---|---|
| Nền dữ liệu | Hoàn thành audit/split | VAIPE còn 9.476 cặp ảnh–nhãn hợp lệ; PharmaVision giữ split gốc |
| Phát hiện viên | Có checkpoint YOLOv7 một lớp `pill` | COCO AP@0.5:0.95 test 74,22%; tạo ROI cho nhận diện |
| Nhận diện ID | Có FGVC-PIM 7 ID | Accuracy closed-set test 97,75%; **không đo khả năng từ chối thuốc lạ** |
| Xác minh thuốc lạ | Đang nghiên cứu | Cổng theo ID mục tiêu còn 24 trường hợp lạ lọt trên 1.414 ROI thuộc ID đánh giá mới, gộp 7 tình huống mục tiêu |
| Viên sứt/lỗi | Có EfficientNetV2-S nghiên cứu | Trên pillQC mới miền, bỏ sót 17/43 viên sứt |
| Pipeline | Có replay CPU và mô phỏng quyết định | 4 ảnh replay, 0 lệnh thả, 0 tăng bộ đếm |

Các ID VAIPE là nhãn ảnh, **không xác nhận hoạt chất hoặc thuốc thật**. Không suy ra độ an toàn của máy từ những tỷ lệ trên.

## 2. Dữ liệu và phạm vi các lớp

- VAIPE ban đầu có 9.502 cặp ảnh/nhãn. Loại **đồng thời ảnh và nhãn** của 26 cặp lỗi (1 JPEG bị cắt đuôi, 25 box không hợp lệ sau EXIF), còn 9.476 cặp. Split theo nhóm chụp: train 6.633 ảnh / 21.103 box; validation 1.421 / 5.794; test 1.422 / 5.810. Không thấy nhóm chụp giao nhau giữa các split. Danh sách loại trừ: [excluded-invalid-pairs.csv](../../data/processed/vaipe/excluded-invalid-pairs.csv).
- PharmaVision có 640 ảnh; giữ split tác giả: 380 train, 60 validation, 200 test.
- YOLOv7 chỉ cần biết **có viên thuốc**, nên học một lớp `pill` trên toàn bộ VAIPE hợp lệ. Nhánh gọi tên thuốc ở vòng đầu chỉ học bảy ID đã chọn: **64, 91, 89, 99, 51, 46, 10**. Đây là phạm vi thử nghiệm, không có nghĩa VAIPE chỉ có bảy loại thuốc. Cấu hình ở [selected-classes.json](../configs/recognition/selected-classes.json).
- Nhãn VAIPE **107** mang nghĩa “ngoài đơn thuốc” theo ngữ cảnh, không phải một ID ngoại hình thuốc lạ. Những phép đo unknown lịch sử có tính 107 không dùng làm kết luận cuối cho xác minh danh tính. Đánh giá đã sửa loại 107 khỏi tập unknown ngoại hình; không gán nó thành known.

## 3. Phát hiện viên và tạo ROI

YOLOv7 một lớp được train 30 epoch, best epoch 29; DINO/ResNet-50 4-scale train 12 epoch. Cùng chấm bằng COCOeval trên 1.422 ảnh, 5.810 box test:

| Model | AP@0.5 | AP@0.75 | AP@0.5:0.95 | AR@0.5:0.95 |
|---|---:|---:|---:|---:|
| YOLOv7 | 98,92% | 86,92% | **74,22%** | 80,13% |
| DINO | 98,68% | 84,48% | 71,47% | **81,70%** |

Chọn YOLOv7 để xuất ROI theo validation AP@0.5:0.95: 76,76% so với DINO 73,31%. DINO có AR cao hơn khi giữ thêm ứng viên điểm thấp; AR này chưa phải recall ở ngưỡng thả viên. Checkpoint YOLOv7: [best.pt](../runs/detector/yolov7_pill_baseline_20261025_v2/weights/best.pt).

ROI được ghép một-một giữa hộp YOLOv7 và nhãn gốc với IoU ≥ 0,5, thêm lề crop 10%. Trong bảy ID, có **9.590 crop hợp lệ**: train 5.782, validation 1.943, test 1.865. Mười nhãn không ghép được bị loại khỏi metric classifier, không gán sai sang hộp khác. Dữ liệu: [yolov7_rois](../../data/processed/vaipe/recognition/yolov7_rois).

## 4. Nhận diện danh tính và thuốc lạ

**FGVC-PIM/ResNet-50 bảy lớp** hoàn thành 20 epoch, best epoch 17; macro F1 validation 97,72%. Trên 1.865 ROI test thuộc đúng bảy lớp đã học: accuracy **97,75%**, macro F1 **97,79%**; nhầm lẫn nổi bật là 30 mẫu ID 89 thành ID 99. Closed-set buộc mọi ảnh vào một trong bảy lớp, nên kết quả này không đủ để quyết định thả viên khi có loại thuốc ngoài bảy ID.

Để đo khả năng từ chối, tập unknown validation được loại nhãn ngữ cảnh 107, rồi chia theo **ID thuốc lạ**: 1.414 ROI hiệu chỉnh và 1.414 ROI thuộc ID chưa xuất hiện trong phía hiệu chỉnh. Known validation gồm 1.216 ROI hiệu chỉnh và 727 ROI từ nhóm ảnh khác. Đây là validation **đã được xem nhiều lần**, không phải test độc lập mới.

| Chính sách xác minh trên phía giữ riêng | Known đúng được nhận | Unknown ID mới bị nhận nhầm |
|---|---:|---:|
| Cổng PIM + verifier gốc, một ngưỡng chung | 404/727 (55,57%) | 26/1.414 (1,84%) |
| Cổng theo **ID thuốc mục tiêu**, ngưỡng nghiêm ngặt từng ID | 337/727 (46,35%) | 24 trường hợp trên 1.414 ROI unknown |
| Đầu MLP mới theo ID mục tiêu | 368/727 (50,62%) | 25 trường hợp trên cùng 1.414 ROI |

Dòng thứ hai và ba cộng kết quả của **bảy tình huống thuốc mục tiêu giả định** trên cùng tập ảnh, không phải tỷ lệ sai của một mẻ máy chỉ có một mục tiêu. Ở cổng theo mục tiêu, từng ID là: 64 **70/113 đúng, 0 lạ**; 91 **135/155, 0**; 89 **114/142, 17**; 99 **7/151, 1**; 51 **1/100, 0**; 46 **0/28, 0**; 10 **10/38, 6**. ID 46 bị loại hết; ID 89 và 10 có thuốc lạ gần giống lọt qua. Ngưỡng được đặt để không chấp nhận ROI sai trên phần hiệu chỉnh, nhưng điều đó không bảo đảm cho ID chưa thấy.

Đã thử ArcFace/SupCon, verifier theo ID, đặc trưng màu, đặc trưng không gian ResNet, DINOv2, kNN, điểm OOD hậu kiểm, huấn luyện thêm âm, kiểm tra xoay ảnh, covariance bilinear và đầu MLP. Một số phương pháp tăng số viên đúng được nhận nhưng cũng tăng thuốc lạ lọt, hoặc giảm lỗi lạ bằng cách từ chối quá nhiều viên đúng. MLP mới tăng 337 → 368 viên đúng nhưng lạ lọt 24 → 25; xoay và bilinear không loại được lỗi lạ nào. **Không thay cổng vận hành theo các thử nghiệm này.**

Đã thử thêm DINOv2 phân loại nhiều ID trên GPU như một hướng mở rộng quá bảy lớp: closed-set bảy ID đạt 98,76%, nhưng khi dùng âm train tách hẳn ID unknown validation, cách chấm tốt nhất về độ phủ trong lượt nghiêm ngặt chỉ nhận 48,56% known và vẫn lọt 32 unknown. Vì vậy việc học thêm nhiều ID chưa tự giải quyết khả năng từ chối loại chưa thấy. Repo có script/checkpoint nghiên cứu; pipeline replay vẫn dùng PIM bảy lớp.

## 5. Kiểm tra viên lỗi

Baseline PharmaVision train trên 380 ảnh, validation 60, test 200. ResNet-50 đóng băng được chọn theo validation; trên test đã mở, nó nhận 96/100 viên lỗi nhưng bỏ sót 4/100 và báo lỗi nhầm 56/100 viên bình thường. EfficientNetV2-S đóng băng cũng bỏ sót 4/100 và báo nhầm 62/100. Test đó không còn độc lập để chọn điều chỉnh mới.

Fine-tune hai block cuối EfficientNetV2-S trên CPU, không dùng test cũ để chọn. Best epoch **12** (dừng sớm ở epoch 18), ngưỡng 0,40: validation nhận **30/30** viên lỗi, báo nhầm **8/30** viên bình thường, F2 **94,94%**. Checkpoint lưu optimizer, scheduler và RNG; kiểm tra resume từ epoch 12 cho epoch 13–18 khớp metric, loss và learning rate của run gốc.

Đánh giá chuyển miền trên pillQC, giữ nguyên checkpoint/ngưỡng, chỉ dùng 43 ảnh `chip` và 149 ảnh `normal`: nhận **26/43** viên sứt, bỏ sót **17/43**, báo lỗi nhầm **2/149** viên bình thường; F2 **65,00%**. Không dùng pillQC để chỉnh ngưỡng. Kết quả cho thấy mô hình này chưa đủ tin cậy cho ảnh ngoài miền huấn luyện hoặc cơ cấu thật. Checkpoint nghiên cứu: [best.pt](../runs/defect/efficientnetv2s_finalblocks_cpu_20261027/best.pt); dự đoán từng ảnh: [predictions.csv](defect-pillqc-cross-domain-20261027/predictions.csv).

## 6. Pipeline chạy thử và an toàn dừng

[replay_ai_pipeline_cpu.py](../scripts/replay_ai_pipeline_cpu.py) dùng YOLOv7 thật trên CPU, sau đó ROI, PIM, verifier chẩn đoán, defect và [decision_simulator.py](../src/common/decision_simulator.py). Replay ba ảnh VAIPE validation và một frame trống giả lập:

| Đầu vào | Số viên YOLOv7 | Quyết định |
|---|---:|---|
| `VAIPE_P_306_0` | 1 | `WRONG_DRUG` — danh tính chưa được xác minh |
| `VAIPE_P_102_14` | 1 | `WRONG_DRUG` — danh tính chưa được xác minh |
| `VAIPE_P_1027_0` | 2 | `MULTIPLE_PILLS` |
| Frame trống giả lập | 0 | `EMPTY_FRAME` |

**0 lệnh thả, 0 tăng bộ đếm.** Thời gian toàn lượt 181–528 ms/ảnh trên laptop CPU cho bốn ảnh này, không gồm khởi tạo model; không phải benchmark Raspberry Pi/camera thật. Logic quyết định có **16/16 kiểm thử đạt**, nhưng chưa kiểm thử cơ cấu hoặc cảm biến. Output run: [events.jsonl](../runs/pipeline/validation_model_replay_with_empty_cpu_20261027/events.jsonl), [summary.json](../runs/pipeline/validation_model_replay_with_empty_cpu_20261027/summary.json), [run-manifest.json](../runs/pipeline/validation_model_replay_with_empty_cpu_20261027/run-manifest.json).

## 7. Việc cần làm tiếp và cách chạy lại

1. Thu ảnh từ **camera và buồng chụp của máy**, ghi ID thuốc thật đã đối chiếu, ảnh thuốc đúng, thuốc sai gần giống, viên lỗi và nhiều góc/mặt khi có thể. [Mẫu manifest và quy tắc chia](../../data/captured/README.md) đã có; hiện chưa có ảnh camera thật.
2. Khóa trước tập đánh giá độc lập theo **viên vật lý, phiên chụp và ID thuốc lạ**. Đánh giá từng thuốc mục tiêu về nhận đúng, nhận nhầm thuốc khác, từ chối khi ảnh mờ/che khuất và lỗi chất lượng. Validation VAIPE đã xem nhiều lần chỉ còn dùng chẩn đoán.
3. Chỉ sau khi hai cổng danh tính và lỗi qua tiêu chí của hệ thống, tích hợp camera, động cơ, cảm biến xác nhận rơi; đo độ trễ và thử dừng trước khi thả trên Raspberry Pi/cơ cấu thật. Giữ `ACCEPTED` tự động tắt đến lúc đó.

**File chạy chính:** [pipeline replay](../scripts/replay_ai_pipeline_cpu.py), [logic quyết định](../src/common/decision_simulator.py). Lệnh phát lại mẫu, môi trường và giới hạn được ghi ở [PIPELINE-REPLAY-SETUP.md](../PIPELINE-REPLAY-SETUP.md). Hướng dẫn tái lập riêng: [detector](../DETECTOR-SETUP.md), [nhận diện](../RECOGNITION-SETUP.md), [kiểm tra lỗi](../DEFECT-SETUP.md). Nhật ký theo mạch *kết quả → lý do → thay đổi → quyết định* ở [NHAT-KY-LAM-VIEC-AI.md](NHAT-KY-LAM-VIEC-AI.md); đây là nhật ký, không phải báo cáo thứ hai cần đọc để nắm kết luận.
