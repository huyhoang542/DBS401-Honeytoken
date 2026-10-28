# Đối chiếu bài báo gốc, Demo A và phần nâng cấp Demo B

## Kết luận kiểm tra độ khớp với bài báo

Bài báo gốc là Prabhaker, Bopche và Arock, “Generation and deployment of honeytokens in relational databases for cyber deception”, *Computers & Security*, tập 146, bài 104032 (2024), DOI 10.1016/j.cose.2024.104032.

Nội dung có thể xác nhận từ trang nhà xuất bản và phần tóm tắt/toàn văn được lập chỉ mục:

- HMA trong thư viện SDV được dùng để sinh dữ liệu tổng hợp cho cơ sở dữ liệu quan hệ nhiều bảng, bảo toàn đặc tính thống kê và cấu trúc/quan hệ cha-con.
- Dữ liệu tổng hợp được triển khai làm honeytoken; mô-đun giám sát theo dõi truy cập và phát cảnh báo.
- Bài báo đánh giá độ tin cậy của honeytoken bằng đánh giá con người.
- Bài báo có phần riêng mô tả workflow và các chiến lược triển khai. Tuy nhiên, bản toàn văn hiện chưa được xác minh đầy đủ để kết luận code ở đây tái tạo chính xác từng chiến lược triển khai.

Nguồn: [ScienceDirect — bài báo gốc](https://www.sciencedirect.com/science/article/pii/S0167404824003377); [bản thảo SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4827562).

## Ánh xạ đúng với mã đồ án

| Thành phần | Bài báo | Demo A trong đồ án | Demo B trong đồ án |
|---|---|---|---|
| Nội dung token | SDV/HMA sinh dữ liệu nhiều bảng | SDV HMASynthesizer sinh employee và các bảng con liên quan | Dùng lại đúng cùng candidate HMA như A để giữ nội dung và ngân sách cố định |
| Vị trí | Bài báo có các chiến lược triển khai; không nên tự gán thuật toán RF cho bài báo | Dùng phân công phòng ban do bản ghi quan hệ HMA sinh ra làm mốc vị trí | Dùng Random Forest/điểm rủi ro phòng ban để phân bổ vị trí |
| Phát hiện/cảnh báo | Theo dõi truy cập honeytoken và báo quản trị viên | Quy tắc token-hit: bản ghi trả về trùng registry thì ghi sự kiện/cảnh báo | Phân loại hành vi truy vấn bằng RF; có thể đánh giá thêm biến thể RF OR token-hit |
| Đánh giá độ tin cậy | Có human evaluation | Chưa thực hiện human evaluation của bài báo | Chưa thực hiện human evaluation của bài báo |

**Cách mô tả học thuật chính xác:** Demo A là bản tham chiếu giáo dục theo hướng HMA/SDV của bài báo, không phải tái tạo đầy đủ bài báo. Vị trí A là phòng ban HMA tạo trong quan hệ nhiều bảng; không khẳng định đây là thuật toán placement tối ưu hay chính xác một chiến lược triển khai trong bài báo khi chưa đối chiếu toàn văn. Demo B là phần mở rộng đồ án: giữ nội dung HMA, dùng RF để chọn vị trí theo rủi ro và phân tích cảnh báo hành vi. HMA không phân loại cảnh báo; cảnh báo A là token-hit, còn RF phân tích hành vi là phần B.

## Câu hỏi nghiên cứu và phép so sánh

Câu hỏi placement: khi cùng một kịch bản truy vấn mục tiêu được chạy trên cùng database với cùng ngân sách và nội dung token, hệ nào trả về honeytoken thường xuyên hơn — vị trí theo quan hệ HMA (A) hay phân bổ RF theo rủi ro (B)?

Câu hỏi cảnh báo: trên cùng phiên hành vi có nhãn kịch bản, quy tắc token-hit của A và bộ phân loại RF của B khác nhau thế nào về precision, recall, F1 và tỷ lệ báo động giả? Đây là phép đo khác với placement; không gộp hai nhóm chỉ số.

Bộ kiểm thử placement mới dùng tất cả phòng ban theo mặc định, với ba kiểu truy vấn lặp lại giống hệt trên A/B:

1. 250 ID nhân viên cao nhất trong phòng ban — giữ làm chẩn đoán bão hòa, không đưa vào chỉ số placement chính.
2. Mẫu có thứ tự giả ngẫu nhiên gồm tối đa 25 nhân viên, seed thay đổi theo lần lặp.
3. 25 nhân viên có ngày tuyển dụng sớm nhất trong phòng ban.

Mặc định 20 lần lặp theo cặp. Chỉ số chính gồm tỷ lệ phiên có ít nhất một token hit, tỷ lệ truy vấn có hit, và số lượt dòng token thực sự trả về. Kịch bản/đầu ra đều được ghi theo phòng ban và lần lặp. Truy vấn 250 ID cao nhất phải xem riêng vì token đang dùng dải ID cao, có thể làm phép đo bão hòa. Kết quả trước đây chỉ có 10/10 phiên hit ở hai mục tiêu d001/d002; nó không chứng minh RF placement tốt hơn.

## Dữ liệu huấn luyện và nhãn

Tách rõ ba nguồn, không gọi chúng chung là “dữ liệu thật”:

1. **Employee Sample Database:** dữ liệu quan hệ công khai dùng làm database đích và nguồn HMA tạo nội dung token. Nó không cung cấp log hành vi người dùng, nhãn benign/attack hay lịch sử xâm nhập. [Bytebase Employee Sample Database](https://github.com/bytebase/employee-sample-database/tree/main/mysql).
2. **Benchmark tổng hợp:** `evaluation/run_common_scenarios.py` tạo đặc trưng và nhãn bằng NumPy với seed cố định. Đây là dữ liệu giả lập để so sánh thuật toán, không phải log thu thập ngoài đời.
3. **Telemetry MySQL lab:** `evaluation/run_live_attack_simulation.py` thu đặc trưng từ SELECT có giới hạn thực thi trên MySQL localhost. Nhãn bình thường/đáng ngờ do kịch bản thử nghiệm gán; không phải nhãn từ sự cố thực tế. Model live Demo B học từ telemetry của phòng lab này.

Nguồn liên quan có log truy vấn SQL thực như PhoneLab nhưng không có nhãn tấn công và là workload SQLite di động; LANL có sự kiện an ninh doanh nghiệp/Red Team nhưng không phải database audit SQL. Không dùng hai nguồn này như thể chúng là log tấn công MySQL. [PhoneLab SQL trace](https://odin.cse.buffalo.edu/papers/2015/TPCTC-sqlite-final.pdf); [LANL Cyber Security Research](https://csr.lanl.gov/data/cyber1/).

## Chạy capture và huấn luyện sau khi người dùng sẵn sàng

Từ thư mục `RandomForest/`, sau khi cả A và B đã có candidate/token và `.env` trỏ cùng DB `employee`:

```powershell
python evaluation\run_live_attack_simulation.py --capture-only
python evaluation\train_live_model.py
python -m streamlit run dashboard\app.py
```

Có thể giới hạn phòng ban/lượt chạy, nhưng phải dùng cùng danh sách cho A/B:

```powershell
python evaluation\run_live_attack_simulation.py --capture-only --target-departments d001,d002 --repeats 20
```

Capture chỉ SELECT trên localhost và thay thế các file kết quả hiện tại, vì vậy chỉ chạy khi muốn tạo bộ kết quả mới. Không cần chạy lại generator/apply token để chỉ kiểm tra kịch bản.

Artifacts sau capture/train:

- `results/live_attack_query_results.csv` — log từng SELECT, hit, nhãn và telemetry.
- `results/live_attack_placement_session_results.csv` — hit theo phiên/lượt.
- `results/live_attack_placement_scenario_metrics.csv` — tổng hợp theo mục tiêu/phương pháp truy vấn.
- `results/live_attack_session_results.csv` và `live_attack_scenario_metrics.csv` — đánh giá cảnh báo theo phiên/kịch bản.
- `results/live_attack_metrics.json` — protocol, tóm tắt placement và phân loại.
- `models/random_forest_live_sim.joblib`, `models/live_sim_model_metadata.json` — mô hình B và metadata nguồn/nhãn.

## Giới hạn cần ghi trong báo cáo

- Đây là mô phỏng lab kiểm soát, không phải kiểm thử thâm nhập và không dùng nhãn sự cố thực tế.
- Cùng một database/candidate giúp so sánh có kiểm soát, nhưng token ID cao và cách truy vấn vẫn có thể gây thiên lệch; phải báo cáo riêng các kiểu truy vấn và không chỉ lấy một tỷ lệ hit tổng.
- Các lần lặp của cùng script không tương đương mẫu độc lập từ nhiều người dùng/tổ chức. Không diễn giải accuracy/FPR là hiệu năng ngoài thực địa.
- Chưa đánh giá human believability như bài báo; chưa khẳng định tái tạo chính xác deployment strategies của bài báo.
- Demo A cảnh báo theo truy cập token. Demo B phân tích hành vi bằng RF; đây là hai cơ chế khác nhau.
