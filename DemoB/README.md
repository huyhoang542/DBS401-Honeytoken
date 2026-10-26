# Demo B Honeytoken thích nghi bằng học máy

**Demo B là phần nâng cấp và đóng góp chính của đồ án.** Demo A chỉ là bản tham chiếu theo phương pháp bài báo, dùng làm baseline đối chứng để đánh giá xem Demo B cải thiện ra sao. Demo B bổ sung telemetry hành vi truy vấn, mô hình Random Forest chấm điểm rủi ro, kết hợp phát hiện honeytoken và thử nghiệm bố trí token theo rủi ro phòng ban. Hai demo dùng chung database Employee Sample và kịch bản so sánh, nhưng giữ registry riêng.

## 1. Thành phần và cơ sở dữ liệu

- Database nghiệp vụ dùng chung: employee.
- Registry, log và cảnh báo Demo B: honeytoken_security_b.
- Dải ID token Demo B: 910001–910050.
- Dải HMA Demo A: 910051–910100.
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

## 2. Chuẩn bị schema và token

Nếu schema bảo mật chưa có, chạy bằng MySQL administrator từ thư mục DemoB:

~~~powershell
Get-Content -Raw .\database\setup_security_schema.sql | mysql -u root -p
Get-Content -Raw .\database\comparison_schema.sql | mysql -u root -p
~~~

Tạo các tài khoản theo database/create_demo_b_users.sql.example hoặc cấp các quyền tương đương. Đảm bảo tài khoản reader chỉ đọc employee và monitor chỉ truy cập registry/log được cấp.

Seeder Demo B dùng Faker, không dùng ML để tạo token. Chỉ chạy khi dải 910001–910050 chưa tồn tại:

~~~powershell
python database\seed_honeytokens.py
~~~

Seeder thêm các bản ghi nhân viên mồi và đăng ký chúng trong honeytoken_security_b. Không chạy lại nếu đã có 50 token. Demo A sinh token bằng SDV HMA; xem [README Demo A](../DemoA/README.md).

Có thể reset hai demo trong môi trường lab bằng script có dry-run mặc định. Chỉ dùng --apply khi chủ động muốn xóa các dải token quy định và log giám sát:

~~~powershell
.\.venv\Scripts\python.exe database\reset_lab_honeytokens.py
.\.venv\Scripts\python.exe database\reset_lab_honeytokens.py --apply
~~~

Lệnh hỏi thông tin MySQL administrator. Script giữ schema và các bản ghi nhân viên thông thường.

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

Capture chạy các truy vấn SELECT có giới hạn trên MySQL cục bộ, 5 lần lặp của 8 kịch bản cho mỗi demo. Nó thu 40 session và 980 truy vấn cho mỗi demo. Không ghi thay đổi vào employee.

Model live Demo B được huấn luyện trên 980 dòng telemetry đo được từ lần chạy đó, với các đặc trưng: số dòng trả về, giờ truy vấn, số bảng đích, tần suất truy vấn trong session, thời lượng và cờ truy vấn phòng ban. Mô hình là Random Forest. Kịch bản gán nhãn bình thường/tấn công mô phỏng; đây không phải nhãn từ sự cố thực tế. Ngưỡng hiện lưu ở models/live_sim_model_metadata.json.

Tám kịch bản gồm: tra cứu từng ID thông thường, báo cáo hàng loạt hợp lệ, truy vấn bảo trì, dò ID nhanh, quét phòng ban, thu thập nhiều bản ghi, truy vấn chậm có chủ đích và kiểm tra token mồi. Kịch bản kiểm tra token chủ động biết ID canary để xác nhận detector, không giả định attacker ngoài đời biết trước ID đó.

## 5. Các nguồn dữ liệu ML cần phân biệt

1. **Benchmark tổng hợp:** evaluation/run_common_scenarios.py tạo đặc trưng và nhãn bằng NumPy với seed cố định. Mô hình Random Forest benchmark có 4.000 dòng tổng hợp. Employee dataset chỉ cung cấp ID tham chiếu; không cung cấp query logs hoặc nhãn tấn công.
2. **Telemetry MySQL lab:** run_live_attack_simulation.py chạy các truy vấn SELECT trên database employee cục bộ và đo số dòng, thời lượng, giờ, mẫu bảng và tần suất. Nhãn do kịch bản đặt. Model live học trên đặc trưng quan sát được, nhưng không học từ sự cố tấn công thật.
3. **Honeytoken của Demo B:** seeder dùng Faker để tạo bản ghi mồi. Đây là dữ liệu decoy tổng hợp, không phải dữ liệu huấn luyện hành vi.
4. **Demo A HMA:** SDV HMASynthesizer học phân bố và quan hệ giữa các bảng để sinh bản ghi mồi liên kết. Đây cũng là dữ liệu tổng hợp.

## 6. Kết quả đã demo

### Benchmark hành vi tổng hợp

Kết quả trong results/ab_metrics.csv dùng 5 lần chia train/test trên các kịch bản tạo bằng code. Một số kết quả tổng hợp:

| Phương pháp | Accuracy | Precision | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|
| Demo A token tĩnh | 58,3% | 90,3% | 18,5% | 0,307 | 2,0% |
| Random Forest | 89,7% | 99,3% | 80,0% | 0,886 | 0,6% |
| Random Forest kết hợp token | 88,8% | 96,9% | 80,1% | 0,877 | 2,6% |

Đây là benchmark sinh bằng chương trình, không phải truy vấn sản xuất.

### Capture MySQL có kiểm soát

Kết quả đã lưu trong results/live_attack_metrics.json: 40 session mỗi demo; 25 session được kịch bản gán nhãn tấn công mô phỏng và 15 session bình thường.

| Phương pháp | TP | TN | FP | FN | Accuracy | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Demo A token tĩnh | 10 | 15 | 0 | 15 | 62,5% | 40% | 0,571 | 0% |
| Demo B Random Forest đã hiệu chỉnh | 25 | 15 | 0 | 0 | 100% | 100% | 1,000 | 0% |
| Demo B Random Forest hoặc token hit | 25 | 15 | 0 | 0 | 100% | 100% | 1,000 | 0% |

Ngưỡng hiện tại là 0,9865. Trong lần chạy này, Demo B không báo động nhầm trong 15 session bình thường. Không diễn giải tỷ lệ 0% này thành bảo đảm trong thực tế: bộ đo nhỏ, gồm 8 mẫu kịch bản cố định lặp lại 5 lần; nhãn do script gán. Việc kiểm định giữ lại một lần lặp để đánh giá nhưng các nhóm kịch bản vẫn được biết trước.

Kết quả theo từng session nằm ở results/live_attack_session_results.csv; theo nhóm kịch bản nằm ở results/live_attack_scenario_metrics.csv. Dashboard hiển thị bảng so sánh, tỷ lệ cảnh báo theo kịch bản, risk scorer, dự đoán gateway và lịch sử bố trí.

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
- Paper chính tập trung sinh và triển khai honeytoken quan hệ bằng HMA/SDV. Random Forest/adaptive placement là phần mở rộng đồ án.

Tài liệu: [Bytebase Employee Sample Database](https://github.com/bytebase/employee-sample-database/tree/main/mysql); [bài báo gốc DOI 10.1016/j.cose.2024.104032](https://doi.org/10.1016/j.cose.2024.104032); [SDV](https://docs.sdv.dev/sdv); [PhoneLab SQL trace paper](https://odin.cse.buffalo.edu/papers/2015/TPCTC-sqlite-final.pdf); [LANL Cyber Security Research datasets](https://csr.lanl.gov/data/).
