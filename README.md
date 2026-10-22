# FreqPilot

Tên làm việc cho workspace nghiên cứu Binance Futures của riêng bạn: ý tưởng → mã → backtest → phân tích → paper. Phiên bản đầu 0.1.0 ưu tiên tái sử dụng FreqUI Ultimate v2.1.0 và API chính thức Freqtrade 2026.9. Đây là tên tạm, chưa xác minh khả năng sử dụng thương hiệu hay tên GitHub công khai.

Đã đối chiếu các yêu cầu bàn giao với source, ZIP kết quả và bộ đang chạy; xem [bảng kiểm bằng chứng](benchmarks/delivery-audit.json) và [trạng thái khi bàn giao](benchmarks/delivery-audit-runtime.json). Kiểm tra mới nhất xác nhận 118 tệp lõi engine của hai dịch vụ nghiên cứu khớp bản chính thức. Những mục “Còn phát triển tiếp” trong PRODUCT là các hướng mở rộng; chưa có tuyên bố tương đương toàn bộ RoboQuant hoặc đã phát hành trên GitHub.

## Mở bộ cài hiện tại

- FreqPilot: http://localhost:8090/studio
- Paper nghiên cứu: http://localhost:8090/paper
- Backtest workspace: http://localhost:8091/studio
- Ultimate độc lập để tham khảo: http://localhost:8092/tools/strategy-dev
- Paper Ultimate độc lập: http://localhost:8093
- Worker paper nghiên cứu riêng: http://localhost:8095 (giám sát từ workspace chính)

Các chiến lược, dữ liệu, cấu hình và database của bộ chính vẫn ở thư mục `../freqtrade/user_data`. Repo này không chứa tài khoản Binance hoặc thông tin đăng nhập. Dùng tài khoản local hiện tại để đăng nhập trên UI nếu được hỏi. Trạng thái vận hành: **chỉ backtest và paper**, không có khóa giao dịch Binance, giữ isolated và 1x cho bộ mẫu so sánh.

## Đã có

- Khi mở workspace, tự tìm dịch vụ nghiên cứu tương thích trong các kết nối đã đăng ký. Lỗi tạm thời được thử tối đa ba lần; có nút **Thử kết nối lại** và hướng dẫn xác thực khi cần. Không tự gửi lại lệnh backtest/paper hoặc tải lại editor đã mở thành công.
- Thư viện chiến lược cùng mô tả, ý tưởng và ghi chú lưu trên máy.
- Thư viện dạng thẻ/danh sách tham khảo Strategies của RoboQuant: tìm tên/mô tả/nhãn, yêu thích, lọc khung và hồ sơ, sắp xếp theo cập nhật hoặc lần chạy. Chỉ số từ gói backtest hoàn tất gần nhất, ghi rõ mã khớp/đã đổi và mẫu ít lệnh. Chọn các chiến lược để so sánh bằng bảng native có sẵn; không cố định vào tám mẫu benchmark.
- Tạo mới hoặc sao chép mẫu có sẵn; editor Monaco tái sử dụng từ Ultimate.
- Lưu mã có kiểm tra cú pháp, chống ghi đè phiên bản cũ, bản sao dự phòng và xem/khôi phục mã cũ.
- So sánh bản sao cũ với mã trong editor bằng DiffViewer có sẵn của Ultimate, không thay hoặc lưu mã khi chỉ xem khác biệt.
- Bộ tham số có tên: đọc bằng API strategy gốc, kiểm tra kiểu/giới hạn/lựa chọn, lưu riêng và tải JSON native. Khi chạy, JSON chỉ được chép vào bản sao backtest/kiểm định; kết quả và hồ sơ paper ghi rõ bộ đã dùng. Không ghi đè tệp tham số cạnh mã gốc và không tự tối ưu.
- Backtest ngay trong workspace bằng API/engine chính thức: ngày, khung tín hiệu, chi tiết 1m, vốn, số tiền mỗi lệnh và số lệnh tối đa.
- Kiểm định lookahead/recursive bằng API gốc, tiến trình và lịch sử kết quả gắn với hash mã; kết quả hoàn tất được lưu ngay cả khi đóng trình duyệt.
- Diễn giải kiểm định tách khỏi trạng thái job: nêu số tín hiệu và giới hạn mẫu, bảng biến thiên indicator theo warmup, phân biệt ô thiếu/không tính được với 0. Đối chiếu mã chính, tham số, khung và khoảng ngày để tránh dùng nhầm kiểm định cũ.
- Kiểm tra dữ liệu local và chặn hồ sơ chạy nếu thiếu nến/mark/funding hoặc ngày bắt đầu nằm trước phạm vi dữ liệu.
- Mỗi lần chạy mới sao chép mã Python local, parameter của chiến lược và dữ liệu feather (nến/mark/funding) vào thư mục riêng; engine chính thức chạy trực tiếp từ bản sao. Lưu ZIP gốc và gói đầu vào/kết quả có SHA-256 để kiểm tra toàn vẹn, xem mã đã chạy và tải về. Báo cáo cũ được ghi rõ là chưa có gói đầy đủ. Gói không đóng băng metadata thị trường lấy qua mạng hoặc môi trường bên ngoài image engine.
- Lịch sử, KPI, đường vốn theo lệnh đóng, bảng chỉ số/giao dịch, biểu đồ lệnh và so sánh nhiều chiến lược. Tái sử dụng chart/report từ Ultimate và FreqUI.
- Chạy lại từ gói đã lưu: xem lại cấu hình gốc rồi tạo backtest mới bằng mã, JSON tham số và feather trong ZIP, bỏ qua thư viện/biểu mẫu hiện tại. Tự đối chiếu chính xác toàn bộ trường của từng lệnh, lệnh con, phí/funding và chín chỉ số/ngữ cảnh native; báo khớp, khác hoặc chưa đủ dữ liệu đối chiếu. Không sửa kết quả gốc hoặc database paper. Metadata Binance lấy qua mạng chưa được đóng băng.
- Soạn yêu cầu cho Codex từ ý tưởng/ghi chú. Chưa có chatbot AI tích hợp riêng.
- Paper trên UI: chuẩn bị hồ sơ từ đúng gói backtest, giữ mã và tham số, tạo database riêng, xem cấu hình trước khi bật. Worker nghiên cứu 8095 dùng CLI --dry-run và lớp chiến lược giới hạn 1x; tái sử dụng API start/pause/reload_config của Freqtrade. Bot paper chính 8090 độc lập.
- Mục Paper mở trang quản lý các hồ sơ nghiên cứu đã chuẩn bị. Giám sát Direct phân biệt kết nối API với trạng thái engine chạy/tạm ngừng/dừng/đang nạp cấu hình, có hạn cập nhật riêng cho trạng thái. Worker 8095 quay về trang Paper để bật/tiếp tục/dừng qua hồ sơ đã kiểm tra; các nút lifecycle native chung không gửi thẳng tới worker. Kết quả thao tác chưa được coi là trạng thái mới cho đến khi đọc lại cấu hình native.
- Lịch sử thao tác và trạng thái paper lưu bền vững trong `freqpilot/paper/history.sqlite`, tách database giao dịch. Có lọc hồ sơ và đọc các trang cũ bằng cursor; yêu cầu, kết quả phản hồi và lần quan sát native là các sự kiện riêng. Lỗi kết nối không bị ghi thành bot dừng; lỗi lưu lịch sử không ngăn tạm ngừng/dừng, nhưng chặn bật mới nếu chưa ghi được yêu cầu. Không dựng lịch sử trước khi có tính năng hoặc tự gán lợi nhuận cho một phiên.
- Nhãn tiền trên các màn hình theo dõi lấy từ bot/cặp lịch sử: Binance USDT-M hiển thị USDT. Nguồn Direct không cộng tiền khác đơn vị. Vốn được bot quản lý có giải thích tỷ lệ phân bổ và dự phòng. Thoát một phần bằng tay trên Binance hiện chưa mở khi chưa đọc được giới hạn sàn; thoát toàn bộ và các quy tắc thoát tự động của engine giữ nguyên.

## Cách dùng

1. Mở thư viện, tìm/lọc và chọn chiến lược hoặc **Tạo chiến lược**. Có thể đổi dạng thẻ/danh sách, chọn nhiều chiến lược để so sánh. Có 7 mẫu futures từ repo freqtrade-strategies chính thức bên cạnh các chiến lược hiện có; nguồn và các sửa đổi tương thích nằm ở `templates/PROVENANCE.json`.
2. Viết ý tưởng, gắn nhãn phân cách bằng dấu phẩy, đánh dấu yêu thích và lưu nghiên cứu; sao chép yêu cầu sang Codex nếu cần phát triển quy tắc. Đánh dấu sao tại thư viện không xóa ý tưởng/ghi chú/nhãn đã lưu.
3. Mở tab Mã, sửa rồi lưu. StarterFutures đang chạy paper được bảo vệ; sửa trên bản sao.
4. Ở tab Backtest, có thể **Đọc / tải lại tham số**, đặt tên rồi **Lưu thành bộ mới và chọn**. Chỉ các khai báo Parameter của Freqtrade mới hiện thành ô nhập; `load=false` chỉ đọc. Giữ lựa chọn gốc nếu chưa cần bộ riêng. Vốn/ngày/phí vẫn thuộc cấu hình lần chạy, tách khỏi bộ tham số. Sau đó chạy backtest; phí hiện tại 0.05% mỗi chiều, dữ liệu chi tiết 1m. Đây là mô phỏng nến, không phải tick/L2.
5. Đọc kết quả, biểu đồ và cảnh báo mẫu nhỏ. **So sánh kết quả thư viện** ưu tiên các kết quả có gói lưu mới nhất, dùng bảng so sánh có sẵn. Trong báo cáo có gói, chọn **Chạy lại từ gói đã lưu**, xem ngày/vốn/phí/tham số gốc rồi **Chạy bản sao & đối chiếu**. Bước xem chưa chạy gì; bước chạy tạo hồ sơ mới và giữ nguyên biểu mẫu/mã đang mở. Kết quả khớp không chứng nhận khớp lệnh thực tế; cả hai báo cáo không có lệnh cũng chưa kiểm tra được hành vi khớp lệnh.
6. Kiểm tra lookahead/recursive trước khi đánh giá khả năng sử dụng. Tab Kiểm định dùng bộ tham số đang chọn và bản sao riêng của mã/JSON, giữ dấu vân tay lúc gửi. Công cụ native có thể ghi đè một số thiết lập mô phỏng theo mục đích chẩn đoán; không coi đây là backtest hiệu suất thay thế. Dữ liệu nến vẫn đọc từ datadir hiện tại. Lưu mã/backtest không tự đổi chiến lược paper đang chạy.
7. Mở **06 · Paper**, chọn **Chuẩn bị hồ sơ paper**, đọc lại mã nguồn, vốn/stake, phí và cảnh báo mẫu nhỏ. Bước chuẩn bị chưa bật bot.
8. Chọn **Bật paper hồ sơ này**. Worker 8095 nạp cấu hình từ hồ sơ và dùng database riêng; mỗi lần đổi hồ sơ cần không còn vị thế đang mở. Lớp thực thi kế thừa tín hiệu gốc, giới hạn leverage 1x và đổi tên metadata của tệp tham số để Freqtrade nạp đúng bộ số cũ.
9. **Tạm ngừng vào lệnh** tiếp tục quản lý thoát lệnh và dừng tăng vị thế theo PAUSED của 2026.9. Các điều chỉnh giảm vị thế / chốt lời từng phần vẫn hoạt động; đã kiểm tra trực tiếp phương thức gốc với State.PAUSED. **Bật / tiếp tục** dùng lại database cũ. **Dừng khi đã hết vị thế** từ chối nếu còn vị thế; không ép đóng lệnh. Khi dịch vụ khởi động lại, worker không tự vào lệnh mới; còn vị thế thì khôi phục PAUSED để quản lý thoát lệnh, không còn thì STOPPED.
10. **Mở giám sát paper** đăng ký kết nối token trong UI hiện tại, dùng lại màn hình Bot/Chart/History/Logs, không cần nhập lại mật khẩu. Luồng local này dùng nguồn Direct; Gateway chưa được nối với worker. Một worker nghiên cứu dùng một hồ sơ tại một thời điểm, có thể giữ nhiều hồ sơ đã chuẩn bị.
11. Từ thanh điều hướng, **Paper** mở tất cả hồ sơ nghiên cứu. Trong màn hình giám sát, **Research paper workspace** quay lại trang quản lý này; không trực tiếp gọi start/reload từ menu bot. Nếu worker đã dừng nhưng còn vị thế, có thể chủ động **Tiếp tục quản lý thoát lệnh** mà chưa bật vào lệnh mới. Khi mất kết nối hoặc đang nạp cấu hình, các nút tương ứng sẽ chờ trạng thái rõ ràng.
12. Chọn **Xem lịch sử paper** để xem yêu cầu và trạng thái đã ghi, lọc theo hồ sơ hoặc xem sự kiện cũ hơn. Khi đang đọc các trang cũ, giao diện giữ vị trí; chọn **Tải lại lịch sử** để trở về mới nhất. “Đã gửi yêu cầu” chưa chứng minh worker đã đổi trạng thái. Những thay đổi ngoài workspace trong khoảng không có lần đọc có thể không xuất hiện; không suy thời lượng chạy hay lợi nhuận phiên từ nhật ký này.

## Phát triển lại

Cài trên thư mục/máy mới: xem [hướng dẫn cài độc lập](docs/INSTALL.md). `Initialize.ps1` tạo dữ liệu và tài khoản local riêng, mặc định dừng; không chép dữ liệu cá nhân từ bộ đang dùng. `Start.ps1 -CheckOnly` kiểm tra trước khi mở dịch vụ, `Start.ps1 -Build` build/mở và `Stop.ps1` giữ lại database. Bộ hiện có tiếp tục dùng `.env` cũ, không chạy lại Initialize.

`Check.ps1 -InstallDependencies` kiểm tra UI/backend và bộ khởi tạo bằng dữ liệu thử riêng; không thay UI đang phục vụ hoặc bật bot. Root workflow `.github/workflows/check.yml` chuẩn bị cùng các bước cho GitHub; chưa có run GitHub hay repo công khai được tạo.

Yêu cầu Node.js 24, pnpm 10.33.2 và Docker Desktop. Cài UI theo lockfile, build UI trong thư mục `ui/`; backend dùng Dockerfile ở `backend/` trên image chính thức đã ghim. `Start.ps1` dùng `.env` để trỏ tới dữ liệu ngoài repo. `.env.example` không có bí mật. Tài khoản, dữ liệu, ZIP kết quả và database không được đưa vào Git.

Kiểm tra: `pnpm --dir ui typecheck`, `pnpm --dir ui exec vitest run tests/unit/datasource/directSource.spec.ts`, `pnpm --dir ui build`; backend chạy unittest `test_*.py` trong image. Bộ UI đầy đủ hiện đạt 1.722 kiểm tra trong 117 tệp (gồm 43 kiểm tra Direct data source, 5 kiểm tra diễn giải/ngữ cảnh kiểm định và 4 kiểm tra tiền tệ); backend đạt 58 kiểm tra từ lần xác minh trước, không đổi trong đợt sửa kết nối này. Luồng kết nối ban đầu có thêm 16 kiểm tra UI cho chọn dịch vụ tương thích, giới hạn thử lại, hủy khi rời trang và giữ editor đã sẵn sàng. Luồng chạy lại có 6 kiểm tra UI và 9 kiểm tra backend bổ sung; đã thử từ giao diện bằng gói FSupertrendStrategy thực và khớp toàn bộ 23 lệnh, gồm lệnh con/phí/funding. Bằng chứng ở `benchmarks/replay-control.json`. Đã sửa một số fixture/harness cũ để phù hợp thương hiệu, trang mở đầu, schema đơn vị tiền và thứ tự chờ show_config; không bỏ qua kiểm tra hoặc nâng timeout. Build, typecheck, thao tác UI tạo/sửa/lưu nghiên cứu, backtest từ snapshot, kiểm tra hash, mở mã gốc, tải gói và kiểm định lookahead/recursive đã được kiểm tra. Báo cáo kiểm định đã kiểm tra trên UI bằng dữ liệu FAdxSma thật: 2 tín hiệu lookahead, 3 ô recursive không tính được, tỷ lệ được đổi sang phần trăm và cảnh báo khi chọn bộ tham số khác. Trang Paper, trạng thái native và quy tắc nút điều khiển có 19 kiểm tra mới; các kiểm tra trạng thái/điều hướng, cache nến rỗng và PaperWorkspace đã chạy riêng trong quá trình sửa, rồi bộ đầy đủ được chạy lại. Bố cục Paper được kiểm tra thêm bằng 6 bài kiểm tra sau lần chạy đầy đủ cuối. Các kiểm tra lifecycle dùng HTTP giả lập, không gửi lệnh tới bot thật. Màn hình paper hiển thị vốn 950 USDT và P&L bằng USDT; trong lần kiểm tra giao diện đó, worker nghiên cứu ở STOPPED và không được bật lại chỉ để kiểm tra. Bộ tham số đã thử đọc/lưu/chọn/tải JSON trên UI, backtest gốc khớp từng lệnh, lookahead/recursive dùng cùng hash tham số; unit test xác nhận paper wrapper nạp đúng giá trị qua StrategyResolver. Thư viện đã thử lưu/tải lại yêu thích và nhãn, lọc tìm kiếm, chế độ danh sách, so sánh hai chiến lược và xem khác biệt phiên bản không thay mã. Paper đã kiểm tra chuẩn bị, bật, tạm ngừng, tiếp tục, giám sát và dừng khi không còn vị thế bằng engine thực; tệp tham số được kiểm tra bằng StrategyResolver gốc. Lỗi chuyển stake dạng chuỗi đã có kiểm tra hồi quy và schema native chặn trước khi nạp worker.

`tools/run_benchmark.py` ghi rõ protocol, dùng timeframe gốc và mặc định chạy riêng từng chiến lược, tránh dùng chung warmup; `tools/compare_benchmark.py` đọc ZIP kết quả thực và đối chiếu từng lệnh. Không tối ưu tham số tự động.

## Phạm vi và nguồn

Xem `PRODUCT.md` cho định hướng so với RoboQuant/Ultimate, `benchmarks/REPORT.md` cho kết quả 8 chiến lược và các giới hạn kiểm định. Bản Ultimate độc lập là công cụ so sánh, không phải engine vận hành chính. Chưa tạo repo GitHub hay xuất bản công khai.

FreqPilot là tác phẩm phái sinh GPL-3.0 của FreqUI Ultimate / FreqUI. Giữ LICENSE và các ghi nhận nguồn ở `SOURCES.md`; mã engine Freqtrade không bị thay bằng fork Ultimate.
