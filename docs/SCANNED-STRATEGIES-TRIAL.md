# Đối chiếu 6 chiến lược từ phiên quét `01a138fe` trên FreqPilot

Ngày thực hiện: 28/10/2026. Báo cáo này ghi nhận việc chuyển 6 chiến lược quy tắc kỹ thuật đạt kết quả **Đạt / Gần đạt** trong phiên quét tự động (`codex://threads/01a138fe-cb27-7cf1-97e7-888ae1c08e1f`, dịch vụ `http://127.0.0.1:8880/api/dashboard`) vào thư viện FreqPilot (`../freqtrade/user_data/strategies/`) và chạy trên cùng một giao thức backtest đóng băng của engine **Freqtrade 2026.9 chính thức**.

---

## 1. Giao thức đóng băng chung (Common Frozen Protocol)

| Hạng mục | Giá trị khóa cứng |
| :--- | :--- |
| **Engine** | Freqtrade chính thức `2026.9` (`dry_run=true`, `backtest_cache=none`) |
| **Thị trường & Đòn bẩy** | `BTC/USDT:USDT`, `ETH/USDT:USDT` — Binance USDT-M Futures Isolated `1x` |
| **Khoảng thời gian (`timerange`)** | `20260918-20261021` (`18/09/2026 00:00` → `21/10/2026 00:00 UTC`) |
| **Khung tín hiệu / Khung chi tiết** | Khung gốc của chiến lược (`1h` hoặc `4h`) / Chi tiết khớp lệnh `1m` |
| **Vốn / Stake / Số lệnh tối đa** | `1.000 USDT` / `100 USDT` mỗi lệnh / Tối đa `2` vị thế mở đồng thời |
| **Phí & Funding** | `0,05%` (`0.0005`) mỗi chiều + dữ liệu mark `1h` và funding rate `8h` thực tế |
| **Chính sách tham số** | Giữ nguyên công thức và giá trị mặc định từ nguồn đã ghim; **không tối ưu lại** |

---

## 2. Nguồn gốc (Provenance) và thay đổi tương thích sang `IStrategy` 1x

| Chiến lược trong FreqPilot | Nguồn gốc & Commit đã ghim | Phân loại ở hệ thống quét | Thay đổi tương thích khi đưa sang `IStrategy` 1x |
| :--- | :--- | :---: | :--- |
| **`MirazizDonchianAtr4h`** | `miraziz-Developer/forex-ai-analyst` (`801a5d276b7a541f939a3e93afdec33f4ab71fd8`) | **Đạt** (`CAGR/\|DD\| = 0,551`) | Dùng bộ tham số lịch năm 2025 (`entry_period=20`, `exit_period=20`, `atr_period=14`, `atr_mult=2.0`) trên khung `4h`, cố định `leverage=1.0`. |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af959350abd55b0d53d09bcaec8ee9967f55db`) | **Gần đạt** (`CAGR/\|DD\| = 0,498`) | Giữ nguyên `ema_short=50`, `ema_long=100`, độ dốc 21 nến, `rsi_entry_offset=10`, `rsi_exit_offset=30`, hỗ trợ cả Long & Short ở `1x`. |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee0aec0590ec1df5d674ecd0bf86cb8321`) | **Gần đạt** (`CAGR/\|DD\| = 0,447`) | Giữ nguyên breakout 20 nến `4h`, bộ lọc `EMA(50)`, `RSI(14)` trong `[45, 70]`, chặn mở lệnh cuối tuần (`weekday < 5`), `stoploss=-0.04`, `ROI=8%`. |
| **`EnriqueVolAdjusted1h`** | `EnriqueCerv/Simple_trading_strats` (`f65acd7a86eab180c631c17fb62c9ed6ec944de9`) | **Gần đạt** (`CAGR/\|DD\| = 0,444`) | Áp dụng công thức `z = pct_change(24) / (rolling_std(120) * sqrt(24)) >= 1.8` trên nến `1h` với chi tiết `1m`, biên dừng lỗ/chốt lời `4,5%` ở `1x`. |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9b653597b4908ab85b4b1f8e570448f79`) | **Gần đạt** (`CAGR/\|DD\| = 0,441`) | Giữ nguyên cấu hình `ema_trend_ride.toml`: `EMA(20) > EMA(50)`, `close > EMA(200)`, `ADX(14) > 20` (và đối xứng cho chiều Short) ở `1x`. |
| **`MesaTrendFollow1h`** | `maucarrasz/arb-paper-bot` (`3cd1df3e33bd5628989389ac70d0d08bb90e0f4a`) | **Gần đạt** (`CAGR/\|DD\| = 0,311`) | Giữ nguyên bộ lọc Mesa v2: `EMA(20) > EMA(50)`, `close > SMA(200)`, `RSI(14) < 75`, `ATR/close < 4%`, xung lượng 3h `[1,2%, 8%]`, `volume >= 1,8x MA20`. |

---

## 3. Kết quả Backtest đóng băng & Kiểm định trên FreqPilot (`20260918-20261021`)

Bảng dưới đây bao gồm 6 chiến lược mới chuyển từ phiên quét cùng 2 chiến lược `freqtrade_france` (`ObvDivergenceFadeDualV1`, `MfiLowvolShortV2`) chạy trên cùng cửa sổ có chi tiết khớp lệnh `1m`:

| Chiến lược | Khung | Gói chạy (`run_id`) | Xác minh SHA256 | Số lệnh | Thắng / Thua | Lãi / lỗ ròng (USDT) | Max Drawdown | Profit Factor | Lookahead / Recursive |
| :--- | :---: | :--- | :---: | ---: | :---: | ---: | ---: | ---: | :---: |
| **`EnriqueVolAdjusted1h`** | `1h` | `4cf305bd46` | ✓ `2ae32cb904` | **6** | 5 / 1 | **+4,78 USDT** (+0,48%) | **0,21%** | **3,27** | `has_bias=false` / `ok` |
| **`MesaTrendFollow1h`** | `1h` | `16d8bc76b6` | ✓ `a8f3a3eca4` | **6** | 2 / 4 | **-0,37 USDT** (-0,04%) | **0,65%** | **0,94** | `has_bias=false` / `ok` |
| **`MirazizDonchianAtr4h`** | `4h` | `30b93870b6` | ✓ `fb7573b36f` | **5** | 2 / 3 | **-0,89 USDT** (-0,09%) | **0,65%** | **0,86** | `has_bias=false` / `ok` |
| **`CodexBotVibe4h`** | `4h` | `c0139f5346` | ✓ `c802afd489` | **2** | 1 / 1 | **-2,08 USDT** (-0,21%) | **0,23%** | **0,09** | `has_bias=false` / `ok` |
| **`BdrEmaRideFutures1h`** | `1h` | `d4e981aee0` | ✓ `a6f4bd11c5` | **33** | 4 / 29 | **-4,63 USDT** (-0,46%) | **1,72%** | **0,80** | `has_bias=false` / `ok` |
| **`ObvDivergenceFadeDualV1`** | `1h` | `dd302b44d4` | ✓ `8353cc1826` | **4** | 2 / 2 | **-5,25 USDT** (-0,52%) | **1,15%** | **0,54** | Đã lưu gói |
| **`DikibagastEmaRsi1h`** | `1h` | `a1b10fe40b` | ✓ `65616a39ae` | **23** | 8 / 15 | **-17,69 USDT** (-1,77%) | **2,16%** | **0,45** | `has_bias=false` / `ok` |
| **`MfiLowvolShortV2`** | `1h` | `f8ea3c6f27` | ✓ `39142b1fc1` | **0** | 0 / 0 | **0,00 USDT** (0,00%) | **0,00%** | — | Đã lưu gói |

---

## 4. Nhận định thực nghiệm & Giới hạn bằng chứng

1. **Tính toàn vẹn kỹ thuật**: Cả 6 chiến lược chuyển từ phiên quét `01a138fe` đều vượt qua kiểm tra `lookahead-analysis` (`has_bias = false`) và `recursive-analysis` (`status = success`) của Freqtrade 2026.9, có khai báo `IntParameter` / `DecimalParameter` để dùng ngay với **Parameter Presets**, **Walk-Forward** và **Ma trận Độ nhạy 2D**.
2. **Đọc kết quả trên cửa sổ `18/09/2026–21/10/2026` (chi tiết `1m`)**:
   - `EnriqueVolAdjusted1h` có kết quả dương (`+4,78 USDT`, 5/6 lệnh thắng, `PF = 3,27`, `MaxDD = 0,21%`), tuy nhiên tổng số lệnh (`6 lệnh`) vẫn là mẫu nhỏ (`< 30 lệnh`), chưa đủ để kết luận lợi thế thống kê dài hạn.
   - `BdrEmaRideFutures1h` (`33 lệnh`, `-4,63 USDT`, `PF = 0,80`) và `DikibagastEmaRsi1h` (`23 lệnh`, `-17,69 USDT`, `PF = 0,45`) tạo đủ mẫu giao dịch trong 1 tháng nhưng bị bào mòn bởi nhiễu đi ngang khi chạy chung trên cả BTC và ETH ở khung `1h`.
3. **Bằng chứng lưu trữ**: Chỉ số chi tiết, mã revision, `run_id`, `artifact_sha256` và ID báo cáo kiểm định được lưu tại [`benchmarks/scanned-strategies-summary.json`](../benchmarks/scanned-strategies-summary.json). Mã nguồn và các gói ZIP đóng băng nằm trong `../freqtrade/user_data/freqpilot/runs/`.
