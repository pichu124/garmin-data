"""Web server nội bộ (chỉ thư viện chuẩn): phục vụ giao diện + JSON đã xử lý.

GET  /                      giao diện (web/)
GET  /data/summary.json     mọi ngày đã tính điểm
GET  /data/days/<ngày>.json chuỗi trong ngày
GET  /api/status            trạng thái đồng bộ
POST /api/sync              đồng bộ Garmin chạy nền rồi build lại
POST /api/journal           {"date": "YYYY-MM-DD", "answers": {key: bool}}
POST /api/settings          {"sleep_baseline_h": 8, ...}
POST /api/login · /api/logout  {"password": "..."} — chỉ khi đã đặt mật khẩu (auth.json)
POST /mcp · /mcp/<token>    connector MCP cho Claude (mcp.py), token riêng, không dùng cookie

Mặc định chỉ nghe 127.0.0.1. POST bắt buộc Content-Type JSON và Origin trùng Host
(chặn trang web lạ gửi form/fetch "simple request" vào server cục bộ).
Host là tên miền chỉ được nhận khi khai trong GARMIN_ALLOWED_HOSTS (đặt sau Caddy), và khi
đó bắt buộc có mật khẩu web: chưa đăng nhập thì / trả trang đăng nhập, /data/* và /api/* trả 401.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import traceback
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import build as builder
from .auth import COOKIE, SESSION_DAYS, Auth, cookie_value
from .config import WEB_DIR, Paths, read_json, save_journal_entry, save_settings
from .mcp import Connector

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
MCP_RE = re.compile(r"^/mcp(?:/([A-Za-z0-9_-]+))?$")
MCP_LOG_RE = re.compile(r"/mcp/[^\s\"]+")
MAX_BODY = 64 * 1024


class App:
    def __init__(self, paths: Paths, *, sync_fn=None, build_fn=None, auth: Auth | None = None, mcp: Connector | None = None):
        self.paths = paths
        self.auth = auth
        self.mcp = mcp
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


def allowed_hosts_from_env() -> tuple[str, ...]:
    """GARMIN_ALLOWED_HOSTS="garmin.duckdns.org,khac.ts.net" — tên miền, không kèm https:// hay cổng."""
    raw = os.getenv("GARMIN_ALLOWED_HOSTS") or ""
    return tuple(h.strip().lower().rstrip(".") for h in raw.replace(",", " ").split() if h.strip())


def host_allowed(host_header: str, *, allow_lan: bool, allowed_hosts: tuple[str, ...] = ()) -> bool:
    """Chống DNS-rebinding: chỉ nhận Host là localhost, tên miền đã khai, hoặc (khi --lan) một địa chỉ IP.

    Trang độc trỏ tên miền của nó về IP máy này sẽ gửi Host = tên miền đó ⇒ bị chặn.
    """
    host = host_header.strip()
    if host.startswith("["):              # [::1]:8765
        host = host[1:].split("]")[0]
    elif host.count(":") == 1:
        host = host.split(":")[0]
    if host in ("127.0.0.1", "localhost", "::1"):
        return True
    if host and host.lower().rstrip(".") in allowed_hosts:
        return True
    if not allow_lan:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def make_handler(app: App, *, allow_lan: bool, allowed_hosts: tuple[str, ...] = ()):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GarminHealth/1"
        _head = False   # do_HEAD: gửi header như GET, bỏ thân

        def log_message(self, fmt, *args):  # gọn log; token trong /mcp/<token> không được lọt vào journalctl
            if not getattr(self, "path", "").startswith(("/api/status",)):
                super().log_message("%s", MCP_LOG_RE.sub("/mcp/***", fmt % args))

        # ---------- tiện ích ----------
        def _send(self, status: int, body: bytes, ctype: str, *, cache: bool = False, cookie: str | None = None,
                  headers: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=300" if cache else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if not self._head:
                self.wfile.write(body)

        def _json(self, status: int, obj, *, cookie: str | None = None, headers: dict | None = None) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), STATIC_TYPES[".json"],
                       cookie=cookie, headers=headers)

        def _file(self, path: Path, ctype: str) -> None:
            try:
                body = path.read_bytes()
            except FileNotFoundError:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            self._send(HTTPStatus.OK, body, ctype)

        def _host_ok(self) -> bool:
            return host_allowed(self.headers.get("Host") or "", allow_lan=allow_lan, allowed_hosts=allowed_hosts)

        def _authed(self) -> bool:
            return app.auth is None or app.auth.valid(cookie_value(self.headers.get("Cookie")))

        def _session_cookie(self, value: str, max_age: int) -> str:
            # Secure khi đi qua HTTPS của Caddy/Tailscale; qua đường hầm SSH (http://127.0.0.1) thì không
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            return f"{COOKIE}={value}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax{secure}"

        def _login(self) -> None:
            if app.auth is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "Chưa đặt mật khẩu web"})
            password = self._body().get("password")
            if not isinstance(password, str):
                raise ValueError("password phải là chuỗi")
            result = app.auth.login(password)
            if result == "locked":
                return self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Sai quá nhiều lần — thử lại sau 10 phút"})
            if result != "ok":
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Sai mật khẩu"})
            cookie = self._session_cookie(app.auth.make_cookie(), SESSION_DAYS * 86400)
            return self._json(HTTPStatus.OK, {"ok": True}, cookie=cookie)

        def _mcp(self, path_token: str | None) -> None:
            if app.mcp is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            auth = self.headers.get("Authorization") or ""
            token = path_token or (auth[7:].strip() if auth[:7].lower() == "bearer " else None)
            if not app.mcp.check(token):
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Sai hoặc thiếu token connector"},
                                  headers={"WWW-Authenticate": 'Bearer realm="garmin-health"'})
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                raise ValueError("Content-Length không hợp lệ")
            try:
                payload = json.loads(self.rfile.read(length))
            except ValueError:
                return self._json(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None,
                                                           "error": {"code": -32700, "message": "JSON không hợp lệ"}})
            reply = app.mcp.handle(payload)
            if reply is None:   # chỉ có notification ⇒ 202, không thân
                return self._send(HTTPStatus.ACCEPTED, b"", STATIC_TYPES[".json"])
            return self._json(HTTPStatus.OK, reply)

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
        def do_DELETE(self):   # MCP: client đóng phiên — server này không giữ phiên
            if not self._host_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "host"})
            return self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "not allowed"}, headers={"Allow": "POST"})

        def do_HEAD(self):
            # curl -I, máy theo dõi uptime; thiếu hàm này http.server trả 501
            self._head = True
            try:
                self.do_GET()
            finally:
                self._head = False

        def do_GET(self):
            if not self._host_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "host"})
            path = urlsplit(self.path).path
            authed = self._authed()
            if path in ("/", "/index.html"):
                return self._file(WEB_DIR / ("index.html" if authed else "login.html"), STATIC_TYPES[".html"])
            if MCP_RE.match(path):   # không mở luồng SSE: chỉ nhận POST
                return self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "POST only"}, headers={"Allow": "POST"})
            if path.startswith(("/data/", "/api/")) and not authed:
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Cần đăng nhập"})
            if path == "/data/summary.json":
                return self._file(app.paths.processed / "summary.json", STATIC_TYPES[".json"])
            m = DAY_FILE_RE.match(path)
            if m:
                return self._file(app.paths.processed / "days" / f"{m.group(1)}.json", STATIC_TYPES[".json"])
            if path == "/api/status":
                state = read_json(app.paths.sync_state, {}) or {}
                return self._json(HTTPStatus.OK, {"sync": app.status, "last_sync": state.get("last_sync"),
                                                  "has_data": (app.paths.processed / "summary.json").is_file(),
                                                  "auth": app.auth is not None})
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
                m = MCP_RE.match(path)
                if m:
                    return self._mcp(m.group(1))
                if path == "/api/login":
                    return self._login()
                if path == "/api/logout":
                    return self._json(HTTPStatus.OK, {"ok": True}, cookie=self._session_cookie("", 0))
                if not self._authed():
                    return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Cần đăng nhập"})
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


class Server(ThreadingHTTPServer):
    # trang nạp ~16 file cùng lúc; hàng đợi mặc định 5 làm Windows từ chối kết nối (ERR_CONNECTION_REFUSED)
    request_queue_size = 64
    daemon_threads = True


def serve(paths: Paths, *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    auth = Auth.load(paths)
    allowed_hosts = allowed_hosts_from_env()
    if allowed_hosts and auth is None:
        # mở ra tên miền mà không có mật khẩu = dữ liệu sức khoẻ công khai trên internet
        raise SystemExit("✗ Đã đặt GARMIN_ALLOWED_HOSTS nhưng chưa có mật khẩu web — chạy: python run.py password")
    mcp = Connector.load(paths)
    app = App(paths, auth=auth, mcp=mcp)
    allow_lan = host not in ("127.0.0.1", "localhost")
    httpd = Server((host, port), make_handler(app, allow_lan=allow_lan, allowed_hosts=allowed_hosts))
    url = f"http://{'127.0.0.1' if not allow_lan else _lan_ip()}:{port}/"
    print(f"[serve] Mở {url}  (Ctrl+C để dừng)")
    if allowed_hosts:
        print(f"[serve] Nhận tên miền: {', '.join(allowed_hosts)}")
    if auth is not None:
        print("[serve] Cần mật khẩu web để xem.")
    if mcp is not None:
        print("[serve] Connector MCP cho Claude: bật (/mcp)")
    elif allow_lan:
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
