# FreqPilot: sử dụng và khôi phục

Phạm vi: Freqtrade chính thức 2026.9, BTC/ETH Binance USDT-M Futures isolated 1x, chỉ backtest và paper. Các trang mới dùng cùng API nghiên cứu đã xác thực; worker paper hiện tại vẫn là dịch vụ riêng.

## Test một chiến lược

1. Vào **Chiến lược**, chọn hoặc sao chép chiến lược. Ghi rõ ý tưởng, lưu mã và đọc phiên bản đang mở.
2. Vào **Dữ liệu**, chọn ngày bắt đầu/kết thúc trong biểu mẫu Backtest. Kiểm tra nến, mark, funding và warmup. Chỉ nhấn **Đối chiếu funding với Binance** khi cần truy vấn công khai; mất mạng được ghi “chưa xác minh”. Nếu thiếu, xem kế hoạch rồi chủ động nhấn tải bù. Bản tải bù được kiểm tra trong vùng riêng trước khi đưa vào kho nghiên cứu.
3. Vào **Backtest** và chạy. Hồ sơ có phiên bản mã, cấu hình, hash dữ liệu và ZIP kết quả native. Kết quả cũ vẫn xem được; mã vừa sửa không biến thành mã đã chạy.
4. Đọc số lệnh, P&L, drawdown, phí/funding, phạm vi và kiểm định. Ít lệnh hoặc funding chưa xác minh không được gọi là chiến lược đạt.
5. Nếu muốn tối ưu, xem trước ngân sách và chạy Hyperopt native. Tab Tối ưu còn có thí nghiệm nhiều seed trên cùng tập train, mỗi seed chạy tuần tự. **Walk-forward** là chuỗi train/OOS rolling; mỗi OOS khởi đầu không vị thế. Holdout tách riêng và chỉ mở bằng nút riêng. **Độ nhạy** chạy backtest native từng bộ tham số và kịch bản phí, ô chưa chạy để trống. **Ma trận** thử BTC/ETH × khung nến thành các ô độc lập, chỉ bắt đầu khi từng ô có dữ liệu và funding được xác minh. Mỗi ô có vốn riêng, không cộng kết quả thành danh mục. `status=success` chỉ nghĩa tác vụ kết thúc; đọc `research_status` và từng cửa sổ/ô để biết kết quả đủ hay thiếu.
6. Chỉ sau khi chọn một gói backtest đã lưu mới chuẩn bị hồ sơ **Paper**. Quan sát paper là phiên bắt đầu từ lúc bấm, không hồi tố. Đóng phiên, chạy backtest cùng hồ sơ nếu nguồn còn khớp và dữ liệu đủ, rồi so sánh. Khi chưa có lệnh hoặc bằng chứng thiếu, báo cáo là “chưa đủ bằng chứng”.

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
