# Nghiên cứu giải pháp VAIPE và sửa phép đo nhận diện — chỉ CPU

*27/10/2026. Đây là phép đánh giá lại trên train/validation đã được xem; không đọc test để chọn model/ngưỡng, không dùng GPU và không thay cổng máy.*

## Phát hiện quyết định từ thể lệ VAIPE

[Thể lệ chính thức](https://www.aihub.ml/competitions/230) mô tả hai nhiệm vụ: phát hiện viên và nhận diện **thuốc ngoài đơn**, khuyến khích sử dụng thông tin đơn thuốc. Nhãn `107` được đánh trọng số cao trong wmAP của cuộc thi. [Mô tả của một đội VAIPE](https://github.com/lynguyenminh/VAIPE2022.Medicine-Pill-Image-Recognition) giải thích rõ: cùng một loại viên có thể là thuốc trong đơn này và **ngoài đơn khác**, nên `class_id=107` có thể chứa ngoại hình của các ID đã biết. Mã [Pill Gates](https://github.com/huyenbui117/pill-yolov7/blob/main/ensemble_postprocess.py) cũng đổi nhãn dự đoán thành 107 khi ID đó không có trong danh sách từ OCR đơn thuốc.

Trước đây nhánh nghiên cứu của dự án đã dùng toàn bộ ID ngoài bảy lớp, **kể cả 107**, làm “thuốc lạ về ngoại hình”. Đây là sai khác giữa nhãn ngữ cảnh và danh tính viên. Trong feature ROI cũ, 107 chiếm **6.458/15.302 ROI train unknown** và **1.005/3.833 ROI validation unknown**. Không thể khẳng định từng ROI 107 là một loại thuốc mới, nên tôi loại 107 khỏi phép đo open-set ngoại hình; không gán nó thành known hay unknown. Các ROI còn lại được lưu **riêng** trong [`yolov7_unknown_identity`](../../data/processed/vaipe/recognition/yolov7_unknown_identity/report.json) và [`open_set_identity_features_20261027`](../runs/recognition/open_set_identity_features_20261027/manifest.json); dữ liệu và báo cáo cũ được giữ để truy vết.

Các verifier PIM gốc và verifier đặc trưng không gian đã train bằng ID âm **không có trong unknown validation**, vì vậy 107 không nằm trong mẫu âm huấn luyện của hai run này. Có thể đánh giá lại checkpoint đã có mà không train lại. Ngưỡng và phép chia unknown cũ thì phải thay.

## Bài học từ các giải pháp công khai

| Nguồn | Ý tưởng có bằng chứng trong mã/tài liệu | Ứng dụng vào máy đếm viên |
|---|---|---|
| [Baseline VAIPE](https://github.com/VAIPE-Challenge-2022/ai4vn-vaipe-baseline) | Khuyến nghị dùng ràng buộc logic từ đơn thuốc, không chỉ detector | Máy đã biết **thuốc mục tiêu do người vận hành chọn**; đây là thông tin ngữ cảnh để xác minh viên trước khi thả |
| [UIT4meow](https://github.com/hungcao0402/UIT4meow_VAIPE) | Pipeline công khai dùng YOLOv7/DINO, FGVC-PIM và VietOCR | Dự án đã thử YOLOv7, DINO detector và PIM; OCR đơn không cần thiết nếu máy nhận mã thuốc mục tiêu trực tiếp |
| [Pill Gates](https://github.com/huyenbui117/pill-yolov7) | Ensemble detector, OCR đơn, hậu xử lý các lớp gần giống; mã chuyển nhãn không có trong đơn thành 107 | Dùng thuốc mục tiêu để giới hạn quyết định, đồng thời coi các lớp gần giống là ca phải kiểm tra kỹ; không xem 107 là một hình dạng thuốc |

Điểm wmAP của cuộc thi ưu tiên phát hiện/nhận diện ngoài đơn trong ảnh nhiều viên. Nó không đo trực tiếp xác suất **máy thả nhầm một viên**; vì vậy không lấy điểm cuộc thi hoặc nhãn 107 làm ngưỡng vận hành.

## Phép đánh giá CPU đã sửa

Giữ 1.216 ROI known calibration và 727 ROI known từ nhóm ảnh khác. Sau khi bỏ 107, 2.828 ROI unknown validation thuộc **67 ID** được chia cân số lượng theo ID thành 1.414 ROI calibration và 1.414 ROI thuộc ID **không xuất hiện trong calibration**. Hai checkpoint được đánh giá trên CPU với temperature và ngưỡng chọn lại chỉ từ calibration. Tất cả dữ liệu validation đã từng được xem, nên đây là chẩn đoán, không phải phép thử độc lập.

| Cổng một ngưỡng, không biết thuốc mục tiêu | Known đúng được nhận trên 727 ROI | Other known bị nhận sai | Unknown ID mới bị nhận nhầm |
|---|---:|---:|---:|
| PIM gốc + verifier gốc | **404/727 (55,57%)** | 0/727 | **26/1.414 (1,84%)** |
| PIM + layer4 trung bình/biến thiên | 387/727 (53,23%) | 0/727 | 25/1.414 (1,77%) |

Cả hai vượt mục tiêu khảo sát 1% trên ID lạ chưa thấy. Vì ngữ nghĩa nhãn và tập calibration đã đổi, không so trực tiếp phần trăm này với số 41,27%/11/1.916 trong báo cáo trước rồi kết luận model mới “kém đi”. Báo cáo cũ đã được đánh dấu **lịch sử, không dùng để chọn cổng**.

## Thử quy tắc có thuốc mục tiêu

Máy chỉ nên xem một viên là ứng viên chấp nhận nếu PIM dự đoán **đúng ID mục tiêu đang được chọn**. Tôi đánh giá lại bảy ngưỡng xác minh, mỗi ngưỡng chỉ dùng tín hiệu của ID mục tiêu. Để kiểm tra giới hạn an toàn, phiên bản nghiêm ngặt chọn ngưỡng sao cho trên calibration có **0 viên khác thuộc bảy ID được nhận** và **0 ROI unknown được nhận** cho từng mục tiêu. Đây là thử nghiệm hồi cứu trên validation, chưa phải quy tắc triển khai.

| Verifier và ngưỡng nghiêm ngặt | Known mục tiêu được nhận đúng, gộp bảy tình huống | Other known bị nhận sai | Unknown bị nhận trong bảy tình huống mục tiêu giả định |
|---|---:|---:|---:|
| PIM gốc | 337/727 (46,35%) | 0 | 24/1.414 |
| PIM không gian | 424/727 (58,32%) | 0 | 33/1.414 |

Số unknown ở cột cuối là tổng lỗi của **bảy tình huống thuốc mục tiêu khác nhau trên cùng tập ảnh**, không phải tỷ lệ lỗi cho một mẻ máy có một mục tiêu. Cần xem từng mục tiêu:

| ID mục tiêu | PIM gốc: viên đúng được nhận | PIM gốc: unknown lọt | PIM không gian: viên đúng được nhận | PIM không gian: unknown lọt |
|---:|---:|---:|---:|---:|
| 64 | 70/113 | 0/1.414 | 59/113 | 1/1.414 |
| 91 | 135/155 | 0/1.414 | 128/155 | 0/1.414 |
| 89 | 114/142 | 17/1.414 | 118/142 | 18/1.414 |
| 99 | 7/151 | 1/1.414 | 81/151 | 8/1.414 |
| 51 | 1/100 | 0/1.414 | 29/100 | 0/1.414 |
| 46 | 0/28 | 0/1.414 | 0/28 | 0/1.414 |
| 10 | 10/38 | 6/1.414 | 9/38 | 6/1.414 |

ID 91 là ca nghiên cứu triển vọng trong tập VAIPE này; 0 lỗi trên 1.414 ROI không bảo đảm an toàn khi gặp viên lạ hoặc camera khác. ID 46 vẫn không có viên nào được nhận. Với các lớp 89/10, quy tắc nghiêm ngặt vẫn lọt viên lạ thuộc ID chưa từng dùng để chọn ngưỡng. Nới mỗi ngưỡng đến 1% unknown trên calibration làm lỗi ở ID mới tăng mạnh (ví dụ ID 10 của PIM không gian: 62/1.414), nên không chọn.

## Thử đầu xác minh mới trên CPU

Để kiểm tra liệu học trực tiếp theo thuốc mục tiêu có hơn việc dùng lại bảy đầu verifier cũ, tôi train **bảy đầu tuyến tính** trên embedding PIM gốc. Mỗi đầu nhận known đúng là dương; các known khác và 1.601 ROI âm thuộc 33 ID không có trong unknown validation là âm. Trọng số âm tăng theo độ gần cosine tới centroid của ID mục tiêu, chỉ tính từ train. Train 200 epoch bằng PyTorch **CPU**, không thêm phụ thuộc mới; ngưỡng vẫn yêu cầu 0 wrong-known và 0 unknown được nhận trên calibration.

| ID mục tiêu | Đầu tuyến tính mới: known đúng được nhận | Thuốc lạ ID mới lọt | Cổng PIM gốc phía trên: known đúng được nhận |
|---:|---:|---:|---:|
| 64 | 61/113 | 0/1.414 | 70/113 |
| 91 | 132/155 | 0/1.414 | 135/155 |
| 89 | 109/142 | 14/1.414 | 114/142 |
| 99 | 5/151 | 1/1.414 | 7/151 |
| 51 | 1/100 | 0/1.414 | 1/100 |
| 46 | 0/28 | 0/1.414 | 0/28 |
| 10 | 2/38 | 6/1.414 | 10/38 |

Đầu mới không cải thiện độ phủ và vẫn lọt các ID lạ khó; **không chọn**. Lệnh thử ban đầu dùng `sklearn` nhưng môi trường dự án không cài thư viện đó; tôi chuyển sang lớp tuyến tính PyTorch có sẵn trước khi chạy train, không thay dữ liệu hay tiêu chí đánh giá. Checkpoint và kết quả: [`heads.npz`](../runs/recognition/vaipe_target_logistic_cpu_20261027/heads.npz), [`validation-results.json`](../runs/recognition/vaipe_target_logistic_cpu_20261027/validation-results.json).

## Quyết định và tái lập

**Không thay checkpoint hay bật `ACCEPTED`.** Sửa dữ liệu đánh giá là tiến bộ quan trọng hơn một lượt train mới: nó loại một nhãn ngữ cảnh gây nhiễu, phơi bày rằng các cổng hiện tại vẫn nhận nhầm thuốc lạ. Bước nghiên cứu tiếp có thể dùng thuốc mục tiêu làm tín hiệu xác minh và thu ảnh camera/viên thật đã đối chiếu, nhưng không lấy ID VAIPE làm danh tính thuốc thật.

```bash
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/filter_vaipe_context_unknown.py
CUDA_VISIBLE_DEVICES='' .venv/bin/python model/scripts/evaluate_vaipe_target_gate_cpu.py
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 .venv/bin/python model/scripts/train_vaipe_target_logistic_cpu.py
```

Kết quả máy đọc được: [`results.json`](../runs/recognition/vaipe_target_gate_cpu_20261027/results.json). Script không đọc test và không dùng GPU.
