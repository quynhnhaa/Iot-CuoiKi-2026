# Dữ liệu cho hai bài toán thị giác

- `external/`: bộ dữ liệu tải từ bên ngoài (ví dụ VAIPE), giữ nguyên file gốc và ghi rõ nguồn, giấy phép, ngày tải.
- `captured/`: ảnh/clip nhóm tự chụp, gồm ảnh điện thoại pilot và sau này là camera của máy; giữ nguyên bản gốc, ghi loại viên, điều kiện sáng, góc chụp, viên vật lý và phiên chụp. Xem [hướng dẫn và inventory](captured/README.md).
- `processed/recognition/`: ảnh/nhãn đã xử lý để kiểm tra **đúng loại so với mẫu của mẻ**. Có thể lưu `reference`, `same_type`, `other_type` hoặc định dạng phù hợp mô hình sau này.
- `processed/defect/`: ảnh/nhãn đã xử lý để kiểm tra **viên cùng loại nguyên hay sứt/vỡ**.
- `splits/`: danh sách file cho train/validation/test, dùng chung qua các lần thử để so sánh công bằng. Tách theo viên vật lý và phiên chụp nếu có thể, tránh ảnh gần trùng ở cả train và test.

Không đặt ảnh gốc vào `model/runs/`. Một viên khác loại đồng thời bị vỡ phải được ghi đủ thông tin gốc; quy tắc phân luồng ba ô sẽ xử lý sau khi hai bài toán đã cho kết quả.
