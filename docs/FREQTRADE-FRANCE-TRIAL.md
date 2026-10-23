# Thử chiến lược Freqtrade France trên FreqPilot và Ultimate

Kiểm tra ngày 23/10/2026. Đây là so sánh **hai engine chạy cùng chiến lược**, không phải xác nhận lợi nhuận tương lai hay tái lập kết quả tác giả. Chỉ backtest BTC/ETH Binance USDT-M Futures; không đổi các bot paper và không giao dịch tiền thật.

## Sáu bài công khai và phạm vi thử

Danh mục [Freqtrade France](https://buymeacoffee.com/freqtrade_france/posts/224036) có năm chiến lược có mã công khai để backtest: [MfiLowvol Short V2](https://buymeacoffee.com/freqtrade_france/mfilowvol-short-v2-money-flow-index-atr-dca), [OBV Divergence Fade Dual V1](https://buymeacoffee.com/freqtrade_france/obvdivergencefadedualv1-obv-obv-ema-rolling-vwap-parabolic-sar-4853585), [Simple VWAP v1](https://buymeacoffee.com/freqtrade_france/simple-vwap-v1-la-stratgie-du-placement-constant), [KAC Index v1](https://buymeacoffee.com/freqtrade_france/stratgie-kac-index-utilisation-d-indexation-sur-le-total3-keltner-atr-et-cci) và [KAC Index v2](https://buymeacoffee.com/freqtrade_france/kac-index-v2-stratgie-atr-cci-indexe-total3-optimise). Bài thứ sáu, [MultiMarketPairList](https://buymeacoffee.com/freqtrade_france/multimarketpairlist-un-seul-bot-freqtrade-pour-trader-crypto-actions-et-matires-premires-sur), là bộ chọn cặp cho nhiều thị trường Hyperliquid; tác giả nói rõ nó không hỗ trợ backtest. Vì vậy không cài nó vào bộ Binance BTC/ETH này.

Mã Python và JSON tham số của năm chiến lược đã được đặt **chỉ trên máy này** trong `../freqtrade/user_data/strategies` và `../freqtrade-ultimate-compare/user_data/strategies`. Các bản lưu không nằm trong Git. Simple VWAP và KAC dùng [nguồn trong kho Ultimate tại commit 878206c](https://github.com/titouannwtt/freqtrade-ultimate/tree/878206c5a3be95d269ed2ff9418071df059171a4/user_data/strategies), kể cả JSON tham số của Simple VWAP/KAC v2. MFI và OBV lấy từ khối mã công khai trong hai bài tương ứng. Tác giả giới hạn việc dùng một số mã vào mục đích cá nhân/giáo dục; không đưa mã hay ZIP kết quả chứa mã vào repo này.

## Giao thức

| Mục | Giá trị |
|---|---|
| Engine | FreqPilot: Freqtrade chính thức 2026.9; Ultimate: fork commit `878206c` |
| Cặp | `BTC/USDT:USDT`, `ETH/USDT:USDT` |
| Thời gian | 01/04/2026 00:00 đến trước 21/10/2026 00:00 UTC |
| Nến chính | 1h cho MFI/OBV/KAC; 4h cho Simple VWAP |
| Chi tiết khớp lệnh | 5m, cùng dữ liệu ở hai engine |
| Vốn, phí | 1.000 USDT; stake tham chiếu 100 USDT; phí 0,05% mỗi chiều; tối đa 2 vị thế |
| Đòn bẩy | 1x; MFI gốc là 2x nên bản thử chỉ đổi hằng số đòn bẩy xuống 1x |
| Tối ưu | Không tối ưu lại, không tự áp tham số mới |

Nguồn nến 1h/4h/5m và mark 1h của hai engine giống từng byte. Funding ở Ultimate cần chuyển sang định dạng sáu cột cho bản đọc cũ; dấu thời gian và tỷ lệ funding khớp chính xác với Pilot. Trong toàn bộ cửa sổ thử, **không thiếu** nến chính, nến 5m, mark 1h hay kỳ funding 8h của cả BTC và ETH. KAC v1/v2 đọc cùng một snapshot `CRYPTOCAP:TOTAL3` TradingView, 1.000 ngày, tải ngày 23/10/2026, SHA-256 `551a20bdf013da2d857a9d4537242ef3642102b6cb7930f189c82393e20fb926`. Thay đổi này chỉ cố định nguồn dữ liệu, giữ nguyên logic tín hiệu; KAC được chặn dùng ở chế độ paper khi snapshot chưa được cập nhật.

## Kết quả

| Chiến lược | Lệnh Pilot / Ultimate | Lãi Pilot / Ultimate | Lãi USDT mỗi engine | Max drawdown mỗi engine |
|---|---:|---:|---:|---:|
| MFI Short V2, 1x | 1 / 1 | +0,296% / +0,296% | +2,96 | 0% |
| OBV Divergence Dual | 25 / 25 | +10,129% / +10,129% | +101,29 | 1,383% |
| Simple VWAP v1 | 21 / 21 | +6,249% / +6,249% | +62,49 | 0,514% |
| KAC Index v1 | 4 / 4 | +0,402% / +0,402% | +4,02 | 0,670% |
| KAC Index v2 | 0 / 0 | 0% / 0% | 0 | 0% |

Danh sách **từng giao dịch khớp chính xác** giữa Pilot và Ultimate, gồm lệnh con, phí và funding. Các mục tóm tắt có khác biệt chỉ là thời điểm chạy/ghi khóa theo đồng hồ máy; thời điểm hết hạn khóa trong backtest trùng nhau. MFI chỉ có một giao dịch, KAC v1 chỉ bốn, KAC v2 không có tín hiệu: các số này không đủ để xếp hạng độ bền chiến lược. OBV dẫn về lãi trong *mẫu BTC/ETH này*, nhưng hai bài gốc được thiết kế cho tập altcoin/Hyperliquid và các điều kiện vốn khác. Simple VWAP gốc nhắm tới nhiều cặp/vị thế hơn. Snapshot TOTAL3 là lịch sử lấy ở thời điểm thử, chưa chứng minh là dữ liệu vốn hóa điểm-thời-gian bất biến. Khớp lệnh 5m cũng chưa mô phỏng sổ lệnh/tick thực.

## Vận hành

- FreqPilot research: <http://localhost:8091/studio>; Ultimate Strategy Dev: <http://localhost:8092/tools/strategy-dev>. Cả năm tên chiến lược xuất hiện trong resolver sau khi khởi động lại hai dịch vụ backtest.
- Thư viện phụ thuộc `ta==0.11.0`, `websocket-client==1.9.0`, `tvdatafeed==2.1.0` được cài trong thư mục runtime riêng; `PYTHONPATH` chỉ bật cho dịch vụ **backtest** của mỗi bộ. Mã engine 2026.9 và Ultimate không bị sửa.
- Các bot paper tại 8090, 8093, 8095 vẫn dùng chiến lược/cấu hình cũ. Không bật paper cho năm chiến lược này trong lần thử. Muốn đưa một bản sang paper cần thẩm định mã, nguồn dữ liệu sống và hồ sơ chạy riêng trước.
- ZIP thô và log lưu cục bộ tại `../strategy-evaluation/results_long`; ZIP có mã tác giả và bản chụp cấu hình nên không đưa vào Git hay chia sẻ công khai. Bằng chứng đã lược nhạy cảm nằm ở [chỉ số](../benchmarks/freqtrade-france-summary.json) và [bảng kiểm dữ liệu](../benchmarks/freqtrade-france-data-quality.json).
