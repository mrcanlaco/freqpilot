# Đối chiếu 6 chiến lược từ phiên quét `01a138fe` trên FreqPilot

Ngày thực hiện: 28/10/2026. Báo cáo này ghi nhận việc chuyển 6 chiến lược quy tắc kỹ thuật đạt kết quả **Đạt / Gần đạt** trong phiên quét tự động (`codex://threads/01a138fe-cb27-7cf1-97e7-888ae1c08e1f`, dịch vụ `http://127.0.0.1:8880/api/dashboard`) sang dạng `IStrategy` của FreqPilot (`../freqtrade/user_data/strategies/`) và chạy trên cùng một giao thức backtest đóng băng của engine **Freqtrade 2026.9 chính thức**.

> **Lưu ý về tính tương đương thực thi**: Đây là các bản chuyển thể sang kiến trúc `IStrategy` của Freqtrade 2026.9 (chạy chung trên 2 cặp `BTC/USDT:USDT` + `ETH/USDT:USDT`, Isolated `1x`, vốn `1.000 USDT`, stake cố định `100 USDT/lệnh`, khớp lệnh chi tiết `1m`, phí `0,05%` mỗi chiều và funding thực tế), **không phải** phép phát lại từng byte của các bộ mô phỏng độc lập trong `CryptoResearch` (vốn dùng sizing theo `% equity` hoặc toàn bộ tiền mặt trên 1 cặp Spot/Perp riêng lẻ, trượt giá riêng và dữ liệu từ 2025).

---

## 1. Giao thức đóng băng chung (Common Frozen Protocol)

| Hạng mục | Giá trị khóa cứng |
| :--- | :--- |
| **Engine** | Freqtrade chính thức `2026.9` (`dry_run=true`, `backtest_cache=none`) |
| **Thị trường & Đòn bẩy** | `BTC/USDT:USDT`, `ETH/USDT:USDT` — Binance USDT-M Futures Isolated `1x` |
| **Khoảng thời gian (`timerange`)** | `20260918-20261021` (`18/09/2026 00:00` → `21/10/2026 00:00 UTC`) |
| **Khung tín hiệu / Khung chi tiết** | Khung gốc của chiến lược (`1h` hoặc `4h`) kèm `merge_informative_pair` (`1d` / `4h`) / Chi tiết `1m` |
| **Vốn / Stake / Số lệnh tối đa** | `1.000 USDT` / `100 USDT` mỗi lệnh / Tối đa `2` vị thế mở đồng thời |
| **Phí & Funding** | `0,05%` (`0.0005`) mỗi chiều + dữ liệu mark `1h` và funding rate `8h` thực tế |
| **Chính sách tham số** | Giữ nguyên công thức chỉ báo, khung informative và hệ số rào chắn từ spec nguồn; **không tối ưu lại** |

---

## 2. Nguồn gốc (Provenance) và ánh xạ quy tắc sang `IStrategy` 1x

| Chiến lược trong FreqPilot | Nguồn gốc & Commit đã ghim | Phân loại ở hệ thống quét | Quy tắc chỉ báo & Rào chắn khớp spec nguồn (`source_aligned_runs`) | Khác biệt của môi trường `IStrategy` |
| :--- | :--- | :---: | :--- | :--- |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af959350abd55b0d53d09bcaec8ee9967f55db`) | **Gần đạt** (`0,498`) | `EMA(50)` vs `EMA(100)`, độ dốc `EMA(100)` qua `21` nến, độ tách biệt `\|EMA50 - EMA100\| >= 2.0 * ATR(14)`, `RSI(14)` offset `10`/`30` hai chiều Long/Short. | Chạy trên cả BTC+ETH với stake `100 USDT` thay vì `45% equity` chỉ trên BTC. |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9b653597b4908ab85b4b1f8e570448f79`) | **Gần đạt** (`0,441`) | Ghép nến `1d` đã đóng (`merge_informative_pair`): `EMA(20) > EMA(50)`, `close > EMA(200)`, `ADX(14) > 20` (đối xứng cho Short); quyết định lúc `00:00 UTC`, dừng lỗ `1.5 * ATR14_1d` kẹp trong `[0,4%, 25%]`. | Stake `100 USDT` thay vì `8% equity` trên mỗi đồng. |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee0aec0590ec1df5d674ecd0bf86cb8321`) | **Gần đạt** (`0,447`) | Breakout đỉnh `20` nến `4h` + ghép nến `1d` đã đóng (`close_1d > EMA50_1d`, `RSI14_1d` trong `[45, 70]`), chặn cuối tuần (`weekday < 5`), rào chắn `2 * ATR14` stop / `4 * ATR14` target (`reward_risk=2`). | Chạy USDT-M `1x` thay vì BTC Spot sizing `0,5% equity / 2 ATR`. |
| **`MesaTrendFollow1h`** | `maucarrasz/arb-paper-bot` (`3cd1df3e33bd5628989389ac70d0d08bb90e0f4a`) | **Gần đạt** (`0,311`) | `EMA(20) > EMA(50)` trên cả `1h` và `4h`, `close_4h > SMA200_4h`, `RSI(14) < 75`, `ATR/close < 4%`, xung lượng 3h `[1,2%, 8%]`, `vol >= 1,8x MA20`; thoát theo `EMA20 < EMA50`, `1.5*ATR` initial stop, `2.5*ATR` Chandelier hoặc `96h`. | Không có `SOLUSDT` trong phạm vi BTC/ETH của FreqPilot. |
| **`MirazizDonchianAtr4h`** | `miraziz-Developer/forex-ai-analyst` (`801a5d276b7a541f939a3e93afdec33f4ab71fd8`) | **Đạt** (`0,551`) | Lịch tham số kỳ `2026-07-01` (`entry_period=100`, `exit_period=20`, `atr_period=14`, `atr_mult=3.0`) trên nến `4h`, cắt lỗ `open_rate - 3.0 * entry_atr`. | Chạy BTC/ETH độc lập thay vì 5 sleeve Futures. |
| **`EnriqueVolAdjusted1h`** | `EnriqueCerv/Simple_trading_strats` (`f65acd7a86eab180c631c17fb62c9ed6ec944de9`) | **Gần đạt** (`0,444`) | Ghép nến `1d` đã đóng (`sigma = std(ret_1d, 30) * sqrt(3)`, `z = pct_change(close_1d, 3) / sigma >= 1.8`), vào lệnh lúc `00:00 UTC`, rào chắn `±1.6 * entry_sigma` mỗi giờ và timeout `24` ngày (`ceil(3 * 1.6^2 * 3)`). | Cửa sổ `1m` local bắt đầu từ `15/09/2026` (33 ngày giao dịch) và stake `100 USDT` trên BTC/ETH Futures thay vì Spot BTC all-in từ `01/01/2025`. |

---

## 3. Kết quả Backtest đóng băng & Kiểm định (`source_aligned_runs` — `20260918-20261021`)

| Chiến lược | Khung | Mã Revision | Gói chạy (`run_id`) | Xác minh SHA256 | Số lệnh | Thắng / Thua | Lãi / lỗ ròng (USDT) | Max Drawdown | Profit Factor | Lookahead / Recursive |
| :--- | :---: | :--- | :--- | :---: | ---: | :---: | ---: | ---: | ---: | :---: |
| **`DikibagastEmaRsi1h`** | `1h` | `b82e4ae101` | `81b6113b7f` | ✓ `c5b6b5f8d6` | **5** | 4 / 1 | **+8,99 USDT** (+0,90%) | **0,37%** | **3,40** | `has_bias=false` / `ok` |
| **`BdrEmaRideFutures1h`** | `1h` | `1474053fd7` | `a23a717003` | ✓ `edaeed3b16` | **2** | 1 / 1 | **+5,55 USDT** (+0,55%) | **0,05%** | **12,06** | `has_bias=false` / `ok` |
| **`CodexBotVibe4h`** | `4h` | `c1e250bee2` | `bb62407e56` | ✓ `dab9dc131e` | **5** | 2 / 3 | **+3,30 USDT** (+0,33%) | **0,74%** | **1,44** | `has_bias=false` / `ok` |
| **`MfiLowvolShortV2`** *(France)* | `1h` | `26200335af` | `f8ea3c6f27` | ✓ `39142b1fc1` | **0** | 0 / 0 | **0,00 USDT** (0,00%) | **0,00%** | — | Đã lưu gói |
| **`MesaTrendFollow1h`** | `1h` | `bc1d04d6fe` | `17b2d1bcb0` | ✓ `ed9a3e18c8` | **5** | 2 / 3 | **-1,75 USDT** (-0,17%) | **0,35%** | **0,50** | `has_bias=false` / `ok` |
| **`MirazizDonchianAtr4h`** | `4h` | `fc9cc006b6` | `851d5099c2` | ✓ `0ed99d6273` | **2** | 0 / 2 | **-4,92 USDT** (-0,49%) | **0,49%** | **0,00** | `has_bias=false` / `ok` |
| **`ObvDivergenceFadeDualV1`** *(France)* | `1h` | `b3b9abdbaa` | `dd302b44d4` | ✓ `8353cc1826` | **4** | 2 / 2 | **-5,25 USDT** (-0,52%) | **1,15%** | **0,54** | Đã lưu gói |
| **`EnriqueVolAdjusted1h`** | `1h` | `62cf4cd1bc` | `991aeb5475` | ✓ `4f6f11a8cb` | **3** | 1 / 2 | **-9,86 USDT** (-0,99%) | **1,41%** | **0,31** | `has_bias=false` / `ok` |

---

## 4. Các gói chạy thăm dò một khung thời gian ban đầu (`retained_exploratory_single_tf_runs`)

Trước khi ghép `merge_informative_pair` (`1d` / `4h`) và rào chắn động `custom_exit`, 6 gói chạy thử nghiệm rút gọn trên một khung thời gian đơn lẻ đã được tạo và **giữ nguyên trong kho lưu trữ** (`user_data/freqpilot/runs/`) để phục vụ đối chiếu qua `RunNotesPanel` (được gắn nhãn rõ là **biến thể thăm dò không tương đương spec nguồn**):

| Chiến lược | Revision thăm dò | Gói chạy (`run_id`) | Khác biệt so với bản khớp spec nguồn | Kết quả thăm dò (`20260918-20261021`) |
| :--- | :--- | :--- | :--- | :--- |
| `MirazizDonchianAtr4h` | `723d40df73` | `30b93870b6` | Dùng lịch kỳ `2025-01-01` (`20/20/2.0`) thay vì lịch `2026-07-01` (`100/20/3.0`). | `5 lệnh · -0,89 USDT · PF 0,86` |
| `DikibagastEmaRsi1h` | `d60458e91d` | `a1b10fe40b` | Chưa bật điều kiện tách biệt `\|EMA50 - EMA100\| >= 2.0 * ATR14`. | `23 lệnh · -17,69 USDT · PF 0,45` |
| `CodexBotVibe4h` | `e0e4ee01e3` | `c0139f5346` | Tính `EMA50`/`RSI14` trên `4h` và stop/ROI tĩnh thay vì ghép `1d` + `2ATR/4ATR`. | `2 lệnh · -2,08 USDT · PF 0,09` |
| `EnriqueVolAdjusted1h` | `236a5d0179` | `4cf305bd46` | Tính z-score trên cửa sổ `24h/120h` và ROI/stoploss tĩnh `±4,5%` thay vì `1d 3d/30d` + `±1.6*sigma`. | `6 lệnh · +4,78 USDT · PF 3,27` |
| `BdrEmaRideFutures1h` | `8278db925b` | `d4e981aee0` | Tính `EMA20/50/200 + ADX14` trên `1h` thay vì ghép `1d` quyết định lúc `00:00 UTC`. | `33 lệnh · -4,63 USDT · PF 0,80` |
| `MesaTrendFollow1h` | `ad288b8ddc` | `16d8bc76b6` | Tính `SMA200` trên `1h` thay vì ghép `4h` + Chandelier `2.5*ATR` + timeout `96h`. | `6 lệnh · -0,37 USDT · PF 0,94` |

---

## 5. Nhận định thực nghiệm

1. **Tác động rõ rệt của bộ lọc đa khung (`1d`/`4h`) và điều kiện tách biệt xu hướng**:
   - Khi khôi phục đúng điều kiện tách biệt `|EMA50 - EMA100| >= 2.0 * ATR(14)` của **`DikibagastEmaRsi1h`**, số lệnh nhiễu giảm từ `23` xuống `5 lệnh`, kết quả chuyển từ `-17,69 USDT` sang **`+8,99 USDT` (`PF = 3,40`, `MaxDD = 0,37%`)**.
   - Khi khôi phục đúng bộ lọc ngày (`1d`) của **`BdrEmaRideFutures1h`** và **`CodexBotVibe4h`**, cả hai đều chuyển từ lỗ do nhiễu ngắn hạn sang lãi dương (**`+5,55 USDT`** và **`+3,30 USDT`**) với drawdown dưới `0,75%`.
2. **Giới hạn kích thước mẫu**: Trong cửa sổ `18/09/2026–21/10/2026` (nơi dữ liệu `1m` có sẵn đầy đủ), số lệnh của từng chiến lược sau khi lọc đa khung dao động từ `2` đến `5` lệnh (`< 30 lệnh`), do đó chỉ dùng để kiểm chứng tính đúng đắn của quy tắc, độ toàn vẹn gói chạy và không phát hiện lookahead/recursive bias — chưa đủ mẫu thống kê để kết luận lợi thế dài hạn.
3. **Bằng chứng lưu trữ**: Toàn bộ `run_id`, `revision`, `artifact_sha256` và ID báo cáo kiểm định của cả hai nhóm (`source_aligned_runs` và `retained_exploratory_single_tf_runs`) được lưu tại [`benchmarks/scanned-strategies-summary.json`](../benchmarks/scanned-strategies-summary.json).
