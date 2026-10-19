"""Mật khẩu web + cookie phiên, tên miền khai qua GARMIN_ALLOWED_HOSTS (chạy sau Caddy), sao lưu."""
import json
import os
import threading
import urllib.error
import urllib.request
import zipfile
from datetime import date

import pytest

from garmin_health import auth
from garmin_health.auth import Auth, check_password, cookie_value, hash_password, set_password
from garmin_health.server import App, Server, allowed_hosts_from_env, host_allowed, make_handler

PW = "mat-khau-dai-du"
FAST = 1000   # số vòng PBKDF2 cho test (thật: auth.ITERATIONS)
DOMAIN = "garmin.example.org"


def test_password_hash_roundtrip():
    stored = hash_password(PW, iterations=FAST)
    assert stored.startswith(f"pbkdf2_sha256${FAST}$")
    assert check_password(PW, stored)
    assert not check_password(PW + "x", stored)
    assert hash_password(PW, iterations=FAST) != stored   # muối ngẫu nhiên
    for bad in ("", "md5$1$00$00", "pbkdf2_sha256$x$zz$00", None):
        assert not check_password(PW, bad)


def test_set_password_writes_private_file(tmp_path):
    from garmin_health.config import default_paths

    paths = default_paths(tmp_path)
    assert Auth.load(paths) is None
    with pytest.raises(ValueError):
        set_password(paths, "ngan", iterations=FAST)
    set_password(paths, PW, iterations=FAST)
    if os.name == "posix":
        assert paths.auth.stat().st_mode & 0o777 == 0o600
    a = Auth.load(paths)
    assert a is not None and a.login(PW) == "ok"
    old_cookie = a.make_cookie()
    set_password(paths, PW, iterations=FAST)   # đổi mật khẩu ⇒ khoá mới ⇒ phiên cũ hết hiệu lực
    assert not Auth.load(paths).valid(old_cookie)


def test_cookie_signature_and_expiry():
    a = Auth(hash_password(PW, iterations=FAST), "ab" * 32)
    c = a.make_cookie(now=1_000_000)
    assert a.valid(c, now=1_000_001)
    assert not a.valid(c, now=1_000_000 + auth.SESSION_DAYS * 86400)
    expires, _, sig = c.partition(".")
    assert not a.valid(f"{int(expires) + 1}.{sig}", now=1_000_001)   # sửa hạn ⇒ chữ ký sai
    assert not Auth(a.password_hash, "cd" * 32).valid(c, now=1_000_001)
    for junk in (None, "", ".", "abc", "123.", "-5.ff", "1e9.ff"):
        assert not a.valid(junk, now=0)


def test_login_locks_after_repeated_failures():
    a = Auth(hash_password(PW, iterations=FAST), "ab" * 32)
    for i in range(auth.MAX_FAILURES):
        assert a.login("sai", now=100 + i) == "bad"
    assert a.login(PW, now=200) == "locked"           # đúng mật khẩu cũng phải đợi
    assert a.login(PW, now=100 + auth.FAIL_WINDOW_S + auth.MAX_FAILURES) == "ok"
    assert not a.failures


def test_cookie_value_parsing():
    assert cookie_value("a=1; gh_session=123.abc; b=2") == "123.abc"
    assert cookie_value("gh_session_x=1; xgh_session=2") is None
    assert cookie_value(None) is None and cookie_value("gh_session") is None


@pytest.mark.parametrize("host,ok", [
    (DOMAIN, True), (f"{DOMAIN}:443", True), (DOMAIN.upper(), True), (f"{DOMAIN}.", True),
    ("evil.example", False), (f"x.{DOMAIN}", False), (f"{DOMAIN}.evil.example", False), ("", False),
])
def test_host_allowed_accepts_declared_domain(host, ok):
    assert host_allowed(host, allow_lan=False, allowed_hosts=(DOMAIN,)) is ok


def test_allowed_hosts_from_env(monkeypatch):
    assert allowed_hosts_from_env() == ()
    monkeypatch.setenv("GARMIN_ALLOWED_HOSTS", " Garmin.Example.org., khac.ts.net  b.example ")
    assert allowed_hosts_from_env() == ("garmin.example.org", "khac.ts.net", "b.example")


def test_serve_refuses_domain_without_password(monkeypatch, tmp_path):
    from garmin_health.config import default_paths
    from garmin_health.server import serve

    monkeypatch.setenv("GARMIN_ALLOWED_HOSTS", DOMAIN)
    with pytest.raises(SystemExit, match="password"):
        serve(default_paths(tmp_path), port=0)


# ---------- server có mật khẩu, đứng sau Caddy ----------
@pytest.fixture()
def locked_server(demo_summary, tmp_path):
    import shutil

    from garmin_health.config import default_paths

    src, _ = demo_summary
    shutil.copytree(src.data, tmp_path / "d")
    paths = default_paths(tmp_path / "d")
    set_password(paths, PW, iterations=FAST)
    syncs = []
    app = App(paths, sync_fn=lambda progress: syncs.append(1) or {"error_count": 0}, build_fn=lambda: None,
              auth=Auth.load(paths))
    httpd = Server(("127.0.0.1", 0), make_handler(app, allow_lan=False, allowed_hosts=(DOMAIN,)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", syncs
    httpd.shutdown()
    httpd.server_close()


def call(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


# yêu cầu như Caddy chuyển vào: Host = tên miền, trình duyệt gửi Origin https://tên-miền
VIA_CADDY = {"Host": DOMAIN, "Origin": f"https://{DOMAIN}", "X-Forwarded-Proto": "https", "Content-Type": "application/json"}


def login(base, password=PW):
    status, _, headers = call(base + "/api/login", "POST", {"password": password}, VIA_CADDY)
    cookie = headers.get("Set-Cookie") or ""
    return status, cookie


def test_without_session_only_login_page_and_assets(locked_server):
    base, syncs = locked_server
    status, body, headers = call(base + "/", headers={"Host": DOMAIN})
    assert status == 200 and b'id="login"' in body and b"summary" not in body
    assert headers["X-Frame-Options"] == "DENY"
    manifest = json.loads(call(base + "/manifest.webmanifest", headers={"Host": DOMAIN})[1])
    icons = [i["src"] for i in manifest["icons"]]
    for path in ["/login.js", "/styles.css", "/manifest.webmanifest", *(f"/{i}" for i in icons)]:
        assert call(base + path, headers={"Host": DOMAIN})[0] == 200, path
    for path in ("/data/summary.json", "/api/status"):
        assert call(base + path, headers={"Host": DOMAIN})[0] == 401, path
    for path, body in (("/api/sync", {}), ("/api/settings", {"sleep_baseline_h": 8}), ("/api/journal", {"date": "2026-10-01", "answers": {}})):
        assert call(base + path, "POST", body, VIA_CADDY)[0] == 401, path
    assert b'id="login"' in call(base + "/", headers={"Host": DOMAIN, "Cookie": "gh_session=9999999999.abcd"})[1]
    assert not syncs


def test_login_sets_secure_session_cookie(locked_server):
    base, syncs = locked_server
    assert login(base, "sai-mat-khau")[0] == 401
    status, cookie = login(base)
    assert status == 200
    attrs = [a.strip() for a in cookie.split(";")]
    assert attrs[0].startswith("gh_session=") and "HttpOnly" in attrs and "SameSite=Lax" in attrs and "Secure" in attrs
    assert f"Max-Age={auth.SESSION_DAYS * 86400}" in attrs
    session = {"Cookie": attrs[0]}

    status, body, _ = call(base + "/", headers={"Host": DOMAIN, **session})
    assert status == 200 and b"app.js" in body
    assert call(base + "/data/summary.json", headers={"Host": DOMAIN, **session})[0] == 200
    st = json.loads(call(base + "/api/status", headers={"Host": DOMAIN, **session})[1])
    assert st["auth"] is True
    assert call(base + "/api/sync", "POST", {}, {**VIA_CADDY, **session})[0] == 202

    status, _, headers = call(base + "/api/logout", "POST", {}, {**VIA_CADDY, **session})
    assert status == 200 and "Max-Age=0" in headers["Set-Cookie"]


def test_plain_http_tunnel_gets_non_secure_cookie(locked_server):
    base, _ = locked_server
    _, _, headers = call(base + "/api/login", "POST", {"password": PW}, {"Content-Type": "application/json"})
    assert "Secure" not in headers["Set-Cookie"]


def test_domain_still_blocks_foreign_origin_and_host(locked_server):
    base, _ = locked_server
    _, cookie = login(base)
    session = {"Cookie": cookie.split(";")[0]}
    assert call(base + "/api/sync", "POST", {}, {**VIA_CADDY, **session, "Origin": "https://evil.example"})[0] == 403
    assert call(base + "/data/summary.json", headers={"Host": "evil.example", **session})[0] == 403


def test_login_lockout_over_http(locked_server):
    base, _ = locked_server
    for _ in range(auth.MAX_FAILURES):
        assert login(base, "sai-mat-khau")[0] == 401
    assert login(base)[0] == 429


def test_status_reports_no_auth_when_unset(demo_summary):
    src, _ = demo_summary
    app = App(src, sync_fn=lambda p: {}, build_fn=lambda: None)
    httpd = Server(("127.0.0.1", 0), make_handler(app, allow_lan=False))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        assert json.loads(call(base + "/api/status")[1])["auth"] is False
        assert call(base + "/api/login", "POST", {"password": PW}, {"Content-Type": "application/json"})[0] == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------- lệnh run.py ----------
def test_password_command(monkeypatch, tmp_path):
    import getpass

    import run

    answers = iter([PW, PW + "khac", PW, PW])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    monkeypatch.setattr(auth, "set_password", lambda paths, pw, iterations=FAST: set_password(paths, pw, iterations=FAST))
    assert run.main(["password", "--data-dir", str(tmp_path)]) == 1          # nhập lại không khớp
    assert not (tmp_path / "auth.json").exists()
    assert run.main(["password", "--data-dir", str(tmp_path)]) == 0
    stored = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert check_password(PW, stored["password"]) and len(stored["secret"]) == 64


def test_backup_zips_only_user_files(tmp_path):
    from garmin_health.backup import backup
    from garmin_health.config import default_paths, save_journal_entry, save_settings

    paths = default_paths(tmp_path / "d")
    assert backup(paths) is None
    save_settings(paths, {"sleep_baseline_h": 8})
    save_journal_entry(paths, "2026-10-18", {"alcohol": True})
    set_password(paths, PW, iterations=FAST)
    target = backup(paths, today=date(2026, 10, 19))
    assert target == paths.backups / "garmin-backup-2026-10-19.zip"
    with zipfile.ZipFile(target) as zf:
        assert sorted(zf.namelist()) == ["journal.json", "settings.json"]   # không mang auth.json đi
        assert json.loads(zf.read("journal.json"))["entries"]["2026-10-18"] == {"alcohol": True}


def test_backup_keeps_newest(tmp_path):
    from garmin_health.backup import backup
    from garmin_health.config import default_paths, save_settings

    paths = default_paths(tmp_path / "d")
    save_settings(paths, {})
    out = tmp_path / "bk"
    for d in range(1, 6):
        backup(paths, out=out, keep=3, today=date(2026, 10, d))
    assert [p.name for p in sorted(out.iterdir())] == [f"garmin-backup-2026-10-0{d}.zip" for d in (3, 4, 5)]
    backup(paths, out=out, keep=0, today=date(2026, 10, 6))
    assert len(list(out.iterdir())) == 4
