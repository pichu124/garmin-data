# CLAUDE.md — garmin-data

App tải dữ liệu Garmin Connect và phân tích kiểu WHOOP (Recovery · Strain ·
Sleep). Người dùng chạy trên Windows, giao diện + README bằng tiếng Việt, số
kiểu EN (`1,234.5`). Xem README.md cho cách dùng và công thức.

## Lệnh
- `python -m pytest -q` — toàn bộ test (không cần mạng). Thêm tính năng ⇒ thêm test.
- `python run.py demo --no-serve --data-dir <tmp>` — sinh dữ liệu mẫu + build để soát giao diện.
- `python run.py serve --data-dir <tmp>` rồi chụp màn hình (Playwright) ở 390px và 1280px.

## Bất biến
- **Dữ liệu sức khoẻ + token không bao giờ vào git** (`data/`, `data-demo/`, `.env` trong .gitignore).
- Raw Garmin lưu NGUYÊN VĂN; mọi diễn giải nằm ở `normalize.py`. Đổi công thức ⇒ `build` lại, không tải lại.
- Thời gian: epoch ms GMT trong normalize; web dùng "phút kể từ nửa đêm địa phương" (âm = tối hôm trước).
- Baseline = 30 ngày TRƯỚC ngày đang xét (không gồm hôm nay), cần ≥4 giá trị.
- Công thức điểm là hàm thuần trong `strain.py` / `sleep_score.py` / `recovery.py`; hằng số hiệu chỉnh
  có test neo (`tests/test_scores.py`) — đổi hằng số phải cập nhật cả README mục "Cách tính".
- `garminconnect` ≥ 0.3 (không còn garth). Lỗi thư viện phân loại theo TÊN lớp trong `sync.call`.
- Web: không CDN, không thư viện; nhãn từ dữ liệu ngoài chèn bằng `textContent`.
  Màu đã kiểm bằng validator dataviz trên nền tối — đổi màu phải kiểm lại.
- Server chỉ nghe 127.0.0.1 trừ `--lan`; POST cần `Content-Type: application/json` + Origin trùng Host.
  Host là tên miền chỉ nhận khi có trong `GARMIN_ALLOWED_HOSTS` (chạy sau Caddy trên VPS); khi đó bắt buộc
  có mật khẩu web (`auth.json`, `run.py password`), thiếu thì `serve` từ chối chạy. Có mật khẩu ⇒ `/data/*`,
  `/api/*` cần cookie phiên; file tĩnh trong `web/` công khai (không chứa dữ liệu).
- `explain.py` chỉ diễn đạt số đã tính (không tính điểm mới); build ghi vào `days/<ngày>.json` → `explain`.
- Connector `/mcp` (mcp.py) CHỈ ĐỌC, token riêng (mcp.json chỉ giữ SHA-256), không dùng cookie web;
  công cụ mới phải `readOnlyHint` + có test; token trong đường dẫn phải bị che khi ghi log.
