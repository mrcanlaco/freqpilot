# Định hướng sản phẩm FreqPilot

Mục tiêu là một workspace nghiên cứu crypto dễ dùng cùng Codex, giữ Freqtrade 2026.9 và ưu tiên tính năng đã có. Điểm học từ RoboQuant là tổ chức công việc quanh một chiến lược và giữ ngữ cảnh từ ý tưởng tới báo cáo; điểm tái sử dụng từ Ultimate là bộ editor, chart/report, store, đăng nhập và giám sát bot. Không sao chép engine hoặc mã độc quyền RoboQuant.

| Tiêu chí | RoboQuant theo tài liệu hiện tại | Ultimate đã khảo sát | FreqPilot 0.1 |
|---|---|---|---|
| Luồng chính | Tạo → compile → backtest → optimize → deploy | Fleet và Strategy Lab / Launch Job | Thư viện → ý tưởng → mã → backtest → kết quả → paper |
| AI tạo chiến lược | Có builder/compile-fix | Editor và launcher, không phải builder AI | Dùng Codex hiện tại; lưu ý tưởng và xuất yêu cầu, chưa có chat riêng |
| Editor | Mã `.rq`, artifact `.rqc` | Monaco + API editor | Dùng lại Monaco; Python `.py`, cú pháp + phiên bản + backup |
| Engine và thị trường | CME, compiled runtime | Fork tập trung Hyperliquid, vẫn có Binance | Freqtrade chính thức 2026.9, BTC/ETH Binance USDT-M |
| Mô phỏng | Bar, tick và L2 khi có dữ liệu | Nền engine Freqtrade | Nến + chi tiết 1m + phí + mark/funding; không mô tả là tick/L2 |
| Hồ sơ tái kiểm tra | Compiled artifacts và lịch sử | ZIP kết quả theo cơ chế engine | Bản sao mã/dữ liệu cho mỗi run, ZIP native, gói kiểm tra SHA-256; chưa đóng băng metadata thị trường từ mạng |
| Kết quả / so sánh | Metrics, chart/replay, lịch sử | Nhiều panel phân tích và so sánh | Tái sử dụng các panel tương thích API chính thức |
| Kiểm định | IS/OOS, walk-forward theo gói | Hyperopt/WFA và các phân tích mở rộng | Dùng lại API lookahead/recursive, có job và lịch sử trên UI; đã khảo sát mẫu bằng CLI |
| Tối ưu | Có nhiều phương pháp | Có launcher hyperopt/WFA | Chưa nối UI, không tối ưu tự động |
| Triển khai | Có Demo/Live | Có công cụ quản lý bot | Hồ sơ từ backtest → review cấu hình → bật/pause/tiếp tục/dừng → giám sát; worker nghiên cứu riêng, database theo hồ sơ, chặn đổi khi còn vị thế |

Đã ẩn các mục công cụ phụ thuộc API fork không tồn tại trên backend chính, thay vì đưa người dùng tới trang không chạy được. Nguồn dữ liệu phân biệt webserver nghiên cứu với bot giao dịch, tránh báo offline hoặc cộng vốn sai cho dịch vụ backtest.

## Tham khảo Strategies của RoboQuant · 22/10/2026

Đã xem trực tiếp trang Strategies và Code của tài khoản đang kết nối, cùng docs `python-strategies` và metadata qua connector; chỉ đọc, không tạo/sửa/compile/chạy tác vụ RoboQuant. Thư viện thực có tìm kiếm, danh sách/thẻ, yêu thích, sắp xếp, section và chỉ số gần nhất. Trang chi tiết đặt Code/Backtest/Optimize/Deployments/Settings quanh cùng chiến lược, có cây tệp và lịch sử phiên bản. Tài liệu còn mô tả cấu hình tham số dùng lại giữa các màn hình.

FreqPilot đã áp dụng thư viện thẻ/danh sách, tìm mô tả/nhãn, yêu thích lưu trên máy, lọc khung/hồ sơ, cập nhật gần nhất, chỉ số từ lần backtest có gói gần nhất, cảnh báo khác mã/mẫu nhỏ và chọn nhiều chiến lược để so sánh. Dùng lại Monaco, DiffViewer, bảng so sánh, API metadata/phiên bản và ZIP kết quả hiện có. Không chọn kết quả lợi nhuận tốt nhất làm đại diện, không gọi là chứng nhận chất lượng; báo cáo không có gói chưa được dùng để gán KPI cho mã hiện tại.

Đã bổ sung bộ tham số có tên bằng API strategy/Parameter và HyperoptTools.export_params gốc, không chạy hyperopt. Hỗ trợ số nguyên, số thực, thập phân, boolean và lựa chọn; kiểm tra đúng tên/kiểu/giới hạn, không đổi trường load=false. JSON bất biến được chép riêng vào backtest và kiểm định; ZIP native phải chứa đúng byte JSON của đầu vào. Paper kế thừa JSON từ gói backtest và đổi strategy_name cho lớp giới hạn 1x theo cơ chế đã có. Mã Python và JSON trong thư viện không bị ghi đè. Bộ gắn với revision mã và schema; mã đổi thì cần bộ mới. Các hằng số không khai báo Parameter vẫn sửa qua editor, chưa có bộ điều khiển ROI/stoploss riêng hoặc import `.set` của RoboQuant.

Chưa triển khai cây tệp đa mô-đun trong editor, section kéo thả, chatbot riêng hoặc bước compile như `.rq`. Freqtrade dùng Python và kiểm tra cú pháp khi lưu; không giả lập compiler/sandbox của RoboQuant. Các phần này cần khảo sát khả năng native trước khi bổ sung.

Nguồn: https://roboquant.dev/dashboard?section=strategies và https://roboquant.dev/docs/python-strategies .

## Nguyên tắc phát triển

- Giữ nguyên engine và tái sử dụng API chính thức trước khi viết adapter.
- Mỗi chiến lược giữ ý tưởng, mã, lần chạy và nhận xét trong cùng ngữ cảnh.
- Tách kết quả kiểm định kỹ thuật khỏi kết luận chiến lược có lợi nhuận.
- Kết quả thiếu tín hiệu / ít lệnh phải được giải thích, không tạo số liệu minh họa giả.
- Không bật live hoặc đổi paper một cách ngầm định.
- Giữ bản Ultimate riêng để đối chiếu hành vi và đọc source; không ép kết quả khớp bằng cách sửa engine chính.

## Còn phát triển tiếp

Các mục sau chưa được coi là đã hoàn tất trong bản 0.1:

1. Hoàn thiện diễn giải kết quả kiểm định và chuẩn hóa tiêu chí chọn mẫu; API/job/lịch sử lookahead/recursive đã được nối trên UI.
2. Luồng paper một worker đã có trên UI bằng Compose/API native. Còn lịch sử phiên chạy paper dài hạn, lưu trữ/ẩn hồ sơ và khảo sát nhiều worker đồng thời nếu cần. Không bật live.
3. Hồ sơ mã, parameter và feather đã được sao chép riêng cho từng run và kiểm tra toàn vẹn trên UI. Còn luồng phát lại tự động từ gói, ghim metadata sàn và cơ chế quản lý dung lượng.
4. Nối hyperopt / out-of-sample theo nhu cầu, ưu tiên adapter từ công cụ hiện có; chỉ chạy khi người dùng yêu cầu.
5. Hoàn thiện tiếng Việt và trạng thái rỗng/lỗi trên các trang kế thừa. Màn hình Bot đã xử lý đăng ký bot mới và trạng thái đang kết nối; còn các nhãn tiền USDC từ Ultimate cần chuyển sang stake_currency của bot, cùng việc diễn giải vốn khả dụng so với vốn ban đầu.
6. Chuẩn hóa cài đặt độc lập, CI, cấu hình ví dụ và kiểm tra trước khi xuất bản GitHub.

Không lấy số lượng tính năng như tick/L2 hoặc AI chat làm tiêu chí để thay engine đang được yêu cầu giữ nguyên.

## Bằng chứng tham khảo

- RoboQuant: https://roboquant.dev/docs và https://roboquant.dev/docs/backtesting ; đã đọc thêm canonical overview/backtesting qua connector, chỉ thao tác đọc, không tạo/chạy gì trên RoboQuant.
- Ultimate: https://github.com/titouannwtt/frequi-ultimate và https://github.com/titouannwtt/freqtrade-ultimate ; so sánh dựa cả source đã lưu và hai bộ chạy cục bộ.

