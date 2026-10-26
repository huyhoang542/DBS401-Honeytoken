# Đồ án DBS401 về Honeytoken thích nghi

**Demo A chỉ đóng vai trò bản tham chiếu để đối chiếu với phương pháp bài báo; Demo B mới là phần nâng cấp và đóng góp chính của đồ án.** Demo A tái hiện luồng honeytoken tĩnh/paper-inspired làm baseline. Demo B mở rộng bằng chấm điểm rủi ro Random Forest, telemetry truy vấn và thử nghiệm bố trí token thích nghi. Bảng so sánh dùng Demo A làm mốc để đo hiệu quả nâng cấp của Demo B. Hai demo dùng chung database Employee Sample nhưng có registry và log riêng.

## 1. Mục tiêu và phạm vi

Dự án thử nghiệm honeytoken trong MySQL. Honeytoken là bản ghi mồi được đặt trong dữ liệu; khi truy vấn trả về bản ghi đó, hệ thống ghi nhận sự kiện và phát cảnh báo.

- **Demo A:** nhận diện truy cập bằng danh sách ID token đã đăng ký.
- **Demo B:** phân tích hành vi truy vấn bằng mô hình ML, kết hợp token hit và thử nghiệm chuyển vị trí token.

Demo A lấy cảm hứng từ bài báo *Generation and deployment of honeytokens in relational databases for cyber deception* (2024). Demo A dùng SDV HMASynthesizer để sinh dữ liệu liên kết nhiều bảng. Đây là triển khai giáo dục theo hướng bài báo, không phải tái tạo đầy đủ phương pháp hay đánh giá người dùng trong bài báo.

## 2. Nền tảng và dữ liệu

| Thành phần | Vai trò |
|---|---|
| Python và MySQL | Chạy generator, gateway và cơ sở dữ liệu |
| SDV HMASynthesizer | Học cấu trúc và phân bố dữ liệu nhiều bảng để sinh token cho Demo A |
| pandas | Xử lý kết quả thực nghiệm |
| Streamlit | Dashboard giám sát |

Demo dùng bộ dataset_large từ [Bytebase Employee Sample Database](https://github.com/bytebase/employee-sample-database/tree/main/mysql). Đây là dữ liệu mẫu, không phải dữ liệu nhân viên sản xuất hay log hành vi người dùng. Bản cài trong đồ án có 10.000 nhân viên, 94.917 bản ghi lương, 11.051 quan hệ phòng ban, 9 phòng ban, 24 bản ghi quản lý và 14.782 chức danh.

Trong cấu hình A/B dùng chung database:

- Demo A dùng registry honeytoken_security và dải HMA 910051–910100.
- Demo B dùng registry honeytoken_security_b và dải Faker 910001–910050.
- Dải Demo A cũ 900001–900050 đã được reset.

## 3. Tạo honeytoken HMA cho Demo A

Quá trình gồm sinh ứng viên và nạp ứng viên. Generator huấn luyện HMA từ các bảng employee, dept_emp, dept_manager, salary, title; bảng department được giữ làm danh mục tham chiếu. Generator không ghi vào MySQL. Ứng viên được lưu trong database/hma_artifacts/.

Từ thư mục DemoA, mở PowerShell:

~~~powershell
Set-Location D:\FPTU\Course\DBS401_Project\DemoA
.\.venv\Scripts\Activate.ps1
python database\generate_hma_honeytokens.py
python database\apply_hma_honeytokens.py
~~~

Lệnh apply_hma_honeytokens.py chạy kiểm tra va chạm ID ở chế độ dry-run. Khi đã xem số dòng và dải ID, nạp bằng:

~~~powershell
python database\apply_hma_honeytokens.py --apply --admin
~~~

Lệnh sẽ hỏi tài khoản MySQL administrator. Tài khoản honey_seeder hiện thiếu quyền INSERT ở bảng dept_manager, do đó khi nạp toàn bộ HMA cần quyền quản trị. Việc nạp được thực hiện trong một transaction.

Manifest hiện ghi 50 bản ghi employee, 467 salary, 55 dept_emp, 1 dept_manager, 74 title. Số dòng con không bằng 50 vì mỗi nhân viên có thể có nhiều khoảng lương, chức danh hoặc phân công.

## 4. Registry và giám sát

Các bảng trong honeytoken_security:

| Bảng | Nội dung |
|---|---|
| honeytoken_registry | ID, chiến lược, phiên bản và trạng thái token |
| access_events | Sự kiện truy vấn được monitor ghi nhận |
| security_alerts | Cảnh báo tương ứng |

Các tài khoản tách biệt theo vai trò: demo_reader chỉ đọc dữ liệu nhân viên; honey_monitor đọc registry và ghi log/cảnh báo; honey_seeder được cấp quyền nạp token ở các bảng được phép. Không đưa mật khẩu .env lên GitHub.

Gateway nằm tại monitoring/query_monitor.py. Ví dụ:

~~~powershell
python monitoring\query_monitor.py 10001
python monitoring\query_monitor.py 910051
~~~

ID thường không phát hiện token; ID HMA đang được đăng ký phải tạo cảnh báo. Gateway hiện chỉ theo dõi truy vấn chạy qua chương trình này; SELECT trực tiếp bằng MySQL client không tự động đi qua gateway.

## 5. Dashboard và kiểm thử Demo A

Chạy dashboard:

~~~powershell
python -m streamlit run dashboard\app.py
~~~

Chạy bộ kiểm thử chức năng:

~~~powershell
python simulation\run_scenarios.py
python evaluation\metrics.py
~~~

Kết quả đã lưu ở results/static_baseline_results.csv và results/static_baseline_metrics.json: 100 truy vấn xác định trước, gồm 50 kết quả dương và 50 âm. Các chỉ số trong JSON là TP=50, TN=50, FP=0, FN=0, Accuracy=100%, Precision=100%, Recall=100%, F1=1, FPR=0%. Độ trễ trung bình 218,63 ms, trung vị 217,27 ms, P95 235,59 ms.

> Đây là kiểm thử chức năng với ID đã biết trước, không chứng minh khả năng phát hiện mọi kiểu tấn công. Độ trễ đo cả tiến trình Python và thao tác MySQL.

## 6. Reset và chạy lại A/B

Reset chỉ dành cho môi trường demo. Script xóa các dải token đã quy định, registry và log giám sát; giữ schema và dữ liệu nhân viên thông thường. Chạy từ DemoB bằng quyền quản trị:

~~~powershell
Set-Location D:\FPTU\Course\DBS401_Project\DemoB
.\.venv\Scripts\python.exe database\reset_lab_honeytokens.py
~~~

Mặc định là dry-run. Chỉ thêm --apply nếu muốn xóa thật:

~~~powershell
.\.venv\Scripts\python.exe database\reset_lab_honeytokens.py --apply
~~~

Sau đó sinh/nạp lại HMA theo Mục 3 và seed Demo B theo hướng dẫn trong [README Demo B](../DemoB/README.md). Không chạy reset trên database ngoài môi trường lab.

## 7. Kết quả và giới hạn

Kết quả chi tiết của Demo A và so sánh A/B được lưu trong results/ của từng demo và DemoB/comparison/RESULTS.md. So sánh công bằng cần dùng chung dataset, ngân sách token, bộ kịch bản, nhãn và quy trình đánh giá. Không dùng kết quả huấn luyện làm kết quả kiểm tra.

HMA học cấu trúc và phân bố bản ghi; điều đó không tự chứng minh token khó phân biệt. Dải ID liên tiếp có thể bị nhận ra. Demo A cũng chưa giám sát mọi câu SQL bên ngoài gateway và bộ kiểm thử 100 truy vấn chỉ là kiểm tra chức năng.

## 8. Tài liệu tham khảo

1. Bopche và cộng sự, *Generation and deployment of honeytokens in relational databases for cyber deception*, Computers & Security, 146 (2024), 104032. [DOI](https://doi.org/10.1016/j.cose.2024.104032).
2. [Bytebase Employee Sample Database](https://github.com/bytebase/employee-sample-database/tree/main/mysql).
3. [Tài liệu SDV](https://docs.sdv.dev/sdv) về tổng hợp dữ liệu bảng đơn và nhiều bảng.
4. Tài liệu yêu cầu đồ án DBS401_Project.docx.
