# FreqPilot — Không gian Nghiên cứu, Kiểm định & Paper Trading Chiến lược Định lượng trên Freqtrade 2026.9 Chính thức

**FreqPilot** là không gian làm việc tập trung vào vòng đời chiến lược (*Ý tưởng → Mã nguồn → Kiểm toán Dữ liệu → Backtest Đóng băng → Kiểm định Lookahead/Recursive → Walk-Forward & Độ nhạy 2D → Paper 1x & Đối chiếu lệnh*), kết hợp giao diện kế thừa từ **FreqUI Ultimate v2.1.0** với **100% engine Freqtrade `2026.9` chính thức**.

- **Không cần đổi sang bản fork**: Hoạt động trực tiếp trên image `freqtradeorg/freqtrade` `2026.9` chính thức (118 tệp lõi engine giữ nguyên từng byte).
- **Bằng chứng đóng băng có dấu vân tay `SHA-256`**: Mỗi lần chạy tự động đóng băng bản sao mã `.py`, bộ tham số `preset`, cấu hình nghiên cứu và tệp dữ liệu `feather` (nến + mark + funding) thành gói `freqpilot-<id>.zip` có thể kiểm tra toàn vẹn, xuất `Dossier (.md)`, nhập lại trên máy khác và chạy `Archive Replay`.
- **An toàn tuyệt đối theo thiết kế**: Khóa cứng `dry_run=true`, `Binance USDT-M Futures Isolated 1x`, không nhận khóa API giao dịch tiền thật, không tự động tối ưu ngầm và không tự ý thay đổi chiến lược Paper đang chạy.

---

## 1. Tại sao chọn FreqPilot thay vì FreqUI mặc định hoặc bản Fork?

| Tiêu chí | FreqUI Mặc định | Bản Fork `frequi-ultimate` (`/strategy-dev`) | **FreqPilot (`/studio`)** |
| :--- | :--- | :--- | :--- |
| **Tương thích Engine Freqtrade `2026.9` gốc** | Có | **Không** (báo lỗi `404 Endpoint Not Found` nếu không cài bản fork `freqtrade-ultimate`) | **Có (100% Freqtrade `2026.9` chính thức)** |
| **Kiểm toán dữ liệu trước khi chạy** | Không | Không | **Kiểm tra nến, mark, funding 8h, khoảng trống timestamp & warmup candles** |
| **Đóng băng bằng chứng & Nhập/Xuất gói `.zip`** | Chỉ lưu JSON/ZIP rời | Điền lại biểu mẫu (`reconstitute`) | **Gói `artifact.zip` có `SHA-256`, `Import .zip`, `Archive Replay` khớp từng trường lệnh & xuất `Dossier (.md)`** |
| **Kiểm định Lookahead & Recursive** | Chỉ chạy qua CLI rời | Không tích hợp trong luồng chiến lược | **Tích hợp trực tiếp ở Bước `06 · Kiểm định`, gắn chặt với `revision` mã và `preset`** |
| **Walk-Forward & Holdout niêm phong** | Không | Ghép phần trăm cửa sổ & chia `WFE` qua 0 | **Rolling Train/OOS độc lập, đối chiếu Baseline không tối ưu vs Ứng viên và khóa Holdout riêng** |
| **Ma trận Độ nhạy 2 chiều (`.sensitivity-pivot`)** | Không | Nhiễu tham số hậu kiểm | **Backtest native thực cho từng ô `(Tham số 1 × Tham số 2 / Kịch bản phí)`** |
| **Đối chiếu Paper 1x vs Backtest** | Không | Chỉ đọc trạng thái bot live | **Quản lý hồ sơ Paper 1x riêng (`8095`), nhật ký `history.sqlite` và đối chiếu lệch lệnh `PaperReconcileWorkspace`** |

---

## 2. Quy trình 11 bước nghiên cứu khép kín trên `/studio`

1. **`01 · Ý tưởng`**: Ghi rõ giả thuyết, điều kiện vào/ra, gắn nhãn (`#tag`) và xuất prompt kèm bằng chứng gói chạy gần nhất cho Codex (`buildEvidenceCodexPrompt`).
2. **`02 · Mã chiến lược`**: Biên tập Python bằng Monaco Editor, tự lưu nháp theo `revision`, khôi phục/bỏ nháp 1 chạm, so sánh lịch sử bằng `DiffViewer` và khóa bảo vệ mã đang chạy Paper.
3. **`03 · Dữ liệu`**: Kiểm toán nến futures, mark price, funding rate và warmup; xem trước ngân sách và tải bù dữ liệu qua vùng tạm an toàn.
4. **`04 · Backtest`**: Chọn bộ tham số định danh (`ParameterPresets`), mở khung mã song song ngay cạnh biểu mẫu (`.run-split-layout`), đóng băng đầu vào hoặc **Nhập gói hồ sơ ngoại vi (`.zip`)**.
5. **`05 · Kết quả`**: Xem KPI cốt lõi, đường vốn đóng lệnh (`EquityCurveChart`), đường sụt giảm vốn (`UnderwaterChart`), bản đồ nhiệt tháng (`MonthlyReturnsHeatmap`), phân bố lý do thoát lệnh (`ExitReasonChart`), hiệu suất theo giờ/thứ UTC (`HourlyPatternChart`, `WeekdayPatternChart`), chạy `Archive Replay`, so sánh khóa giao thức (`protocol_hash`) và **Xuất Dossier (`.md`)**.
6. **`06 · Kiểm định`**: Chạy `lookahead-analysis` và `recursive-analysis` chính thức của Freqtrade 2026.9.
7. **`07 · Tối ưu`**: Chạy Hyperopt CLI chính thức với seed cố định, tách ngày Train / OOS bắt buộc và thí nghiệm đa seed (`SeedExperimentsWorkspace`).
8. **`08 · Walk-forward`**: Chuỗi rolling Train/OOS có `.wfa-timeline`, cột `Train tốt nhất`, đối chiếu Baseline và thẻ **Holdout niêm phong (`.holdout-grid`)**.
9. **`09 · Độ nhạy`**: Bảng ma trận 2 chiều `.sensitivity-pivot` đánh dấu ô `Mặc định`, không ngụy tạo số `0` cho các ô chưa chạy.
10. **`10 · Ma trận`**: Chạy kiểm thử độc lập trên từng cặp và khung thời gian với ví riêng.
11. **`11 · Paper`**: Chuẩn bị hồ sơ Paper `1x Isolated` từ gói backtest đã xác minh, quản lý vòng đời qua RPC chính thức và mở phiên quan sát đối chiếu lệnh thực tế với backtest.

---

## 3. Bằng chứng thực nghiệm đã kiểm chứng trong kho này

Toàn bộ các phép thử dưới đây đều chạy trên engine **Freqtrade 2026.9 chính thức** (`BTC/USDT:USDT` + `ETH/USDT:USDT`, Isolated `1x`, vốn `1.000 USDT`, stake `100 USDT`, tối đa `2` vị thế, phí `0,05%` mỗi chiều, có đầy đủ mark và funding thực tế, **không tinh chỉnh tham số để làm đẹp kết quả**):

### 3.1. Sàng lọc 6,7 tháng (`01/04/2026–21/10/2026`, chi tiết `5m`) từ 10 chiến lược trong phiên quét tự động
Chi tiết đầy đủ về nguồn gốc, công thức đa khung (`merge_informative_pair`), Ma trận Độ nhạy `3×3` và Walk-Forward/Holdout nằm tại **[`docs/SCANNED-STRATEGIES-TRIAL.md`](docs/SCANNED-STRATEGIES-TRIAL.md)** và **[`benchmarks/scanned-strategies-summary.json`](benchmarks/scanned-strategies-summary.json)**:

| Chiến lược | Nguồn gốc quy tắc | Khung | Gói lưu (`run_id`) | Số lệnh (6,7 tháng) | Lãi / lỗ ròng (USDT) | Max Drawdown | Profit Factor | Kết quả thẩm định độ bền |
| :--- | :--- | :---: | :--- | ---: | ---: | ---: | ---: | :--- |
| **`RocketHunterSma501h`** | `rocket-hunter-research` (`d8dae34e`) | `1h` (`+1d`) | `6826363795` | **8** | **+61,83 USDT** (+6,18%) | **0,35%** | **18,29** | Lãi cao nhất, drawdown thấp (`0,35%`), đã chuẩn bị hồ sơ Paper 1x. |
| **`DikibagastEmaRsi1h`** | `Dikibagast EMA RSI` (`a7af9593`) | `1h` | `8ebeb7170c` | **30** | **+44,23 USDT** (+4,42%) | **0,73%** | **3,96** | **Đạt 9/9 ô Độ nhạy 2D có lãi (`+26` → `+46 USDT`)**; Baseline thắng trên Holdout (`+9,16 USDT`). |
| **`BdrEmaRideFutures1h`** | `BDR-Pro/crypto-futures` (`0df59de9`) | `1h` (`+1d`) | `353953f473` | **8** | **+9,37 USDT** (+0,94%) | **1,41%** | **1,67** | Giữ lãi dương qua cả cửa sổ ngắn (1m) và dài (6,7 tháng). |
| **`TrendCoreBagging1h`** | `0x-boss/quant_crypto_strategy` | `1h` (`+1d`) | `bba655ff87` | **2** | **+2,15 USDT** (+0,21%) | **0,15%** | **2,45** | Giữ lãi dương, bộ lọc 100/150/200 ngày khắt khe. |
| **`CodexBotVibe4h`** | `erfanrhb/CodexBot` (`922e26ee`) | `4h` (`+1d`) | `c3b0b4c882` | **30** | **-20,02 USDT** (-2,00%) | **2,96%** | **0,67** | Minh chứng chống overfit: Lãi `+3,30 USDT` ở 1 tháng cuối nhưng lỗ `-20,02 USDT` khi xét đủ 6,7 tháng. |

### 3.2. Các báo cáo đối chứng khác trong kho
- **Đối chiếu 5 chiến lược công khai của Freqtrade France (FreqPilot vs Ultimate)**: Khớp từng giao dịch, lệnh con, phí và funding giữa 2 engine — xem **[`docs/FREQTRADE-FRANCE-TRIAL.md`](docs/FREQTRADE-FRANCE-TRIAL.md)**.
- **Đối chiếu 8 chiến lược mẫu từ `freqtrade-strategies`**: Xem **[`benchmarks/REPORT.md`](benchmarks/REPORT.md)** và **[`templates/PROVENANCE.json`](templates/PROVENANCE.json)**.

---

## 4. Cài đặt & Khởi chạy trong 3 bước

Yêu cầu: **Node.js 24**, **pnpm 10.33.2**, **Docker Desktop** và **PowerShell** (tương thích cả Windows PowerShell 5.1 và PowerShell 7).

```powershell
# Bước 1: Khởi tạo thư mục dữ liệu riêng, mật khẩu API ngẫu nhiên và 8 chiến lược mẫu (mặc định STOPPED, dry_run=true)
./Initialize.ps1

# Bước 2: Kiểm tra cấu hình, cổng mạng và schema chiến lược trước khi chạy
./Start.ps1 -CheckOnly

# Bước 3: Build giao diện + image nghiên cứu và khởi động dịch vụ
./Start.ps1 -Build
```

Sau khi khởi động:
- **FreqPilot Studio**: `http://localhost:8090/studio` (hoặc trực tiếp tại dịch vụ nghiên cứu `http://localhost:8091/studio`)
- **Quản lý Hồ sơ Paper 1x**: `http://localhost:8090/paper`
- **Tài khoản đăng nhập local**: Được tạo riêng trong tệp `<user_data>/ACCESS.txt` (không bao giờ lưu trong Git).

Để chạy toàn bộ bộ kiểm định tự động (Typecheck, `1.745` bài test UI, `133` bài test backend trong container cô lập không mạng, `28` bài kiểm tra bảo vệ cài đặt):
```powershell
./Check.ps1
```

---

## 5. Tài liệu & Giấy phép

- **Hướng dẫn vận hành, sao lưu & khôi phục**: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- **Hướng dẫn cài đặt độc lập**: [`docs/INSTALL.md`](docs/INSTALL.md)
- **Định hướng sản phẩm & Giới hạn hiện tại**: [`PRODUCT.md`](PRODUCT.md)
- **Chiến lược Thương hiệu & Định vị thị trường**: [`docs/BRAND-AND-MARKETING-PLAN.md`](docs/BRAND-AND-MARKETING-PLAN.md)
- **Giấy phép**: FreqPilot là phần mềm nguồn mở phát hành theo giấy phép **GNU GPL-3.0**, kế thừa từ FreqUI Ultimate v2.1.0 và FreqUI/Freqtrade. Xem đầy đủ ghi nhận bản quyền tại [`SOURCES.md`](SOURCES.md).
