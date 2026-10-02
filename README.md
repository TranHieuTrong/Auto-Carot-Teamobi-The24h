# ⚡ TOOL AUTO TOPUP THE24H.VN - NẠP CAROT / TEAMOBI HÀNG LOẠT

Tool Python có giao diện đồ họa hiện đại (**GUI CustomTkinter**) hỗ trợ nạp tiền thẻ game Teamobi / Carot (Ngọc Rồng, Ninja School, Avatar, Hiệp Sĩ Online, KPAH, Mobi Army...) hàng loạt cùng lúc trên website [the24h.vn](https://the24h.vn).

---

## 🌟 TÍNH NĂNG NỔI BẬT

1. **Nạp hàng loạt nhiều tài khoản cùng lúc (Batch Topup)**:
   - Nhập danh sách tài khoản trực tiếp trên giao diện hoặc bấm nạp từ file `.txt`.
   - Hỗ trợ nạp chung 1 Game / Máy chủ / Mệnh giá cho toàn bộ danh sách, hoặc tùy biến từng tài khoản theo cú pháp `taikhoan|server|menhgia`.
2. **Tự động đăng nhập & Quản lý số dư**:
   - Tự động đăng nhập tài khoản the24h.vn của bạn.
   - Hiển thị thông tin tên chủ tài khoản và số dư ví VND trực tiếp trên giao diện, có nút làm mới số dư nhanh.
3. **Tự động thanh toán bằng Quỹ VND (Hỗ trợ Mật khẩu cấp 2 - MKC2)**:
   - Tự động lấy CSRF token, gửi đơn nạp, bắt mã hóa đơn và tự động xác thực mã MKC2 qua cổng Quỹ VND.
   - Có tùy chọn nạp hoàn tất hoặc chỉ tạo đơn chờ thanh toán.
4. **Hỗ trợ đầy đủ các game Teamobi / Carot**:
   - Ngọc Rồng (19 server từ 1 Sao đến 15 Sao, VIP, Super).
   - Ninja School, Avatar, Avatar 3, Hiệp Sĩ Online, KPAH, Mobi Army 2, Mobi Army 3, Hải Tặc Tí Hon...
   - Tự động tính toán chiết khấu % và số tiền thực trả hiển thị trực quan.
5. **Theo dõi tiến trình thời gian thực**:
   - Bảng danh sách chi tiết (STT, Tài khoản, Server, Gói nạp, Số tiền, Trạng thái, Mã đơn, Chi tiết lỗi).
   - Thanh tiến trình % hoàn thành và thống kê (Tổng đơn, Thành công, Thất bại, Tổng tiền đã chi).
   - Nhật ký (Log) chi tiết từng giây.
6. **Nạp Quỹ Tự Động Bằng Mã QR VietQR 24/7 (Thông Minh)**:
   - **Tự động tính số tiền thiếu**: So sánh số dư ví the24h.vn với tổng tiền cần nạp cho danh sách nick.
   - **Tự động tạo mã VietQR chuẩn**: Nếu thiếu tiền, hệ thống tự động tạo mã QR VietQR đúng số tiền còn thiếu kèm chính xác cú pháp nạp tiền cá nhân `THE24H [username]` và số tài khoản ngân hàng thụ hưởng.
   - **Quét mã 1 chạm**: Quét bằng mọi App Ngân Hàng (VCB, BIDV, MB, Techcombank, TPBank, Momo...) mà không phải tự gõ số tiền hay nội dung.
   - **Tự động nhận diện tiền vào ví (Auto-polling)**: Lắng nghe trạng thái số dư ví mỗi 4 giây. Khi tiền vừa vào ví web, tool tự động phát hiện số dư mới và cho phép 1-click `🚀 ĐỦ TIỀN RỒI - BẮT ĐẦU NẠP NGAY` để tự động chạy tiếp!
7. **Xuất báo cáo & Tra cứu lịch sử**:
   - Tra cứu trực tiếp lịch sử nạp gần nhất từ tài khoản the24h.vn với tên server chuẩn (7 Sao, 15 Sao...).
   - Xuất toàn bộ kết quả nạp ra file `.CSV` hoặc `.TXT` để lưu trữ hoặc đối soát đơn.
8. **Hỗ trợ cả chế độ API Partner chính thức**:
   - Có sẵn module kết nối API Partner (`partner_id`, `partner_key`, mã hóa MD5 signature) qua endpoint `https://the24h.vn/api/rechargews`.

---

## 🚀 HƯỚNG DẪN KHỞI ĐỘNG NHANH

### Cách 1: Chạy trực tiếp bằng 1 cú nhấp chuột (Khuyên dùng)
- Nhấp đúp chuột vào file: **`Chay_Tool_Nap_The24h.bat`**

### Cách 2: Chạy bằng lệnh trong terminal
```bash
python app.py
```
*(Hoặc dùng đường dẫn Python 3.12 vừa cài: `C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe app.py`)*

---

## 📖 HƯỚNG DẪN SỬ DỤNG

1. **Bước 1: Đăng nhập**
   - Nhập tài khoản và mật khẩu the24h.vn của bạn.
   - Nhập **Mật khẩu cấp 2 (MKC2)** nếu muốn tool tự động thanh toán đơn qua Quỹ VND.
   - Bấm **"ĐĂNG NHẬP THE24H"**. Khi kết nối thành công, số dư ví sẽ hiển thị ở góc trên bên phải.

2. **Bước 2: Chọn cấu hình game & gói nạp**
   - Chọn Game muốn nạp (ví dụ: *Ngọc Rồng*).
   - Chọn Máy chủ (ví dụ: *1 Sao*, *2 Sao*...).
   - Chọn Gói nạp (ví dụ: *10,000 đ*, *50,000 đ*...).

3. **Bước 3: Nhập danh sách tài khoản game**
   - **Cách A**: Nhập mỗi nick trên 1 dòng vào ô text:
     ```text
     accgame1
     accgame2
     accgame3
     ```
   - **Cách B**: Nhập theo file `.txt` có sẵn bằng nút **"📂 Nhập File .TXT"**.
   - **Cách C**: Tùy chỉnh server hoặc mệnh giá riêng cho từng acc:
     ```text
     accgame1|1|10000
     accgame2|2|20000
     accgame3|14|50000
     ```
   - Bấm nút **"📥 NẠP VÀO BẢNG DANH SÁCH"**.

4. **Bước 4: Bắt đầu nạp**
   - Đặt độ trễ (delay) giữa các đơn (mặc định 2.0 giây để an toàn).
   - Bấm nút xanh **"🚀 BẮT ĐẦU NẠP DANH SÁCH"**.
   - Tool sẽ lần lượt nạp, thanh toán và cập nhật trạng thái từng tài khoản.

5. **Bước 5: Xuất báo cáo**
   - Sau khi hoàn thành, bấm **"📊 Xuất Báo Cáo"** để lưu file CSV danh sách kết quả mã đơn hàng.

## 🔒 CAM KẾT BẢO MẬT & AN TOÀN TUYỆT ĐỐI (OPEN-SOURCE SAFE)

- **Không lưu trữ thông tin đăng nhập**: Tool hoàn toàn **KHÔNG** lưu tài khoản, mật khẩu hay Mật khẩu cấp 2 (MKC2) vào bất kỳ file nào trên máy tính.
- **Hoạt động hoàn toàn trên RAM**: Khi nhập thông tin và chạy tool, các giá trị chỉ nằm tạm thời trên bộ nhớ RAM. Khi bạn tắt ứng dụng, mọi dữ liệu đăng nhập sẽ tự động biến mất hoàn toàn.
- **100% An toàn khi Public lên GitHub**: Không có bất kỳ dữ liệu nhạy cảm hay file lưu trữ bí mật nào được tạo ra, người dùng có thể thoải mái fork, clone hoặc chia sẻ công khai mà không lo lộ lọt thông tin cá nhân.

---

## 📁 CẤU TRÚC FILE DỰ ÁN

- `app.py`: Giao diện chính CustomTkinter hiện đại, đa luồng, bảo mật RAM-only.
- `the24h_client.py`: Client backend tương tác web và API chính thức the24h.vn.
- `games_catalog.json`: Bảng dữ liệu tất cả game, server và giá gói nạp carot.
- `danh_sach_acc_mau.txt`: File danh sách tài khoản mẫu.
- `Chay_Tool_Nap_The24h.bat`: File khởi động nhanh 1-click.
