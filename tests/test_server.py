"""Server: phục vụ file, chặn đường dẫn lạ, chặn POST khác origin, journal/settings/sync."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from garmin_health.server import App, Server, make_handler


@pytest.fixture()
def server(demo_summary, tmp_path):
    import shutil

    from garmin_health.config import default_paths

    src, _ = demo_summary
    shutil.copytree(src.data, tmp_path / "d")
    paths = default_paths(tmp_path / "d")
    builds = []

    def fake_sync(progress):
        progress(1, 2, "giả lập")
        return {"error_count": 0}

    app = App(paths, sync_fn=fake_sync, build_fn=lambda: builds.append(1))
    httpd = Server(("127.0.0.1", 0), make_handler(app, allow_lan=False))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", paths, builds
    httpd.shutdown()
    httpd.server_close()


def req(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


JSON = {"Content-Type": "application/json"}


def test_serves_ui_and_data(server):
    base, paths, _ = server
    assert req(base + "/")[0] == 200
    assert req(base + "/app.js")[0] == 200
    status, body = req(base + "/data/summary.json")
    day = json.loads(body)["days"][-1]["date"]
    assert status == 200 and req(f"{base}/data/days/{day}.json")[0] == 200


def test_index_assets_are_served(server):
    import re

    base, _, _ = server
    html = req(base + "/")[1].decode("utf-8")
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts[:2] == ["charts.js", "core.js"] and scripts[-1] == "app.js"
    assert "styles.css" in re.findall(r'href="([^"]+)"', html)
    for path in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert req(f"{base}/{path}")[0] == 200, path


@pytest.mark.parametrize("path", ["/data/days/../../settings.json", "/../run.py", "/data/raw/_sync.json", "/%2e%2e/run.py", "/journal.json"])
def test_blocks_unknown_paths(server, path):
    base, _, _ = server
    assert req(base + path)[0] == 404


def test_post_requires_json_and_same_origin(server):
    base, _, _ = server
    assert req(base + "/api/sync", "POST", {}, {"Content-Type": "text/plain"})[0] == 403
    assert req(base + "/api/sync", "POST", {}, {**JSON, "Origin": "http://evil.example"})[0] == 403


def test_journal_and_settings(server):
    base, paths, builds = server
    day = json.loads(req(base + "/data/summary.json")[1])["days"][-1]["date"]
    assert req(base + "/api/journal", "POST", {"date": day, "answers": {"alcohol": True}}, JSON)[0] == 200
    assert json.loads(paths.journal.read_text(encoding="utf-8"))["entries"][day] == {"alcohol": True}
    assert req(base + "/api/journal", "POST", {"date": "15/10/2026", "answers": {}}, JSON)[0] == 400
    assert req(base + "/api/settings", "POST", {"sleep_baseline_h": 20}, JSON)[0] == 400
    assert req(base + "/api/settings", "POST", {"sleep_baseline_h": 8.5, "target_wake": "6:05"}, JSON)[0] == 200
    assert json.loads(paths.settings.read_text(encoding="utf-8"))["target_wake"] == "06:05"
    assert len(builds) == 2


def test_sync_runs_in_background(server):
    base, _, builds = server
    status, body = req(base + "/api/sync", "POST", {}, JSON)
    assert status == 202 and json.loads(body)["started"]
    for _ in range(50):
        st = json.loads(req(base + "/api/status")[1])["sync"]
        if not st["running"]:
            break
        time.sleep(0.05)
    assert not st["running"] and st["error"] is None and builds


def test_rejects_foreign_host_header(server):
    base, _, _ = server
    assert req(base + "/data/summary.json", headers={"Host": "evil.example"})[0] == 403


@pytest.mark.parametrize("host,lan,ok", [
    ("127.0.0.1:8765", False, True), ("localhost:8765", False, True), ("[::1]:8765", False, True),
    ("192.168.1.20:8765", False, False), ("192.168.1.20:8765", True, True),
    ("attacker.example", True, False), ("attacker.example:8765", True, False), ("", True, False),
])
def test_host_allowed_blocks_dns_rebinding(host, lan, ok):
    from garmin_health.server import host_allowed

    assert host_allowed(host, allow_lan=lan) is ok


def _raw_post(base, path, body: bytes, length=None):
    import http.client
    from urllib.parse import urlsplit

    u = urlsplit(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    conn.putrequest("POST", path)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(body) if length is None else length))
    conn.endheaders()
    conn.send(body)
    resp = conn.getresponse()
    status = resp.status
    conn.close()
    return status


def test_bad_bodies_get_an_answer(server):
    base, _, _ = server
    assert _raw_post(base, "/api/settings", b"{}", length=-1) == 400
    assert _raw_post(base, "/api/settings", b'{"hr_max": 1e400}') == 400
    assert _raw_post(base, "/api/settings", b'{"sleep_baseline_h": 1e400}') == 400
    assert _raw_post(base, "/api/settings", b"[1,2]") == 400


def test_concurrent_journal_saves_keep_both(server):
    base, paths, _ = server
    days = [d["date"] for d in json.loads(req(base + "/data/summary.json")[1])["days"][-6:]]
    threads = [threading.Thread(target=req, args=(base + "/api/journal", "POST", {"date": d, "answers": {"sauna": True}}, JSON)) for d in days]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    entries = json.loads(paths.journal.read_text(encoding="utf-8"))["entries"]
    assert all(entries[d].get("sauna") is True for d in days)
