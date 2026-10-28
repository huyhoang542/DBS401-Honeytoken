# Schema so sánh chung cho Demo A và Demo B

Hai demo có thể lưu metadata thí nghiệm và kết quả theo cùng định dạng trong các bảng so sánh.

- experiment_runs: một dòng cho mỗi lần chạy độc lập, gồm phiên bản demo, phiên bản dataset, ngân sách token, bộ kịch bản, seed và cấu hình mô hình.
- experiment_query_results: một dòng cho mỗi kịch bản, dùng nhãn thực tế/dự đoán nhị phân và độ trễ. risk_score có thể để trống cho Demo A tĩnh.
- placement_update_history: một dòng cho mỗi lần đổi vị trí token. Demo A có thể không phát sinh dòng nào.

Áp dụng database/comparison_schema.sql một lần trên schema dùng chung của Demo A. Các bảng registry, access_events và security_alerts hiện có không bị thay đổi. Hai demo cần dùng cùng dataset, ngân sách token, bộ kịch bản, định nghĩa nhãn và quy trình chạy. Khi báo cáo, dùng các kịch bản giữ lại để đánh giá; không gộp nhiều lần chạy vào cùng một run_id.

Quy ước nhãn: actual_label=1 nghĩa là truy cập honeytoken hoặc hành vi đáng ngờ theo chính sách nhãn đã ghi cho thí nghiệm. predicted_label=1 nghĩa là detector phát cảnh báo. Ghi định nghĩa nhãn trong experiment_runs.notes hoặc model_config. Mỗi kịch bản đã thử cần được ghi đúng một lần; lỗi chạy cần ghi riêng, không tính ngầm thành mẫu âm tính.
