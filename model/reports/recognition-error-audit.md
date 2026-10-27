# Kiểm tra ảnh nhận diện sai và thuốc lạ lọt ngưỡng

> **Đính chính:** Ảnh mang nhãn VAIPE 107 là “ngoài đơn” theo ngữ cảnh, không chứng minh danh tính thuốc lạ. Các ví dụ 107 trong audit này chỉ còn là ảnh chẩn đoán ngoại hình. Xem [đánh giá CPU đã loại 107](recognition-vaipe-solution-review-cpu-20261027.md).

Script [`audit_recognition_errors.py`](../scripts/audit_recognition_errors.py) nối từng hàng `.npz` với manifest ROI tương ứng, tính lại đúng ngưỡng SupCon đã khóa và xuất CSV cùng ảnh ghép vào [`recognition-error-audit`](recognition-error-audit/). Các ảnh test ở đây chỉ dùng để chẩn đoán kết quả **đã công bố**; không dùng để chọn ngưỡng của thí nghiệm tiếp theo.

| Nhóm lỗi | ROI | Nhóm ảnh độc lập |
|---|---:|---:|
| Known validation bị phân loại sai | 29/1.943 | — |
| Unknown validation bị chấp nhận | 38/3.833 | 19 |
| Known test bị phân loại sai | 40/1.865 | — |
| Unknown test bị chấp nhận | 19/3.927 | 9 |

Trong 29 lỗi known validation, cặp **89→99** có 17 ROI và **99→89** có 3 ROI. Ảnh ghép cho thấy nhiều viên trắng dài có đường rãnh rất gần nhau; góc chụp, ánh sáng và độ rõ của rãnh làm hai ID khó phân biệt.

Unknown bị chấp nhận tập trung theo ID: validation có **19 ROI ID 107**, **9 ROI ID 2**; test có **9 ROI ID 107**, **6 ROI ID 2**. ID 107 đã được báo cáo dữ liệu mô tả là không đồng nhất về ngoại hình; ảnh kiểm tra xác nhận nó chứa viên tròn nhiều màu, viên nang và nhiều bề mặt khác nhau. Một số ROI thuốc lạ rất giống lớp known về hình và màu (chẳng hạn viên nang hai màu). Chỉ bằng ảnh không thể kết luận chúng cùng hay khác hoạt chất; nhãn VAIPE cũng không đủ để xác minh điều đó.

Nhiều ROI unknown được chấp nhận có xác suất sau temperature scaling và cosine gần **1,0**. Vì vậy không thể coi các điểm này là xác suất an toàn vận hành. Bước thử tiếp theo dùng ROI unknown từ **train** làm ví dụ âm cho một bộ từ chối học trên embedding PIM; tách validation theo `group_id` để chọn ngưỡng và đo trên nhóm chưa dùng chọn ngưỡng. Tập test hiện tại không dùng để chỉnh mô hình mới.

Các ảnh ghép: [known validation](recognition-error-audit/validation-known-misclassified.jpg), [unknown validation](recognition-error-audit/validation-unknown-false-accepted.jpg), [unknown test](recognition-error-audit/test-unknown-false-accepted.jpg).
