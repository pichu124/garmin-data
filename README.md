# Garmin Health — phân tích dữ liệu Garmin kiểu WHOOP

Tải dữ liệu sức khoẻ từ **Garmin Connect** về máy, tính 3 chỉ số cốt lõi
theo cách của **WHOOP**, rồi hiển thị bằng giao diện tối giống app WHOOP
(chạy trên trình duyệt máy tính hoặc điện thoại cùng Wi-Fi):

| WHOOP | Ở đây | Tính từ dữ liệu Garmin |
|---|---|---|
| **Recovery** 0–100% (xanh/vàng/đỏ) | Hồi phục | HRV đêm qua, nhịp tim nghỉ, hiệu suất ngủ, nhịp thở, SpO2 — so với baseline 30 ngày **của chính bạn** |
| **Strain** 0–21 | Strain | Nhịp tim cả ngày (mỗi 2 phút) theo % dự trữ nhịp tim → tải tim mạch (TRIMP) → thang logarit 0–21 |
| **Sleep Performance** % | Hiệu suất ngủ | Giờ ngủ so với **nhu cầu ngủ** (nền + strain hôm qua + nợ ngủ − ngủ trưa), hiệu quả, độ đều |
| Strain Coach | Strain mục tiêu | Vùng strain tối ưu theo recovery sáng nay |
| Sleep Planner | Kế hoạch ngủ | Giờ nên lên giường để đạt 100% / 85% / 70% |
| Health Monitor | Sức khoẻ | HRV, RHR, nhịp thở, SpO2 có trong ngưỡng bình thường của bạn không |
| Journal | Nhật ký | Trả lời "hôm qua có uống rượu / ăn muộn…" → app đo thói quen nào làm hồi phục tăng/giảm |
| Trends / Weekly | Xu hướng | 7 ngày · 30 ngày · 3 tháng · 6 tháng, tổng kết tuần, strain hôm trước → hồi phục hôm sau |

Ngoài ra vẫn hiện các chỉ số riêng của Garmin (Body Battery, Training
Readiness, Sleep Score, Stress, VO2 max, HRV Status) để đối chiếu.

> ⚠️ WHOOP không công bố công thức. Điểm ở đây là **ước lượng theo cùng nguyên
> lý** (mô tả ở cuối file), không phải số của WHOOP, và **không phải tư vấn y tế**.

## Cài đặt (Windows, một lần)

Cần **Python 3.12 trở lên** (thư viện `garminconnect` yêu cầu).

```powershell
git clone https://github.com/pichu124/garmin-data.git
cd garmin-data
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Dùng hằng ngày

```powershell
python run.py login        # LẦN ĐẦU: email + mật khẩu Garmin (+ mã MFA nếu có)
python run.py sync         # tải dữ liệu mới (lần đầu: 90 ngày, ~5–8 phút) + tính điểm
python run.py serve --open # mở http://127.0.0.1:8765
```

- Mật khẩu **không được lưu**. Đăng nhập xong, token nằm ở
  `~/.garminconnect/garmin_tokens.json` và tự gia hạn — các lần sau
  (kể cả nút **↻ Đồng bộ** trên giao diện) không cần mật khẩu nữa.
  Token có quyền vào tài khoản Garmin của bạn: giữ như mật khẩu.
- Muốn lấy nhiều lịch sử hơn: `python run.py sync --days 365`.
- Xem trên **điện thoại** (cùng Wi-Fi): `python run.py serve --lan` rồi mở địa chỉ
  in ra. Trên iPhone/Android có thể "Thêm vào màn hình chính" để mở như app.
  Chế độ này cho mọi máy trong mạng LAN xem được dữ liệu — chỉ dùng ở nhà.
- Tự đồng bộ mỗi sáng: tạo task trong **Task Scheduler** chạy
  `C:\đường\dẫn\garmin-data\.venv\Scripts\python.exe run.py sync` lúc ~9:00
  (sau khi đồng hồ đã đồng bộ giấc ngủ lên Garmin Connect).
- Kiểm tra dữ liệu đang có: `python run.py doctor`.

### Chưa muốn đăng nhập? Xem thử với dữ liệu mẫu

```powershell
python run.py demo --open
```

Sinh 150 ngày dữ liệu giả **đúng định dạng JSON của Garmin** vào `data-demo/`
(không đụng dữ liệu thật) và mở giao diện.

## Giao diện

- **Tổng quan**: 3 vòng Ngủ · Hồi phục · Strain (bấm vào để xem chi tiết),
  huấn luyện viên (mức hồi phục + strain mục tiêu), hoạt động trong ngày,
  chỉ số chính so với trung bình 30 ngày, nhịp tim cả ngày.
- **Ngủ**: nhu cầu ngủ chi tiết, giai đoạn ngủ, hypnogram, hiệu quả / độ đều,
  kế hoạch ngủ đêm nay, giờ ngủ vs nhu cầu 30 ngày.
- **Hồi phục**: "vì sao hôm nay như vậy" — mỗi chỉ số cộng/trừ bao nhiêu điểm;
  HRV / nhịp tim nghỉ / nhịp thở với dải ngưỡng bình thường.
- **Strain**: thời gian trong 5 vùng tim, strain từng hoạt động, 30 ngày với vùng tối ưu.
- **Xu hướng**, **Sức khoẻ**, **Nhật ký** ở thanh dưới.
- Phím ← → để chuyển ngày; mỗi biểu đồ có nút **Bảng** để xem số liệu dạng bảng.
- ⚙ **Cài đặt**: nhu cầu ngủ nền, nhịp tim tối đa, giờ muốn dậy.

## Dữ liệu nằm ở đâu

```
data/
  raw/<loại>/<ngày>.json     JSON gốc từ Garmin (giữ để tính lại không cần tải lại)
  raw/activities/<id>.json
  processed/summary.json     điểm mọi ngày (giao diện đọc file này)
  processed/days/<ngày>.json chuỗi nhịp tim / stress / giai đoạn ngủ trong ngày
  settings.json  journal.json
```

`data/` đã nằm trong `.gitignore` — dữ liệu sức khoẻ không bao giờ bị commit.
Đổi công thức hoặc cài đặt ⇒ `python run.py build` tính lại từ raw trong vài giây.

## Cách tính (tóm tắt)

**Baseline cá nhân**: mỗi chỉ số so với 30 ngày *trước* hôm đó (không gồm hôm
nay). Cần ≥ 4 ngày mới có điểm (giống giai đoạn "calibrating" của WHOOP).

**Recovery** = `100 · Φ(0.55·z(ln HRV) + 0.20·z(−RHR) + 0.20·z(hiệu suất ngủ) − phạt + 0.2)`
— Φ là phân phối chuẩn tích luỹ; phạt khi nhịp thở tăng > 1 độ lệch hoặc
SpO2 giảm > 1 độ lệch (dấu hiệu ốm). Ngày "bình thường" ≈ 58%. Không có HRV
(đồng hồ đời cũ) ⇒ tự chia lại trọng số cho RHR + giấc ngủ.

**Strain**: mỗi mẫu nhịp tim → `%HRR = (HR − RHR)/(HRmax − RHR)` → TRIMP
Banister `x·0,64·e^(1,92x)` mỗi phút (nữ: 0,86 và 1,67), bỏ qua dưới 20% HRR
(sinh hoạt nhẹ) → `Strain = 21·(1 − e^(−tải/176))`. Hiệu chỉnh: ngày chỉ đi lại
≈ 3–6, chạy 60 phút vừa sức ≈ 12–14, 2,5 giờ cường độ cao ≈ 18–19.
HRmax lấy theo thứ tự: cài đặt → vùng tim trên Garmin → 208 − 0,7·tuổi → dữ liệu.

**Nhu cầu ngủ** = nền (mặc định 7h45) + tối đa 1h theo strain hôm qua
(từ strain 8 trở lên) + nợ ngủ (50% / 25% / 12,5% phần thiếu của 3 đêm trước,
tối đa 1h30) − ngủ trưa.
**Hiệu suất ngủ** = 70% đủ giờ + 15% hiệu quả (ngủ/nằm) + 15% độ đều giờ giấc 4 đêm.

**Strain mục tiêu** = `4 + 0,14·recovery ± 1,5` (xanh ≈ 14–18, đỏ < 10).

**Nhật ký**: so recovery trung bình của các sáng trả lời *Có* với *Không*
(cần ≥ 3 mỗi bên); ★ khi |t| ≥ 2 (kiểm định Welch). Đây là tương quan, không phải nhân quả.

## Phát triển

```powershell
pip install -r requirements.txt
python -m pytest -q          # 46 test, ~12 giây, không cần mạng/Garmin
```

Python thuần (không pandas/numpy); web là HTML/CSS/JS thuần, biểu đồ SVG tự vẽ
(chạy offline, không CDN). Server dùng `http.server` của thư viện chuẩn, mặc
định chỉ nghe `127.0.0.1`; POST bắt buộc JSON + cùng origin.

| File | Vai trò |
|---|---|
| `garmin_health/sync.py` | đăng nhập + tải từ Garmin Connect (`garminconnect` ≥ 0.3) |
| `garmin_health/normalize.py` | JSON Garmin → bản ghi gọn, chịu thiếu khoá |
| `garmin_health/strain.py` · `sleep_score.py` · `recovery.py` | công thức điểm (hàm thuần) |
| `garmin_health/build.py` | raw → `processed/*.json` |
| `garmin_health/insights.py` | nhật ký, tổng kết tuần |
| `garmin_health/demo.py` | sinh dữ liệu mẫu đúng định dạng Garmin |
| `garmin_health/server.py` | web server + API đồng bộ / nhật ký / cài đặt |
| `web/` | giao diện |
