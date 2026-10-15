"""Web server nội bộ (chỉ thư viện chuẩn): phục vụ giao diện + JSON đã xử lý.

GET  /                      giao diện (web/)
GET  /data/summary.json     mọi ngày đã tính điểm
GET  /data/days/<ngày>.json chuỗi trong ngày
GET  /api/status            trạng thái đồng bộ
POST /api/sync              đồng bộ Garmin chạy nền rồi build lại
POST /api/journal           {"date": "YYYY-MM-DD", "answers": {key: bool}}
POST /api/settings          {"sleep_baseline_h": 8, ...}

Mặc định chỉ nghe 127.0.0.1. POST bắt buộc Content-Type JSON và Origin trùng Host
(chặn trang web lạ gửi form/fetch "simple request" vào server cục bộ).
"""
from __future__ import annotations

import ipaddress
import json
import re
import threading
import traceback
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import build as builder
from .config import WEB_DIR, Paths, read_json, save_journal_entry, save_settings

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}
DAY_FILE_RE = re.compile(r"^/data/days/(\d{4}-\d{2}-\d{2})\.json$")
STATIC_RE = re.compile(r"^/([a-z0-9_-]+\.(?:js|css|svg|png|webmanifest))$")
MAX_BODY = 64 * 1024


class App:
    def __init__(self, paths: Paths, *, sync_fn=None, build_fn=None):
        self.paths = paths
        self.lock = threading.Lock()
        self.sync_fn = sync_fn
        self.build_fn = build_fn or (lambda: builder.build(paths))
        self.status = {"running": False, "done": 0, "total": 0, "label": "", "error": None, "finished_at": None}

    def start_sync(self) -> bool:
        with self.lock:
            if self.status["running"]:
                return False
            self.status.update(running=True, done=0, total=0, label="Đang kết nối Garmin…", error=None)
        threading.Thread(target=self._run_sync, daemon=True).start()
        return True

    def _run_sync(self) -> None:
        def progress(done, total, label):
            self.status.update(done=done, total=total, label=label)

        try:
            if self.sync_fn is None:
                from .sync import sync

                result = sync(self.paths, progress=progress)
            else:
                result = self.sync_fn(progress)
            self.status["label"] = "Đang tính điểm…"
            with self.lock:
                self.build_fn()
            errs = (result or {}).get("error_count") or 0
            if (result or {}).get("aborted"):
                self.status.update(error=result["aborted"], label="Dừng giữa chừng")
            else:
                self.status.update(label=f"Xong{f' ({errs} lỗi nhỏ)' if errs else ''}")
        except Exception as exc:  # báo lỗi lên UI thay vì chết thread im lặng
            name = type(exc).__name__
            msg = "Chưa đăng nhập Garmin — chạy: python run.py login" if name == "AuthRequired" else f"{name}: {exc}"
            self.status.update(error=msg[:300], label="Lỗi")
            traceback.print_exc()
        finally:
            from datetime import datetime, timezone

            self.status.update(running=False, finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def host_allowed(host_header: str, *, allow_lan: bool) -> bool:
    """Chống DNS-rebinding: chỉ nhận Host là localhost, hoặc (khi --lan) một địa chỉ IP.

    Trang độc trỏ tên miền của nó về IP máy này sẽ gửi Host = tên miền đó ⇒ bị chặn.
    """
    host = host_header.strip()
    if host.startswith("["):              # [::1]:8765
        host = host[1:].split("]")[0]
    elif host.count(":") == 1:
        host = host.split(":")[0]
    if host in ("127.0.0.1", "localhost", "::1"):
        return True
    if not allow_lan:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def make_handler(app: App, *, allow_lan: bool):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GarminHealth/1"

        def log_message(self, fmt, *args):  # gọn log
            if not self.path.startswith(("/api/status",)):
                super().log_message(fmt, *args)

        # ---------- tiện ích ----------
        def _send(self, status: int, body: bytes, ctype: str, *, cache: bool = False):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=300" if cache else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), STATIC_TYPES[".json"])

        def _file(self, path: Path, ctype: str) -> None:
            try:
                body = path.read_bytes()
            except FileNotFoundError:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            self._send(HTTPStatus.OK, body, ctype)

        def _host_ok(self) -> bool:
            return host_allowed(self.headers.get("Host") or "", allow_lan=allow_lan)

        def _post_ok(self) -> bool:
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return False
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return False
            return True

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= MAX_BODY:
                raise ValueError("Content-Length không hợp lệ")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("body phải là object JSON")
            return data

        # ---------- GET ----------
        def do_GET(self):
            if not self._host_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "host"})
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                return self._file(WEB_DIR / "index.html", STATIC_TYPES[".html"])
            if path == "/data/summary.json":
                return self._file(app.paths.processed / "summary.json", STATIC_TYPES[".json"])
            m = DAY_FILE_RE.match(path)
            if m:
                return self._file(app.paths.processed / "days" / f"{m.group(1)}.json", STATIC_TYPES[".json"])
            if path == "/api/status":
                state = read_json(app.paths.sync_state, {}) or {}
                return self._json(HTTPStatus.OK, {"sync": app.status, "last_sync": state.get("last_sync"),
                                                  "has_data": (app.paths.processed / "summary.json").is_file()})
            m = STATIC_RE.match(path)
            if m:
                name = m.group(1)
                return self._file(WEB_DIR / name, STATIC_TYPES[Path(name).suffix])
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        # ---------- POST ----------
        def do_POST(self):
            if not self._host_ok() or not self._post_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "Yêu cầu bị chặn (Origin/Content-Type)"})
            path = urlsplit(self.path).path
            try:
                if path == "/api/sync":
                    started = app.start_sync()
                    return self._json(HTTPStatus.ACCEPTED, {"started": started, "sync": app.status})
                body = self._body()
                if path == "/api/journal":
                    day = str(body.get("date", ""))
                    date.fromisoformat(day)  # ném ValueError nếu sai
                    answers = body.get("answers")
                    if not isinstance(answers, dict):
                        raise ValueError("answers phải là object")
                    with app.lock:   # đọc–sửa–ghi journal.json không được xen kẽ
                        save_journal_entry(app.paths, day, answers)
                        app.build_fn()
                    return self._json(HTTPStatus.OK, {"ok": True})
                if path == "/api/settings":
                    with app.lock:
                        settings = save_settings(app.paths, body)
                        app.build_fn()
                    return self._json(HTTPStatus.OK, {"ok": True, "settings": settings})
            except (ValueError, TypeError, OverflowError) as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:  # luôn trả lời, đừng cắt kết nối im lặng
                traceback.print_exc()
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(exc).__name__}: {exc}"[:300]})
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    return Handler


def serve(paths: Paths, *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    app = App(paths)
    allow_lan = host not in ("127.0.0.1", "localhost")
    httpd = ThreadingHTTPServer((host, port), make_handler(app, allow_lan=allow_lan))
    url = f"http://{'127.0.0.1' if not allow_lan else _lan_ip()}:{port}/"
    print(f"[serve] Mở {url}  (Ctrl+C để dừng)")
    if allow_lan:
        print("[serve] ⚠ Đang mở cho cả mạng LAN — ai cùng Wi-Fi cũng xem được dữ liệu sức khoẻ.")
    if open_browser:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] dừng.")
    finally:
        httpd.server_close()


def _lan_ip() -> str:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
