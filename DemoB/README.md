# Demo B Honeytoken thích nghi bằng học máy

**Demo B là phần nâng cấp và đóng góp chính của đồ án.** Demo A chỉ là bản tham chiếu theo phương pháp bài báo, dùng làm baseline đối chứng để đánh giá xem Demo B cải thiện ra sao. Demo B bổ sung telemetry hành vi truy vấn, mô hình Random Forest chấm điểm rủi ro, kết hợp phát hiện honeytoken và thử nghiệm bố trí token theo rủi ro phòng ban. Hai demo dùng chung database Employee Sample và kịch bản so sánh, nhưng giữ registry riêng.

## 1. Thành phần và cơ sở dữ liệu

- Database nghiệp vụ dùng chung: employee.
- Registry, log và cảnh báo Demo B: honeytoken_security_b.
- Dải ID token Demo B: 910001–910050 (nội dung lấy từ HMA, vị trí theo Random Forest).
- Dải HMA Demo A: 910051–910100 (nội dung và vị trí lấy từ HMA).
- Dataset mục tiêu là bộ Bytebase Employee Sample Database, bản dataset_large có 10.000 nhân viên. Đây là dữ liệu mẫu; bản thân nó không chứa lịch sử truy vấn hay nhãn tấn công.

Demo B có gateway truy vấn, bộ thu telemetry, Random Forest, dashboard Streamlit và mô-đun thử nghiệm adaptive placement. Cài thư viện:

~~~powershell
Set-Location D:\FPTU\Course\DBS401_Project\DemoB
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
~~~

Điền thông tin kết nối vào .env. Với so sánh A/B, cả hai demo phải dùng DB_NAME=employee. Không chép mật khẩu vào README hoặc Git.

## 2. Xóa token cũ và chạy lại từ đầu

> Chỉ chạy trên MySQL lab cục bộ dùng chung `employee`. Với `--apply`, reset xóa token và dòng con trong các dải `900001–900050`, `910001–910050`, `910051–910100`, registry, toàn bộ log truy cập/cảnh báo của hai demo và các file kết quả/mô hình mà dashboard đọc. Nó giữ nhân viên thường, schema và file sao lưu `live_attack_query_results.before-reset.csv`.

### Bước 1 — xem trước phạm vi xóa

~~~powershell
Set-Location D:\FPTU\Course\DBS401_Project\DemoB
.\.venv\Scripts\Activate.ps1
python database\reset_lab_honeytokens.py
~~~

Nhập thông tin MySQL administrator khi được hỏi. Lệnh mặc định chỉ in số hàng sẽ bị xóa. Xác nhận host là `localhost`, port đúng và database là `employee`.

### Bước 2 — xóa token cũ

~~~powershell
python database\reset_lab_honeytokens.py --apply
~~~

Chạy sau khi dry-run hiển thị đúng phạm vi. Script hỏi lại thông tin administrator và xóa trong transaction. Không chạy lại nếu không chủ động muốn xóa các dải này.

### Bước 3 — sinh và nạp Demo A bằng HMA

~~~powershell
Set-Location D:\FPTU\Course\DBS401_Project\DemoA
.\.venv\Scripts\Activate.ps1
~~~

Nếu đã có `database\hma_artifacts\employee_hma.pkl`, dùng model đã fit; nếu chưa có, bỏ `--reuse-model` (lần fit đầu có thể lâu):

~~~powershell
python database\generate_hma_honeytokens.py --reuse-model
python database\apply_hma_honeytokens.py
python database\apply_hma_honeytokens.py --apply --admin
~~~

Lệnh thứ hai là dry-run. Kiểm tra dòng ứng viên và dải ID trước lệnh thứ ba. HMA sinh nội dung liên quan nhiều bảng; mỗi token có đúng một phòng ban hiện hành theo vị trí HMA.

### Bước 4 — bootstrap Random Forest cho Demo B

Capture khởi tạo dùng huấn luyện RF khi B chưa có token; **không dùng kết quả này so sánh vị trí**. Capture sẽ ghi đè CSV kết quả truy vấn. Sao lưu file hiện có trước nếu cần giữ lại:

~~~powershell
Set-Location D:\FPTU\Course\DBS401_Project\DemoB
.\.venv\Scripts\Activate.ps1
if (Test-Path .\results\live_attack_query_results.csv) { Copy-Item .\results\live_attack_query_results.csv .\results\live_attack_query_results.before-reset.csv }
python evaluation\run_live_attack_simulation.py --capture-only --bootstrap-rf
python evaluation\train_live_model.py
~~~

Đặc trưng model được đo từ truy vấn MySQL; nhãn bình thường/tấn công do kịch bản đặt, không phải nhãn sự cố thực tế.

### Bước 5 — ghi điểm rủi ro theo phòng ban

Chạy từng truy vấn qua gateway để RF chấm điểm và lưu risk score theo phòng ban:

~~~powershell
python monitoring\query_gateway.py --department d001 --limit 100
python monitoring\query_gateway.py --department d002 --limit 100
python monitoring\query_gateway.py --department d003 --limit 100
python monitoring\query_gateway.py --department d004 --limit 100
python monitoring\query_gateway.py --department d005 --limit 100
python monitoring\query_gateway.py --department d006 --limit 100
python monitoring\query_gateway.py --department d007 --limit 100
python monitoring\query_gateway.py --department d008 --limit 100
python monitoring\query_gateway.py --department d009 --limit 100
~~~

### Bước 6 — tạo và nạp Demo B

~~~powershell
python database\generate_rf_honeytokens.py
python database\apply_rf_honeytokens.py
python database\apply_rf_honeytokens.py --apply --admin
~~~

Generator chỉ ghi candidate CSV vào `database\rf_artifacts`; không ghi MySQL. Lệnh apply đầu là dry-run. Chỉ chạy lệnh cuối sau khi xác nhận dải `910001–910050` còn trống. Demo B dùng cùng nội dung HMA như A, còn vị trí phòng ban được phân bổ theo điểm rủi ro RF.

### Bước 7 — chạy cùng mục tiêu attacker trên A và B

Capture/train cuối sẽ ghi đè file kết quả trước; sao lưu trước nếu cần. Mặc định mục tiêu là tất cả phòng ban; mọi phòng ban và cách truy vấn đều chạy giống nhau trên A/B:

~~~powershell
if (Test-Path .\results\live_attack_query_results.csv) { Copy-Item .\results\live_attack_query_results.csv .\results\live_attack_query_results.before-placement.csv }
python evaluation\run_live_attack_simulation.py --capture-only --repeats 20
python evaluation\train_live_model.py
python evaluation\run_common_scenarios.py
~~~

Mặc định chạy mọi phòng ban trong 20 lần lặp theo cặp. Mỗi phòng ban có truy vấn lấy mẫu seeded tối đa 25 dòng và truy vấn 25 nhân viên có ngày tuyển dụng sớm nhất; đây là chỉ số placement chính. Query 250 ID cao nhất chỉ là chẩn đoán bão hòa. Khi truyền `--target-departments`, dùng cùng danh sách cho cả A/B. Lệnh benchmark tạo bộ dữ liệu tổng hợp riêng cho tab 3; nó không đọc MySQL và không trộn với kết quả live.

### Bước 8 — mở dashboard và đọc kết quả

~~~powershell
python -m streamlit run dashboard\app.py
~~~

Dashboard có ba tab: **Hiệu quả vị trí honeytoken** đo token thực sự được trả về theo phòng ban/cách truy vấn; **Cảnh báo và phát hiện hành vi ML** so sánh quy tắc token-hit A với RF B theo phiên và từng kịch bản; **Benchmark tổng hợp** trình bày riêng các mẫu NumPy giả lập. Kết quả placement nằm trong `results\live_attack_placement_session_results.csv`, `results\live_attack_placement_scenario_metrics.csv` và `placement_evaluation` trong `results\live_attack_metrics.json`. Tab vận hành đã bỏ. Sau reset các artifacts này bị xóa và dashboard để trống cho đến khi bạn chạy lại capture/train hoặc benchmark.

## 3. Cổng truy vấn và bố trí thích nghi

Ví dụ chạy gateway:

~~~powershell
python monitoring\query_gateway.py --ids 10001,10002,910001
python monitoring\query_gateway.py --department d001 --limit 100
~~~

Gateway giới hạn truy vấn, kiểm tra các bản ghi trả về với registry, ghi access event và phát cảnh báo khi có token hit. Các đặc trưng và dự đoán gần đây được ghi vào results/behavior_events.sqlite3.

Chạy truy vấn phòng ban qua gateway để có dữ liệu rủi ro, sau đó xem đề xuất bố trí:

~~~powershell
python adaptive\placement.py --dry-run
~~~

Chỉ dùng --apply sau khi kiểm tra đề xuất và đã cấp quyền UPDATE/INSERT cần thiết. Mô-đun này thay đổi phân công phòng ban của token và lưu lịch sử; không thay đổi lương nhân viên.

## 4. Huấn luyện từ telemetry và dashboard

Để capture và huấn luyện lại từ đầu, hai registry phải có 50 token hoạt động, và hai file .env phải dùng chung DB_NAME=employee. Từ thư mục DemoB:

~~~powershell
python evaluation\run_live_attack_simulation.py --capture-only
python evaluation\train_live_model.py
python -m streamlit run dashboard\app.py
~~~

Capture placement dùng các truy vấn SELECT có giới hạn trên MySQL cục bộ. Mặc định kiểm tra tất cả phòng ban và chạy 20 lần lặp theo cặp; có thể giới hạn `--target-departments d001,d002` và đặt `--repeats 20`. Mỗi phòng ban có ba mục tiêu truy vấn giống hệt trên A/B: lấy 250 ID cao nhất (chẩn đoán bão hòa), lấy mẫu có thứ tự giả ngẫu nhiên tối đa 25 dòng và lấy 25 nhân viên có ngày tuyển dụng sớm nhất. Hai phép sau là chỉ số placement chính; truy vấn ID cao nhất được báo riêng vì ID token cao có thể khiến mọi truy vấn hit. Capture chỉ đọc MySQL.

Model live Demo B dùng các đặc trưng đo được: số dòng trả về, giờ truy vấn, số bảng đích, tần suất truy vấn trong session, thời lượng và cờ truy vấn phòng ban. Mô hình là Random Forest. Kịch bản gán nhãn bình thường/tấn công mô phỏng; đây không phải nhãn từ sự cố thực tế. Ngưỡng hiện lưu ở models/live_sim_model_metadata.json. Điểm RF theo phòng ban còn được dùng để chọn vị trí token B.

Các kịch bản gồm: tra cứu từng ID thông thường, báo cáo hàng loạt hợp lệ, truy vấn bảo trì, dò ID nhanh, quét phòng ban, thu thập nhiều bản ghi, truy vấn chậm có chủ đích, cùng từng tổ hợp phòng ban × mục tiêu (ID mới nhất, mẫu giả ngẫu nhiên, ngày tuyển dụng sớm). Kịch bản kiểm tra token chủ động biết ID canary để xác nhận detector; nó được báo riêng và không dùng làm bằng chứng hiệu quả placement.

## 5. Các nguồn dữ liệu ML cần phân biệt

1. **Benchmark tổng hợp:** evaluation/run_common_scenarios.py tạo đặc trưng và nhãn bằng NumPy với seed cố định. Mô hình Random Forest benchmark có 4.000 dòng tổng hợp. Employee dataset chỉ cung cấp ID tham chiếu; không cung cấp query logs hoặc nhãn tấn công.
2. **Telemetry MySQL lab:** run_live_attack_simulation.py chạy các truy vấn SELECT trên database employee cục bộ và đo số dòng, thời lượng, giờ, mẫu bảng và tần suất. Nhãn do kịch bản đặt. Model live học trên đặc trưng quan sát được, nhưng không học từ sự cố tấn công thật.
3. **Nội dung honeytoken A/B:** SDV HMASynthesizer học phân bố và quan hệ giữa các bảng employee, dept_emp, dept_manager, salary, title để sinh dữ liệu mồi tổng hợp. Demo B tái sử dụng cùng candidate HMA.
4. **Vị trí Demo B:** Random Forest không sinh nội dung các cột; nó chấm điểm telemetry truy vấn theo phòng ban. Điểm trung bình rủi ro được dùng để phân bổ ngân sách token B.

## 6. Kết quả đã demo

### Benchmark hành vi tổng hợp

Kết quả cũ trong results/ab_metrics.csv dùng 5 lần chia train/test trên các kịch bản tạo bằng code. Đây là benchmark phân loại hành vi, không đo vị trí HMA so với RF. Một số kết quả tổng hợp:

| Phương pháp | Accuracy | Precision | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|
| Demo A token tĩnh | 58,3% | 90,3% | 18,5% | 0,307 | 2,0% |
| Random Forest | 89,7% | 99,3% | 80,0% | 0,886 | 0,6% |
| Random Forest kết hợp token | 88,8% | 96,9% | 80,1% | 0,877 | 2,6% |

Đây là benchmark sinh bằng chương trình, không phải truy vấn sản xuất.

### Capture MySQL có kiểm soát

Kết quả cũ đã lưu trong results/live_attack_metrics.json thuộc phép đo phân loại trước khi có kịch bản placement theo mục tiêu: 40 session mỗi demo; 25 session gán nhãn tấn công mô phỏng và 15 session bình thường.

| Phương pháp | TP | TN | FP | FN | Accuracy | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Demo A token tĩnh | 10 | 15 | 0 | 15 | 62,5% | 40% | 0,571 | 0% |
| Demo B Random Forest đã hiệu chỉnh | 25 | 15 | 0 | 0 | 100% | 100% | 1,000 | 0% |
| Demo B Random Forest hoặc token hit | 25 | 15 | 0 | 0 | 100% | 100% | 1,000 | 0% |

Ngưỡng hiện tại là 0,9865. Trong lần chạy này, Demo B không báo động nhầm trong 15 session bình thường. Không diễn giải tỷ lệ 0% này thành bảo đảm trong thực tế: bộ đo nhỏ, gồm 8 mẫu kịch bản cố định lặp lại 5 lần; nhãn do script gán. Việc kiểm định giữ lại một lần lặp để đánh giá nhưng các nhóm kịch bản vẫn được biết trước.

Các số trên là phép đo phát hiện hành vi cũ, không phải bằng chứng so sánh vị trí A-HMA với B-RF. Sau khi nạp token mới vào cả hai registry, cần chạy lại capture/train; kết quả hit theo vị trí sẽ nằm trong live_attack_placement_session_results.csv, live_attack_placement_scenario_metrics.csv và live_attack_metrics.json. Dashboard tách bảng token hit này khỏi chỉ số phân loại Random Forest.

## 7. Chạy benchmark tổng hợp tùy chọn

~~~powershell
python evaluation\run_common_scenarios.py
~~~

Lệnh tạo results/ab_query_results.csv, results/ab_metrics.csv, results/ab_scenario_metrics.csv, results/ab_metrics.json và mô hình models/random_forest_synthetic.joblib. Muốn lưu kết quả vào database, áp dụng comparison_schema.sql rồi chạy evaluation/persist_results.py --apply với quyền phù hợp.

## 8. Giới hạn và tài liệu tham khảo

- Không có trong project một tập công khai kết hợp query audit MySQL thực, bối cảnh nhân viên và ground-truth tấn công nội bộ.
- PhoneLab là workload SQL thật trên SQLite di động, nhưng không có nhãn tấn công và khác miền so với MySQL doanh nghiệp.
- LANL có sự kiện an ninh doanh nghiệp và mốc Red Team, nhưng không phải query log database.
- Kết quả lab không đo gateway alert end-to-end cho mọi MySQL client và không xác nhận hiệu năng trên người dùng hoặc hành vi chưa thấy.
- Bài báo gốc dùng HMA/SDV để sinh dữ liệu quan hệ nhiều bảng, triển khai/giám sát honeytoken và đánh giá độ tin cậy bằng con người. Demo A là bản tham chiếu giáo dục; chưa tái hiện human evaluation và chưa khẳng định tái tạo đầy đủ các chiến lược triển khai. Demo B bổ sung Random Forest cho phân bổ vị trí theo rủi ro và phân tích cảnh báo hành vi.

Tài liệu: [Bytebase Employee Sample Database](https://github.com/bytebase/employee-sample-database/tree/main/mysql); [bài báo gốc DOI 10.1016/j.cose.2024.104032](https://doi.org/10.1016/j.cose.2024.104032); [SDV](https://docs.sdv.dev/sdv); [PhoneLab SQL trace paper](https://odin.cse.buffalo.edu/papers/2015/TPCTC-sqlite-final.pdf); [LANL Cyber Security Research datasets](https://csr.lanl.gov/data/).
