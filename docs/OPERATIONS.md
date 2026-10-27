# FreqPilot: sử dụng và khôi phục

Phạm vi: Freqtrade chính thức 2026.9, BTC/ETH Binance USDT-M Futures isolated 1x, chỉ backtest và paper. Các trang mới dùng cùng API nghiên cứu đã xác thực; worker paper hiện tại vẫn là dịch vụ riêng.

## Test một chiến lược

1. Vào **Chiến lược**, chọn hoặc sao chép chiến lược. Ghi rõ ý tưởng, lưu mã và đọc phiên bản đang mở.
2. Vào **Dữ liệu**, chọn ngày bắt đầu/kết thúc trong biểu mẫu Backtest. Kiểm tra nến, mark, funding và warmup. Chỉ nhấn **Đối chiếu funding với Binance** khi cần truy vấn công khai; mất mạng được ghi “chưa xác minh”. Nếu thiếu, xem kế hoạch rồi chủ động nhấn tải bù. Bản tải bù được kiểm tra trong vùng riêng trước khi đưa vào kho nghiên cứu.
3. Vào **Backtest** và chạy. Hồ sơ có phiên bản mã, cấu hình, hash dữ liệu và ZIP kết quả native. Kết quả cũ vẫn xem được; mã vừa sửa không biến thành mã đã chạy.
4. Đọc số lệnh, P&L, drawdown, phí/funding, phạm vi và kiểm định. Ít lệnh hoặc funding chưa xác minh không được gọi là chiến lược đạt.
5. Nếu muốn tối ưu, xem trước ngân sách và chạy Hyperopt native. Tab Tối ưu còn có thí nghiệm nhiều seed trên cùng tập train, mỗi seed chạy tuần tự. **Walk-forward** là chuỗi train/OOS rolling; mỗi OOS khởi đầu không vị thế. Holdout tách riêng và chỉ mở bằng nút riêng. **Độ nhạy** chạy backtest native từng bộ tham số và kịch bản phí, ô chưa chạy để trống. **Ma trận** thử BTC/ETH × khung nến thành các ô độc lập, chỉ bắt đầu khi từng ô có dữ liệu và funding được xác minh. Mỗi ô có vốn riêng, không cộng kết quả thành danh mục. `status=success` chỉ nghĩa tác vụ kết thúc; đọc `research_status` và từng cửa sổ/ô để biết kết quả đủ hay thiếu.
6. Chỉ sau khi chọn một gói backtest đã lưu mới chuẩn bị hồ sơ **Paper**. Quan sát paper là phiên bắt đầu từ lúc bấm, không hồi tố. Đóng phiên, chạy backtest cùng hồ sơ nếu nguồn còn khớp và dữ liệu đủ, rồi so sánh. Khi chưa có lệnh hoặc bằng chứng thiếu, báo cáo là “chưa đủ bằng chứng”.

Trong danh sách Paper, dùng **Lưu trữ hồ sơ** để ẩn hồ sơ cũ. Worker phải kết nối được và không đang chọn hồ sơ đó. **Xem hồ sơ đã lưu trữ → Hiện lại hồ sơ** để dùng lại; trạng thái hiển thị được lưu riêng, không xóa hoặc chỉnh sửa mã, database hay lịch sử. Muốn bật paper từ hồ sơ đã lưu trữ, cần hiện lại trước.

Không thao tác nào ở trên tự bật giao dịch tiền thật. Chuyển tab, xem ứng viên hoặc mở holdout không đổi hồ sơ paper.

Freqtrade 2026.9 chỉ cho chọn nhóm tham số Hyperopt qua CLI; khoảng `low/high` của từng `Parameter` lấy từ mã. Trang Tối ưu hiển thị phạm vi hiện có nhưng không cho đổi ngầm trên một snapshot. Muốn đổi một khoảng, sửa định nghĩa trong mã như revision mới, rồi backtest và kiểm định lại.

## Dung lượng và sao lưu

Đo trước khi chạy tác vụ lớn:

```powershell
python tools/storage_report.py ../freqtrade/user_data
```

Báo cáo chỉ đọc, nhóm kích thước và các bản sao có cùng hash. **Không xóa hoặc hardlink** vì một gói lưu có thể còn được hồ sơ nghiên cứu tham chiếu. Preview của tác vụ dữ liệu/WFA cũng báo dung lượng ước tính.

Sao lưu riêng (thư mục đích phải mới và nằm ngoài `user_data`):

```powershell
python tools/workspace_backup.py backup ../freqtrade/user_data ../freqpilot-private-backup-YYYYMMDD
python tools/workspace_backup.py verify ../freqpilot-private-backup-YYYYMMDD
python tools/workspace_backup.py restore ../freqpilot-private-backup-YYYYMMDD ../freqpilot-restored-YYYYMMDD
```

Script dùng API backup SQLite để chứa giao dịch đã commit trong WAL, hash từng tệp, và chỉ khôi phục vào thư mục chưa tồn tại. Bản backup **có thể chứa mật khẩu API nội bộ**, vì vậy giữ riêng, không đẩy Git hoặc chia sẻ như gói kết quả backtest. Sau restore, kiểm tra `config.json` vẫn `dry_run=true`, SQLite integrity, thư viện chiến lược và số gói ZIP trước khi thay bất kỳ đường mount nào. Không trỏ Compose vào bản khôi phục chỉ để thử.

## Bằng chứng trên máy này, 23/10/2026

- Báo cáo read-only: `user_data` khoảng 78 MB; 53 nhóm tệp trùng hash nhỏ. Đây là cơ hội xem xét dung lượng, chưa phải các tệp an toàn để xóa.
- Đã tạo backup riêng 633 tệp và restore sang thư mục mới. Tất cả 633 tệp khớp hash; SQLite `integrity_check=ok`; bản khôi phục có 11 chiến lược `.py`, 24 gói backtest ZIP và 99 bản ghi JSON nghiên cứu.
- Chưa thử khôi phục trên máy thứ hai và chưa chuyển worker paper sang bản khôi phục.
- Thử native runner ma trận trên bản snapshot chỉ đọc và scratch riêng: hai ô BTC/ETH 1h, 22/09–01/10/2026 đều xuất ZIP/hash riêng, không có lệnh trong khoảng chọn. Lần đầu preflight Binance bắt chênh timestamp funding 4 ms và chặn; sau khi sửa verifier, đã kiểm tra lại riêng trên dữ liệu chính. Bài thử runner không động đến dữ liệu hoặc worker paper chính.
- Verifier cuối ghép funding một-một với dung sai tối đa 10 ms và vẫn kiểm tra rate/trùng/thiếu. Đối chiếu read-only trên dữ liệu chính 12–21/10: BTC 27/27 và ETH 27/27 sự kiện; API chất lượng dữ liệu báo `ok`, 0 vấn đề trên 8 tệp trong khoảng 1h + chi tiết 1m. Xem trước ma trận một ô BTC 1h báo `ready=true`, funding `ok`; **chưa khởi chạy ma trận trên dữ liệu chính**.
- Image backend mới đã qua 130/130 test trong container không mạng. UI qua typecheck, build và 1.737/1.737 test. Bản cài Compose riêng chạy ở cổng 18091 với 8 chiến lược mẫu, các trang chính trả HTTP 200, không có dữ liệu/job và `dry_run=true`, `initial_state=stopped`; đã dừng và tháo bản thử riêng.
- Dịch vụ nghiên cứu 8091 đã chuyển sang image mới. Hai container paper 8090/8095 giữ nguyên ID và trạng thái running. Image cũ được giữ dưới tag `freqpilot-backend-rollback:20261023`; UI của commit nền `21e73a1` được build tại `work/release-check-20261023/previous/ui/dist` để có đường quay về. Bản này chưa thử trên máy thứ hai.

Để quay về bản trước khi nâng cấp, giữ image/UI trước đó và mount `user_data` gốc. Chỉ thay container nghiên cứu khi kiểm thử image mới đạt; không cần restart bot paper để xem tính năng mới.

## Bổ sung lưu trữ hồ sơ paper, 27/10/2026

- Kiểm thử đầy đủ đạt 1.738 kiểm tra UI và 132 kiểm tra backend; sau chỉnh sửa câu giải thích trên UI, 10 kiểm tra PaperWorkspace và bản dựng UI chạy lại đạt. Backend được kiểm thử trong container riêng không có mạng.
- Dịch vụ nghiên cứu 8091 dùng image `freqpilot-paper-archive:20261026`; API trả trạng thái lưu trữ cho hồ sơ hiện có. Bản UI mới được phục vụ thành công. Hai container paper không bị tạo lại khi cập nhật; quan sát worker nghiên cứu ở trạng thái stopped, dry-run, không vị thế mở. Paper chính báo Freqtrade 2026.9, futures isolated, dry-run.
- Chrome dùng để kiểm tra chưa đăng ký bot nghiên cứu; chưa có ảnh kiểm chứng trang sau đăng nhập. Giao diện đã được kiểm tra bằng component test và HTTP asset, không thực hiện thao tác lưu trữ trên hồ sơ thật.
- Bản UI và cấu hình môi trường trước cập nhật nằm tại `work/release-paper-archive-20261027`; image trước đó được giữ dưới tag `freqpilot-backend-before-paper-archive:20261027`. Tệp môi trường trong bản lưu là riêng tư. Việc thử lưu trữ/hiện lại thực hiện bằng dữ liệu giả trong test; không thay đổi hồ sơ paper thật để nghiệm thu.

## Cải tiến giao diện và luồng sử dụng, 27/10/2026

- Khắc phục lỗi căn giữa văn bản từ `.legacy-host` trên toàn bộ `FreqPilotStudio` và các panel nghiên cứu; đồng bộ chữ số `tabular-nums`, bảng dữ liệu và nhãn X-axis của `EquityCurveChart`.
- Tách cảnh báo kết nối/health của bot giao dịch trên `AppShell` khỏi hai trang nghiên cứu (`studio`, `paper`) để không hiển thị báo động giả `bots offline` khi đang nghiên cứu.
- Tại **Thư viện chiến lược**: ưu tiên hiển thị chiến lược đã có gói backtest hoàn tất lên đầu, biến các thẻ thống kê (`Tổng cộng`, `Yêu thích`, `Có gói backtest`, `Mã khớp / đã đổi`) thành nút lọc 1 chạm và thêm nút chọn nhanh các chiến lược có gói để so sánh.
- Tại **Workspace chiến lược**: bổ sung thanh ngữ cảnh 4 ô (**Mã nguồn**, **Cấu hình & Tham số**, **Gói Backtest gần nhất**, **Kiểm định & Paper**), thanh 11 bước hiển thị trọn trên một hàng, nút thu gọn/mở rộng danh sách chiến lược bên trái có kèm huy hiệu P&L, các nút chọn nhanh khoảng ngày (`Toàn bộ dữ liệu`, `30 ngày`, `14 ngày`, `7 ngày`) từ phạm vi feather thực tế và nút gợi ý ngày tách IS/OOS 70/30 trong Tối ưu.
- Tại **05 · Kết quả**: đưa KPI chính, `BacktestSummaryCards`, bộ chuyển chế độ và biểu đồ đường vốn lên đầu trang ngay dưới danh sách lịch sử; phần kiểm tra gói lưu, `ReplayBacktest` và `RunNotesPanel` xếp thành lưới 2 cột bên dưới.
- Kiểm chứng thực tế: `pnpm --dir ui typecheck`, `pnpm --dir ui exec vitest run` (118/118 tệp, 1.738/1.738 kiểm tra đạt), `pnpm --dir ui build` và kiểm tra trực tiếp trên trình duyệt đã xác thực tại `http://localhost:8091/studio`.

## Nâng cấp chuyên sâu UX, Ultimate Analytics, Xuất Dossier & Nhập gói đóng băng, 28/10/2026

- **Dẫn đường & Biên tập mã (`FreqPilotStudio.vue`)**: bổ sung thanh `.next-step-banner` theo trạng thái thực tế của chiến lược; nút `Bỏ nháp, khôi phục mã đã lưu`; phím tắt `Ctrl+B` thu gọn/mở rộng danh sách chiến lược và thanh kéo `.sidebar-resize-handle` (`220px`–`440px`); khung `CodeEditor` mở song song ngay trong `04 · Backtest` (`.run-split-layout`); `buildEvidenceCodexPrompt` đính kèm ID gói chạy, khoảng thời gian, P&L và trạng thái khớp `revision` khi sao chép yêu cầu sang Codex; `router.onError` tự nạp lại đường dẫn đích nếu trình duyệt giữ tên chunk cũ sau khi build.
- **Biểu đồ phân tích hậu kiểm & Trình bày WFA / Độ nhạy (`strategyLibrary.ts`, `WalkForwardWorkspace.vue`, `SensitivityWorkspace.vue`)**:
  - `buildTradeAnalytics`: tính đường sụt giảm vốn thực nhận (`UnderwaterChart`), lợi nhuận theo tháng (`MonthlyReturnsHeatmap`), phân bố lý do thoát lệnh (`ExitReasonChart`) và hiệu suất theo giờ/thứ UTC (`HourlyPatternChart`, `WeekdayPatternChart`) trực tiếp từ `result.trades` của Freqtrade 2026.9. Bảo toàn phân biệt `null` (ngoài mẫu hoặc thiếu `profit_ratio`) với `0` thực tế.
  - `mapWalkForwardWindowRow` & `WalkForwardWorkspace`: hiển thị `.wfa-timeline`, cột `Train tốt nhất` từ `hyperopt.best_epoch.metrics` khi `status === 'success'`, giữ `wfe: null` / `degradation: null`, và hiển thị thẻ đối chiếu song song `.holdout-grid` (Baseline vs Ứng viên).
  - `buildSensitivityPivot` & `SensitivityWorkspace`: dựng bảng ma trận 2D `.sensitivity-pivot` đánh dấu ô tham số gốc (`Mặc định`), giữ `'—'` cho ô `pending`/`failed`, không tự gán nhãn an toàn từ hệ số biến thiên.
- **Xuất Dossier (`.md`) & Nhập gói hồ sơ đóng băng (`POST /studio/runs/import`)**:
  - `buildResearchDossierMarkdown`: xuất tài liệu Markdown gồm nguồn gốc (`revision`, `preset`, `artifact_sha256`), giao thức đóng băng, bảng kết quả & `exit_reason`, trạng thái Lookahead/Recursive, hướng dẫn 3 bước kiểm chứng và tuyên bố rõ giới hạn không đóng băng metadata thị trường trực tuyến của Binance ở gói cũ.
  - `POST /studio/runs/import` (`backend/api_runs.py`): kiểm tra SHA256 tổng của gói ZIP (tối đa 64 MB nén / 256 MB giải nén), chặn path traversal / symlink / tệp lạ, đối chiếu SHA256 từng tệp đầu vào và mã nhúng trong ZIP kết quả native, xác thực `validate_saved_config` rồi nạp vào `user_data/freqpilot/runs/<id>` và `user_data/backtest_results/` mà không ghi đè tệp `.py` trong thư viện.
- **Bằng chứng kiểm chứng**: `pnpm --dir ui typecheck` (0 lỗi), `pnpm --dir ui exec vitest run` (118/118 tệp, 1.743/1.743 kiểm tra đạt), `docker run ... unittest discover` (133/133 kiểm tra backend đạt), và kiểm chứng trực tiếp trên trình duyệt tại `http://localhost:8091/studio` & `http://localhost:8090/studio`.
