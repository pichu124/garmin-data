"""Phân tích tổng hợp: tác động của thói quen (Journal) và tổng kết theo tuần."""
from __future__ import annotations

import math
from datetime import date, timedelta

from .stats import mean

MIN_PER_SIDE = 3   # cần ≥3 ngày "Có" và ≥3 ngày "Không" mới so được


def _welch(a: list[float], b: list[float]) -> tuple[float, float | None]:
    diff = sum(a) / len(a) - sum(b) / len(b)
    var = lambda xs: sum((x - sum(xs) / len(xs)) ** 2 for x in xs) / (len(xs) - 1)  # noqa: E731
    se = math.sqrt(var(a) / len(a) + var(b) / len(b))
    return diff, (diff / se if se > 0 else None)


def journal_impact(days: list[dict], questions: list[dict]) -> list[dict]:
    """Recovery TB khi trả lời Có so với Không (câu hỏi buổi sáng về hôm qua).

    `significant` khi |t| ≥ 2 (Welch) — dưới ngưỡng này chênh lệch có thể chỉ là nhiễu.
    """
    out = []
    for q in questions:
        key = q["key"]
        groups: dict[bool, dict[str, list[float]]] = {
            True: {"rec": [], "sleep": []},
            False: {"rec": [], "sleep": []},
        }
        for d in days:
            ans = (d.get("journal") or {}).get(key)
            rec = (d.get("recovery") or {}).get("score")
            if ans is None or rec is None:
                continue
            groups[ans]["rec"].append(rec)
            perf = (d.get("sleep") or {}).get("performance")
            if perf is not None:
                groups[ans]["sleep"].append(perf)
        yes, no = groups[True], groups[False]
        item = {"key": key, "label": q["label"], "n_yes": len(yes["rec"]), "n_no": len(no["rec"])}
        if len(yes["rec"]) >= MIN_PER_SIDE and len(no["rec"]) >= MIN_PER_SIDE:
            diff, t = _welch(yes["rec"], no["rec"])
            item.update(
                recovery_diff=round(diff, 1),
                recovery_yes=round(mean(yes["rec"]), 1),
                recovery_no=round(mean(no["rec"]), 1),
                t=round(t, 2) if t is not None else None,
                significant=t is not None and abs(t) >= 2,
            )
            if len(yes["sleep"]) >= MIN_PER_SIDE and len(no["sleep"]) >= MIN_PER_SIDE:
                item["sleep_diff"] = round(mean(yes["sleep"]) - mean(no["sleep"]), 1)
        out.append(item)
    out.sort(key=lambda x: (x.get("recovery_diff") is None, -abs(x.get("recovery_diff") or 0)))
    return out


def weekly(days: list[dict], weeks: int = 26) -> list[dict]:
    """Trung bình theo tuần (thứ Hai → Chủ nhật), mới nhất cuối danh sách."""
    buckets: dict[str, list[dict]] = {}
    for d in days:
        day = date.fromisoformat(d["date"])
        monday = (day - timedelta(days=day.weekday())).isoformat()
        buckets.setdefault(monday, []).append(d)
    out = []
    for monday in sorted(buckets)[-weeks:]:
        ds = buckets[monday]
        recs = [(d.get("recovery") or {}).get("score") for d in ds]
        zones = [(d.get("recovery") or {}).get("zone") for d in ds]
        out.append({
            "week": monday,
            "days": len(ds),
            "recovery": _r(mean(recs)),
            # ngày hôm nay còn đang tích strain ⇒ không tính vào trung bình tuần
            "strain": _r(mean((d.get("strain") or {}).get("score") for d in ds if not d.get("partial")), 1),
            "sleep_perf": _r(mean((d.get("sleep") or {}).get("performance") for d in ds)),
            "sleep_h": _r(mean((d.get("sleep") or {}).get("hours") for d in ds), 2),
            "hrv": _r(mean((d.get("vitals") or {}).get("hrv") for d in ds), 1),
            "rhr": _r(mean((d.get("vitals") or {}).get("rhr") for d in ds), 1),
            "green": zones.count("green"),
            "yellow": zones.count("yellow"),
            "red": zones.count("red"),
        })
    return out


def _r(x: float | None, nd: int = 0):
    if x is None:
        return None
    return round(x, nd) if nd else round(x)
