"""Giấc ngủ kiểu WHOOP: nhu cầu ngủ, nợ ngủ, độ đều, hiệu suất, Sleep Planner."""
from __future__ import annotations

from typing import Sequence

from .stats import circular_diff_minutes, circular_mean_minutes, clamp

STRAIN_NEED_MAX_H = 1.0          # strain 21 ⇒ cần ngủ thêm tối đa 1 giờ
STRAIN_NEED_FROM = 8.0           # strain dưới 8 không làm tăng nhu cầu ngủ
DEBT_WEIGHTS = (0.5, 0.25, 0.125)  # phần thiếu của 3 đêm gần nhất được "trả" dần
DEBT_CAP_H = 1.5
NAP_CREDIT_MAX_H = 1.5
CONSISTENCY_NIGHTS = 4
# Hiệu suất ngủ = đủ giờ (chính) + hiệu quả + độ đều (WHOOP 2023 gộp các ý này)
PERF_WEIGHTS = {"sufficiency": 0.70, "efficiency": 0.15, "consistency": 0.15}
# Sleep Planner: 3 mức như WHOOP
PLANNER_LEVELS = (("peak", "Đỉnh", 1.0), ("perform", "Tốt", 0.85), ("get_by", "Tạm đủ", 0.70))


def strain_adjustment_h(prev_strain: float | None) -> float:
    if not prev_strain:
        return 0.0
    return STRAIN_NEED_MAX_H * max(0.0, prev_strain - STRAIN_NEED_FROM) / (21.0 - STRAIN_NEED_FROM)


def sleep_debt_h(shortfalls_h: Sequence[float | None]) -> float:
    """shortfalls_h[0] = đêm gần nhất. Mỗi phần tử = max(0, nhu cầu − giờ ngủ)."""
    debt = sum(w * (s or 0.0) for w, s in zip(DEBT_WEIGHTS, shortfalls_h))
    return min(DEBT_CAP_H, debt)


def sleep_need(
    *, baseline_h: float, prev_strain: float | None, shortfalls_h: Sequence[float | None], nap_h: float = 0.0
) -> dict:
    strain_h = strain_adjustment_h(prev_strain)
    debt_h = sleep_debt_h(shortfalls_h)
    nap_credit = min(nap_h or 0.0, NAP_CREDIT_MAX_H)
    total = max(4.0, baseline_h + strain_h + debt_h - nap_credit)
    return {
        "total_h": round(total, 2),
        "baseline_h": round(baseline_h, 2),
        "strain_h": round(strain_h, 2),
        "debt_h": round(debt_h, 2),
        "nap_h": round(-nap_credit, 2),
    }


def consistency(onsets_min: Sequence[float], wakes_min: Sequence[float]) -> float | None:
    """0–100: giờ đi ngủ/thức dậy của ≤4 đêm gần nhất lệch nhau bao nhiêu.

    Lệch trung bình 30' cả hai đầu ⇒ ~70; giờ giấc y hệt ⇒ 100.
    """
    if len(onsets_min) < 2 or len(wakes_min) < 2:
        return None

    def mad(vals: Sequence[float]) -> float:
        c = circular_mean_minutes(vals)
        return sum(circular_diff_minutes(v, c) for v in vals) / len(vals)

    return round(clamp(100 - 0.5 * (mad(onsets_min) + mad(wakes_min)), 0, 100))


def performance(*, slept_h: float, need_h: float, efficiency: float | None, consistency_pct: float | None) -> dict:
    sufficiency = clamp(slept_h / need_h, 0, 1) * 100 if need_h else 0
    parts = {"sufficiency": sufficiency, "efficiency": efficiency, "consistency": consistency_pct}
    weights = {k: w for k, w in PERF_WEIGHTS.items() if parts[k] is not None}
    total_w = sum(weights.values())
    score = sum(parts[k] * w for k, w in weights.items()) / total_w
    return {"score": round(clamp(score, 0, 100)), "sufficiency": round(sufficiency)}


def plan_bedtimes(*, need_h: float, wake_min: float, efficiency: float | None) -> list[dict]:
    """Giờ lên giường để đạt từng mức (trừ hao thời gian thức trong đêm)."""
    eff = clamp((efficiency or 90) / 100, 0.75, 0.98)
    out = []
    for key, label, level in PLANNER_LEVELS:
        in_bed_min = need_h * level / eff * 60
        out.append({
            "key": key,
            "label": label,
            "pct": round(level * 100),
            "bedtime_min": round((wake_min - in_bed_min) % 1440),
            "in_bed_h": round(in_bed_min / 60, 2),
        })
    return out
