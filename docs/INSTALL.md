# Cài FreqPilot trên thư mục mới

Bộ hiện tại dành cho máy cá nhân, Binance BTC/ETH USDT-M Futures isolated 1x, chỉ backtest và paper. Engine được ghim ở Freqtrade 2026.9. Hướng dẫn này không thay bộ đang chạy và không xuất bản lên GitHub.

## Điều kiện

Windows với PowerShell 7, Docker Desktop đang mở, Node.js 24 và pnpm 10.33.2. Chạy các bước dưới đây tại thư mục gốc của bản sao repo FreqPilot. Các cổng 8090, 8091 và 8095 cần trống khi thực sự bật dịch vụ; bộ cũ và bản mới không dùng chung những cổng này đồng thời.

## Tạo cấu hình riêng

```powershell
./Initialize.ps1
```

Lệnh tạo `runtime/user_data`, `.env`, tám chiến lược mẫu và tài khoản local ngẫu nhiên. Mật khẩu nằm trong `runtime/user_data/ACCESS.txt`, không in ra màn hình. Mặc định `dry_run=true`, `initial_state=stopped`, ví 1.000 USDT, stake 100 USDT, tối đa hai lệnh, phí 0,05% mỗi chiều; không có khóa giao dịch Binance. Chưa có dữ liệu giá, báo cáo hay database giao dịch cũ được chép sang.

Để chọn thư mục dữ liệu khác, dùng đường dẫn tuyệt đối:

```powershell
./Initialize.ps1 -UserDataPath 'D:/FreqPilot/private-user-data' -EnvFile './private.env' -ProjectName 'freqpilot-personal'
```

Không ghi đè tệp env hoặc thư mục dữ liệu đã tồn tại. Muốn mở bộ cũ, giữ `.env` cũ và dùng `Start.ps1`; không chạy lại Initialize. Nếu dùng `-EnvFile`, giữ cùng lựa chọn đó ở mọi lệnh Start/Stop bên dưới. Các thư mục dữ liệu nằm ngoài repo cần được bạn giữ riêng khi sao lưu hoặc chia sẻ.

## Build và mở dịch vụ

```powershell
./Start.ps1 -Build
```

Start kiểm tra danh tính dự án và cổng trước khi thay đổi dịch vụ, cài UI theo lockfile, build UI/backend từ checkout hiện tại rồi mở ba dịch vụ trên loopback. Cả hai lệnh chạy paper ép `--dry-run`. Bộ mới vẫn dừng vào lệnh cho đến khi bạn chủ động bật trên giao diện.

Để kiểm tra cấu hình mà chưa mở dịch vụ, sau khi có bản UI build:

```powershell
./Start.ps1 -CheckOnly
```

CheckOnly kiểm tra Compose và nạp mẫu StarterFutures bằng schema/StrategyResolver của image chính thức, trong container không có mạng và chỉ đọc dữ liệu. Nó không khởi động bot, tải giá hay backtest. Chiến lược khác đang sửa lỗi không chặn việc mở editor. Việc nạp Python vẫn thực thi mã ở cấp module của chiến lược theo cơ chế Freqtrade, không phải sandbox Python.

Nếu tên dự án đã thuộc thư mục dữ liệu khác hoặc cổng do ứng dụng khác chiếm, Start dừng trước bước mở dịch vụ. Không tự dừng bộ cũ để nhường chỗ. `.env` cũ không có tên dự án vẫn dùng `codex-freqtrade` như trước.

## Đăng nhập lần đầu

1. Mở **http://localhost:8091/studio**. Khi chưa có kết nối, UI đưa tới trang đăng ký bot.
2. Chọn **Add a bot**. Đặt tên `Backtest`, **Address of the bot API** là `http://localhost:8091`, nhập username/password từ ACCESS.txt rồi chọn **Add the bot**. Tên “bot” là cách gọi chung của giao diện; đây là dịch vụ nghiên cứu webserver.
3. Mở **Nghiên cứu** để thấy thư viện mẫu. Có thể dùng cùng workspace trên http://localhost:8090/studio.
4. Nếu muốn giám sát bot StarterFutures độc lập, thêm kết nối `Paper chính` ở địa chỉ `http://localhost:8090` bằng cùng tài khoản local. Không cần tự thêm 8095: khi đã có hồ sơ, **Mở giám sát paper** đăng ký worker nghiên cứu tự động.

Phiên đăng nhập lưu trong trình duyệt. Không đưa ACCESS.txt, config.json, `.env`, database hoặc gói mã/dữ liệu riêng lên GitHub.

## Backtest rồi paper

Ở bản cài mới, dữ liệu đang trống. Dùng công cụ tải dữ liệu native của Freqtrade trong UI, chọn Binance Futures, BTC/ETH, khung của chiến lược và chi tiết 1m. Cần tải cả nến, mark price và funding; preflight trong workspace sẽ chỉ rõ phần thiếu. Không dùng funding bằng 0 để lấp dữ liệu chưa tải.

Trong một chiến lược: ý tưởng → mã → tham số → backtest → đọc kết quả/kiểm định → chuẩn bị hồ sơ paper. Trang **Paper** chỉ bật đúng hồ sơ từ gói backtest đã kiểm tra, dùng database riêng và giới hạn 1x. Mở giám sát không bật giao dịch. Nếu bot dừng và cache nến phân tích trống, giao diện giải thích trạng thái này; dữ liệu giá đã tải trên đĩa không đồng nghĩa cache đang chạy đã có nến.

## Kiểm tra trước khi chia sẻ mã

```powershell
./Check.ps1 -InstallDependencies
```

Lệnh chạy typecheck, toàn bộ unit/component test UI, build vào `ui/dist-next`, build image backend riêng để chạy unittest không có mạng, kiểm tra bảo vệ cài đặt và kiểm tra native cho tám mẫu trên cấu hình mới. Không thay `ui/dist` đang được phục vụ, không dùng dữ liệu cá nhân và không khởi động dịch vụ giao dịch. Một phần kiểm tra Start/Stop dùng Docker giả lập để chứng minh từ chối đúng dự án/cổng/cấu hình; phần schema/StrategyResolver dùng image thật.

Workflow gốc `.github/workflows/check.yml` chạy cùng quy trình khi repo được đưa lên GitHub. Các action được ghim SHA từ [actions/checkout](https://github.com/actions/checkout), [actions/setup-node](https://github.com/actions/setup-node) và [pnpm/action-setup](https://github.com/pnpm/action-setup). Workflow không publish, deploy, chạy tối ưu hay mở paper. Các workflow kế thừa trong `ui/.github` giữ để tham khảo upstream, không tự hoạt động như workflow gốc của repo này. Chưa xác nhận kết quả trên GitHub khi chưa có repo/run thực tế.

## Dừng và sao lưu

```powershell
./Stop.ps1
```

Stop kiểm tra đúng dự án và mount dữ liệu trước khi dừng, vẫn cho phép dừng nếu nội dung config bị sửa lỗi. Không xóa database, dữ liệu giá hoặc hồ sơ. Với vị thế đang mở, dùng **Tạm ngừng vào lệnh** trong trang Paper để tiếp tục quản lý thoát; Stop.ps1 dừng toàn bộ dịch vụ.

Giữ riêng toàn bộ thư mục user_data và tệp env. `Initialize.ps1` không phải lệnh khôi phục bản sao lưu và không thay mật khẩu của bộ cũ. Dữ liệu và engine không được nâng cấp tự động.
