"""Strain kiểu WHOOP: tải tim mạch (TRIMP theo %HRR) → thang logarit 0–21.

WHOOP không công bố công thức. Ở đây dùng TRIMP Banister (mỗi phút nặng ký
theo hàm mũ của %HRR), bỏ qua nhịp tim sinh hoạt thấp (< 20% HRR), rồi ép về
0–21 bằng đường bão hoà `21·(1 − e^(−load/K))` — càng lên cao càng khó tăng,
đúng cảm giác "logarit" của WHOOP. K hiệu chỉnh để: ngày chỉ đi lại ≈ 4–6,
chạy 60' vừa sức ≈ 12–14, 2,5h cường độ cao ≈ 18–19.
"""
from __future__ import annotations

import math
from typing import Sequence

STRAIN_MAX = 21.0
STRAIN_K = 176.0
FLOOR_LO, FLOOR_HI = 0.20, 0.30   # dưới 20% HRR không tính, 20→30% tăng dần
MAX_GAP_S = 300                   # mẫu HR cách nhau > 5' ⇒ coi là mất tín hiệu
DEFAULT_STEP_S = 120              # Garmin ghi HR cả ngày mỗi 2 phút
# Vùng tim WHOOP theo %HRR: Z1 50–60 … Z5 90–100
ZONE_EDGES = (0.5, 0.6, 0.7, 0.8, 0.9)

# hệ số Banister theo giới
_BANISTER = {"female": (0.86, 1.67), "male": (0.64, 1.92)}


def hrr_fraction(hr: float, rhr: float, hr_max: float) -> float:
    span = max(hr_max - rhr, 20.0)
    return (hr - rhr) / span


def trimp_per_min(x: float, sex: str | None = None) -> float:
    if x <= FLOOR_LO:
        return 0.0
    x = min(x, 1.1)
    a, b = _BANISTER.get(sex or "male", _BANISTER["male"])
    w = x * a * math.exp(b * x)
    if x < FLOOR_HI:
        w *= (x - FLOOR_LO) / (FLOOR_HI - FLOOR_LO)
    return w


def zone_of(x: float) -> int:
    """0 = dưới vùng 1; 1..5 theo ZONE_EDGES."""
    z = 0
    for i, edge in enumerate(ZONE_EDGES, start=1):
        if x >= edge:
            z = i
    return z


def cardio_load(
    samples: Sequence[tuple[int, float]],
    *,
    rhr: float,
    hr_max: float,
    sex: str | None = None,
    t0: int | None = None,
    t1: int | None = None,
) -> tuple[float, list[float]]:
    """(tải TRIMP, phút trong vùng 0..5) cho mẫu HR nằm trong [t0, t1)."""
    pts = [(t, hr) for t, hr in samples if (t0 is None or t >= t0) and (t1 is None or t < t1)]
    zones = [0.0] * 6
    load = 0.0
    for i, (t, hr) in enumerate(pts):
        if i + 1 < len(pts):
            step = (pts[i + 1][0] - t) / 1000
            if step > MAX_GAP_S:
                step = DEFAULT_STEP_S
        else:
            step = DEFAULT_STEP_S
        if t1 is not None:
            step = min(step, max(0.0, (t1 - t) / 1000))
        minutes = step / 60
        x = hrr_fraction(hr, rhr, hr_max)
        load += trimp_per_min(x, sex) * minutes
        zones[zone_of(x)] += minutes
    return load, zones


def strain_from_load(load: float) -> float:
    if load <= 0:
        return 0.0
    return round(STRAIN_MAX * (1 - math.exp(-load / STRAIN_K)), 1)


def strain_target(recovery: float | None) -> tuple[float, float] | None:
    """Strain Coach: khoảng strain tối ưu theo recovery (xanh ≈ 14–18, đỏ < 10)."""
    if recovery is None:
        return None
    center = 4.0 + 0.14 * recovery
    return (round(max(0.0, center - 1.5), 1), round(min(STRAIN_MAX, center + 1.5), 1))


def estimate_hr_max(
    *,
    configured: float | None,
    garmin: float | None,
    birth_year: int | None,
    year: int,
    observed: Sequence[float],
) -> tuple[float, str]:
    """Nhịp tối đa: cài đặt > Garmin > công thức Tanaka (208 − 0,7·tuổi) > dữ liệu.

    Khi có cả công thức lẫn dữ liệu, lấy max của hai (người tập nặng hay vượt
    công thức), nhưng dùng giá trị CAO THỨ HAI của dữ liệu để loại spike lỗi cảm biến.
    """
    if configured:
        return float(configured), "cài đặt"
    if garmin:
        return float(garmin), "Garmin"
    obs = sorted(v for v in observed if v and 100 < v < 230)
    robust_obs = obs[-2] if len(obs) >= 2 else (obs[-1] if obs else None)
    if birth_year:
        formula = 208 - 0.7 * (year - birth_year)
        if robust_obs and robust_obs > formula:
            return float(robust_obs), "dữ liệu"
        return round(formula), "tuổi"
    if robust_obs and robust_obs >= 160:
        return float(robust_obs), "dữ liệu"
    return 190.0, "mặc định"
