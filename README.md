# FreqPilot

Tên làm việc cho workspace nghiên cứu Binance Futures của riêng bạn: ý tưởng → mã → backtest → phân tích → paper. Phiên bản đầu 0.1.0 ưu tiên tái sử dụng FreqUI Ultimate v2.1.0 và API chính thức Freqtrade 2026.9. Đây là tên tạm, chưa xác minh khả năng sử dụng thương hiệu hay tên GitHub công khai.

## Mở bộ cài hiện tại

- FreqPilot: http://localhost:8090/studio
- Backtest workspace: http://localhost:8091/studio
- Ultimate độc lập để tham khảo: http://localhost:8092/tools/strategy-dev
- Paper Ultimate độc lập: http://localhost:8093

Các chiến lược, dữ liệu, cấu hình và database của bộ chính vẫn ở thư mục `../freqtrade/user_data`. Repo này không chứa tài khoản Binance hoặc thông tin đăng nhập. Dùng tài khoản local hiện tại để đăng nhập trên UI nếu được hỏi. Trạng thái vận hành: **chỉ backtest và paper**, không có khóa giao dịch Binance, giữ isolated và 1x cho bộ mẫu so sánh.

## Đã có

- Thư viện chiến lược cùng mô tả, ý tưởng và ghi chú lưu trên máy.
- Tạo mới hoặc sao chép mẫu có sẵn; editor Monaco tái sử dụng từ Ultimate.
- Lưu mã có kiểm tra cú pháp, chống ghi đè phiên bản cũ, bản sao dự phòng và xem/khôi phục mã cũ.
- Backtest ngay trong workspace bằng API/engine chính thức: ngày, khung tín hiệu, chi tiết 1m, vốn, số tiền mỗi lệnh và số lệnh tối đa.
- Kiểm định lookahead/recursive bằng API gốc, tiến trình và lịch sử kết quả gắn với hash mã; kết quả hoàn tất được lưu ngay cả khi đóng trình duyệt.
- Kiểm tra dữ liệu local và chặn hồ sơ chạy nếu thiếu nến/mark/funding hoặc ngày bắt đầu nằm trước phạm vi dữ liệu.
- Mỗi lần chạy mới sao chép mã Python local, parameter của chiến lược và dữ liệu feather (nến/mark/funding) vào thư mục riêng; engine chính thức chạy trực tiếp từ bản sao. Lưu ZIP gốc và gói đầu vào/kết quả có SHA-256 để kiểm tra toàn vẹn, xem mã đã chạy và tải về. Báo cáo cũ được ghi rõ là chưa có gói đầy đủ. Gói không đóng băng metadata thị trường lấy qua mạng hoặc môi trường bên ngoài image engine.
- Lịch sử, KPI, đường vốn theo lệnh đóng, bảng chỉ số/giao dịch, biểu đồ lệnh và so sánh nhiều chiến lược. Tái sử dụng chart/report từ Ultimate và FreqUI.
- Soạn yêu cầu cho Codex từ ý tưởng/ghi chú. Chưa có chatbot AI tích hợp riêng.
- Theo dõi bot paper hiện tại. Chưa có nút tự triển khai paper cho chiến lược mới; cần cấu hình riêng cùng Codex.

## Cách dùng

1. Chọn chiến lược hoặc **Tạo chiến lược**. Có 7 mẫu futures từ repo freqtrade-strategies chính thức bên cạnh các chiến lược hiện có; nguồn và các sửa đổi tương thích nằm ở `templates/PROVENANCE.json`.
2. Viết ý tưởng, lưu nghiên cứu; sao chép yêu cầu sang Codex nếu cần phát triển quy tắc.
3. Mở tab Mã, sửa rồi lưu. StarterFutures đang chạy paper được bảo vệ; sửa trên bản sao.
4. Chạy backtest. Phí của bộ hiện tại là 0.05% mỗi chiều, dữ liệu chi tiết 1m. Đây là mô phỏng nến, không phải tick/L2.
5. Đọc kết quả, biểu đồ và cảnh báo mẫu nhỏ. **So sánh kết quả thư viện** ưu tiên các kết quả có gói lưu mới nhất của 8 chiến lược thử, dùng bảng so sánh có sẵn.
6. Kiểm tra lookahead/recursive và quan sát paper trước khi đánh giá khả năng sử dụng. Lưu mã/backtest không tự đổi chiến lược paper đang chạy.

## Phát triển lại

Yêu cầu Node.js 24, pnpm 10.33.2 và Docker Desktop. Cài UI theo lockfile, build UI trong thư mục `ui/`; backend dùng Dockerfile ở `backend/` trên image chính thức đã ghim. `Start.ps1` dùng `.env` để trỏ tới dữ liệu ngoài repo. `.env.example` không có bí mật. Tài khoản, dữ liệu, ZIP kết quả và database không được đưa vào Git.

Kiểm tra: `pnpm --dir ui typecheck`, `pnpm --dir ui exec vitest run tests/unit/datasource/directSource.spec.ts`, `pnpm --dir ui build`; backend chạy unittest `test_*.py` trong image. Các kiểm tra hiện tại gồm 37 kiểm tra data source, 3 kiểm tra diễn giải profit factor và 13 kiểm tra backend. Build, typecheck, thao tác UI tạo/sửa/lưu nghiên cứu, backtest từ snapshot, kiểm tra hash, mở mã gốc, tải gói và kiểm định lookahead/recursive đã được kiểm tra.

`tools/run_benchmark.py` ghi rõ protocol, dùng timeframe gốc và mặc định chạy riêng từng chiến lược, tránh dùng chung warmup; `tools/compare_benchmark.py` đọc ZIP kết quả thực và đối chiếu từng lệnh. Không tối ưu tham số tự động.

## Phạm vi và nguồn

Xem `PRODUCT.md` cho định hướng so với RoboQuant/Ultimate, `benchmarks/REPORT.md` cho kết quả 8 chiến lược và các giới hạn kiểm định. Bản Ultimate độc lập là công cụ so sánh, không phải engine vận hành chính. Chưa tạo repo GitHub hay xuất bản công khai.

FreqPilot là tác phẩm phái sinh GPL-3.0 của FreqUI Ultimate / FreqUI. Giữ LICENSE và các ghi nhận nguồn ở `SOURCES.md`; mã engine Freqtrade không bị thay bằng fork Ultimate.

