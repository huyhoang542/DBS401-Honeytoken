# Schema kết quả thí nghiệm Demo B

Áp dụng database/comparison_schema.sql một lần lên schema honeytoken_security_b. File tạo các bảng:

- experiment_runs: phiên bản demo, dataset, ngân sách token, bộ kịch bản, seed và cấu hình mô hình.
- experiment_query_results: một dòng cho mỗi kịch bản, gồm nhãn thực tế/dự đoán, điểm rủi ro và độ trễ.
- placement_update_history: mỗi lần di chuyển honeytoken và chi phí đo được.

Benchmark ghi CSV/JSON trong thư mục results/. Có thể dùng evaluation/persist_results.py --apply để ghi các dòng benchmark tổng hợp vào database. Nhãn dương ở benchmark nghĩa là hành vi đáng ngờ theo kịch bản đã sinh, không đơn thuần là truy vấn trả về honeytoken.
