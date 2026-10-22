# So sánh 8 chiến lược trên FreqPilot và Ultimate

Đã chạy 8 chiến lược riêng lẻ trên cả hai engine, không tối ưu. Bảng chính dưới đây dùng cách chạy riêng để tránh warmup của chiến lược khác ảnh hưởng dữ liệu khởi động. Bảng chạy nhóm ban đầu được giữ trong grouped-comparison.json. Bộ chính dùng engine chính thức 2026.9; Ultimate riêng dùng mã fork khai báo 2026.6. Đây là khảo sát kỹ thuật và mẫu kết quả, chưa tìm được chiến lược được chứng minh có lợi thế.

## Protocol

BTC/USDT:USDT + ETH/USDT:USDT, Binance Futures isolated 1x, vốn 1000 USDT, stake khai báo 100 USDT, tối đa 2 lệnh, phí 0.0005 mỗi chiều, chi tiết 1m, cache tắt; mỗi chiến lược là một lần chạy riêng. Khoảng yêu cầu 18/09/2026–22/10/2026 (ngày kết thúc không bao gồm); dữ liệu thực dừng ở 21/10/2026 khoảng 18:00–19:30 UTC theo timeframe, tương đương rạng sáng 22/10 giờ Việt Nam. Mỗi chiến lược giữ khung gốc 5m, 15m hoặc 1h; không ép chung một timeframe trái thiết kế. So sánh lợi nhuận giữa các chiến lược vì vậy chỉ mang tính tham khảo.

Funding/mark của bộ chính nguyên vẹn. Ultimate dùng bản sao funding chuyển đổi định dạng, giữ nguyên từng timestamp/rate. Các hàm custom stake và DCA của chiến lược vẫn hoạt động: stake khai báo 100 không có nghĩa mọi lệnh thực tế có cùng giá trị 100.

## Kết quả engine chính thức

| Chiến lược | Khung | Lệnh | Lãi/lỗ USDT | Drawdown | Win rate | Profit factor | So với Ultimate |
|---|---|---:|---:|---:|---:|---:|---|
| StarterFutures | 15m | 144 | -22.181 | 3.80% | 20.14% | 0.65 | Khớp từng lệnh |
| FAdxSmaStrategy | 1h | 2 | -3.385 | 0.34% | 0.00% | 0.00 | Khớp từng lệnh |
| FReinforcedStrategy | 5m | 24 | -1.215 | 0.25% | 8.33% | 0.70 | Khớp từng lệnh |
| FSampleStrategy | 1h | 5 | -8.379 | 1.52% | 40.00% | 0.45 | Khớp từng lệnh |
| FSupertrendStrategy | 1h | 23 | -1.773 | 1.65% | 43.48% | 0.90 | Khớp từng lệnh |
| FOttStrategy | 1h | 6 | -3.186 | 0.76% | 50.00% | 0.69 | Khớp từng lệnh |
| TrendFollowingStrategy | 5m | 6 | +9.441 | 0.81% | 66.67% | 2.14 | Khớp từng lệnh |
| VolatilitySystem | 1h | 2 | +2.327 | 0.00% | 100.00% | — | Khác quy tắc sizing |

Profit factor để trống khi không có lệnh lỗ; engine gốc dùng giá trị 0 trong trường hợp này, không diễn giải 0 như bằng chứng hiệu quả kém hay tốt. Tất cả lệnh của cả hai engine trong phép thử đều 1x.

Hai mẫu có lãi trên bộ chính là TrendFollowingStrategy (+9.441 USDT, 6 lệnh) và VolatilitySystem (+2.327 USDT, 2 lệnh). Mẫu quá nhỏ để chọn chiến lược thắng cuộc. Các mẫu còn lại đều lỗ; StarterFutures có 144 lệnh và lỗ khoảng 2.22%. Không tự chọn mẫu lợi nhuận cao để thay bot paper.

## Khác biệt engine có ý nghĩa

7/8 chiến lược khớp tất cả trường được kiểm tra: cặp, thời gian vào/ra, giá vào/ra, lượng, funding, lợi nhuận, exit reason và leverage. VolatilitySystem có 2 lệnh / +2.32679280 USDT trên bản chính thức, còn Ultimate có 5 lệnh / +1.60424641 USDT. Hai lệnh ETH khớp; Ultimate nhận thêm ba lệnh BTC.

Chiến lược này trả custom_stake_amount bằng nửa mức đề xuất, tức khoảng 50 USDT. Wallets.validate_stake_amount của bản chính thức chỉ nâng lên mức sàn nếu tăng không quá 30%; Ultimate cho tới 80%. Kiểm tra trực tiếp cùng đầu vào desired=50, min=82, available=1000 cho kết quả chính thức=0 (bỏ lệnh), Ultimate=82 (nhận lệnh). Điều này giải thích việc một số lệnh BTC xuất hiện trên Ultimate và được DCA tiếp. Không sửa engine để ép khớp. Bằng chứng ở stake-policy-check.json và source wallets.py của hai bản.

## Chạy nhóm có thể làm thay đổi warmup

Benchmark đầu chạy chung các chiến lược cùng timeframe. Engine dùng `required_startup` lớn nhất của nhóm khi tải dữ liệu. Vì vậy, chiến lược khai báo startup=0 có thể nhận thêm lịch sử do chiến lược khác trong nhóm.

- TrendFollowing: chạy nhóm 5m nhận 14 nến từ FReinforced; chạy riêng giữ mặc định 0. Lệnh đầu chuyển từ 00:05 sang 00:10 ngày 18/09 UTC; PnL từ +9.43954565 thành +9.44052495.
- VolatilitySystem: nhóm 1h có mức lớn nhất 30 từ FSample; chạy riêng giữ 0. Kết quả từ 3 lệnh / +2.64869848 thành 2 lệnh / +2.32679280.
- Đã chạy CLI chính thức riêng hai chiến lược trên dữ liệu gốc: từng trường lệnh khớp snapshot. Đã chạy thêm cấu hình chẩn đoán warmup=14 và 30: tái hiện đúng kết quả chạy nhóm. Không sửa file chiến lược và không chọn warmup để tối ưu lợi nhuận. Bằng chứng ở warmup-controls.json và controls/*.log.

`tools/run_benchmark.py` hiện mặc định chạy từng chiến lược trong tiến trình riêng. Cờ `--grouped` giữ khả năng khảo sát hành vi nhóm. UI so sánh ưu tiên kết quả có gói lưu mới nhất; nếu chưa có mới dùng lịch sử native.

## Hồ sơ đầu vào và kết quả

Cả 8 chiến lược đã được chạy lại qua adapter snapshot. Mỗi lần sao chép mã Python local, parameter của chiến lược và toàn bộ feather local sang thư mục riêng, gọi API backtest chính thức trên bản sao, giữ ZIP native và gói SHA-256. Cả 8 gói kiểm tra toàn vẹn thành công. Sáu mẫu khớp benchmark nhóm trước; hai mẫu còn lại khớp CLI chạy riêng như giải thích ở trên.

UI đã kiểm tra xuyên suốt với StarterFuturesResearch: 144 lệnh, -22.18148145 USDT, đúng kết quả trước; mở mã đã chạy, kiểm tra hash và tải gói thành công. Báo cáo cũ không bị gắn nhầm với mã hiện tại. Gói không đóng băng metadata Binance lấy qua mạng, thư viện ngoài image hoặc mọi loại file phụ trợ tùy ý. Không mô tả gói là môi trường mô phỏng hoàn toàn độc lập.

## Chất lượng và kiểm định

Đã chạy công cụ lookahead chính thức cho 8 mẫu. CSV không phát hiện biased entry/exit hoặc indicator trong các trường hợp đã xét; với nhóm 1h chỉ có 2 tín hiệu được phân tích cho mỗi mẫu, nhóm 5m và StarterFutures có 20. Đây là mẫu chẩn đoán hạn chế, không phải chứng nhận không có bias. Nguồn CSV và log được giữ cùng báo cáo.

Recursive-analysis chỉ dùng BTC dù tham số có cả hai cặp (đúng hành vi công cụ). Kết quả không đồng nghĩa kiểm tra cả BTC và ETH. Phát hiện:
- StarterFutures: ở 200 nến warmup, sai khác cuối mẫu được làm tròn gần 0%; vẫn chỉ là một phép khảo sát độ ổn định.
- FAdxSmaStrategy: warmup gốc 14 tạo NaN cho ADX/SMA; cần xem lại trước khi sử dụng.
- FSampleStrategy: warmup 30 có NaN và sai lệch đáng kể ở một số indicator.
- FOttStrategy: warmup 18 cho sai lệch OTT khoảng -2.022%, VAR khoảng -0.479%; 100–200 ổn định hơn trong mẫu. Chưa sửa warmup để làm đẹp kết quả.
- FReinforcedStrategy: recursive không hoàn tất ở cấu hình gốc, báo không có đủ dữ liệu cho cửa sổ kiểm tra. Không ghi là đã pass.
- TrendFollowingStrategy và VolatilitySystem: công cụ từ chối vì startup_candle_count=0. Có trường hợp CLI trả exit code 0 dù log báo lỗi, nên báo cáo dựa vào nội dung log chứ không chỉ exit code.
- Xem log FSupertrendStrategy trong recursive/ để xem các giá trị warmup thực tế; không suy ra đã được chứng nhận chỉ vì có bảng kết quả.

## Nguồn và sửa tương thích

7 mẫu được lấy từ repo chính thức freqtrade/freqtrade-strategies, commit f3340ce11f5bdf62f598522e64d1f5638eaa13f5. StarterFutures là mẫu cài đặt local có sẵn. Không đổi ngưỡng tín hiệu/ROI/stoploss để tối ưu: chỉ bổ sung metadata parameter space của FReinforced, cập nhật import math và gán DataFrame/dtype của FOtt cho numpy/pandas hiện tại, hạ leverage mẫu VolatilitySystem từ 2x xuống 1x theo chỉ dẫn người dùng. Tất cả thay đổi và hash gốc/bản cài ở ../templates/PROVENANCE.json.

FSupertrend, FOtt và TrendFollowing có tín hiệu short trong mã nhưng không khai báo can_short=true; phép thử giữ hành vi gốc long-only thay vì bật short ngầm.

## Đọc bằng chứng

comparison.json chứa số liệu mới và tên ZIP chạy riêng ở hai thư mục runtime. frozen-comparison.json gắn 8 hồ sơ snapshot với lần chạy nhóm gốc và các đối chứng CLI; grouped-comparison.json giữ số liệu ban đầu để kiểm toán. main/run.json và ultimate/run.json ghi protocol/nhóm chạy; mỗi nhóm có log riêng. Source template và hash được lưu trong repo, nhưng cấu hình có credentials, dữ liệu và ZIP runtime không được đưa vào Git. Không có giao dịch tiền thật trong các lượt chạy.
