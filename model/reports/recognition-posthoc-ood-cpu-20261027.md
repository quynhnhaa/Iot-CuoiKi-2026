# Thử các điểm OOD hậu kiểm trên đặc trưng PIM (CPU, 27/10/2026)

Script: `scripts/benchmark_posthoc_ood_cpu.py`; kết quả: `runs/recognition/posthoc_ood_cpu_20261027/results.json`.
Giao thức giống [báo cáo sửa VAIPE](recognition-vaipe-solution-review-cpu-20261027.md): bỏ 107, ngưỡng chọn trên calibration với unknown FAR ≤ 1%, báo trên phía ID lạ chưa thấy (727 known, 1.414 unknown). Không train, không đọc test. Thống kê Gaussian/kNN/ViM chỉ fit trên train-known.

Mốc so sánh: cổng gốc nhận 404/727 (55,57%) known, lọt 26/1.414.

| Điểm | Known nhận đúng | Unknown lọt | Ghi chú |
|---|---:|---:|---|
| MSP | 19,94% | 36 | |
| Energy | 15,82% | 41 | |
| Mahalanobis (Lee 2018) | 25,72% | 26 | ID 46 lần đầu được nhận (6/28) |
| Relative Mahalanobis | 6,74% | 28 | |
| kNN k=1 / k=10 | 8,25% / 12,79% | 7 / 11 | |
| ViM | 20,77% | 38 | |
| Mahalanobis so với tâm thuốc lạ train (33 ID, đã loại mọi ID unknown validation) | 28,47% | **3** | Chỉ ID 91/89 được nhận nhiều |

Lần chạy đầu của dòng cuối cho 60,66% known / 27 lọt, nhưng tập âm khi đó chứa **cùng ID** với phía đánh giá. Kết quả đó bị loại vì rò rỉ.

**Kết luận:** không phương pháp hậu kiểm nào vượt cổng gốc về độ phủ ở cùng mức an toàn. Dòng cuối an toàn hơn rõ (3 so với 26) nhưng chỉ phủ 2/7 ID. Không thay cổng vận hành.
