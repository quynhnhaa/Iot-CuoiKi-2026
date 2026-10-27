# Vì sao ID 46 và 10 không được cổng nhận — audit CPU

> **Lưu ý sau nghiên cứu VAIPE:** Các bảng unknown lịch sử của audit này có thể chứa nhãn 107 “ngoài đơn” theo ngữ cảnh. Chỉ dùng ảnh để tìm cặp ngoại hình khó, không diễn giải toàn bộ nhóm unknown là thuốc có danh tính khác. Xem [đánh giá lại đã loại 107](recognition-vaipe-solution-review-cpu-20261027.md).

Phân tích lại checkpoint **PIM gốc + verifier theo ID** trên nhóm validation giữ riêng (727 ROI known, 1.710 ROI unknown). Script [`audit_recognition_id46_id10.py`](../scripts/audit_recognition_id46_id10.py) chạy trên CPU, nối đúng từng feature với manifest ROI, xuất [bảng điểm](recognition-id46-id10-audit/scores.csv), [JSON](recognition-id46-id10-audit/summary.json) và [ảnh sát ranh giới](recognition-id46-id10-audit/hard-cases.jpg). Không dùng test VAIPE.

| Nhóm | Số ROI | PIM dự đoán đúng | Trung vị điểm cổng | Điểm cổng cao nhất | Được nhận ở ngưỡng chung 0,97057 |
|---|---:|---:|---:|---:|---:|
| ID 46 đúng | 28 | **28/28** | 0,9125 | 0,9305 | 0 |
| Thuốc lạ bị PIM đoán 46 | 238 | — | 0,7232 | **0,9321** | 0 |
| ID 10 đúng | 38 | **38/38** | 0,9391 | 0,9663 | 0 |
| Thuốc lạ bị PIM đoán 10 | 447 | — | 0,2262 | **0,9615** | 0 |

PIM **không phân loại sai** 66 ROI known này. Lỗi nằm ở cổng xác minh: xác suất classifier của viên đúng rất cao, nhưng điểm verifier thấp hơn ngưỡng chung. Với ID 46, điểm cao nhất của thuốc lạ còn cao hơn điểm cao nhất của viên đúng trong nhóm này; hạ ngưỡng để nhận bất kỳ mẫu ID 46 nào sẽ đồng thời nhận ít nhất một mẫu thuốc lạ ở nhóm đã đo. Với ID 10, phân bố có phần chồng lấn và nhiều thuốc lạ được PIM dự đoán thành 10; ID lạ 2 là một nguồn cạnh tranh nổi bật.

[Ảnh sát ranh giới](recognition-id46-id10-audit/hard-cases.jpg) cho thấy các viên tròn sáng màu cạnh tranh với ID 46 và các nang đỏ/cam–vàng cạnh tranh với ID 10. Màu, ánh sáng, kích thước ảnh và mặt viên thay đổi nhiều trong VAIPE. Đây là quan sát hình ảnh, **không chứng minh hai nhãn là cùng hay khác hoạt chất**.

**Quyết định:** không hạ ngưỡng dựa trên các ảnh đã xem và không tự động thả. Thu dữ liệu từ camera/buồng chụp thật với danh tính thuốc được đối chiếu, mặt trước/sau và điều kiện ánh sáng ghi rõ. Manifest và kiểm tra dữ liệu được chuẩn bị tại [data/captured/README.md](../../data/captured/README.md).
