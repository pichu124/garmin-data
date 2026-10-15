"""Recovery kiểu WHOOP (0–100%) + Health Monitor.

Mỗi chỉ số so với BASELINE CÁ NHÂN 30 ngày trước đó (z-score), gộp có trọng số
rồi đưa qua CDF chuẩn để ra phần trăm:

    composite = 0.55·z(ln HRV) + 0.20·z(−RHR) + 0.20·z(hiệu suất ngủ) − phạt(nhịp thở↑, SpO2↓)
    recovery  = 100·Φ(composite + 0.2)

Ngày "bình thường" (mọi z = 0) ≈ 58% — xấp xỉ trung bình thành viên WHOOP.
Vùng: ≥67 xanh, 34–66 vàng, ≤33 đỏ.
"""
from __future__ import annotations

import math

from .stats import Baseline, clamp, norm_cdf

WEIGHTS = {"hrv": 0.55, "rhr": 0.20, "sleep": 0.20}
OFFSET = 0.2
SLEEP_REF, SLEEP_SCALE = 80.0, 15.0   # hiệu suất ngủ 80% = trung tính
RESP_PENALTY_W, SPO2_PENALTY_W = 0.15, 0.10
# chặn dưới độ lệch baseline (đơn vị gốc; HRV theo ln)
SD_FLOORS = {"hrv_ln": 0.06, "rhr": 1.5, "resp": 0.4, "spo2": 0.8}
HEALTH_SD_FLOORS = {"hrv": 4.0, "rhr": 1.5, "resp": 0.4, "spo2": 0.8}
HEALTH_BAND = 1.5   # Health Monitor: ngoài mean ± 1,5·sd ⇒ "ngoài ngưỡng"

ZONES = (("green", 67), ("yellow", 34), ("red", 0))


def zone(score: float | None) -> str | None:
    if score is None:
        return None
    for name, lo in ZONES:
        if score >= lo:
            return name
    return "red"


def _z(value: float | None, base: Baseline | None, *, invert: bool = False, log: bool = False) -> float | None:
    if value is None or base is None:
        return None
    v = math.log(value) if log else value
    z = (v - base.mean) / base.sd
    return clamp(-z if invert else z, -3.0, 3.0)


def compute(
    *,
    hrv: float | None,
    rhr: float | None,
    sleep_perf: float | None,
    resp: float | None,
    spo2: float | None,
    bases: dict[str, Baseline | None],
) -> dict:
    """bases: hrv_ln, rhr, resp, spo2 (Baseline hoặc None khi chưa đủ ngày)."""
    z = {
        "hrv": _z(hrv, bases.get("hrv_ln"), log=True),
        "rhr": _z(rhr, bases.get("rhr"), invert=True),
        "sleep": clamp((sleep_perf - SLEEP_REF) / SLEEP_SCALE, -2.5, 1.5) if sleep_perf is not None else None,
    }
    z_resp = _z(resp, bases.get("resp"))
    z_spo2 = _z(spo2, bases.get("spo2"))
    penalties = {
        "resp": -RESP_PENALTY_W * max(0.0, z_resp - 1.0) if z_resp is not None else 0.0,
        "spo2": -SPO2_PENALTY_W * max(0.0, -z_spo2 - 1.0) if z_spo2 is not None else 0.0,
    }
    if z["hrv"] is None and z["rhr"] is None:
        calibrating = hrv is not None or rhr is not None
        return {"score": None, "zone": None, "calibrating": calibrating, "inputs": [], "contributions": {}}

    # Thiếu chỉ số (đồng hồ không đo HRV…) ⇒ chia lại trọng số cho phần còn lại
    weights = {k: w for k, w in WEIGHTS.items() if z[k] is not None}
    scale = sum(WEIGHTS.values()) / sum(weights.values())
    terms = {k: w * scale * z[k] for k, w in weights.items()}
    composite = sum(terms.values()) + sum(penalties.values())
    score = 100 * norm_cdf(composite + OFFSET)

    # Đóng góp = điểm thay đổi bao nhiêu nếu chỉ số đó ở đúng mức baseline
    contributions = {
        k: round(score - 100 * norm_cdf(composite - t + OFFSET), 1) for k, t in {**terms, **penalties}.items() if t
    }
    score = round(clamp(score, 1, 99))
    return {
        "score": score,
        "zone": zone(score),
        "calibrating": False,
        "inputs": sorted(weights),
        "contributions": contributions,
        "z": {k: (round(v, 2) if v is not None else None) for k, v in {**z, "resp": z_resp, "spo2": z_spo2}.items()},
    }


def health_monitor(values: dict[str, float | None], bases: dict[str, Baseline | None]) -> dict:
    """Từng chỉ số: giá trị, baseline, ngưỡng [lo, hi], trạng thái in/high/low."""
    out = {}
    for key, value in values.items():
        base = bases.get(key)
        item = {"value": value, "mean": None, "lo": None, "hi": None, "status": None}
        if base is not None:
            band = HEALTH_BAND * base.sd
            item.update(mean=round(base.mean, 1), lo=round(base.mean - band, 1), hi=round(base.mean + band, 1))
            if value is not None:
                item["status"] = "high" if value > item["hi"] else "low" if value < item["lo"] else "in"
        out[key] = item
    return out
