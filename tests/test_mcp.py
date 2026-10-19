"""Connector MCP: JSON-RPC (initialize, tools, prompts), công cụ chỉ đọc trên dữ liệu mẫu, token, HTTP."""
import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from garmin_health import mcp
from garmin_health.mcp import Connector

TOKEN = "t" * 43


@pytest.fixture()
def conn(demo_summary):
    paths, _ = demo_summary
    return Connector(paths, mcp._hash(TOKEN))


def rpc(conn, method, params=None, mid=1):
    msg = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    return conn.handle(msg)


def call(conn, name, **args):
    res = rpc(conn, "tools/call", {"name": name, "arguments": args})["result"]
    return res, (json.loads(res["content"][0]["text"]) if not res["isError"] else res["content"][0]["text"])


def test_initialize_negotiates_version(conn):
    r = rpc(conn, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})["result"]
    assert r["protocolVersion"] == "2025-06-18"
    assert set(r["capabilities"]) == {"tools", "prompts"} and r["serverInfo"]["name"] == "garmin-health"
    assert "get_day" in r["instructions"]
    newer = rpc(conn, "initialize", {"protocolVersion": "2099-01-01"})["result"]
    assert newer["protocolVersion"] == mcp.PROTOCOL_VERSIONS[0]   # client tự quyết có dùng được bản này không


def test_jsonrpc_shapes(conn):
    assert conn.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None   # notification ⇒ 202
    assert conn.handle({"jsonrpc": "2.0", "id": 5, "result": {}}) is None                  # response từ client
    batch = conn.handle([{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/cancelled"}])
    assert batch == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    assert rpc(conn, "server/discover")["error"]["code"] == -32601   # giao thức 2026: client lùi về initialize
    assert conn.handle({"id": 1, "method": "ping"})["error"]["code"] == -32600
    assert conn.handle([])["error"]["code"] == -32600
    assert rpc(conn, "tools/call", {"name": "xoa_du_lieu"})["error"]["code"] == -32602
    assert rpc(conn, "tools/call", "sai")["error"]["code"] == -32602


def test_tools_are_listed_read_only_with_schemas(conn):
    tools = rpc(conn, "tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == ["get_day", "get_days", "get_trends", "get_journal_insights", "get_activities", "get_methodology"]
    for t in tools:
        assert t["inputSchema"]["type"] == "object" and t["annotations"]["readOnlyHint"] is True
        assert t["description"] and t["title"]


def test_get_day_latest_and_older(conn, demo_summary):
    _, summary = demo_summary
    res, d = call(conn, "get_day")
    last = summary["days"][-1]
    assert d["date"] == last["date"] and d["partial_day"] is True
    assert d["recovery"]["score_pct"] == last["recovery"]["score"]
    assert set(d["app_explanation"]) == {"outlook", "recovery", "sleep", "strain", "health"}
    assert d["sleep_plan_tonight"]["options"][0]["label"] == "Đỉnh"
    assert "onset_min" not in (d["sleep"] or {}) and "load" not in d["strain"]
    _, old = call(conn, "get_day", date=summary["days"][-10]["date"])
    assert "sleep_plan_tonight" not in old and old["partial_day"] is False
    journaled = next(x for x in reversed(summary["days"]) if x.get("journal"))
    _, j = call(conn, "get_day", date=journaled["date"])
    assert "Uống rượu bia" in j["journal_about_previous_day"]   # khoá → nhãn câu hỏi
    for bad in ("1999-01-01", "19/10/2026"):
        res, text = call(conn, "get_day", date=bad)
        assert res["isError"] and ("Không có dữ liệu" in text or "không hợp lệ" in text)


def test_get_days_ranges(conn, demo_summary):
    _, summary = demo_summary
    _, d = call(conn, "get_days")
    assert len(d["days"]) == mcp.DEFAULT_RANGE_DAYS and d["days"][-1]["date"] == summary["days"][-1]["date"]
    assert all("None" not in json.dumps(r) and r.get("recovery", 0) is not None for r in d["days"])
    _, d = call(conn, "get_days", start="2026-10-01", end="2026-10-05")
    assert [r["date"] for r in d["days"]] == [f"2026-10-0{i}" for i in range(1, 6)]
    assert call(conn, "get_days", start="2026-10-05", end="2026-10-01")[0]["isError"]
    assert call(conn, "get_days", start="2025-01-01", end="2026-10-01")[0]["isError"]   # > 180 ngày
    res, text = call(conn, "get_days", start="2026-10-01", limit=5)
    assert res["isError"] and "limit" in text


def test_trends_journal_activities_methodology(conn):
    _, t = call(conn, "get_trends", days=7)
    assert t["period"]["days"] == 7 and t["previous"]["days"] == 7
    assert set(t["change"]) >= {"recovery", "hrv", "sleep_h"} and t["weekly"]
    assert call(conn, "get_trends", days=3)[0]["isError"]
    _, j = call(conn, "get_journal_insights")
    assert j["impact"] and j["entries"] > 0 and j["recent_answers"]
    _, a = call(conn, "get_activities", start="2026-09-01", end="2026-09-30")
    assert a["count"] == len(a["activities"]) > 0 and all(x["date"].startswith("2026-09") for x in a["activities"])
    _, m = call(conn, "get_methodology")
    assert m["methodology"].startswith("## Cách tính") and "Recovery" in m["methodology"] and m["profile"]["hr_max"]


def test_prompts(conn):
    names = [p["name"] for p in rpc(conn, "prompts/list")["result"]["prompts"]]
    assert names == ["nhan-dinh-sang-nay", "tong-ket-tuan", "thoi-quen"]
    msg = rpc(conn, "prompts/get", {"name": "nhan-dinh-sang-nay"})["result"]["messages"][0]
    assert msg["role"] == "user" and "get_day" in msg["content"]["text"]
    assert rpc(conn, "prompts/get", {"name": "khong-co"})["error"]["code"] == -32602


def test_no_data_and_internal_errors(tmp_path, conn, monkeypatch):
    from garmin_health.config import default_paths

    empty = Connector(default_paths(tmp_path), "x")
    res, text = call(empty, "get_day")
    assert res["isError"] and "sync" in text
    monkeypatch.setattr(Connector, "tool_get_methodology", lambda self: 1 / 0)
    assert rpc(conn, "tools/call", {"name": "get_methodology"})["error"]["code"] == -32603


def test_token_file_keeps_only_hash(tmp_path):
    from garmin_health.config import default_paths

    paths = default_paths(tmp_path)
    assert Connector.load(paths) is None
    token = mcp.new_token(paths)
    stored = paths.mcp.read_text(encoding="utf-8")
    assert token not in stored and len(token) >= 40
    if os.name == "posix":
        assert paths.mcp.stat().st_mode & 0o777 == 0o600
    c = Connector.load(paths)
    assert c.check(token) and not c.check(token + "x") and not c.check(None) and not c.check("")
    assert mcp.new_token(paths) != token and not Connector.load(paths).check(token)   # đổi token ⇒ token cũ vô hiệu
    assert mcp.revoke(paths) and Connector.load(paths) is None and not mcp.revoke(paths)


def test_mcp_token_command(tmp_path, capsys):
    import run

    assert run.main(["mcp-token", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    token = next(line.strip() for line in out.splitlines() if len(line.strip()) >= 40 and " " not in line.strip())
    assert f"Authorization: Bearer {token}" in out and f"/mcp/{token}" in out
    from garmin_health.config import default_paths

    assert Connector.load(default_paths(tmp_path)).check(token)
    assert run.main(["mcp-token", "--revoke", "--data-dir", str(tmp_path)]) == 0
    assert not (tmp_path / "mcp.json").exists()


# ---------- HTTP ----------
@pytest.fixture()
def http(demo_summary, tmp_path):
    import shutil

    from garmin_health.auth import Auth, set_password
    from garmin_health.config import default_paths
    from garmin_health.server import App, Server, make_handler

    src, _ = demo_summary
    shutil.copytree(src.data, tmp_path / "d")
    paths = default_paths(tmp_path / "d")
    set_password(paths, "mat-khau-dai-du", iterations=1000)   # web có mật khẩu: connector vẫn chỉ cần token
    servers = []

    def start(with_mcp=True):
        app = App(paths, sync_fn=lambda p: {}, build_fn=lambda: None, auth=Auth.load(paths),
                  mcp=Connector(paths, mcp._hash(TOKEN)) if with_mcp else None)
        httpd = Server(("127.0.0.1", 0), make_handler(app, allow_lan=False, allowed_hosts=("garmin.example.org",)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def send(url, method="POST", body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
BEARER = {"Authorization": f"Bearer {TOKEN}"}


def test_http_token_in_header_or_path(http):
    base = http()
    status, body, _ = send(base + "/mcp", body=INIT, headers={**BEARER, "Host": "garmin.example.org"})
    assert status == 200 and json.loads(body)["result"]["serverInfo"]["name"] == "garmin-health"
    status, body, _ = send(f"{base}/mcp/{TOKEN}", body={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert status == 200 and len(json.loads(body)["result"]["tools"]) == 6
    status, body, _ = send(base + "/mcp", body={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=BEARER)
    assert (status, body) == (202, b"")
    assert send(base + "/mcp", body=INIT, headers={"Authorization": TOKEN})[0] == 200   # token trơn, thiếu "Bearer"


def test_http_rejects_without_valid_token(http):
    base = http()
    for headers, path in (({}, "/mcp"), ({"Authorization": "Bearer sai"}, "/mcp"), ({}, "/mcp/sai-token"),
                          ({"Authorization": f"Basic {TOKEN}"}, "/mcp")):
        status, _, h = send(base + path, body=INIT, headers=headers)
        assert status == 401 and h["WWW-Authenticate"].startswith("Bearer"), (headers, path)
    assert send(base + "/mcp", body=INIT, headers={**BEARER, "Origin": "https://evil.example"})[0] == 403
    assert send(base + "/mcp", body=INIT, headers={**BEARER, "Content-Type": "text/plain"})[0] == 403
    assert send(base + "/mcp", body=INIT, headers={**BEARER, "Host": "evil.example"})[0] == 403
    status, body, _ = send(base + "/mcp", raw=b"{khong phai json", headers=BEARER)
    assert status == 400 and json.loads(body)["error"]["code"] == -32700


def test_http_methods_and_disabled_connector(http):
    base = http()
    for method in ("GET", "DELETE"):
        status, _, h = send(base + "/mcp", method=method, headers=BEARER)
        assert status == 405 and h["Allow"] == "POST", method
    off = http(with_mcp=False)
    assert send(off + "/mcp", body=INIT, headers=BEARER)[0] == 404
    assert send(off + "/api/sync", body={})[0] == 401   # web vẫn cần đăng nhập như cũ


def test_log_hides_path_token():
    from garmin_health.server import MCP_LOG_RE

    line = f'"POST /mcp/{TOKEN} HTTP/1.1" 200 -'
    assert MCP_LOG_RE.sub("/mcp/***", line) == '"POST /mcp/*** HTTP/1.1" 200 -'
