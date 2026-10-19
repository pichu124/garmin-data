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
  Muốn xem trên điện thoại ở mọi nơi: chạy trên VPS, xem mục [Chạy trên VPS](#chạy-trên-vps).
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
- **Strain**: thời gian ở mức Nhẹ + 5 vùng tim, "nguồn strain" (% tải theo mức),
  strain từng hoạt động, 30 ngày với dải strain tối ưu.
- **Chi tiết hoạt động** (bấm vào một hoạt động): vòng strain, thời lượng, calo,
  quãng đường, HR TB/max, Training Effect, nhịp tim trong lúc tập, vùng tim.
- **Sức khoẻ**: Health Monitor (HRV, RHR, nhịp thở, SpO2 so với ngưỡng của bạn —
  lệch theo hướng tốt vẫn tính là ổn), **Stress Monitor** (stress Garmin trong ngày
  tô theo mức nghỉ / thấp / vừa / cao + số giờ mỗi mức so với 30 ngày), chỉ số riêng của Garmin.
- **Xu hướng**, **Sức khoẻ**, **Nhật ký** ở thanh dưới.
- Bấm nhãn ngày ở trên cùng để mở **lịch tháng** (mỗi ngày tô màu theo hồi phục);
  phím ← → để chuyển ngày; mỗi biểu đồ có nút **Bảng** để xem số liệu dạng bảng.
- ⚙ **Cài đặt**: nhu cầu ngủ nền, nhịp tim tối đa, giờ muốn dậy.

## Dữ liệu nằm ở đâu

```
data/
  raw/<loại>/<ngày>.json     JSON gốc từ Garmin (giữ để tính lại không cần tải lại)
  raw/activities/<id>.json
  processed/summary.json     điểm mọi ngày (giao diện đọc file này)
  processed/days/<ngày>.json chuỗi nhịp tim / stress / giai đoạn ngủ trong ngày
  settings.json  journal.json
  auth.json                  băm mật khẩu web (chỉ có khi đã chạy `password`)
  backups/                   bản sao lưu settings + journal (lệnh `backup`)
```

`data/` đã nằm trong `.gitignore` — dữ liệu sức khoẻ không bao giờ bị commit.
Đổi công thức hoặc cài đặt ⇒ `python run.py build` tính lại từ raw trong vài giây.

## Chạy trên VPS

Để xem trên **điện thoại Android ở mọi nơi**: chạy app trên một VPS, Caddy lo HTTPS cho
một tên miền riêng, app đòi **mật khẩu web**. Ví dụ dưới dùng VPS Ubuntu 24.04 (Oracle Free
Tier, user `ubuntu`) đã có Caddy chạy một web khác (cổng 80/443 đã mở). garmin-data vẫn chỉ
nghe `127.0.0.1:8765`, không mở thêm cổng nào.

```
Điện thoại ──HTTPS──▶ Caddy :443 (garmin-cua-ban.duckdns.org) ──▶ 127.0.0.1:8765 (garmin-data)
```

Thay `garmin-cua-ban.duckdns.org` bằng tên miền của bạn, `<IP-VPS>` bằng IP công khai,
`$key` bằng file khoá SSH trong mọi lệnh dưới.

**1. Cài đặt**

```bash
sudo apt install -y python3-venv
sudo git clone https://github.com/pichu124/garmin-data.git /opt/garmin-data
sudo chown -R ubuntu:ubuntu /opt/garmin-data
cd /opt/garmin-data
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo mkdir -p /var/lib/garmin-data && sudo chown ubuntu:ubuntu /var/lib/garmin-data
```

**2. Đăng nhập Garmin, tải dữ liệu**

```bash
.venv/bin/python run.py login
.venv/bin/python run.py sync --data-dir /var/lib/garmin-data
```

Garmin có thể chặn đăng nhập từ IP của trung tâm dữ liệu. Nếu `login` báo lỗi, chạy
`python run.py login` trên Windows rồi chép token sang (PowerShell):

```powershell
ssh -i $key ubuntu@<IP-VPS> "mkdir -p ~/.garminconnect && chmod 700 ~/.garminconnect"
scp -i $key $HOME\.garminconnect\garmin_tokens.json ubuntu@<IP-VPS>:~/.garminconnect/
ssh -i $key ubuntu@<IP-VPS> "chmod 600 ~/.garminconnect/garmin_tokens.json"
```

**3. Mật khẩu web**

```bash
.venv/bin/python run.py password --data-dir /var/lib/garmin-data
```

Ít nhất 10 ký tự, đừng trùng mật khẩu Garmin. Mật khẩu lưu dạng băm PBKDF2 trong
`/var/lib/garmin-data/auth.json` (quyền 600). Đã khai tên miền mà chưa có mật khẩu thì
server **từ chối chạy**.

**4. Service systemd**

```bash
sudo tee /etc/systemd/system/garmin-data.service >/dev/null <<'UNIT'
[Unit]
Description=Garmin Health
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/garmin-data
Environment=GARMIN_ALLOWED_HOSTS=garmin-cua-ban.duckdns.org
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/garmin-data/.venv/bin/python run.py serve --data-dir /var/lib/garmin-data
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now garmin-data
journalctl -u garmin-data -n 5 --no-pager   # phải thấy "Nhận tên miền" và "Cần mật khẩu web"
```

`GARMIN_ALLOWED_HOSTS` là danh sách tên miền (cách nhau dấu phẩy, không kèm `https://`) mà
server chấp nhận trong Host. Tên miền khác vẫn bị chặn để chống DNS-rebinding.

**5. Tên miền + Caddy**

Trên [duckdns.org](https://www.duckdns.org), tạo thêm một subdomain (ví dụ `garmin-cua-ban`)
trỏ về IP của VPS. Rồi thêm một khối vào Caddyfile, giữ nguyên các khối đang có:

```bash
sudo tee -a /etc/caddy/Caddyfile >/dev/null <<'CADDY'

garmin-cua-ban.duckdns.org {
	encode gzip
	reverse_proxy 127.0.0.1:8765
}
CADDY
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

Caddy tự lấy chứng chỉ HTTPS cho tên mới. Mở `https://garmin-cua-ban.duckdns.org` trên máy
tính để kiểm tra: phải thấy trang đăng nhập.

**6. Trên điện thoại Android**

Chrome → `https://garmin-cua-ban.duckdns.org` → nhập mật khẩu web → menu **⋮** →
**Thêm vào màn hình chính** (hoặc **Cài đặt ứng dụng**). App mở toàn màn hình như app thường;
phiên đăng nhập giữ 90 ngày. Nút **Đăng xuất** nằm trong ⚙ Cài đặt.

**7. Đồng bộ + sao lưu tự động**

```bash
(crontab -l 2>/dev/null
 echo "15 9 * * * cd /opt/garmin-data && .venv/bin/python run.py sync --data-dir /var/lib/garmin-data >> /home/ubuntu/garmin-sync.log 2>&1"
 echo "30 9 * * * cd /opt/garmin-data && .venv/bin/python run.py backup --data-dir /var/lib/garmin-data >> /home/ubuntu/garmin-sync.log 2>&1") | crontab -
```

Lệnh này giữ nguyên các dòng cron đã có (ví dụ cron sao lưu của web khác). Giờ trong cron theo
giờ máy (Asia/Ho_Chi_Minh). Nút **↻ Đồng bộ** trên app vẫn dùng được bất cứ lúc nào.

`backup` ghi `garmin-backup-YYYY-MM-DD.zip` (settings.json + journal.json) vào
`/var/lib/garmin-data/backups/` và giữ 30 bản mới nhất. Số liệu Garmin không cần sao lưu vì
`sync --days 365` tải lại được, còn nhật ký và cài đặt chỉ có trên VPS. **Bản sao lưu vẫn
nằm trên VPS**, mà Oracle có thể tắt hoặc thu hồi máy rỗi hay vượt hạn mức Always Free
([hạn mức hiện tại](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
nên kiểm trong Console). Thỉnh thoảng kéo về Windows:

```powershell
mkdir -Force $HOME\Documents\garmin-backup
scp -i $key "ubuntu@<IP-VPS>:/var/lib/garmin-data/backups/*.zip" $HOME\Documents\garmin-backup\
```

Khôi phục (máy mới thì `scp` file zip lên trước): giải nén vào thư mục dữ liệu rồi tính lại.

```bash
cd /opt/garmin-data
.venv/bin/python -m zipfile -e /var/lib/garmin-data/backups/garmin-backup-2026-10-19.zip /var/lib/garmin-data
.venv/bin/python run.py build --data-dir /var/lib/garmin-data
```

**Cập nhật mã**

```bash
cd /opt/garmin-data && git pull && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py build --data-dir /var/lib/garmin-data
sudo systemctl restart garmin-data
```

**Lưu ý**

- Đổi mật khẩu: chạy lại `run.py password`, rồi `sudo systemctl restart garmin-data`. Mọi
  phiên cũ (kể cả trên điện thoại bị mất) bị đăng xuất.
- Sai mật khẩu 10 lần trong 10 phút thì đăng nhập bị khoá 10 phút. Phiên đang mở vẫn dùng được.
- Trên VPS không dùng `--lan` và không mở cổng 8765 trên tường lửa.
- Không muốn mở ra internet: bỏ dòng `Environment=GARMIN_ALLOWED_HOSTS` và bước 5, rồi xem
  qua đường hầm SSH từ máy tính Windows (giữ cửa sổ mở, vào `http://127.0.0.1:8765`):

  ```powershell
  ssh -i $key -L 8765:127.0.0.1:8765 ubuntu@<IP-VPS>
  ```

## Cách tính (tóm tắt)

**Baseline cá nhân**: mỗi chỉ số so với 30 ngày *trước* hôm đó (không gồm hôm
nay). Cần ≥ 4 ngày mới có điểm (giống giai đoạn "calibrating" của WHOOP).

**Recovery** = `100 · Φ(0.55·z(ln HRV) + 0.20·z(−RHR) + 0.20·z(hiệu suất ngủ) − phạt + 0.2)`
— Φ là phân phối chuẩn tích luỹ; phạt khi nhịp thở tăng > 1 độ lệch hoặc
SpO2 giảm > 1 độ lệch (dấu hiệu ốm). Ngày "bình thường" ≈ 58%. Không có HRV
(đồng hồ đời cũ) ⇒ tự chia lại trọng số cho RHR + giấc ngủ.

**Strain**: mỗi mẫu nhịp tim → `%HRR = (HR − RHR)/(HRmax − RHR)` → TRIMP
Banister `x·0,64·e^(1,92x)` mỗi phút (nữ: 0,86 và 1,67), bỏ qua dưới 20% HRR
(ngồi yên) → `Strain = 21·(1 − e^(−tải/176))`. Hiệu chỉnh: ngày chỉ đi lại
≈ 3–6, chạy 60 phút vừa sức ≈ 12–14, 2,5 giờ cường độ cao ≈ 18–19.
RHR trong %HRR = trung bình RHR 30 ngày trước hôm đó (chưa đủ 4 ngày thì dùng
RHR hôm đó) — một đêm RHR thấp bất thường không thổi phồng strain cả ngày.
HRmax lấy theo thứ tự: cài đặt → vùng tim trên Garmin → 208 − 0,7·tuổi → dữ liệu.
Vùng 1–5 = 50–60 / 60–70 / 70–80 / 80–90 / 90–100% HRR. **Nhẹ 20–50% HRR**
(đi lại, việc nhà) dưới Vùng 1 nhưng vẫn có tải, nên ngày chỉ đi lại có strain
dù vùng 1–5 đều 0 phút; `light_min` là số phút nhẹ, `load_pct` là % tải theo
[nhẹ, Vùng 1…5].

**Stress theo mức** (`stress_min`): phút ở 0–25 nghỉ / 26–50 thấp / 51–75 vừa /
76–100 cao (thang Garmin), bỏ mẫu -1/-2 (không đo/đang vận động) và khoảng mất tín hiệu.

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
python -m pytest -q          # 92 test, ~1–2 phút, không cần mạng/Garmin
```

Python thuần (không pandas/numpy); web là HTML/CSS/JS thuần, biểu đồ SVG tự vẽ
(chạy offline, không CDN). Server dùng `http.server` của thư viện chuẩn, mặc
định chỉ nghe `127.0.0.1`; POST bắt buộc JSON + cùng origin. Host là tên miền chỉ được nhận
khi khai trong `GARMIN_ALLOWED_HOSTS`, và khi đó bắt buộc có mật khẩu web.

| File | Vai trò |
|---|---|
| `garmin_health/sync.py` | đăng nhập + tải từ Garmin Connect (`garminconnect` ≥ 0.3) |
| `garmin_health/normalize.py` | JSON Garmin → bản ghi gọn, chịu thiếu khoá |
| `garmin_health/strain.py` · `sleep_score.py` · `recovery.py` | công thức điểm (hàm thuần) |
| `garmin_health/build.py` | raw → `processed/*.json` |
| `garmin_health/insights.py` | nhật ký, tổng kết tuần |
| `garmin_health/demo.py` | sinh dữ liệu mẫu đúng định dạng Garmin |
| `garmin_health/server.py` | web server + API đồng bộ / nhật ký / cài đặt / đăng nhập |
| `garmin_health/auth.py` | mật khẩu web (PBKDF2) + cookie phiên ký HMAC, khoá khi sai nhiều lần |
| `garmin_health/backup.py` | sao lưu settings.json + journal.json thành zip theo ngày |
| `web/` | giao diện: `app.js` khung + router, `core.js` tiện ích chung, `view-*.js` từng màn hình, `charts.js` biểu đồ SVG, `login.html` + `login.js` trang đăng nhập |
| `scripts/shots.py` | chụp mọi màn hình 390px + 1280px (cần `pip install playwright`, dùng Chrome/Edge có sẵn) |
