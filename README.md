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
| Daily Outlook / Insights | Hôm nay nên tập thế nào? + Giải thích | Một kết luận mỗi sáng (tập nặng / vừa / nghỉ) kèm vì sao, số phút cần tập, giờ đi ngủ; mỗi chỉ số có câu giải thích và lời khuyên — sinh từ chính số liệu (không cần AI) |
| WHOOP Coach | Trò chuyện với Claude | Hỏi đáp bằng gói Claude Pro/Max của bạn qua connector chỉ đọc (mục [Trò chuyện với Claude](#trò-chuyện-với-claude-connector)) |

Ngoài ra vẫn hiện các chỉ số riêng của Garmin (Body Battery, Training
Readiness, Sleep Score, Stress, VO2 max, HRV Status) để đối chiếu — ở tab Sức khoẻ,
không ở trang chủ.

**Triết lý:** Garmin có rất nhiều chỉ số nhưng không xếp chúng quanh một vòng lặp đơn
giản. App này xếp mọi thứ quanh đúng 3 trụ **Hồi phục → Strain → Ngủ**, hiệu chỉnh theo
baseline của chính bạn, và gộp thành **một câu trả lời mỗi sáng: hôm nay nên tập nặng
tới đâu?** — "Garmin là đồng hồ thi đấu, app này là huấn luyện viên của cơ thể".

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
- Muốn lấy nhiều lịch sử hơn: `python run.py sync --start 2023-01-01` (chỉ tải ngày còn thiếu,
  ~3–5 giây mỗi ngày; Garmin giới hạn tốc độ thì dừng giữa chừng, chạy lại sẽ tải tiếp).
- Cập nhật số liệu trong ngày: `python run.py sync --quick` chỉ tải phần còn thay đổi (5–10 lượt
  gọi thay vì ~31) — hợp để chạy định kỳ 30 phút/lần:
  - mọi lượt: tổng ngày (bước chân, calo, Body Battery), nhịp tim, stress, giấc ngủ (vì giấc trưa
    được trừ vào nhu cầu ngủ đêm nay) + hoạt động;
  - HRV đêm qua và Training Readiness buổi sáng: tới khi đồng hồ đã đẩy lên (sau đó không đổi);
  - cả ngày hôm qua, tới khi lượt đầy đủ trong ngày chạy xong (không sót 23:30–24:00);
  - không có VO2max (chỉ đổi sau buổi chạy/đi bộ đủ điều kiện) và hồ sơ — lượt đầy đủ sáng hôm sau lấy.

  Garmin trả dữ liệu **theo cả ngày** (mọi điểm của ngày tính tới lúc hỏi) và mỗi ngày × loại là
  một file bị ghi đè, nên lượt 10:00 tự chứa mọi điểm sau lượt 9:30 — không sót, không trùng; một
  lượt lỗi mạng thì lượt sau bù. Đừng chạy dày hơn 30 phút: Garmin không có API công khai, gọi quá
  nhiều sẽ bị trả lỗi 429 hoặc chặn tạm thời.
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

- **Tổng quan** — đọc từ trên xuống theo vòng lặp trong ngày, câu trả lời trước, số liệu sau:
  1. **Hôm nay nên tập thế nào?** Vòng Hồi phục + một kết luận theo vùng — *Tập nặng được*
     (xanh) · *Tập vừa sức* (vàng) · *Nghỉ ngơi chủ động* (đỏ) — trên thang Nhẹ · Vừa · Nặng,
     kèm **Vì sao**: các yếu tố cộng/trừ ≥3 điểm (HRV, nhịp tim nghỉ, giấc ngủ…) và thói
     quen trong nhật ký hôm qua.
  2. **Tải tập hôm nay**: strain so với vùng tối ưu + còn bao nhiêu phút Vùng 2 / Vùng 3
     để vào vùng (ngày đỏ chỉ gợi ý vận động nhẹ).
  3. **Ngủ đêm nay**: đêm qua ngủ bao nhiêu / cần bao nhiêu, giờ lên giường (đạt 85% và
     100% nhu cầu), nợ ngủ.
  4. **Sức khoẻ** gói thành một dòng (x/4 chỉ số trong ngưỡng; lệch thì hiện cảnh báo),
     rồi hoạt động, chỉ số chính so với 30 ngày, nhịp tim cả ngày.

  Bấm vòng/thẻ để sang tab chi tiết; các tab xếp theo vòng lặp: Hồi phục → Strain → Ngủ.
- **Giải thích & lời khuyên** ở đầu các trang Hồi phục, Ngủ, Strain, Sức khoẻ: câu chữ
  sinh theo quy tắc từ đúng các số đang hiển thị (`explain.py`), không gửi dữ liệu đi đâu.
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
- Mỗi lần mở lại app (và mỗi 5 phút khi đang xem) app hỏi máy chủ có lượt đồng bộ mới không — có thì
  tự cập nhật số; ở nền ≥ 30 phút thì tải lại cả trang (nhận giao diện mới nếu máy chủ vừa cập nhật).
  Số chỉ mới khi đồng hồ đã đẩy dữ liệu lên Garmin qua app Garmin Connect trên điện thoại.

## Dữ liệu nằm ở đâu

```
data/
  raw/<loại>/<ngày>.json     JSON gốc từ Garmin (giữ để tính lại không cần tải lại)
  raw/activities/<id>.json
  raw/activity_details/<id>.json  nhịp tim theo giây của buổi tập — chỉ cho ngày cũ (xem dưới)
  processed/summary.json     điểm mọi ngày (giao diện đọc file này)
  processed/days/<ngày>.json chuỗi nhịp tim / stress / giai đoạn ngủ trong ngày
  settings.json  journal.json
  auth.json                  băm mật khẩu web (chỉ có khi đã chạy `password`)
  backups/                   bản sao lưu (lệnh `backup`)
  mcp.json                   băm token connector Claude (chỉ có khi đã chạy `mcp-token`)
```

`data/` đã nằm trong `.gitignore` — dữ liệu sức khoẻ không bao giờ bị commit.

**Garmin chỉ giữ nhịp tim và stress theo phút khoảng 4–5 tháng** (giấc ngủ, HRV, tổng ngày và
buổi tập thì giữ lâu). Vì vậy `raw/heart_rates` và `raw/stress` của các ngày cũ hơn **chỉ còn trên
máy này** — lệnh `backup` gói kèm hai thư mục đó. Ngày Garmin đã xoá nhịp tim cả ngày thì lượt
đồng bộ đầy đủ tải nhịp tim chi tiết của từng buổi tập (một lần mỗi buổi) để vẫn tính được strain.
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
(crontab -l 2>/dev/null | grep -v "garmin-data"
 echo "15 9 * * * cd /opt/garmin-data && flock -n /tmp/garmin-sync.lock .venv/bin/python run.py sync --data-dir /var/lib/garmin-data >> /home/ubuntu/garmin-sync.log 2>&1"
 echo "*/30 6-23 * * * cd /opt/garmin-data && flock -n /tmp/garmin-sync.lock .venv/bin/python run.py sync --quick --data-dir /var/lib/garmin-data >> /home/ubuntu/garmin-sync.log 2>&1"
 echo "30 9 * * * cd /opt/garmin-data && .venv/bin/python run.py backup --data-dir /var/lib/garmin-data >> /home/ubuntu/garmin-sync.log 2>&1") | crontab -
```

- 9:15: đồng bộ đầy đủ (giấc ngủ, HRV đêm qua; tải lại 3 ngày gần nhất, ~31 lượt gọi).
- Mỗi 30 phút từ 6:00 đến 23:30: `sync --quick` (xem mục Dùng hằng ngày) — 5–10 lượt gọi, cả ngày
  ~200 lượt. Giấc ngủ đêm qua lên app ngay ở lượt đầu tiên sau khi đồng hồ đồng bộ, không phải
  đợi 9:15. Đồng hồ cũng chỉ đẩy số liệu lên Garmin khi điện thoại đồng bộ, nên gọi dày hơn không
  thấy số mới hơn mà dễ bị Garmin chặn.
- `flock -n`: lượt nào đang chạy thì lượt sau bỏ qua, không chạy chồng nhau.

Lệnh này thay các dòng garmin-data cũ và giữ nguyên dòng cron khác (ví dụ cron sao lưu của
web khác). Giờ trong cron theo giờ máy (Asia/Ho_Chi_Minh). Nút **↻ Đồng bộ** trên app vẫn dùng
được bất cứ lúc nào.

**Tải toàn bộ lịch sử** (lần đầu chỉ tải 90 ngày): chạy nền để thoát SSH không bị ngắt, dùng
chung khoá với cron:

```bash
cd /opt/garmin-data
nohup flock /tmp/garmin-sync.lock .venv/bin/python run.py sync --start 2023-01-01 \
  --data-dir /var/lib/garmin-data > ~/garmin-backfill.log 2>&1 &
ls /var/lib/garmin-data/raw/summary | wc -l   # số ngày đã có — chạy lại để xem tiến độ
```

Chọn `--start` gần ngày bắt đầu đeo Garmin: ngày chưa có dữ liệu vẫn tốn 7 lượt gọi và hiện
thành ngày trống. Ngày cũ hơn ~4–5 tháng không còn nhịp tim/stress theo phút trên Garmin: giấc ngủ,
HRV, hồi phục vẫn đủ, strain chỉ tính từ buổi tập, không có stress. Mỗi ngày ~3–5 giây (1 năm ≈ 20–30 phút). Garmin giới hạn tốc độ thì lệnh
dừng (`~/garmin-backfill.log` ghi "giới hạn tốc độ"), dữ liệu đã tải vẫn giữ — đợi ~1 giờ rồi chạy
lại đúng lệnh trên để tải tiếp.

`backup` ghi `garmin-backup-YYYY-MM-DD.zip` vào `/var/lib/garmin-data/backups/` và giữ 30 bản
mới nhất. Zip gồm phần **không tải lại được**: settings.json, journal.json và `raw/heart_rates`,
`raw/stress` (Garmin xoá bản theo phút sau ~4–5 tháng). Phần còn lại `sync --start` tải lại được.
**Bản sao lưu vẫn nằm trên VPS**, mà Oracle có thể tắt hoặc thu hồi máy rỗi hay vượt hạn mức Always Free
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

## Trò chuyện với Claude (connector)

Hỏi đáp về số liệu của bạn kiểu WHOOP Coach, bằng **gói Claude Pro/Max có sẵn**, không tốn
tiền API. App mở một connector MCP **chỉ đọc** ở `/mcp`; trong app Claude, Claude tự gọi vào
để lấy số rồi trả lời. Máy chủ của Anthropic phải gọi tới được app, nên cần làm xong mục
[Chạy trên VPS](#chạy-trên-vps) (có HTTPS) trước.

**1. Tạo token trên VPS**

```bash
cd /opt/garmin-data
.venv/bin/python run.py mcp-token --data-dir /var/lib/garmin-data
sudo systemctl restart garmin-data
```

Lệnh in token **một lần duy nhất**. Ai có token đọc được toàn bộ dữ liệu sức khoẻ, nên giữ như
mật khẩu. Chạy lại lệnh để đổi token (token cũ hết hiệu lực); `--revoke` để tắt connector.
Kiểm tra nhanh, phải thấy danh sách công cụ:

```bash
curl -s https://garmin-cua-ban.duckdns.org/mcp -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 300
```

**2. Thêm connector** trên máy tính (claude.ai hoặc Claude Desktop): **Customize → Connectors →
+ Add → Add custom connector**.

- Name: `Garmin Health`
- URL: `https://garmin-cua-ban.duckdns.org/mcp`
- Đăng nhập: **No sign in**
- **Request headers**: tên `Authorization`, giá trị `Bearer <token>`

Không thấy mục Request headers thì dùng URL `https://garmin-cua-ban.duckdns.org/mcp/<token>`
(server che token khi ghi log).

**3. Tạo Project "Garmin Coach"** (nên làm): **Projects → New project**, bật connector
Garmin Health cho project, rồi dán vào **Instructions**:

```
Bạn là huấn luyện viên sức khoẻ của tôi, theo kiểu WHOOP Coach. Dữ liệu Garmin của tôi
nằm trong connector Garmin Health.
- Trước khi nói về cơ thể, giấc ngủ, tập luyện: gọi công cụ để lấy số thật (get_day,
  get_days, get_trends, get_journal_insights). Không đoán số.
- Trích ngày và con số cụ thể; so với mức thường ngày của chính tôi.
- Lời khuyên làm được ngay: strain mục tiêu, số phút tập, giờ đi ngủ.
- Ngắn gọn, tiếng Việt, số kiểu 1,234.5.
- Không chẩn đoán bệnh; dấu hiệu bất thường kéo dài thì khuyên đi khám.
```

**4. Trên Android**: connector gắn với tài khoản Claude, nên mở app Claude, vào project
Garmin Coach và hỏi. Anthropic ghi việc *thêm* connector trên điện thoại còn là bản thử nghiệm;
nếu app chưa thấy connector, cập nhật app hoặc mở claude.ai bằng trình duyệt điện thoại.

**Hỏi gì?** "Nhận định sáng nay", "Vì sao tuần này hồi phục thấp?", "So giấc ngủ tháng 9 với
tháng 10", "Rượu bia ảnh hưởng tôi thế nào?", "Hôm nay nên chạy bao lâu?". Connector cũng có
sẵn 3 mẫu câu: *Nhận định sáng nay*, *Tổng kết tuần*, *Thói quen ảnh hưởng thế nào*.

| Công cụ | Claude lấy được gì |
|---|---|
| `get_day` | Mọi chỉ số một ngày + phần giải thích của app; ngày mới nhất có kế hoạch ngủ đêm nay |
| `get_days` | Bảng gọn mỗi ngày một dòng, tối đa 180 ngày |
| `get_trends` | Trung bình N ngày so với N ngày trước + theo tuần |
| `get_journal_insights` | Thói quen nào đi kèm hồi phục cao/thấp (Welch) |
| `get_activities` | Các buổi tập: thời lượng, strain, nhịp tim, vùng tim |
| `get_methodology` | Mục "Cách tính" ở dưới + HRmax, nhu cầu ngủ nền đang dùng |

Connector **chỉ đọc**: không sửa cài đặt/nhật ký, không đồng bộ Garmin, không thấy mật khẩu
hay token Garmin. Số liệu Claude đọc sẽ nằm trong cuộc trò chuyện Claude của bạn.

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
Ngày Garmin đã xoá nhịp tim cả ngày (cũ hơn ~4–5 tháng): cùng công thức trên nhịp tim theo giây
của các buổi tập trong ngày (`strain.source = "activities"`) — thấp hơn thực tế vì thiếu phần đi lại.
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

**Giải thích & lời khuyên** chỉ diễn đạt lại các số trên: nêu yếu tố cộng/trừ ≥ 3 điểm hồi phục,
so với mức thường ngày (baseline 30 ngày); số phút Vùng 2/3 còn thiếu để vào strain mục tiêu
tính bằng cách đảo đường cong strain (`load = −176·ln(1 − strain/21)`) với tải mỗi phút ở 65% / 75% HRR.

## Phát triển

```powershell
pip install -r requirements.txt
python -m pytest -q          # 129 test, ~1–2 phút, không cần mạng/Garmin
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
| `garmin_health/explain.py` | giải thích + lời khuyên theo quy tắc cho từng ngày (ghi vào `days/<ngày>.json`) |
| `garmin_health/mcp.py` | connector MCP chỉ đọc cho Claude (JSON-RPC, token riêng) |
| `web/` | giao diện: `app.js` khung + router, `core.js` tiện ích chung, `view-*.js` từng màn hình, `charts.js` biểu đồ SVG, `login.html` + `login.js` trang đăng nhập |
| `scripts/shots.py` | chụp mọi màn hình 390px + 1280px (cần `pip install playwright`, dùng Chrome/Edge có sẵn) |
