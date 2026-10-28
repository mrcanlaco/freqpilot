# Bộ Tài Liệu Ra Mắt Sản Phẩm & Kênh Phân Phối (Commercial Launch Kit) — FreqPilot

Tài liệu này cung cấp sẵn **cấu hình trỏ tên miền `.dev` trên Cloudflare**, **danh sách 4 gói sản phẩm `.zip` đã xuất**, và **nội dung bài đăng (Copywriting) dựng sẵn** cho BuyMeACoffee/Gumroad, Reddit và X (Twitter).

---

## 1. Kết nối tên miền `freqpilot.dev` trên Cloudflare (Chỉ mất 2 phút)

Trang Landing Page tĩnh (`site/index.html`) đã được gắn canonical `https://freqpilot.dev/` và triển khai trên cả repo lẫn Nginx container tại máy MSI (`http://127.0.0.1:8088`). Bạn có **2 cách** đưa `freqpilot.dev` lên sóng:

### Cách A (Khuyên dùng số 1 — Miễn phí 100%, CDN toàn cầu, không phụ thuộc máy MSI): Cloudflare Pages
1. Vào **Cloudflare Dashboard** → **Workers & Pages** → **Create** → **Pages** → **Upload assets** (hoặc kết nối GitHub repo `freqpilot` với thư mục build là `site`).
2. Kéo thả thư mục `E:\FreqPilot\freqpilot\site` lên.
3. Vào tab **Custom domains** → nhập `freqpilot.dev` → Cloudflare tự động trỏ DNS và cấp SSL trong 30 giây.

### Cách B: Trỏ trực tiếp về Nginx trên Máy MSI (`100.88.76.126:8088`) qua Cloudflare Tunnel sẵn có
Trên máy MSI (`DaoVangServer`), container `freqpilot-landing-web` đang chạy sẵn ở cổng `127.0.0.1:8088`.
Nếu bạn dùng Cloudflare Zero Trust Dashboard (**Networks → Tunnels**):
- Chọn Tunnel của máy MSI → **Public Hostname** → **Add a public hostname**:
  - **Domain**: `freqpilot.dev`
  - **Service Type**: `HTTP`
  - **URL**: `localhost:8088` (hoặc `host.docker.internal:8088`).
---

## 2. Gói Sản Phẩm Đã Xuất Sẵn Để Đưa Lên BuyMeACoffee / Gumroad (`work/release-dossiers/`)

Trong thư mục `E:\FreqPilot\freqpilot\work\release-dossiers\` đã có sẵn **4 cặp tệp `.zip` + `.md`** (đã kiểm tra khớp `SHA-256` 100%) để bạn tải thẳng lên mục **Extras / Products / Members-only Posts** của BuyMeACoffee hoặc Gumroad:

| Tệp Gói Đóng Băng (`.zip`) | Tài liệu Dossier (`.md`) | Dấu vân tay `SHA-256` | Kết quả 6,7 tháng (`5m`) | Phân loại bán |
| :--- | :--- | :--- | :--- | :--- |
| `freqpilot-DikibagastEmaRsi1h-8ebeb7170c.zip` | `dossier-DikibagastEmaRsi1h-8ebeb7170c.md` | `c3318b980e6282da...` | **+44,23 USDT** · 30 lệnh · DD `0,73%` · PF `3,96` *(Đạt 9/9 ô Độ nhạy 2D & thắng Holdout)* | **Gói Chủ Lực (Paid / Member)** |
| `freqpilot-RocketHunterSma501h-6826363795.zip` | `dossier-RocketHunterSma501h-6826363795.md` | `c621b60697a716d3...` | **+61,83 USDT** · 8 lệnh · DD `0,35%` · PF `18,29` | **Gói Chủ Lực (Paid / Member)** |
| `freqpilot-BdrEmaRideFutures1h-353953f473.zip` | `dossier-BdrEmaRideFutures1h-353953f473.md` | `d50ef29c3a7c82fb...` | **+9,37 USDT** · 8 lệnh · DD `1,41%` · PF `1,67` | **Gói Chủ Lực (Paid / Member)** |
| `freqpilot-TrendCoreBagging1h-bba655ff87.zip` | `dossier-TrendCoreBagging1h-bba655ff87.md` | `9f8699dfca98e06c...` | **+2,15 USDT** · 2 lệnh · DD `0,15%` · PF `2,45` | **Gói Mẫu Miễn Phí (Free Lead Magnet)** |

---

## 3. Nội dung dựng sẵn cho trang BuyMeACoffee / Gumroad (Copy & Paste)

### Tên trang / Sản phẩm:
**FreqPilot Quant Lab — Verified Strategy Dossiers & Reproducible Freqtrade Bundles**

### Mô tả Gói Hội Viên ($29/tháng) hoặc Gói Mua Lẻ ($39):
> **Không bán lời hứa lợi nhuận. Bán bằng chứng thực nghiệm có thể tái lập kèm dấu vân tay `SHA-256`.**
>
> Các chiến lược trong **FreqPilot Quant Lab** được sàng lọc từ hơn 920+ nguồn nghiên cứu công khai và kiểm chứng trên **Engine Freqtrade 2026.9 chính thức** (`BTC/USDT:USDT` & `ETH/USDT:USDT` Isolated `1x`) với phạm vi bằng chứng rõ ràng cho từng chiến lược:
> 1. **Toàn bộ 4 chiến lược trong gói (`DikibagastEmaRsi1h`, `RocketHunterSma501h`, `BdrEmaRideFutures1h`, `TrendCoreBagging1h`)**: Đã hoàn tất kiểm toán dữ liệu & phí funding 8h thực tế, kiểm định `lookahead-analysis` (`has_bias = false`) + `recursive-analysis`, và có gói đóng băng `SHA-256` trên cả cửa sổ ngắn (`1m` detail) lẫn cửa sổ dài 6,7 tháng (`20260401-20261021`, `5m` detail).
> 2. **Riêng `DikibagastEmaRsi1h`**: Đã chạy thêm bảng **Ma trận Độ nhạy 2D (`3×3` — `d28b58b598`, 9/9 ô dương)** và **Walk-Forward 2 cửa sổ + Holdout hồi cứu tách khỏi Hyperopt (`94b955e45b`)** để đối chiếu trực tiếp bộ tham số gốc (**Baseline**) với ứng viên Hyperopt.
>
> **Những gì bạn nhận được ngay khi tham gia:**
> - Trọn bộ tệp **`freqpilot-<id>.zip` (`SHA-256`)** + **`Dossier (.md)`** của các chiến lược trong gói.
> - Nạp 1 chạm vào mục **Nhập gói hồ sơ (`.zip`)** trong FreqPilot `/studio` và bấm **Archive Replay** để tự kiểm chứng.
> - Cập nhật **Báo cáo Đối chiếu Paper 1x vs Backtest** hàng tuần từ cụm máy chủ chạy 24/7.

---

## 4. Bài đăng mở màn trên Reddit (`r/algotrading` & `r/freqtrade`)

**Title:**
> I built an open-source Research Studio on top of official Freqtrade 2026.9 (Sealed Holdout WFA, 2D Sensitivity Matrix, SHA-256 Frozen Bundles) and audited 10 public crypto strategies over 6.7 months of 5m + funding data — here is what survived.

**Body:**
> Most open-source strategy backtests fail in production for three reasons: unverified funding rates, single-month cherry-picking, or Hyperopt overfitting without an untuned baseline comparison on a sealed holdout.
>
> Over the past weeks, I built **FreqPilot** — an open-source (GPL-3.0) research workspace that runs 100% on **official Freqtrade 2026.9** (zero engine modifications, no fork lock-in) and packages every run into a SHA-256 verified bundle (`code + preset + feather candles/mark/funding + native result ZIP`).
>
> **Key findings from auditing 10 rule-based strategies (`BTC/USDT:USDT` + `ETH/USDT:USDT`, 1x Isolated, 0.05% fee/side, actual funding):**
> 1. **Why 1-month tests lie:** `CodexBotVibe4h` (4h 20-bar breakout + daily EMA50/RSI14 filter) was profitable (`+3.30 USDT`, PF `1.44`) on the last 33-day `1m` window, but dropped to **`-20.02 USDT` (30 trades, PF `0.67`)** when expanded to the full 6.7-month `5m` window (`2026-04-01` to `2026-10-21`).
> 2. **2D Parameter Neighbor Continuity (Historical Sample):** `DikibagastEmaRsi1h` (EMA 50/100 + 21-bar slope + `2.0 * ATR(14)` separation + RSI 14 offset 10/30) finished the 6.7-month window at **`+44.23 USDT` (30 trades, MaxDD `0.73%`, PF `3.96`)**, and all 9/9 cells in its `3×3` 2D Sensitivity Matrix (`ema_short ∈ {45,50,55} × rsi_offset ∈ {8,10,12}`) were positive (`+26.21` to `+46.09 USDT` in this sample).
> 3. **Untuned Baseline vs. Hyperopt (Retrospective WFA Holdout Check):** In a 2-window Walk-Forward test (`94b955e45b`), the untuned default baseline outperformed the Hyperopt-selected candidate on both Window #1 OOS (`+13.18 USDT` vs `+6.78 USDT`) and the post-Hyperopt `2026-09-16` to `2026-10-21` interval (`+9.16 USDT, PF 3.44` vs `-3.46 USDT`).
> Full benchmark report, provenance hashes, and open-source studio code: https://github.com/mrcanlaco/freqpilot (Website: https://freqpilot.dev). Feedback and critiques on the methodology are very welcome!
