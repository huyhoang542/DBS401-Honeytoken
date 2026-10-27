# DBS401 Honeytoken Project

Đồ án nghiên cứu và trình diễn honeytoken trên cơ sở dữ liệu quan hệ.

## Vai trò của hai demo

- **Demo A — mốc tham chiếu theo bài báo:** SDV/HMA học cấu trúc/phân bố quan hệ để sinh honeytoken nhiều bảng; vị trí phòng ban giữ theo quan hệ HMA sinh. Monitor phát cảnh báo theo token-hit. Đây là bản triển khai giáo dục, chưa tái hiện human evaluation hay khẳng định tái tạo mọi chiến lược triển khai của bài báo.
- **Demo B — phần nâng cấp của đồ án:** dùng cùng nội dung HMA để đối chiếu; Random Forest học từ telemetry để phân tích hành vi/cảnh báo và chấm điểm rủi ro phòng ban nhằm phân bổ vị trí. Đây là phần mở rộng, không phải phương pháp của bài báo gốc.

Hai demo dùng Employee Sample Database, cùng ngân sách token và cùng kịch bản tấn công. So sánh chính đo số phiên/truy vấn tấn công thực sự trả về token; chất lượng phân loại Random Forest được trình bày riêng. Nhãn tấn công do kịch bản kiểm thử gán, không đại diện cho sự cố hoặc môi trường sản xuất.

## Bắt đầu

1. Làm theo [hướng dẫn Demo A](DemoA/README.md) để chuẩn bị database và baseline.
2. Làm theo [hướng dẫn Demo B](DemoB/README.md) để chạy phần nâng cấp, huấn luyện mô hình và dashboard.
3. Xem [kết quả đối chiếu](DemoB/comparison/RESULTS.md) và [nguồn dữ liệu/phương pháp](DemoB/comparison/PAPER_AND_TRAINING_DATA.md).
4. Tài liệu tổng hợp: [Nguồn dữ liệu và kết quả demo](Nguon_du_lieu_va_ket_qua_demo_Honeytoken.docx).

