# 📺 IPTV Auto-Updater 

Hệ thống tự động thu thập và sắp xếp danh sách kênh IPTV Việt Nam chất lượng cao.
Playlist được cập nhật tự động mỗi 6giờ một lần thông qua GitHub Actions.

---

## 🔗 Link Playlist Tự Động 

Bạn có thể copy liên kết này để thêm trực tiếp vào các ứng dụng xem IPTV (như Tivimate, OTT Navigator, Perfect Player, VLC...):

```
https://raw.githubusercontent.com/MFT-T/diwi-iptv/main/http-iptv.m3u
```

---

## 🔗 Link Playlist Cố Định, Chỉ Cập Nhật Tự Động EPG

```
https://raw.githubusercontent.com/MFT-T/diwi-iptv/refs/heads/main/my_list.m3u
```

---
## 🛠 Cơ Chế Hoạt Động Của Hệ Thống

- **Bộ lọc thông minh (Deduplication & Quality Max Selection):** Nếu một kênh xuất hiện ở nhiều nguồn hoặc có nhiều luồng dữ liệu, hệ thống tự động chấm điểm kỹ thuật (Tier phân giải từ 8K/4K/FHD/HD/SD kết hợp với Bitrate) để chỉ giữ lại duy nhất luồng có chất lượng tốt nhất, dedup đồng thời theo cả tên kênh lẫn URL xuyên suốt các nguồn.

- **Chuẩn hóa tvg-id theo chuẩn vnepg:** Toàn bộ tvg-id thu thập được sẽ được chuẩn hóa (viết liền, không dấu gạch ngang, tra qua bảng alias) để khớp chính xác với lịch phát sóng, đồng thời gắn cố định URL EPG (`url-tvg` / `x-tvg-url`) ngay trong header của file playlist.

- **Lọc nhiễu (Noise Filtering):** Tự động loại bỏ các kênh rác, kênh trùng lặp không rõ nguồn gốc hoặc không xác định được nhóm (dựa theo danh sách từ khóa và tiền tố tvg-id/tên kênh đã biết là nhiễu).

- **Phân nhóm & Sắp xếp Khoa học:**
  - **VTV:** Sắp xếp cố định từ VTV1 đến VTV10 và các kênh khu vực (Tây Nam Bộ, Tây Nguyên).
  - **HTV / HTVC:** Sắp xếp chuẩn theo hệ thống kênh HTV và HTVC.
  - **VTVCab / SCTV:** Sắp xếp theo thứ tự.
  - **Địa phương:** Gom gọn vào 1 nhóm duy nhất, tự động sắp xếp thứ tự A-Z theo tên các tỉnh/thành đầy đủ.
  - **Quốc Phòng:** Tách riêng ANTV và QPVN thành một nhóm chuyên biệt, không bị lẫn vào nhóm địa phương.

---

## 📋 Nguồn Dữ Liệu Thu Thập

Hệ thống thu thập dữ liệu từ danh sách nguồn (`SOURCES`) được khai báo trong `update_iptv.py`.

| Vai trò | Nguồn |
|---|---|
| Nguồn đang hoạt động | Dropbox mirror playlist (`coban66.m3u`) |
| EPG (Lịch phát sóng) | `epg.io.vn/epgu.xml` — hệ thống sẽ tải nguồn về và tự động chỉnh lại cho khớp thời gian, sau đó xuất ra đường dẫn riêng và gắn trực tiếp vào playlist  |

> Có thể tự thêm nguồn mới bằng cách bổ sung URL playlist `.m3u`/`.m3u8` vào danh sách `SOURCES` trong file `update_iptv.py`.

---



## ⚖️ Tuyên Bố Miễn Trừ Trách Nhiệm

Dự án này là một công cụ mã nguồn mở được viết ra nhằm mục đích **học tập, nghiên cứu** kỹ thuật xử lý luồng dữ liệu (data parsing/cleansing) và tự động hóa với Python.

Chúng tôi **không sở hữu, không lưu trữ và không trực tiếp phát sóng** bất kỳ luồng truyền hình nào. Tất cả các liên kết stream (`.m3u8`) đều được thu thập tự động từ các nguồn công khai miễn phí trên Internet.

Bất kỳ vấn đề nào liên quan đến bản quyền luồng phát, vui lòng liên hệ trực tiếp với các nhà cung cấp nguồn gốc được liệt kê trong mục dữ liệu.