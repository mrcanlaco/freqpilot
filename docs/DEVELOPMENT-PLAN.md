# Kế hoạch phát triển FreqPilot

Ngày: 23/10/2026 — cơ sở: bản `21e73a1`, engine Freqtrade chính thức 2026.9.

**Trạng thái: đang nghiệm thu bản triển khai ngày 23/10/2026.** Các mốc 1–5 đã có mã và giao diện; chứng cứ thực nghiệm, giới hạn native và quy trình vận hành được ghi trong [OPERATIONS.md](OPERATIONS.md). Các tiêu chí phụ thuộc dữ liệu paper có giao dịch thật trong dry-run hoặc máy thứ hai chưa thể tuyên bố đã đạt. Phạm vi là máy cá nhân, BTC/ETH Binance USDT-M Futures isolated 1x, backtest và paper; engine giữ Freqtrade chính thức 2026.9.

## 1. Mục tiêu và cách kết hợp hai ứng dụng tham khảo

Một người dùng có thể đi từ ý tưởng tới kết quả có thể kiểm tra, chọn một bộ tham số và quan sát paper bằng giao diện tiếng Việt. Codex tiếp tục hỗ trợ viết và sửa mã. Thành công được đo bằng khả năng tự hoàn tất quy trình, tính đầy đủ của bằng chứng và khả năng giải thích sai khác; không đo bằng lợi nhuận đẹp hoặc số lượng tính năng.

| Nguồn | Phần tốt nên lấy | Cách đưa vào FreqPilot |
|---|---|---|
| RoboQuant | Tổ chức quanh chiến lược; cấu hình dùng xuyên backtest/optimize/deploy; kết quả và lịch sử cùng ngữ cảnh | Một hồ sơ thí nghiệm liên kết phiên bản mã, tham số, dữ liệu, lần chạy, kiểm định và paper. Học hành vi sản phẩm; không nhập mã độc quyền |
| RoboQuant | Cách trình bày IS/OOS, walk-forward, phân bố thử nghiệm và nhiều thị trường | Timeline tập học/ngoài mẫu, bảng từng cửa sổ và so sánh ứng viên; chỉ mở tính năng có dữ liệu và backend thực |
| FreqUI Ultimate | Monaco, diff, biểu đồ, bảng giao dịch, so sánh, bảng WFA và heatmap | Nối dữ liệu mới vào component đã có; giữ GPL/ghi nhận nguồn; sửa nhãn, đơn vị và giá trị thiếu |
| Freqtrade Ultimate | Cấu trúc job, WFA, sensitivity, nhiều seed | Tham khảo cách tổ chức; lớp điều phối gọi Hyperopt/backtest chính thức trên đầu vào riêng, không thay cả backend bằng fork |
| Freqtrade chính thức | Dữ liệu sàn, chiến lược Python, backtest, Hyperopt, lookahead/recursive, dry-run | Tiếp tục là engine thực thi duy nhất của bộ chính |

Engine RoboQuant hiện được tài liệu mô tả dùng CME/Tradovate. Không lấy tính năng tick/L2 CME làm yêu cầu tương đương cho Binance hoặc làm căn cứ thay engine hiện tại.

## 2. Nền đã có — không làm lại

- Thư viện chiến lược, ý tưởng/ghi chú/nhãn, tìm kiếm, yêu thích, tạo/sao chép mã.
- Monaco, kiểm tra cú pháp, chống lưu đè revision, backup và diff phiên bản.
- Bộ tham số có tên; backtest với snapshot mã/JSON/feather; ZIP native và hash; chạy lại từ gói và đối chiếu.
- Lookahead/recursive với lịch sử và ngữ cảnh; Hyperopt native với seed, bảng epoch, dừng, IS/OOS và lưu ứng viên.
- Paper theo hồ sơ backtest, database riêng, giới hạn 1x, một worker nghiên cứu, trạng thái native và lịch sử thao tác.
- Bộ khởi tạo, Start/Stop, kiểm tra cài đặt và các bằng chứng benchmark.

Đợt trước đã kiểm tra engine bằng 179 test backtest upstream, đối chiếu tám chiến lược với Ultimate, thử replay và tối ưu. Giữ nguyên các bằng chứng và benchmark chưa tối ưu. Không chạy lại toàn bộ kiểm thử chỉ để lập kế hoạch.

## 3. Kiến trúc và quy ước chung

Luồng chính: **Chiến lược → dữ liệu → backtest gốc → kiểm định → tối ưu tùy chọn → đánh giá ngoài mẫu → paper → đối chiếu**.

Giữ bảy tab đang có trong chiến lược. Thanh điều hướng cấp cao hướng tới: **Chiến lược / Dữ liệu / Tác vụ / Paper / Cài đặt**. Dữ liệu và tác vụ là trang dùng chung, không tạo thêm một bản biểu mẫu riêng cho từng tab.

| Lớp | Trách nhiệm | Thành phần hiện có để mở rộng |
|---|---|---|
| Giao diện | Ngữ cảnh chiến lược, cấu hình, giải thích kết quả, thao tác chủ động | `FreqPilotStudio.vue`, `StrategyLibrary`, `ParameterPresets`, `OptimizationWorkspace`, `PaperWorkspace` |
| Điều phối nghiên cứu | Kiểm tra dữ liệu, lưu kế hoạch, snapshot, quản lý child job, lưu báo cáo | `api_studio.py`, `api_runs.py`, `api_optimization.py`, `api_replay.py` |
| Thực thi | Đọc dữ liệu, tính tín hiệu, mô phỏng, tối ưu và paper | CLI/API chính thức; giữ image đã ghim |
| Bằng chứng | Mã/JSON/dữ liệu/hash, kết quả native, lịch sử và nguyên nhân chưa đủ đối chiếu | Kho `freqpilot` hiện có, ZIP native, `paper_history.py` |

Quy ước bắt buộc:

- Ngày nội bộ UTC, khoảng `[start, end)`, phân biệt nến mở với nến đã đóng; UI có giờ Việt Nam rõ ràng.
- Phân biệt khoảng yêu cầu, khoảng thực có, khoảng giao dịch và warmup. Không tự đổi ngày hoặc warmup để chạy được.
- Mỗi thí nghiệm có ID và bản kế hoạch bất biến: revision mã/helper, preset, dataset/hash, cấu hình hiệu lực đã loại bí mật, engine/image, seed, mục tiêu, ngân sách và child run IDs.
- Trạng thái tác vụ tách khỏi kết luận nghiên cứu. `completed` không có nghĩa đủ dữ liệu, không bias hoặc có lợi nhuận.
- Không tự chạy khi mở trang, không tự áp dụng ứng viên hoặc chuyển hồ sơ paper. Một lần bắt đầu WFA có thể cho phép chuỗi con trong đúng kế hoạch đã xem lại; chuỗi không được tự mở rộng phạm vi.
- Gói cũ tiếp tục đọc được. Trường bằng chứng chưa có trong gói cũ được ghi là chưa có, không dựng thêm từ môi trường hiện tại.
- Metadata sàn được ghi lại cùng thời điểm lấy; ghi nhận không đồng nghĩa engine đã tái dùng metadata đó khi replay. Không mô tả là metadata lịch sử nếu chỉ lấy thông tin hiện tại.

## 4. Mốc 1 — dữ liệu đủ và biết chính xác đang chạy gì

**Ưu tiên P0; quy mô vừa; có thể dùng độc lập ngay khi nghiệm thu.**

### Công việc

**D1. Chuẩn hóa báo cáo phạm vi.** Mở rộng inventory/manifest hiện có thành bảng theo cặp, khung và loại dữ liệu. Ghi ngày đầu/cuối, nến đã đóng gần nhất, warmup yêu cầu và khoảng thực sự đủ. Cặp/khung informative hoặc dữ liệu phụ chưa xác định được phải được nêu rõ.

**D2. Kiểm tra dữ liệu thô.** Đọc feather trước bước engine tự lấp nến; kiểm tra timestamp, khoảng trống trong chuỗi, giá trị hữu hạn, quan hệ OHLC và khối lượng phù hợp từng loại dữ liệu. Mark không được kiểm tra như volume giao dịch. Phát hiện thiếu đầu, cuối và giữa khoảng bắt buộc, gồm warmup.

**D3. Kiểm tra funding theo sự kiện.** Đối chiếu timestamp/rate theo lịch sử công khai Binance đã phân trang đầy đủ; giữ timestamp thô và quy tắc chuẩn hóa native. Không giả định mỗi 8 giờ phải có funding. API thiếu/không truy cập được tạo trạng thái chưa xác minh, không biến thành đạt hoặc kết luận thiếu.

**D4. Tải bổ sung có xem trước.** Tái dùng downloader native; chỉ rõ cặp/khung/loại/khoảng cần tải, ngân sách tài nguyên và thời điểm kiểm tra. Tải vào vùng tạm hoặc phiên dữ liệu mới rồi kiểm tra trước khi đưa vào kho đang dùng. Mạng lỗi không được ghi thành công. Snapshot cũ giữ nguyên; không ghi đè dữ liệu đang được tác vụ nghiên cứu đọc.

**D5. Lưu bằng chứng đầu vào.** Kết quả kiểm tra gắn hash dữ liệu, thời gian, phiên bản bộ kiểm tra và phạm vi truy vấn Binance. Nếu dữ liệu đổi, báo cáo cũ không còn là kiểm tra của dữ liệu mới. Lưu metadata sàn và image digest để giải thích thay đổi precision/minimum stake; chưa hứa replay hoàn toàn offline.

### Nghiệm thu

- Dữ liệu thử cố ý thiếu một đoạn, trùng timestamp, sai OHLC và thiếu warmup đều được phát hiện đúng vị trí.
- Ngày kết thúc vượt phạm vi dữ liệu không bị rút ngắn ngầm; người dùng được chọn tải thêm hoặc chủ động đổi phạm vi.
- Funding thiếu sự kiện đã xác nhận bị chặn; lịch funding thay đổi không bị báo thiếu giả. Mất mạng được ghi chưa xác minh.
- Luồng phát hiện → tải bù → kiểm tra lại → backtest chạy được trên bản dữ liệu thử riêng.
- UI cho biết mỗi phần là **đủ / thiếu / lỗi / chưa xác minh** và lý do. Các chặn cứng dựa vào lỗi cụ thể; trạng thái chưa xác minh không có nhãn “đã khớp Binance”.
- So sánh baseline trên dữ liệu nguyên vẹn vẫn khớp trước; không sửa công thức engine.

Đề xuất mở rộng dữ liệu nghiên cứu tới khoảng 12 tháng trước, sau đó 24 tháng nếu chiến lược và tài nguyên cần. Chọn phạm vi trước khi xem kết quả; đây là đề xuất cho đợt thực hiện, chưa tải trong bước lập kế hoạch.

## 5. Mốc 2 — đo chênh lệch backtest và paper

**Ưu tiên P1 cao; quy mô lớn; phụ thuộc Mốc 1.**

### Công việc

**P1. Phiên quan sát paper.** Bổ sung ID phiên quan sát liên kết đúng hồ sơ, revision, JSON tham số, engine, vốn và sizing hiệu lực. Đọc thông tin native bằng API hoặc bản sao DB nhất quán ở chế độ đọc; lưu riêng, không sửa database giao dịch. Ghi khoảng mất liên lạc và thay đổi cấu hình.

**P2. Thu bằng chứng tín hiệu và lệnh.** Ưu tiên dữ liệu phân tích/candle/order native sẵn có. Phần không lấy được phải ghi chưa quan sát; không dựng tín hiệu lịch sử từ mã mới. Giao dịch có trước phiên, vị thế còn mở cuối phiên, DCA và thoát từng phần cần được nhận diện riêng.

**P3. Backtest cùng khoảng và đối chiếu.** Dùng đúng hồ sơ với dữ liệu đã hoàn tất và warmup cần thiết. So sánh cặp/chiều, thời gian tín hiệu, vào/ra, sizing, giá mô phỏng, lệnh con, phí/funding và lý do thoát. Ghép lệnh bằng quy tắc rõ và có thể kiểm tra; trường hợp không ghép duy nhất được để chưa rõ, không tự chọn lệnh gần nhất.

### Nghiệm thu

- Báo cáo có ba nhóm **khớp / khác / chưa đủ bằng chứng**; số tiền, bps và độ lệch thời gian giữ nguyên giá trị thay vì làm tròn để ép khớp.
- Phân biệt nguyên nhân được chứng minh với giả thuyết. Thiếu log không được kết luận do slippage.
- Các ca cố ý lệch timestamp/fee/funding, DCA, partial exit và mất quan sát được phân loại đúng.
- Một phiên thật có giao dịch hoàn tất được dùng làm bằng chứng tích hợp. Nếu chưa có giao dịch, chỉ xác nhận luồng thu thập; không ép tín hiệu để hoàn thành nghiệm thu.
- Không yêu cầu paper khớp 100% với backtest vì hai mô hình thời điểm/khớp lệnh có thể khác. Replay từ cùng gói vẫn giữ phép đối chiếu chính xác hiện có.

Paper ở đây là dry-run Freqtrade trên dữ liệu thị trường, không phải fill từ tài khoản Binance thật. Thời gian thu đủ mẫu phụ thuộc chiến lược; không cam kết một số ngày cố định sẽ chứng minh chất lượng.

## 6. Mốc 3 — phòng tối ưu có kiểm định nhiều giai đoạn

**Ưu tiên P1; quy mô lớn; triển khai từng phần sau Mốc 1. Mốc 2 có thể tiếp tục thu bằng chứng song song.**

### Công việc

**O1. Thí nghiệm và tác vụ liên kết.** Mở rộng hồ sơ tối ưu hiện có thành kế hoạch cha/con. Có xem trước số lần đánh giá, ngày, seed, nhóm tham số, tiêu chí, baseline và giới hạn CPU/đĩa. Mặc định chạy nghiên cứu tuần tự; tiếp tục giới hạn worker hiện tại. Tái dùng khóa hoạt động native và quản lý đúng tiến trình con.

**O2. Walk-forward bản đầu chỉ rolling.** Hiển thị timeline các cửa sổ train/OOS không chồng lấn ở phần OOS. Mỗi cửa sổ chạy Hyperopt trên train, chọn ứng viên theo quy tắc chỉ dùng train, rồi native backtest trên OOS. Có baseline không tối ưu chạy cùng cửa sổ. Holdout cuối được tách trước và chỉ mở đánh giá bằng thao tác riêng.

**O3. Báo cáo độ bền.** Bảng từng cửa sổ: tham số, số lệnh, P&L, drawdown, chi phí, mức giảm từ train sang OOS và phần dữ liệu thiếu. Ghép đường vốn chỉ khi công bố rõ quy tắc vốn/reset; không cộng phần trăm hoặc trung bình Sharpe/drawdown thành chỉ số toàn kỳ. Tính profit factor từ tổng lời/lỗ gộp; không biến số không xác định thành 0.

**O4. Sensitivity và nhiều seed.** Quét lân cận một hoặc hai tham số đã hỗ trợ, dùng nhiều seed định trước và kịch bản phí native công khai. Heatmap chỉ chứa các backtest thực, ô chưa chạy để trống. Nếu bổ sung chi phí trượt giá bằng hậu xử lý, ghi rõ đó chỉ là ước lượng tác động lên P&L, không mô phỏng lại lệnh/fill.

**O5. Phạm vi tham số và phương pháp tìm kiếm.** Trước hết dùng nhóm/giới hạn native đang có. Sau đó khảo sát chỉnh khoảng tìm kiếm từng Parameter bằng cơ chế native/wrapper riêng, có kiểm tra không thay tín hiệu ngoài phạm vi. Chỉ mở thêm sampler khi tương thích engine 2026.9 được chứng minh. Chưa đưa PlateauSampler/CPCV/Pareto vào phiên đầu.

### Ràng buộc phương pháp

- Khoảng `[start,end)` và warmup thống nhất; dữ liệu trước OOS có thể dùng để khởi động indicator, không được tính vào P&L OOS hoặc chọn tham số bằng OOS.
- Mỗi OOS ban đầu là bài thử độc lập, bắt đầu không vị thế. Hiển thị force-exit ở cuối cửa sổ. Không gọi chuỗi này là mô phỏng bot liên tục đổi tham số khi đang giữ vị thế.
- Khoảng cách train/OOS có thể cấu hình theo chiến lược; không mô tả một số ngày gap cố định là bảo đảm hết rò rỉ dữ liệu.
- Không có epoch hợp lệ thì cửa sổ thất bại có lý do; baseline phải là kết quả riêng, không âm thầm thay ứng viên bằng mặc định.
- Nếu dùng OOS để chọn lại tham số, seed hoặc tạo consensus, dữ liệu đó đã tham gia phát triển. Ứng viên mới cần holdout mới; không gán hiệu suất OOS cũ cho ứng viên chưa từng chạy.
- Holdout là kỷ luật nghiên cứu và lịch sử truy cập trong UI, không phải sandbox ngăn chủ máy đọc dữ liệu. Lưu số lần sử dụng và phiên bản đã đánh giá.

### Nghiệm thu

- Fixture xác nhận không nhầm train/OOS, không đếm lặp OOS, có đủ warmup và force-exit được trình bày rõ.
- Mỗi cửa sổ truy ra đúng source/preset/data/seed và ZIP native; chạy lại một cửa sổ từ gói khớp phép đối chiếu native.
- Dừng chuỗi chỉ dừng child thuộc chuỗi; các child đã hoàn tất giữ nguyên. Reload UI nhận đúng trạng thái; restart đánh dấu interrupted, không tự chạy lại.
- Giai đoạn lỗi hoặc không lệnh không bị loại khỏi báo cáo để làm đẹp kết quả.
- Bảng heatmap và các chỉ số không dùng nhãn “an toàn/đạt” chỉ từ hệ số biến thiên. Đặc biệt trung bình bằng 0 không được diễn giải là độ biến thiên bằng 0.

### Tái sử dụng từ Ultimate

Các component đã có trong repo: `WfaWindowTable`, `WfaParamStabilityTable`, `WfaDegradationTable`, `WfaHoldoutCard`, `SensitivityGridChart`, `EpochComparePanel`, `ComparePanel`. Tạo bộ chuyển đổi kết quả native sang dữ liệu trình bày của chúng; không giả lập toàn bộ API fork. Sửa null/đơn vị/nhãn trước khi mở cho người dùng.

`walk_forward.py` và job manager của fork chỉ là nguồn tham khảo cấu trúc. Runner FreqPilot tiếp tục gọi launcher/Hyperopt chính thức với bản sao riêng; tránh phụ thuộc callback và cờ nội bộ riêng của fork.

## 7. Mốc 4 — hoàn thiện trải nghiệm theo chiến lược

**Ưu tiên P1; quy mô vừa. Các phần nền làm song song từ Mốc 1; nghiệm thu tổng thể sau Mốc 3.**

### Công việc

**U1. Luồng “Test một chiến lược”.** Từ thư viện, đi qua dữ liệu → cấu hình → backtest → kết quả; bước tiếp theo hiện theo trạng thái thực. Thiếu dữ liệu dẫn tới đúng trang sửa, lỗi mã dẫn tới editor. Mặc định hiển thị ít lựa chọn; phần nâng cao mở khi cần.

**U2. Báo cáo đầu trang dễ hiểu.** Trình bày khoảng thực, số lệnh, baseline/ứng viên, train/OOS, phí/funding, phiên bản mã/tham số và giới hạn kiểm định. Biểu đồ/giao dịch dùng component hiện có. Giữ kết quả cũ khi sửa cấu hình nhưng đánh dấu khác ngữ cảnh.

**U3. Tổ chức thí nghiệm.** Gắn nhãn/ghi chú, ghim baseline, so sánh các lần chạy cùng protocol. Ma trận BTC/ETH × timeframe chỉ thêm sau runner chuỗi; mỗi ô là bài thử độc lập, không gọi là danh mục dùng chung vốn. Giữ khả năng backtest BTC+ETH chung vốn hiện có và phân biệt rõ hai chế độ.

**U4. Editor và Codex.** Hoàn thiện tiếng Việt, lưu nháp có chống mất mã, diff và thông báo lỗi có hướng xử lý. Nếu chiến lược thực sự cần helper, mở cây tệp trong thư mục được phép với revision/hash đầy đủ. Tiếp tục dùng chức năng xuất yêu cầu sang Codex, chưa xây chatbot riêng.

### Nghiệm thu

- Người dùng hoàn tất backtest và đọc báo cáo qua UI mà không cần terminal ở quy trình thường ngày.
- Cùng tên chiến lược, đơn vị USDT, ngày giờ và trạng thái được dùng xuyên các trang; không trộn nghiên cứu webserver với bot đang chạy.
- Không tự chạy tác vụ, thay mã hoặc đổi paper khi chuyển tab/chọn ứng viên.
- Các trạng thái dữ liệu trống, lỗi mạng, tác vụ gián đoạn, ít lệnh và preset cũ có thông báo cụ thể.
- Kiểm tra bố cục desktop phổ biến, bàn phím, nhãn nút và bảng dài; tái dùng giao diện Ultimate thay vì viết lại chart/editor.

## 8. Mốc 5 — bản ổn định có thể khôi phục và bảo trì

**Ưu tiên P1/P2; quy mô vừa. Một phần quản lý đĩa cần làm sớm nếu dữ liệu mở rộng gây áp lực.**

### Công việc

**R1. Quản lý dung lượng.** Đo dung lượng snapshot và dự kiến trước tác vụ. Khảo sát lưu dữ liệu bất biến dùng chung theo hash; tránh hardlink tới file mutable. Có chính sách lưu trữ, ghim và xem trước phần sẽ dọn. Không xóa dữ liệu còn được hồ sơ/phiên paper tham chiếu hoặc tự xóa gói cũ.

**R2. Backup và khôi phục.** Sao lưu nhất quán SQLite bằng cơ chế thích hợp, gồm WAL khi cần; không chỉ copy tệp DB đang ghi. Phân biệt bản sao lưu cá nhân có bí mật với gói nghiên cứu chia sẻ đã loại bí mật. Khôi phục vào thư mục mới rồi kiểm tra hash, hồ sơ và lịch sử.

**R3. Vận hành.** Hiển thị tuổi dữ liệu, trạng thái worker, khoảng mất quan sát, tác vụ gián đoạn và dung lượng. Cảnh báo chỉ mô tả bằng chứng đang có, không suy RUNNING từ API Online. Mặc định một worker paper nghiên cứu; mở nhiều worker/Gateway khi nhu cầu và tải đo được chứng minh cần.

**R4. Phát hành.** Kiểm tra từ bản Git sạch, chạy Compose ở môi trường riêng với cổng riêng, thử khôi phục và đường quay về image/UI trước. GitHub CI chỉ ghi đạt sau khi có run thật; chưa cần publish repo hoặc mở internet. Mỗi đợt thay đổi nhỏ có bằng chứng, giới hạn và ảnh UI khi có sửa giao diện.

### Nghiệm thu

- Một hồ sơ nghiên cứu, gói kết quả và lịch sử paper được khôi phục đúng từ backup.
- Mất điện/khởi động lại không gây tự chạy lại tối ưu hoặc tự vào lệnh mới ngoài chính sách paper hiện có.
- Bản cài riêng không ghi đè cấu hình/dữ liệu, không lộ tài khoản và không chiếm dịch vụ bộ chính.
- Chỉ ghi “đã kiểm chứng máy thứ hai” sau khi làm thật; bài thử máy sạch riêng và bằng chứng trên máy hiện tại được ghi đúng tên.

## 9. Thứ tự thực hiện và chia việc

Thứ tự phụ thuộc: **Mốc 1 → Mốc 2 và Mốc 3 → hoàn thiện Mốc 4 → nghiệm thu Mốc 5**. UX nền của Mốc 4 và đóng gói của Mốc 5 có thể tiến hành song song; dữ liệu không đạt thì không mở WFA như tính năng đã sẵn sàng.

| Luồng làm việc | Phạm vi sở hữu khi triển khai | Phụ thuộc |
|---|---|---|
| Backend/dữ liệu | Coverage, funding evidence, tải bù, manifest | Chốt hợp đồng kết quả trước khi UI tích hợp |
| UI | Trang Dữ liệu, hướng dẫn, báo cáo và bảng Ultimate | Fixture cùng hợp đồng; không chỉnh engine |
| Nghiên cứu/kiểm định | Paper reconciliation; sau đó WFA và sensitivity | Native launcher, dữ liệu đủ và protocol bất biến |
| Tích hợp/nghiệm thu | Ghép thay đổi, test trọng tâm, kiểm tra runtime và phát hành | Sau các luồng trên; một người điều phối việc cập nhật dịch vụ |

Tối đa ba luồng phụ cùng điều phối chính khi dùng subagent. Chia theo file/phạm vi để tránh sửa đè. Các công việc nặng dùng chung engine chạy tuần tự; không tăng số job chỉ vì có nhiều agent. Review độc lập tập trung vào các chỗ có thể làm sai kết quả, không lặp audit toàn bộ vô hạn.

Khi triển khai, đã làm D1–D5 trước rồi mới nối P1–P3 và O1–O5. Các luồng UI, backup và cài riêng được thực hiện song song. Nghiệm thu vẫn tách rõ: chạy được tính năng không đồng nghĩa dữ liệu thị trường được xác minh hoặc chiến lược có lợi thế.

## 10. Cách nghiệm thu xuyên suốt

- Bảo toàn benchmark gốc; mỗi sửa đổi có kết quả trước/sau với cùng protocol khi có thể ảnh hưởng tính toán.
- Test tập trung vào lỗi thực: ranh giới thời gian, thiếu dữ liệu, nguồn tham số, ownership/cancel, phục hồi, ghép lệnh và aggregation. Không thêm test chỉ đếm component.
- Chạy typecheck/build và bộ test liên quan; chạy bộ đầy đủ khi tích hợp bản phát hành. Chỉ mở rộng/chạy lại khi thay đổi hoặc lỗi mới đòi hỏi.
- Kiểm tra thực trên dữ liệu/container riêng trước khi cập nhật research service. Không dùng kiểm thử để tự bật/tắt hồ sơ paper hiện tại.
- Mỗi màn hình chỉ hiện dữ liệu đã có: chưa đo → chưa đo; không lệnh → không lệnh; chưa xác minh → chưa xác minh.
- Chất lượng công cụ, độ ổn định vận hành và lợi thế chiến lược là ba kết luận riêng. Không đặt ngưỡng số giao dịch duy nhất để cấp chứng nhận chiến lược.

## 11. Chưa đưa vào đợt phát triển này

Tick/L2 Binance hoặc engine fill mới; live trading; SaaS/thu phí/nhiều tenant; AI chatbot riêng; tái viết editor/chart; chuyển toàn bộ engine sang Ultimate; gateway/fleet lớn; CPCV/Pareto/PlateauSampler trước khi WFA đơn giản được kiểm chứng. Các mục này được xem lại khi giải quyết một nhu cầu đo được.

## Nguồn và bằng chứng

- [RoboQuant: tổ chức engine và phạm vi CME](https://roboquant.dev/docs/overview)
- [RoboQuant: backtest, optimization và validation](https://roboquant.dev/docs/backtesting)
- [RoboQuant: tham số và cấu hình chiến lược](https://roboquant.dev/docs/python-strategies)
- [FreqUI Ultimate: component nghiên cứu v2.1.0](https://github.com/titouannwtt/frequi-ultimate/tree/v2.1.0/src/components/strategyDev)
- [Ultimate: WFA đúng commit đã khảo sát](https://github.com/titouannwtt/freqtrade-ultimate/blob/878206c5a3be95d269ed2ff9418071df059171a4/freqtrade/optimize/walk_forward.py)
- [Ultimate: job manager đúng commit](https://github.com/titouannwtt/freqtrade-ultimate/blob/878206c5a3be95d269ed2ff9418071df059171a4/freqtrade/rpc/api_server/api_stratdev_jobs.py)
- [Freqtrade: giới hạn backtest](https://www.freqtrade.io/en/stable/backtesting/#assumptions-made-by-backtesting)
- Local: `PRODUCT.md`, `benchmarks/REPORT.md`, `benchmarks/optimization-control.json`, `benchmarks/replay-control.json`, `benchmarks/portable-install-control.json`, `docs/INSTALL.md`.
