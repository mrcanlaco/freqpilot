# FreqPilot

Tên làm việc cho workspace nghiên cứu Binance Futures của riêng bạn: ý tưởng → mã → backtest → phân tích → paper. Phiên bản đầu 0.1.0 ưu tiên tái sử dụng FreqUI Ultimate v2.1.0 và API chính thức Freqtrade 2026.9. Đây là tên tạm, chưa xác minh khả năng sử dụng thương hiệu hay tên GitHub công khai.

## Mở bộ cài hiện tại

- FreqPilot: http://localhost:8090/studio
- Backtest workspace: http://localhost:8091/studio
- Ultimate độc lập để tham khảo: http://localhost:8092/tools/strategy-dev
- Paper Ultimate độc lập: http://localhost:8093
- Worker paper nghiên cứu riêng: http://localhost:8095 (giám sát từ workspace chính)

Các chiến lược, dữ liệu, cấu hình và database của bộ chính vẫn ở thư mục `../freqtrade/user_data`. Repo này không chứa tài khoản Binance hoặc thông tin đăng nhập. Dùng tài khoản local hiện tại để đăng nhập trên UI nếu được hỏi. Trạng thái vận hành: **chỉ backtest và paper**, không có khóa giao dịch Binance, giữ isolated và 1x cho bộ mẫu so sánh.

## Đã có

- Thư viện chiến lược cùng mô tả, ý tưởng và ghi chú lưu trên máy.
- Thư viện dạng thẻ/danh sách tham khảo Strategies của RoboQuant: tìm tên/mô tả/nhãn, yêu thích, lọc khung và hồ sơ, sắp xếp theo cập nhật hoặc lần chạy. Chỉ số từ gói backtest hoàn tất gần nhất, ghi rõ mã khớp/đã đổi và mẫu ít lệnh. Chọn các chiến lược để so sánh bằng bảng native có sẵn; không cố định vào tám mẫu benchmark.
- Tạo mới hoặc sao chép mẫu có sẵn; editor Monaco tái sử dụng từ Ultimate.
- Lưu mã có kiểm tra cú pháp, chống ghi đè phiên bản cũ, bản sao dự phòng và xem/khôi phục mã cũ.
- So sánh bản sao cũ với mã trong editor bằng DiffViewer có sẵn của Ultimate, không thay hoặc lưu mã khi chỉ xem khác biệt.
- Backtest ngay trong workspace bằng API/engine chính thức: ngày, khung tín hiệu, chi tiết 1m, vốn, số tiền mỗi lệnh và số lệnh tối đa.
- Kiểm định lookahead/recursive bằng API gốc, tiến trình và lịch sử kết quả gắn với hash mã; kết quả hoàn tất được lưu ngay cả khi đóng trình duyệt.
- Kiểm tra dữ liệu local và chặn hồ sơ chạy nếu thiếu nến/mark/funding hoặc ngày bắt đầu nằm trước phạm vi dữ liệu.
- Mỗi lần chạy mới sao chép mã Python local, parameter của chiến lược và dữ liệu feather (nến/mark/funding) vào thư mục riêng; engine chính thức chạy trực tiếp từ bản sao. Lưu ZIP gốc và gói đầu vào/kết quả có SHA-256 để kiểm tra toàn vẹn, xem mã đã chạy và tải về. Báo cáo cũ được ghi rõ là chưa có gói đầy đủ. Gói không đóng băng metadata thị trường lấy qua mạng hoặc môi trường bên ngoài image engine.
- Lịch sử, KPI, đường vốn theo lệnh đóng, bảng chỉ số/giao dịch, biểu đồ lệnh và so sánh nhiều chiến lược. Tái sử dụng chart/report từ Ultimate và FreqUI.
- Soạn yêu cầu cho Codex từ ý tưởng/ghi chú. Chưa có chatbot AI tích hợp riêng.
- Paper trên UI: chuẩn bị hồ sơ từ đúng gói backtest, giữ mã và tham số, tạo database riêng, xem cấu hình trước khi bật. Worker nghiên cứu 8095 dùng CLI --dry-run và lớp chiến lược giới hạn 1x; tái sử dụng API start/pause/reload_config của Freqtrade. Bot paper chính 8090 độc lập.

## Cách dùng

1. Mở thư viện, tìm/lọc và chọn chiến lược hoặc **Tạo chiến lược**. Có thể đổi dạng thẻ/danh sách, chọn nhiều chiến lược để so sánh. Có 7 mẫu futures từ repo freqtrade-strategies chính thức bên cạnh các chiến lược hiện có; nguồn và các sửa đổi tương thích nằm ở `templates/PROVENANCE.json`.
2. Viết ý tưởng, gắn nhãn phân cách bằng dấu phẩy, đánh dấu yêu thích và lưu nghiên cứu; sao chép yêu cầu sang Codex nếu cần phát triển quy tắc. Đánh dấu sao tại thư viện không xóa ý tưởng/ghi chú/nhãn đã lưu.
3. Mở tab Mã, sửa rồi lưu. StarterFutures đang chạy paper được bảo vệ; sửa trên bản sao.
4. Chạy backtest. Phí của bộ hiện tại là 0.05% mỗi chiều, dữ liệu chi tiết 1m. Đây là mô phỏng nến, không phải tick/L2.
5. Đọc kết quả, biểu đồ và cảnh báo mẫu nhỏ. **So sánh kết quả thư viện** ưu tiên các kết quả có gói lưu mới nhất của 8 chiến lược thử, dùng bảng so sánh có sẵn.
6. Kiểm tra lookahead/recursive trước khi đánh giá khả năng sử dụng. Lưu mã/backtest không tự đổi chiến lược paper đang chạy.
7. Mở **06 · Paper**, chọn **Chuẩn bị hồ sơ paper**, đọc lại mã nguồn, vốn/stake, phí và cảnh báo mẫu nhỏ. Bước chuẩn bị chưa bật bot.
8. Chọn **Bật paper hồ sơ này**. Worker 8095 nạp cấu hình từ hồ sơ và dùng database riêng; mỗi lần đổi hồ sơ cần không còn vị thế đang mở. Lớp thực thi kế thừa tín hiệu gốc, giới hạn leverage 1x và đổi tên metadata của tệp tham số để Freqtrade nạp đúng bộ số cũ.
9. **Tạm ngừng vào lệnh** tiếp tục quản lý thoát lệnh và dừng tăng vị thế theo PAUSED của 2026.9. Các điều chỉnh giảm vị thế / chốt lời từng phần vẫn hoạt động; đã kiểm tra trực tiếp phương thức gốc với State.PAUSED. **Bật / tiếp tục** dùng lại database cũ. **Dừng khi đã hết vị thế** từ chối nếu còn vị thế; không ép đóng lệnh. Khi dịch vụ khởi động lại, worker không tự vào lệnh mới; còn vị thế thì khôi phục PAUSED để quản lý thoát lệnh, không còn thì STOPPED.
10. **Mở giám sát paper** đăng ký kết nối token trong UI hiện tại, dùng lại màn hình Bot/Chart/History/Logs, không cần nhập lại mật khẩu. Luồng local này dùng nguồn Direct; Gateway chưa được nối với worker. Một worker nghiên cứu dùng một hồ sơ tại một thời điểm, có thể giữ nhiều hồ sơ đã chuẩn bị.

## Phát triển lại

Yêu cầu Node.js 24, pnpm 10.33.2 và Docker Desktop. Cài UI theo lockfile, build UI trong thư mục `ui/`; backend dùng Dockerfile ở `backend/` trên image chính thức đã ghim. `Start.ps1` dùng `.env` để trỏ tới dữ liệu ngoài repo. `.env.example` không có bí mật. Tài khoản, dữ liệu, ZIP kết quả và database không được đưa vào Git.

Kiểm tra: `pnpm --dir ui typecheck`, `pnpm --dir ui exec vitest run tests/unit/datasource/directSource.spec.ts`, `pnpm --dir ui build`; backend chạy unittest `test_*.py` trong image. Các kiểm tra hiện tại gồm 39 kiểm tra data source, 3 kiểm tra diễn giải profit factor, 4 kiểm tra thư viện và 27 kiểm tra backend. Build, typecheck, thao tác UI tạo/sửa/lưu nghiên cứu, backtest từ snapshot, kiểm tra hash, mở mã gốc, tải gói và kiểm định lookahead/recursive đã được kiểm tra. Thư viện đã thử lưu/tải lại yêu thích và nhãn, lọc tìm kiếm, chế độ danh sách, so sánh hai chiến lược và xem khác biệt phiên bản không thay mã. Paper đã kiểm tra chuẩn bị, bật, tạm ngừng, tiếp tục, giám sát và dừng khi không còn vị thế bằng engine thực; tệp tham số được kiểm tra bằng StrategyResolver gốc. Lỗi chuyển stake dạng chuỗi đã có kiểm tra hồi quy và schema native chặn trước khi nạp worker.

`tools/run_benchmark.py` ghi rõ protocol, dùng timeframe gốc và mặc định chạy riêng từng chiến lược, tránh dùng chung warmup; `tools/compare_benchmark.py` đọc ZIP kết quả thực và đối chiếu từng lệnh. Không tối ưu tham số tự động.

## Phạm vi và nguồn

Xem `PRODUCT.md` cho định hướng so với RoboQuant/Ultimate, `benchmarks/REPORT.md` cho kết quả 8 chiến lược và các giới hạn kiểm định. Bản Ultimate độc lập là công cụ so sánh, không phải engine vận hành chính. Chưa tạo repo GitHub hay xuất bản công khai.

FreqPilot là tác phẩm phái sinh GPL-3.0 của FreqUI Ultimate / FreqUI. Giữ LICENSE và các ghi nhận nguồn ở `SOURCES.md`; mã engine Freqtrade không bị thay bằng fork Ultimate.
