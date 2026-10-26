# DBS401 Honeytoken Project

Đồ án nghiên cứu và trình diễn honeytoken trên cơ sở dữ liệu quan hệ.

## Vai trò của hai demo

- **Demo A — baseline tham chiếu:** triển khai paper-inspired/static honeytoken để làm mốc đối chiếu với phương pháp bài báo. Demo A không phải phần nâng cấp chính của đồ án.
- **Demo B — phần nâng cấp của đồ án:** thu thập telemetry truy vấn, chấm điểm rủi ro bằng Random Forest và thử nghiệm kết hợp honeytoken với bố trí token thích nghi.

Hai demo dùng Employee Sample Database làm dữ liệu mục tiêu và được so sánh trên các kịch bản dùng chung. Nhãn tấn công trong mô phỏng được gán bởi kịch bản kiểm thử; kết quả không đại diện cho hiệu quả trên sự cố hoặc môi trường sản xuất.

## Bắt đầu

1. Làm theo [hướng dẫn Demo A](DemoA/README.md) để chuẩn bị database và baseline.
2. Làm theo [hướng dẫn Demo B](DemoB/README.md) để chạy phần nâng cấp, huấn luyện mô hình và dashboard.
3. Xem [kết quả đối chiếu](DemoB/comparison/RESULTS.md) và [nguồn dữ liệu/phương pháp](DemoB/comparison/PAPER_AND_TRAINING_DATA.md).
4. Tài liệu tổng hợp: [Nguồn dữ liệu và kết quả demo](Nguon_du_lieu_va_ket_qua_demo_Honeytoken.docx).

