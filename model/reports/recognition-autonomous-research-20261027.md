# Nghiên cứu tiếp nhánh nhận diện — 27/10/2026

> **Đính chính về nhãn VAIPE 107:** Các phép đo unknown bên dưới đã xem `class_id=107` như một ID thuốc lạ. Tài liệu cuộc thi cho thấy 107 là nhãn **ngoài đơn theo ngữ cảnh**, có thể chứa viên thuộc ID đã biết. Vì vậy các tỷ lệ unknown trong báo cáo này chỉ là dấu vết thí nghiệm lịch sử, **không dùng để chọn cổng**. Xem [đánh giá lại bằng CPU sau khi sửa ngữ nghĩa nhãn](recognition-vaipe-solution-review-cpu-20261027.md).

## Mục tiêu và cách giữ phép đo

Người dùng cho phép dùng GPU và yêu cầu tự thử thuật toán. Mục tiêu là tăng tỷ lệ viên thuộc bảy ID được nhận đúng mà vẫn từ chối viên thuộc ID khác **trước khi thả**. Các ID VAIPE là nhãn hình ảnh nghiên cứu, chưa phải danh tính thuốc được đối chiếu. Không phương án nào ở đây được đưa vào máy.

Mọi lượt train mới chỉ dùng ROI train và 1.601 ROI thuốc lạ train thuộc 33 ID không xuất hiện trong unknown validation. Không đọc test VAIPE để chọn mô hình hoặc ngưỡng. Known validation vẫn chia theo SHA-256(`group_id`): 1.216 calibration và 727 phần còn lại. Phép đo cũ chia unknown validation theo nhóm ảnh nhưng còn trùng ID thuốc lạ giữa hai phía; để kiểm tra tổng quát hóa, tôi bổ sung chia **68 ID thuốc lạ thành hai tập không giao nhau**, cân số ROI theo số lượng nhãn trước khi xem điểm model: 1.917 ROI calibration và 1.916 ROI đánh giá. Các ID và kết quả chi tiết nằm trong [`results.json`](../runs/recognition/unseen_id_audit_20261027/results.json).

Nhóm validation này đã được xem qua nhiều thí nghiệm, nên mọi kết quả dưới đây chỉ là **chẩn đoán nghiên cứu**, chưa phải chứng nhận độc lập. Ngưỡng mỗi phương án được chọn trên calibration để unknown lọt tối đa 1%; số ở phía ID lạ chưa thấy là phép kiểm tra mức tổng quát hóa, không được dùng để chỉnh tiếp ngưỡng của chính phương án đó.

## Hướng thử và lý do

| Quan sát dẫn đến thử nghiệm | Thay đổi đã chạy | Quyết định sau kết quả |
|---|---|---|
| Verifier gốc bỏ hết ID 46/10; embedding có thể không thể hiện mật độ của viên đúng | kNN cosine trên embedding train, ba điểm `own`, `margin`, `joint` bằng GPU | Cổng kNN nhận đúng tối đa 9,79% known trên calibration ở mức 1% unknown; loại |
| Verifier bảy đầu sigmoid có thể chưa học trạng thái lạ trực tiếp | Đầu MLP tám trạng thái: bảy ID + unknown; 30 epoch GPU, lưu `last.pt` để resume | Ở nhóm theo ID lạ chưa thấy, 36,59% known, 10/1.916 unknown lọt; không hơn mốc gốc |
| Thuốc lạ có thể cần tác động vào backbone ảnh | Fine-tune PIM với outlier exposure từ 33 ID âm train, 4 epoch GPU; trích feature và train lại verifier | Macro F1 known validation giảm 97,72→93,78% ở best epoch 1; cổng đạt 30,54% known, 7/1.916 unknown lọt; loại |
| Vector combiner 256 chiều có thể làm mất chi tiết | Trích thêm ResNet layer4 2.048 chiều, chuẩn hóa và ghép trọng số 0,5; train verifier | Calibration 38,82% known, 19/1.917 unknown. Trên ID lạ chưa thấy: 40,44% known, 14/1.916 unknown; ID 46 vẫn 0 |
| Ngưỡng riêng theo ID trước đó tăng known nhưng vượt ngân sách lỗi chung | Tối ưu bảy ngưỡng bằng quy hoạch động với một ngân sách lỗi tổng 0,5% hoặc 1% trên calibration | Ở mức 1%, known tăng lên 50,21% nhưng unknown mới lọt **82/1.916 = 4,28%**; loại |
| Cổng gốc và đa tầng có thể bổ sung cho nhau | Trung bình điểm 50/50 cố định, hiệu chỉnh một ngưỡng chung | 39,20% known và 7/1.916 unknown ở nhóm ID mới; kết quả thăm dò, không được chọn theo calibration (ứng viên đa tầng cao hơn ở đó) |
| Backbone tự giám sát có thể giữ chi tiết khác ResNet | Trọng số [DINOv2 ViT-S/14 chính thức](https://github.com/facebookresearch/dinov2/blob/main/README.md), trích feature trên GPU; ghép PIM hoặc huấn luyện linear probe riêng | PIM+DINOv2 đạt 34,39% known, 8/1.916 unknown trên ID mới; linear probe DINOv2 macro F1 known validation 94,40% (PIM 97,72%) và verifier riêng chỉ nhận 21,60% known, lọt 32/1.710 unknown ở cách chia cũ; loại |
| 33 ID âm train có thể quá ít và một ID chiếm nhiều ảnh | Dùng 62 ID/10.664 ROI âm train, loại toàn bộ ID dành cho đánh giá; lấy mẫu âm cân bằng theo ID rồi train verifier | Calibration tăng đến 42,76% known nhưng ID lạ mới lọt **46/1.916 = 2,40%**; loại. Một phần ID calibration đã có trong train nên điểm calibration lạc quan |
| Dấu khắc và vân bề mặt có thể bị trung bình không gian che mất | Trích thêm độ lệch chuẩn theo không gian của 2.048 kênh ResNet layer4, ghép với PIM và trung bình layer4, train verifier | **Ứng viên nghiên cứu tốt nhất theo calibration**: 39,14% known, 19/1.917 unknown; trên ID lạ chưa thấy đạt 41,27% known, 11/1.916 unknown. ID 46 vẫn 0 |

Động cơ thử kNN đến từ [nghiên cứu Deep Nearest Neighbors](https://proceedings.mlr.press/v162/sun22d.html); outlier exposure từ [công trình gốc](https://arxiv.org/abs/1812.04606); thử backbone tự giám sát dựa trên [DINOv2](https://arxiv.org/abs/2304.07193). Các bài này đề xuất phương pháp tổng quát; số liệu ở bảng là phép đo của **dự án này** và không suy ra từ bài báo.

## So sánh trên ID thuốc lạ không có trong calibration

Ngưỡng của từng hàng được chọn lại **chỉ trên calibration của phép chia này**. Known dùng 727 ROI từ các nhóm ảnh còn lại; unknown dùng 1.916 ROI từ các ID khác hoàn toàn 1.917 ROI calibration.

| Phương án | Known đúng được chấp nhận | Unknown bị nhận nhầm | ID 46 | ID 10 |
|---|---:|---:|---:|---:|
| PIM gốc + verifier gốc | 36,73% | 7/1.916 (0,37%) | 0/28 | 0/38 |
| PIM + màu HSV/RGB | 27,10% | 1/1.916 (0,05%) | 0/28 | 0/38 |
| Đầu tám trạng thái | 36,59% | 10/1.916 (0,52%) | 0/28 | 0/38 |
| PIM outlier exposure + verifier | 30,54% | 7/1.916 (0,37%) | 0/28 | 0/38 |
| PIM + layer4 + verifier | **40,44%** | 14/1.916 (0,73%) | 0/28 | 7/38 |
| PIM + DINOv2 + verifier | 34,39% | 8/1.916 (0,42%) | 0/28 | 0/38 |
| Verifier với 62 ID âm cân bằng | 39,20% | **46/1.916 (2,40%)** | 0/28 | 30/38 |
| PIM + layer4 trung bình/độ biến thiên | **41,27%** | 11/1.916 (0,57%) | 0/28 | 8/38 |

Ở ứng viên không gian, có **300/727 known được nhận đúng, 0/727 known được nhận sai** trong nhóm này. Theo từng ID: **64: 20/113, 91: 128/155, 89: 84/142, 99: 40/151, 51: 20/100, 46: 0/28, 10: 8/38**. Tỷ lệ gộp 41,27% che đi độ phủ rất lệch giữa các loại viên; không thể xem đó là tỷ lệ nhận diện ổn định cho cả bảy ID.

Với ứng viên không gian, 11 ROI thuốc lạ lọt thuộc **5 trong 115 nhóm ảnh** có ID lạ dành cho đánh giá: ID 2 có 4 ROI bị đoán thành ID 10, ID 3 có 4 ROI bị đoán thành ID 89, ID 7 có 2 ROI bị đoán thành ID 46, ID 23 có một ROI bị đoán thành ID 99. Tỷ lệ theo nhóm có ít nhất một lỗi là **5/115 = 4,35%**; đây là phép đo khác tỷ lệ theo ROI vì một nhóm có nhiều cơ hội xảy ra lỗi. Ngay cả tính các ROI như phép thử độc lập để minh họa, cận trên nhị thức 95% cho 11/1.916 khoảng **1,02%**; phụ thuộc giữa ROI và việc đã xem validation làm bằng chứng thực tế yếu hơn.

## Kết luận và điểm dừng hợp lý

Tầng ResNet bổ sung cải thiện độ phủ gộp và bắt đầu nhận một số ROI ID 10; thêm độ biến thiên không gian giảm số ROI lạ lọt so với chỉ lấy trung bình. Tuy vậy ID 46 vẫn bị loại toàn bộ và vẫn có viên lạ gần giống lọt. Phép gộp điểm 50/50 với cổng gốc được đo cố định: với cổng không gian, 39,61% known và 8/1.916 unknown; nó không được chọn theo calibration. Không có bằng chứng để bật `ACCEPTED` tự động. Việc tiếp tục chọn loss hoặc ngưỡng trên cùng validation sẽ làm phép đo kém tin cậy; cần **ảnh mới từ camera, ánh sáng và cơ cấu thật**, gắn với thuốc có danh tính đã đối chiếu. Chụp cả hai mặt khi có thể, nhất là dấu khắc mờ ở ID tròn sáng và hai đầu nang hai màu. Nghiên cứu [ePillID](https://arxiv.org/abs/2005.14288) cũng xem hai mặt là thông tin riêng trong bài toán nhận diện viên thuốc; đây là lý do thực nghiệm để thu thêm góc nhìn, không phải bảo đảm rằng thêm ảnh sẽ giải quyết mọi cặp.

Trước khi vận hành, khóa tập đánh giá camera theo **phiên chụp, viên vật lý và ID thuốc lạ**; đối chiếu nhãn với bao bì/lô; đo tỷ lệ nhận đúng từng thuốc, số thuốc lạ lọt, ảnh mờ bị từ chối và thời điểm dừng cơ cấu. `data/captured` hiện chưa có ảnh camera thật. Khi thiếu bằng chứng, hệ thống phải dừng trước khi thả và trả `WRONG_DRUG` để kiểm tra thủ công.

Các bước thu và chia tập ảnh được ghi cụ thể trong [kế hoạch dữ liệu camera](recognition-camera-evaluation-plan.md).

## Tái lập và dấu vết

- Script: `evaluate_recognition_knn.py`, `train_recognition_unknown_head.py`, `finetune_recognition_pim_oe.py`, `extract_recognition_features.py --extra-layer4 --extra-layer4-std`, `build_recognition_multilayer_features.py`, `build_recognition_spatial_features.py`, `evaluate_recognition_unseen_ids.py`, `optimize_recognition_class_thresholds.py`, `evaluate_recognition_score_fusion.py`, `extract_recognition_dinov2.py`, `build_recognition_dinov2_features.py`, `train_recognition_dinov2_probe.py`, `train_recognition_verifier_diverse_unknown.py` trong `model/scripts/`.
- Checkpoint, manifest, kết quả JSON và feature `.npz`: `model/runs/recognition/` với tên run nêu trong script; log văn bản ở `model/reports/`.
- DINOv2 ViT-S/14: trọng số chính thức ở `model/.cache/torch/hub/checkpoints/dinov2_vits14_pretrain.pth`, checksum và transform trong [`manifest.json`](../runs/recognition/dinov2_vits14_features_20261027/manifest.json). Kích thước 84,2 MiB. Source Python dùng cache Torch Hub được ghi trong manifest.
- Fine-tune outlier exposure lưu model/optimizer/scheduler/scaler/RNG từng epoch và kiểm tra LR khi resume. Resume đúng mốc epoch và LR; thứ tự ảnh/augmentation của DataLoader sau khởi động lại **không được bảo đảm bitwise trùng**. Run đã hoàn thành 4/4.
