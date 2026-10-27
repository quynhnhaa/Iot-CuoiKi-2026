# So sánh detector trên cùng tập test VAIPE

Hai checkpoint đã được chọn bằng validation trước khi chấm test. Quyết định dùng YOLOv7 làm nguồn ROI cũng dựa trên validation: cùng COCOeval cho YOLOv7 AP@0.5:0.95 = **0,7676**, DINO = **0,7331**. Test bên dưới chỉ xác nhận xu hướng, không dùng để chỉnh ngưỡng. Tập test giữ riêng có **1.422 ảnh và 5.810 hộp**. Dự đoán được xuất về COCO JSON và cùng chấm bằng `pycocotools.COCOeval`, bbox IoU 0.50:0.95, `maxDets=[1,10,100]`, category `pill=0`.

| Model | COCO AP@0.5 | COCO AP@0.75 | COCO AP@0.5:0.95 | COCO AR@0.5, 100 hộp | COCO AR@0.5:0.95, 100 hộp |
|---|---:|---:|---:|---:|---:|
| YOLOv7 | 0,9892 | 0,8692 | **0,7422** | 0,9969 | 0,8013 |
| DINO/ResNet-50 | 0,9868 | 0,8448 | 0,7147 | **0,9990** | **0,8170** |

COCO AP của YOLOv7 cao hơn **2,75 điểm phần trăm** ở IoU 0.50:0.95. DINO có Recall cao hơn khi giữ tối đa 100 dự đoán/ảnh, nhưng nó xuất 300 ứng viên/ảnh, phần lớn score thấp; YOLOv7 xuất trung bình 4,5 hộp/ảnh sau NMS. Vì vậy AR không phải Recall của quyết định thả viên ở một ngưỡng vận hành.

Kiểm tra chẩn đoán ở score cutoff **0,25**, ghép hộp một-một theo confidence, IoU ≥0,5 (ngưỡng này chỉ để xem ROI, **không chốt từ test**):

| Model | Hộp sau cutoff | TP | FP | FN | Precision | Recall | IoU trung vị của hộp ghép đúng |
|---|---:|---:|---:|---:|---:|---:|---:|
| YOLOv7 | 5.823 | 5.791 | 32 | 19 | 0,9945 | 0,9967 | 0,8974 |
| DINO | 5.820 | 5.783 | 37 | 27 | 0,9936 | 0,9954 | 0,8962 |

**Quyết định cho nhánh ROI nhận diện đầu tiên:** dùng YOLOv7. Nó có AP validation cao hơn, số hộp ít, và thời gian inference đã đo ~5,2 ms/ảnh ở batch 8 trên RTX 5060 Ti (chưa gồm camera/nhận diện). DINO giữ vai trò mốc chất lượng. Ảnh [overlay ROI](pill-roi-preview.jpg) cho thấy hộp nhìn chung bám viên, nhưng có ít FP và viên chồng lấn; bước nhận diện phải đánh giá trên ROI dự đoán, không chỉ GT crop.

Giới hạn: DINO train detector từ đầu với backbone ImageNet pretrained, còn YOLOv7 khởi tạo từ checkpoint detection pretrained; đây là hai cấu hình thực tế đã chạy, không phải ablation ngang điều kiện khởi tạo. Tập VAIPE khác buồng chụp thật. Ngưỡng chấp nhận và chính sách `WRONG_DRUG` phải hiệu chỉnh trên validation và thử camera thật. Không dùng test để chỉnh ngưỡng.

- [Số liệu COCO chi tiết](pill-detector-common-coco.json)
- [Kiểm tra ROI](pill-roi-audit.json)
- Dự đoán: `model/runs/detector/yolov7_pill_common_eval/best_predictions.json`, `model/runs/detector/dino_pill_common_eval_predictions.json`.
- Script tái lập: `model/scripts/compare_pill_detectors_coco.py`, `model/scripts/audit_pill_rois.py`.
