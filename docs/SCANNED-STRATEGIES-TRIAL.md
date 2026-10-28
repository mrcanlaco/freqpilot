# Đối chiếu 10 chiến lược từ phiên quét `01a138fe` & Thẩm định độ bền trên FreqPilot

Ngày thực hiện: 28/10/2026. Báo cáo này ghi nhận việc chuyển **10 chiến lược quy tắc kỹ thuật** đạt kết quả **Đạt / Gần đạt** trong phiên quét tự động (`codex://threads/01a138fe-cb27-7cf1-97e7-888ae1c08e1f`, dịch vụ `http://127.0.0.1:8880/api/dashboard`) sang dạng `IStrategy` của FreqPilot (`../freqtrade/user_data/strategies/`), chạy kiểm định trên cả **cửa sổ ngắn chi tiết `1m` (`18/09/2026–21/10/2026`)** lẫn **cửa sổ dài 6,7 tháng chi tiết `5m` (`01/04/2026–21/10/2026`)**, quét **Ma trận Độ nhạy 2D (`3×3`)**, chạy **Walk-Forward + Holdout niêm phong**, và chuẩn bị **Hồ sơ Paper 1x Isolated**.

> **Lưu ý về tính tương đương thực thi**: Đây là các bản chuyển thể sang kiến trúc `IStrategy` của Freqtrade 2026.9 (chạy chung trên 2 cặp `BTC/USDT:USDT` + `ETH/USDT:USDT`, Isolated `1x`, vốn `1.000 USDT`, stake cố định `100 USDT/lệnh`, phí `0,05%` mỗi chiều và funding thực tế), **không phải** phép phát lại từng byte của các bộ mô phỏng độc lập trong `CryptoResearch`.

---

## 1. Danh mục 10 chiến lược chuyển từ phiên quét `01a138fe` (Đợt 1 & Đợt 2)

| # | Chiến lược trong FreqPilot | Nguồn gốc & Commit đã ghim | Phân loại quét | Quy tắc chỉ báo & Rào chắn khớp spec nguồn |
| :-: | :--- | :--- | :---: | :--- |
| **1** | **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af9593`) | **Gần đạt** (`0,498`) | `EMA(50)` vs `EMA(100)`, độ dốc 21 nến, khoảng cách tách biệt `\|EMA50 - EMA100\| >= 2.0 * ATR(14)`, `RSI(14)` offset `10`/`30` hai chiều Long/Short. |
| **2** | **`RocketHunterSma501h`** | `accordgtsx-cyber/rocket-hunter-research` (`d8dae34e`) | **Gần đạt** (`0,346`) | Ghép nến `1d` đã đóng (`merge_informative_pair`): Long khi `close_1d > SMA(50)`, thoát khi `close_1d <= SMA(50)` tại `00:00 UTC`. |
| **3** | **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9`) | **Gần đạt** (`0,441`) | Ghép nến `1d` đã đóng: `EMA(20) > EMA(50)`, `close > EMA(200)`, `ADX(14) > 20` (đối xứng cho Short); quyết định lúc `00:00 UTC`, stop `1.5 * ATR14_1d` kẹp `[0,4%, 25%]`. |
| **4** | **`TrendCoreBagging1h`** | `0x-boss/quant_crypto_strategy` (`TrendCore`) | **Gần đạt** (`0,376`) | Ghép nến `1d` đã đóng: trung bình 3 cổng xu hướng (`100`, `150`, `200` ngày: `close > SMA(k)` & `close > close[k]` & `EWMAC > 0`), vào khi `score >= 0.5`, thoát khi `< 0.3`. |
| **5** | **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee`) | **Gần đạt** (`0,447`) | Breakout đỉnh 20 nến `4h` + ghép nến `1d` đã đóng (`close_1d > EMA50_1d`, `RSI14_1d` trong `[45, 70]`), chặn cuối tuần, stop `2*ATR14` / target `4*ATR14`. |
| **6** | **`CodeAlchemyLowPassFisher1h`** | `CodeAlchemy LowPass200 Fisher10` (`4b55d57f`) | **Gần đạt** (`0,349`) | Ghép nến `1d` đã đóng: bộ lọc đệ quy bậc 2 `LowPass(200)` (Zorro Workshop 4a) kết hợp `Fisher Transform(10)` hai chiều Long/Short. |
| **7** | **`MesaTrendFollow1h`** | `maucarrasz/arb-paper-bot` (`3cd1df3e`) | **Gần đạt** (`0,311`) | `EMA(20) > EMA(50)` trên `1h` & `4h`, `close_4h > SMA200_4h`, `RSI(14) < 75`, `ATR/close < 4%`, xung lượng 3h `[1,2%, 8%]`, `vol >= 1,8x MA20`; Chandelier `2.5*ATR` & `96h`. |
| **8** | **`QuantgenTrendVoting1h`** | `xkg4real/quantgen` (`QUANTGEN C3`) | **Gần đạt** (`0,407`) | Ghép nến `1d` đã đóng: trung bình dấu 9 phiếu (`mom 7/14/21/28` + `SMA 10/20/50/100/200`), ngưỡng trễ `hysteresis = ±0.2`. |
| **9** | **`MirazizDonchianAtr4h`** | `miraziz-Developer/forex-ai-analyst` (`801a5d27`) | **Đạt** (`0,551`) | Lịch tham số kỳ `2026-07-01` (`entry_period=100`, `exit_period=20`, `atr_period=14`, `atr_mult=3.0`) trên nến `4h`. |
| **10** | **`EnriqueVolAdjusted1h`** | `EnriqueCerv/Simple_trading_strats` (`f65acd7a`) | **Gần đạt** (`0,444`) | Ghép nến `1d` đã đóng (`sigma = std(30)*sqrt(3)`, `z = pct_change(3)/sigma >= 1.8`), vào lúc `00:00 UTC`, rào chắn `±1.6*sigma` & timeout `24` ngày. |

---

## 2. Kết quả Backtest đóng băng & Kiểm định trên cửa sổ ngắn `1m` (`20260918-20261021`)

| Chiến lược | Khung | Revision | Gói chạy (`run_id`) | Xác minh SHA256 | Số lệnh | Thắng / Thua | Lãi / lỗ ròng (USDT) | Max Drawdown | Profit Factor | Lookahead / Recursive |
| :--- | :---: | :--- | :--- | :---: | ---: | :---: | ---: | ---: | ---: | :---: |
| **`DikibagastEmaRsi1h`** | `1h` | `b82e4ae101` | `81b6113b7f` | ✓ `c5b6b5f8d6` | **5** | 4 / 1 | **+8,99 USDT** (+0,90%) | **0,37%** | **3,40** | `has_bias=false` / `ok` |
| **`RocketHunterSma501h`** | `1h` | `484cebfefa` | `079221779f` | ✓ `66a8818477` | **2** | 2 / 0 | **+6,80 USDT** (+0,68%) | **0,00%** | — | `has_bias=false` / `ok` |
| **`BdrEmaRideFutures1h`** | `1h` | `1474053fd7` | `a23a717003` | ✓ `edaeed3b16` | **2** | 1 / 1 | **+5,55 USDT** (+0,55%) | **0,05%** | **12,06** | `has_bias=false` / `ok` |
| **`TrendCoreBagging1h`** | `1h` | `f1260f2655` | `327848ca28` | ✓ `4fa88f8656` | **2** | 1 / 1 | **+5,55 USDT** (+0,55%) | **0,05%** | **12,06** | `has_bias=false` / `ok` |
| **`CodexBotVibe4h`** | `4h` | `c1e250bee2` | `bb62407e56` | ✓ `dab9dc131e` | **5** | 2 / 3 | **+3,30 USDT** (+0,33%) | **0,74%** | **1,44** | `has_bias=false` / `ok` |
| **`CodeAlchemyLowPassFisher1h`** | `1h` | `95c0f731db` | `be2030ee60` | ✓ `e40fa70a0d` | **2** | 1 / 1 | **-1,19 USDT** (-0,12%) | **0,72%** | **0,84** | `has_bias=false` / `ok` |
| **`MesaTrendFollow1h`** | `1h` | `bc1d04d6fe` | `17b2d1bcb0` | ✓ `ed9a3e18c8` | **5** | 2 / 3 | **-1,75 USDT** (-0,17%) | **0,35%** | **0,50** | `has_bias=false` / `ok` |
| **`QuantgenTrendVoting1h`** | `1h` | `eb8ed665d5` | `070169696b` | ✓ `1aa14c1714` | **2** | 1 / 1 | **-4,65 USDT** (-0,46%) | **0,56%** | **0,17** | `has_bias=false` / `ok` |
| **`MirazizDonchianAtr4h`** | `4h` | `fc9cc006b6` | `851d5099c2` | ✓ `0ed99d6273` | **2** | 0 / 2 | **-4,92 USDT** (-0,49%) | **0,49%** | **0,00** | `has_bias=false` / `ok` |
| **`EnriqueVolAdjusted1h`** | `1h` | `62cf4cd1bc` | `991aeb5475` | ✓ `4f6f11a8cb` | **3** | 1 / 2 | **-9,86 USDT** (-0,99%) | **1,41%** | **0,31** | `has_bias=false` / `ok` |

---

## 3. Thẩm định dài hạn 6,7 tháng (`20260401-20261021`, chi tiết `5m`) cho Top 5 chiến lược có lãi

Khi mở rộng cửa sổ kiểm thử lên **6,7 tháng (`01/04/2026–21/10/2026`)** với dữ liệu chi tiết `5m` (`75.690` nến/cặp):

| Chiến lược | Khung | Gói chạy (`run_id`) | Xác minh SHA256 | Số lệnh | Lãi / lỗ ròng (USDT) | Tỷ suất % | Max Drawdown | Profit Factor | Đánh giá độ bền 6,7 tháng |
| :--- | :---: | :--- | :---: | ---: | ---: | ---: | ---: | ---: | :--- |
| **`RocketHunterSma501h`** | `1h` | `6826363795` | ✓ `c621b60697` | **8** | **+61,83 USDT** | **+6,18%** | **0,35%** | **18,29** | Lãi cao nhất, drawdown cực thấp (`0,35%`), nhưng tần suất thấp (`8` lệnh / 6,7 tháng). |
| **`DikibagastEmaRsi1h`** | `1h` | `8ebeb7170c` | ✓ `c3318b980e` | **30** | **+44,23 USDT** | **+4,42%** | **0,73%** | **3,96** | **Đạt chuẩn mẫu cơ bản (`30` lệnh)**, lợi nhuận ổn định, `PF = 3,96`, `MaxDD = 0,73%`. |
| **`BdrEmaRideFutures1h`** | `1h` | `353953f473` | ✓ `d50ef29c3a` | **8** | **+9,37 USDT** | **+0,94%** | **1,41%** | **1,67** | Giữ lãi dương qua 6,7 tháng (`PF = 1,67`). |
| **`TrendCoreBagging1h`** | `1h` | `bba655ff87` | ✓ `9f8699dfca` | **2** | **+2,15 USDT** | **+0,21%** | **0,15%** | **2,45** | Giữ lãi dương, bộ lọc 100/150/200 ngày rất khắt khe. |
| **`CodexBotVibe4h`** | `4h` | `c3b0b4c882` | ✓ `667e07f6a7` | **30** | **-20,02 USDT** | **-2,00%** | **2,96%** | **0,67** | **Bị loại**: Lãi ở 1 tháng cuối nhưng âm `-20,02 USDT` khi xét đủ 30 lệnh trên 6,7 tháng. |

---

## 4. Ma trận Độ nhạy 2D (`d28b58b598`) & Walk-Forward + Holdout (`94b955e45b`) của `DikibagastEmaRsi1h`

### 4.1. Ma trận Độ nhạy 2D (`ema_short` $\in \{45, 50, 55\} \times$ `rsi_entry_offset` $\in \{8, 10, 12\}$, kỳ `20260401-20261021`)
Toàn bộ **9/9 ô lân cận** đều có lãi ròng dương (từ **`+26,21 USDT`** đến **`+46,09 USDT`**) và Drawdown dưới **`1,53%`**, phản ánh tính liên tục của vùng tham số lân cận `(50, 10)` trên mẫu 6,7 tháng này (không phải chứng minh tuyệt đối không overfit):

| `ema_short` \ `rsi_entry_offset` | `8` | `10` *(Gốc)* | `12` |
| :--- | :--- | :--- | :--- |
| **`45`** | `+39,68 USDT` · 40 lệnh · DD `1,52%` | `+44,93 USDT` · 38 lệnh · DD `0,99%` | `+42,26 USDT` · 38 lệnh · DD `1,00%` |
| **`50` *(Gốc)*** | `+46,09 USDT` · 32 lệnh · DD `0,84%` | **`+44,23 USDT` · 30 lệnh · DD `0,73%` [Mặc định]** | `+40,20 USDT` · 29 lệnh · DD `0,76%` |
| **`55`** | `+35,82 USDT` · 23 lệnh · DD `0,41%` | `+28,16 USDT` · 20 lệnh · DD `0,36%` | `+26,21 USDT` · 20 lệnh · DD `0,36%` |

### 4.2. Walk-Forward (`2` cửa sổ rolling `90d Train / 35d OOS`) & Holdout tách khỏi Hyperopt (`20260916-20261021`)
- **Cửa sổ #0 (`Train 20260401-20260630` → `OOS 20260630-20260804`)**:
  - Train tốt nhất (`epoch #1`): `+6,09 USDT` (`5` lệnh) | Baseline OOS: `-6,42 USDT` (`4` lệnh) | Ứng viên OOS: `-0,60 USDT` (`3` lệnh, `DD 0,27%`).
- **Cửa sổ #1 (`Train 20260506-20260804` → `OOS 20260804-20260908`)**:
  - Train tốt nhất (`epoch #1`): `+5,54 USDT` (`8` lệnh) | **Baseline OOS: `+13,18 USDT` (`11` lệnh, `PF 7,97`)** | Ứng viên OOS: `+6,78 USDT` (`5` lệnh, `PF 3,56`).
- **Holdout tách khỏi Hyperopt (`20260916-20261021` — đối chiếu hồi cứu / retrospective check, do bản baseline & ma trận độ nhạy đã chạy qua cửa sổ 01/04–21/10)**:
  - **Baseline (không tối ưu — `50/100/10/30/2.0`)**: **`+9,16 USDT` (`5` lệnh, `+0,92%`, `MaxDD 0,37%`, `PF 3,44`)**.
  - **Ứng viên Hyperopt (`58/102/16/22/2.2`)**: `-3,46 USDT` (`2` lệnh, `MaxDD 0,36%`).
- **Kết luận từ phép đối chiếu**: Bộ tham số gốc không tối ưu (**Baseline**) vượt trội hơn ứng viên Hyperopt trên cả OOS #1 lẫn kỳ `20260916-20261021` → **giữ nguyên bộ tham số gốc để đưa sang Paper 1x**.

---

## 5. Hồ sơ Paper 1x Isolated đã chuẩn bị sẵn sàng (`/paper`)

Từ hai gói backtest 6,7 tháng đã xác minh `SHA256`, hai hồ sơ Paper `1x Isolated` (`dry_run=true`, `initial_state=stopped`) đã được chuẩn bị trong `user_data/freqpilot/paper/profiles/` (không tự động thay thế hoặc khởi động đè lên worker hiện tại):
1. **`DikibagastEmaRsi1h · 6.7m Verified 1x`** (`profile_id = 4e1b0cb3ef0745e69a5c7bd1ab837e8f`, wrapper `FPPaper_4e1b0cb3ef0745e6`, từ gói `8ebeb7170c`).
2. **`RocketHunterSma501h · 6.7m Verified 1x`** (`profile_id = f26d19d9d7254c1b87d3ea8701fd5a87`, wrapper `FPPaper_f26d19d9d7254c1b`, từ gói `6826363795`).
