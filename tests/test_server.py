"""Server: phục vụ file, chặn đường dẫn lạ, chặn POST khác origin, journal/settings/sync."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from garmin_health.server import App, make_handler


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
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, allow_lan=False))
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
