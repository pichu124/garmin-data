"""Connector MCP để Claude (claude.ai / app Claude, gói Pro/Max) đọc dữ liệu sức khoẻ — CHỈ ĐỌC.

Giao thức: MCP Streamable HTTP, JSON-RPC 2.0. Server không giữ phiên (không Mcp-Session-Id) và không
mở luồng SSE: mỗi POST trả đúng một JSON (hoặc 202 cho notification).

    POST /mcp            token trong header  Authorization: Bearer <token>
    POST /mcp/<token>    cho ô cấu hình chỉ có URL (server che token khi ghi log)

Token chỉ lưu dạng SHA-256 trong <data>/mcp.json; tạo/đổi bằng `python run.py mcp-token`.
Công cụ chỉ đọc summary.json + days/<ngày>.json — không sửa cài đặt, nhật ký, không gọi Garmin.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
import traceback
from datetime import date, datetime, timedelta, timezone

from .config import ROOT, Paths, read_json, write_json
from .stats import mean

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # mới nhất trước
SERVER_INFO = {"name": "garmin-health", "title": "Garmin Health", "version": "1.0"}
MAX_RANGE_DAYS = 180
DEFAULT_RANGE_DAYS = 30
MAX_ACTIVITIES = 100

INSTRUCTIONS = """\
Dữ liệu Garmin của MỘT người dùng, đã tính điểm kiểu WHOOP: Recovery 0–100% (xanh ≥67, vàng 34–66, đỏ ≤33),
Strain 0–21 (logarit), Hiệu suất ngủ %, nhu cầu ngủ, Health Monitor (HRV, nhịp tim nghỉ, nhịp thở, SpO2 so với
ngưỡng cá nhân = baseline 30 ngày trước ± 1,5 độ lệch).
Quy ước ngày: Recovery và giấc ngủ của ngày D là đêm D-1 → sáng D; Strain của D là cả ngày D (ngày hôm nay còn
đang cộng dồn: partial_day = true); nhật ký ngày D là câu trả lời buổi sáng D về hôm trước.
Khi tư vấn: luôn gọi công cụ để lấy số thật (get_day cho một ngày, get_days/get_trends cho xu hướng,
get_journal_insights cho thói quen, get_methodology cho công thức), trích ngày + con số cụ thể, so với baseline
của chính người dùng thay vì chuẩn chung. Trả lời tiếng Việt, số kiểu 1,234.5. Không chẩn đoán bệnh: dấu hiệu bất
thường kéo dài (SpO2 thấp, nhịp tim nghỉ tăng cùng nhịp thở) thì khuyên gặp bác sĩ. Đây là ước lượng theo nguyên
lý WHOOP, không phải số của WHOOP.
Garmin chỉ giữ nhịp tim/stress theo phút ~4–5 tháng: ngày cũ hơn có strain.source = "activities" (strain chỉ từ
buổi tập, thấp hơn thực tế) và không có stress.
get_day → app_explanation.coach là kết luận app đang hiện trên trang chủ: verdict (tập nặng được / tập vừa sức /
nghỉ ngơi chủ động), why (yếu tố + điểm), strain.text (còn bao nhiêu phút để vào vùng tối ưu), tonight (giờ lên giường).
Tư vấn nên khớp với kết luận đó; nếu thấy khác thì nói rõ vì sao."""

_DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
TOOLS = [
    {
        "name": "get_day",
        "title": "Chi tiết một ngày",
        "description": (
            "Toàn bộ chỉ số của một ngày: hồi phục (+ điểm mỗi yếu tố cộng/trừ so với baseline), giấc ngủ và nhu cầu ngủ, "
            "strain + vùng tối ưu + vùng tim, chỉ số sống so với ngưỡng cá nhân, chỉ số riêng Garmin (Body Battery, "
            "stress theo phút, Training Readiness, VO2max), hoạt động, nhật ký, phần giải thích + lời khuyên của app; "
            "ngày mới nhất kèm kế hoạch ngủ đêm nay. Đơn vị: giờ (h), phút (min), HRV ms, nhịp tim bpm."),
        "inputSchema": {"type": "object", "properties": {
            "date": {**_DATE, "description": "YYYY-MM-DD; bỏ trống = ngày mới nhất"}}, "additionalProperties": False},
    },
    {
        "name": "get_days",
        "title": "Bảng nhiều ngày",
        "description": (
            f"Bảng gọn mỗi ngày một dòng (hồi phục, HRV, nhịp tim nghỉ, nhịp thở, SpO2, giờ ngủ/nhu cầu, hiệu suất ngủ, "
            f"strain/mục tiêu, buổi tập, phút stress vừa+cao, nhật ký) trong khoảng [start, end], tối đa {MAX_RANGE_DAYS} ngày. "
            f"Bỏ trống = {DEFAULT_RANGE_DAYS} ngày gần nhất."),
        "inputSchema": {"type": "object", "properties": {"start": _DATE, "end": _DATE}, "additionalProperties": False},
    },
    {
        "name": "get_trends",
        "title": "Xu hướng",
        "description": "Trung bình N ngày gần nhất so với N ngày trước đó (hồi phục, HRV, nhịp tim nghỉ, giấc ngủ, strain, số ngày mỗi vùng) + trung bình theo tuần.",
        "inputSchema": {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 7, "maximum": MAX_RANGE_DAYS, "description": "N, mặc định 30"}},
            "additionalProperties": False},
    },
    {
        "name": "get_journal_insights",
        "title": "Thói quen ảnh hưởng hồi phục",
        "description": ("Nhật ký thói quen: hồi phục trung bình các sáng trả lời Có so với Không cho từng câu hỏi "
                        "(rượu bia, ăn muộn, cà phê muộn, điện thoại trên giường…), kiểm định Welch (significant khi |t| ≥ 2), "
                        "kèm câu trả lời 14 ngày gần nhất. Là tương quan, không phải nhân quả."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_activities",
        "title": "Danh sách hoạt động",
        "description": f"Các buổi tập trong khoảng [start, end] (mặc định {DEFAULT_RANGE_DAYS} ngày gần nhất): loại, thời lượng, strain, HR TB/max, quãng đường, Training Effect, phút từng vùng tim.",
        "inputSchema": {"type": "object", "properties": {"start": _DATE, "end": _DATE}, "additionalProperties": False},
    },
    {
        "name": "get_methodology",
        "title": "Cách tính các chỉ số",
        "description": "Công thức Recovery, Strain, nhu cầu ngủ, hiệu suất ngủ, strain mục tiêu, vùng tim + hồ sơ đang dùng (HRmax, nhu cầu ngủ nền, cài đặt).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
for _t in TOOLS:
    _t["annotations"] = {"readOnlyHint": True, "openWorldHint": False}

PROMPTS = {
    "nhan-dinh-sang-nay": {
        "title": "Nhận định sáng nay",
        "description": "Cơ thể hôm nay ra sao, vì sao, nên tập gì và ngủ lúc nào.",
        "text": ("Gọi get_day (ngày mới nhất) và get_trends với days=7, rồi viết nhận định sáng nay cho tôi. Câu đầu trả lời "
                 "thẳng: hôm nay nên tập nặng tới đâu (theo app_explanation.coach). Sau đó: hồi phục và vì sao (yếu tố nào "
                 "kéo lên/xuống), giấc ngủ đêm qua so với nhu cầu, nên tập gì hôm nay (strain mục tiêu, bao nhiêu phút), "
                 "giờ đi ngủ tối nay, lưu ý sức khoẻ nếu có. Ngắn gọn, có số liệu."),
    },
    "tong-ket-tuan": {
        "title": "Tổng kết tuần",
        "description": "Tuần qua so với tuần trước và 3 việc nên làm tuần tới.",
        "text": ("Gọi get_trends với days=7 và get_days cho 14 ngày gần nhất, rồi tổng kết tuần qua so với tuần trước: "
                 "hồi phục, giấc ngủ, strain, ngày tốt/xấu nhất và vì sao, rồi đề xuất 3 việc cụ thể cho tuần tới."),
    },
    "thoi-quen": {
        "title": "Thói quen ảnh hưởng thế nào",
        "description": "Thói quen nào làm hồi phục của tôi tăng/giảm rõ nhất.",
        "text": ("Gọi get_journal_insights rồi giải thích thói quen nào ảnh hưởng hồi phục và giấc ngủ của tôi rõ nhất, "
                 "mức tin cậy (cỡ mẫu, |t|), và gợi ý thay đổi. Nhắc rằng đây là tương quan."),
    },
}


# ---------- token ----------
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token(paths: Paths) -> str:
    token = secrets.token_urlsafe(32)
    write_json(paths.mcp, {"token_sha256": _hash(token), "created": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    try:
        os.chmod(paths.mcp, 0o600)
    except OSError:  # Windows
        pass
    return token


def revoke(paths: Paths) -> bool:
    try:
        paths.mcp.unlink()
        return True
    except FileNotFoundError:
        return False


class ToolError(Exception):
    """Lỗi do tham số/dữ liệu — trả về cho Claude dạng isError để nó tự sửa."""


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class Connector:
    def __init__(self, paths: Paths, token_sha256: str):
        self.paths = paths
        self.token_sha256 = token_sha256

    @classmethod
    def load(cls, paths: Paths) -> Connector | None:
        """None nếu chưa tạo token — khi đó /mcp trả 404."""
        h = (read_json(paths.mcp) or {}).get("token_sha256")
        return cls(paths, h) if h else None

    def check(self, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(_hash(token), self.token_sha256)

    # ---------- JSON-RPC ----------
    def handle(self, payload) -> object | None:
        """Một message hoặc một mảng (batch). None ⇒ chỉ toàn notification/response ⇒ HTTP 202."""
        if isinstance(payload, list):
            if not payload:
                return _error(None, -32600, "Batch rỗng")
            out = [r for r in (self._one(m) for m in payload) if r is not None]
            return out or None
        return self._one(payload)

    def _one(self, msg) -> dict | None:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Không phải JSON-RPC 2.0")
        if "method" not in msg:
            return None          # response từ client (ta không gửi request nào) — bỏ qua
        if "id" not in msg:
            return None          # notification: initialized, cancelled…
        mid, method, params = msg["id"], msg["method"], msg.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RpcError(-32602, "params phải là object")
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call(params)
            elif method == "prompts/list":
                result = {"prompts": [{"name": k, "title": v["title"], "description": v["description"], "arguments": []}
                                      for k, v in PROMPTS.items()]}
            elif method == "prompts/get":
                p = PROMPTS.get(params.get("name"))
                if not p:
                    raise RpcError(-32602, f"Không có prompt: {params.get('name')}")
                result = {"description": p["description"],
                          "messages": [{"role": "user", "content": {"type": "text", "text": p["text"]}}]}
            else:
                raise RpcError(-32601, f"Không hỗ trợ: {method}")
        except RpcError as exc:
            return _error(mid, exc.code, str(exc))
        except Exception:  # lỗi lập trình: báo -32603 thay vì làm rơi cả yêu cầu
            traceback.print_exc()
            return _error(mid, -32603, "Lỗi nội bộ của máy chủ")
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion")
        return {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        }

    def _call(self, params: dict) -> dict:
        name, args = params.get("name"), params.get("arguments") or {}
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            raise RpcError(-32602, f"Không có công cụ: {name}")
        if not isinstance(args, dict):
            raise RpcError(-32602, "arguments phải là object")
        unknown = set(args) - set(tool["inputSchema"]["properties"])
        if unknown:
            return _tool_error(f"Tham số không hỗ trợ: {', '.join(sorted(unknown))}")
        try:
            data = getattr(self, f"tool_{name}")(**{k: v for k, v in args.items() if v is not None})
        except ToolError as exc:
            return _tool_error(str(exc))
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}],
                "isError": False}

    # ---------- dữ liệu ----------
    def _summary(self) -> dict:
        s = read_json(self.paths.processed / "summary.json")
        if not s or not s.get("days"):
            raise ToolError("Chưa có dữ liệu — chạy `python run.py sync` trên máy chủ.")
        return s

    def _index(self, s: dict, day: str | None) -> int:
        if not day:
            return len(s["days"]) - 1
        idx = {d["date"]: i for i, d in enumerate(s["days"])}
        key = _parse_date(day).isoformat()
        if key not in idx:
            raise ToolError(f"Không có dữ liệu ngày {day}. Có từ {s['days'][0]['date']} đến {s['days'][-1]['date']}.")
        return idx[key]

    def _range(self, s: dict, start: str | None, end: str | None) -> list[dict]:
        last = date.fromisoformat(s["days"][-1]["date"])
        e = _parse_date(end) if end else last
        b = _parse_date(start) if start else e - timedelta(days=DEFAULT_RANGE_DAYS - 1)
        if b > e:
            raise ToolError("start phải trước hoặc bằng end")
        if (e - b).days + 1 > MAX_RANGE_DAYS:
            raise ToolError(f"Tối đa {MAX_RANGE_DAYS} ngày mỗi lần — chia nhỏ khoảng ngày.")
        return [d for d in s["days"] if b.isoformat() <= d["date"] <= e.isoformat()]

    def tool_get_day(self, date: str | None = None) -> dict:
        s = self._summary()
        i = self._index(s, date)
        d = s["days"][i]
        labels = {q["key"]: q["label"] for q in s.get("journal_questions") or []}
        detail = read_json(self.paths.processed / "days" / f"{d['date']}.json") or {}
        rec = d.get("recovery") or {}
        sleep = {k: v for k, v in (d.get("sleep") or {}).items() if k not in ("onset_min", "wake_min", "start_min", "end_min")}
        out = {
            "date": d["date"],
            "partial_day": d.get("partial", False),
            "recovery": {"score_pct": rec.get("score"), "zone": rec.get("zone"), "calibrating": rec.get("calibrating"),
                         "points_vs_baseline": rec.get("contributions"), "inputs": rec.get("inputs")},
            "sleep": sleep or None,
            "sleep_need_h": d.get("need"),
            "strain": {k: v for k, v in (d.get("strain") or {}).items() if k != "load"} or None,
            "vitals_vs_personal_range": d.get("health"),
            "garmin": d.get("garmin"),
            "activities": d.get("activities"),
            "journal_about_previous_day": {labels.get(k, k): v for k, v in (d.get("journal") or {}).items()} or None,
            "app_explanation": detail.get("explain"),
            "profile": s.get("profile"),
        }
        if i == len(s["days"]) - 1 and s.get("planner"):
            p = s["planner"]
            out["sleep_plan_tonight"] = {"wake": p["wake"], "wake_source": p["wake_source"], "need_h": p["need"],
                                         "options": [{k: o[k] for k in ("label", "pct", "bedtime", "in_bed_h")} for o in p["options"]]}
        return out

    def tool_get_days(self, start: str | None = None, end: str | None = None) -> dict:
        s = self._summary()
        labels = {q["key"]: q["label"] for q in s.get("journal_questions") or []}
        return {"days": [_row(d, labels) for d in self._range(s, start, end)],
                "units": "recovery %, hrv ms, rhr bpm, resp lần/phút, spo2 %, giờ (h), strain 0–21, stress_hi_min = phút stress vừa + cao"}

    def tool_get_trends(self, days: int = DEFAULT_RANGE_DAYS) -> dict:
        if not isinstance(days, int) or not 7 <= days <= MAX_RANGE_DAYS:
            raise ToolError(f"days phải là số nguyên 7–{MAX_RANGE_DAYS}")
        s = self._summary()
        all_days = s["days"]
        cur, prev = all_days[-days:], all_days[-2 * days:-days]
        a, b = _averages(cur), _averages(prev) if len(prev) >= days // 2 else None
        out = {"period": {"from": cur[0]["date"], "to": cur[-1]["date"], **a}}
        if b:
            out["previous"] = {"from": prev[0]["date"], "to": prev[-1]["date"], **b}
            out["change"] = {k: round(a[k] - b[k], 2) for k in a if isinstance(a.get(k), float) and isinstance(b.get(k), float)}
        out["weekly"] = (s.get("insights") or {}).get("weekly", [])[-min(26, math.ceil(days / 7) + 1):]
        return out

    def tool_get_journal_insights(self) -> dict:
        s = self._summary()
        labels = {q["key"]: q["label"] for q in s.get("journal_questions") or []}
        recent = [{"date": d["date"], "yes": [labels.get(k, k) for k, v in d["journal"].items() if v]}
                  for d in s["days"][-14:] if d.get("journal")]
        return {"impact": (s.get("insights") or {}).get("journal", []),
                "entries": sum(1 for d in s["days"] if d.get("journal")),
                "recent_answers": recent,
                "note": "recovery_diff = hồi phục TB các sáng trả lời Có trừ Không; cần ≥3 ngày mỗi bên."}

    def tool_get_activities(self, start: str | None = None, end: str | None = None) -> dict:
        s = self._summary()
        acts = [{"date": d["date"], **a} for d in self._range(s, start, end) for a in d.get("activities") or []]
        return {"activities": acts[-MAX_ACTIVITIES:], "count": len(acts)}

    def tool_get_methodology(self) -> dict:
        s = self._summary()
        return {"methodology": _readme_section("## Cách tính"), "profile": s.get("profile"), "settings": s.get("settings")}


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError as exc:
        raise ToolError(f"Ngày không hợp lệ: {text!r} (dạng YYYY-MM-DD)") from exc


def _row(d: dict, labels: dict) -> dict:
    rec, sl, st, v = d.get("recovery") or {}, d.get("sleep") or {}, d.get("strain") or {}, d.get("vitals") or {}
    sm = (d.get("garmin") or {}).get("stress_min") or {}
    row = {
        "date": d["date"], "recovery": rec.get("score"), "zone": rec.get("zone"),
        "hrv": v.get("hrv"), "rhr": v.get("rhr"), "resp": v.get("resp"), "spo2": v.get("spo2"),
        "sleep_h": sl.get("hours"), "need_h": (d.get("need") or {}).get("total_h"), "sleep_perf": sl.get("performance"),
        "strain": st.get("score"), "strain_target": st.get("target"),
        "workouts": [f"{a.get('name') or a.get('type')} {a.get('duration_min')}min" for a in d.get("activities") or []] or None,
        "stress_hi_min": (sm.get("medium") or 0) + (sm.get("high") or 0) if sm else None,
        "journal_yes": [labels.get(k, k) for k, x in (d.get("journal") or {}).items() if x] or None,
        "partial_day": d.get("partial") or None,
    }
    return {k: x for k, x in row.items() if x is not None}


def _averages(days: list[dict]) -> dict:
    def avg(get, nd=1, skip_partial=False):
        m = mean(get(d) for d in days if not (skip_partial and d.get("partial")))
        return round(m, nd) if m is not None else None

    g = lambda *keys: lambda d: _dig(d, keys)  # noqa: E731
    zones = [_dig(d, ("recovery", "zone")) for d in days]
    return {
        "days": len(days),
        "recovery": avg(g("recovery", "score")),
        "hrv": avg(g("vitals", "hrv")),
        "rhr": avg(g("vitals", "rhr")),
        "resp": avg(g("vitals", "resp"), 2),
        "sleep_h": avg(g("sleep", "hours"), 2),
        "need_h": avg(g("need", "total_h"), 2),
        "sleep_perf": avg(g("sleep", "performance")),
        "strain": avg(g("strain", "score"), skip_partial=True),   # ngày đang dở chưa đủ strain
        "green": zones.count("green"), "yellow": zones.count("yellow"), "red": zones.count("red"),
    }


def _dig(d, keys):
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _readme_section(heading: str) -> str:
    try:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
    except OSError:
        return "Không đọc được README."
    start = text.find(heading)
    if start < 0:
        return "README không có mục cách tính."
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end > 0 else None].strip()


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}
