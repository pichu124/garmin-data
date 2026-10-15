"""Tiện ích thống kê thuần (không numpy) — baseline cá nhân, CDF chuẩn, thời gian vòng."""
from __future__ import annotations

import math
from typing import Iterable, NamedTuple, Sequence

MIN_BASELINE_DAYS = 4   # WHOOP cần 4 ngày để "hiệu chỉnh"
BASELINE_WINDOW = 30    # baseline = 30 ngày TRƯỚC ngày đang xét (không gồm hôm nay)


class Baseline(NamedTuple):
    mean: float
    sd: float
    n: int


def clean(values: Iterable[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None]


def mean(values: Iterable[float | None]) -> float | None:
    vals = clean(values)
    return sum(vals) / len(vals) if vals else None


def median(values: Iterable[float | None]) -> float | None:
    vals = sorted(clean(values))
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def baseline(
    history: Sequence[float | None],
    *,
    sd_floor: float,
    min_n: int = MIN_BASELINE_DAYS,
    transform=None,
) -> Baseline | None:
    """Trung bình ± độ lệch của `history` (đã cắt cửa sổ ở chỗ gọi).

    `sd_floor` chặn dưới độ lệch: vài ngày đầu số liệu gần giống nhau làm sd ≈ 0
    ⇒ z-score bùng nổ. Floor giữ điểm ổn định trong giai đoạn hiệu chỉnh.
    """
    vals = clean(history)
    if transform:
        vals = [transform(v) for v in vals]
    if len(vals) < min_n:
        return None
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1) if len(vals) > 1 else 0.0
    return Baseline(m, max(math.sqrt(var), sd_floor), len(vals))


def window(values: Sequence, idx: int, size: int = BASELINE_WINDOW) -> Sequence:
    """Các giá trị TRƯỚC vị trí idx, tối đa `size` phần tử."""
    return values[max(0, idx - size) : idx]


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def circular_mean_minutes(minutes: Sequence[float], period: float = 1440.0) -> float:
    """Trung bình giờ trong ngày (23:50 và 00:10 → 00:00, không phải 12:00)."""
    s = sum(math.sin(2 * math.pi * m / period) for m in minutes)
    c = sum(math.cos(2 * math.pi * m / period) for m in minutes)
    ang = math.atan2(s, c)
    return (ang / (2 * math.pi) * period) % period


def circular_diff_minutes(a: float, b: float, period: float = 1440.0) -> float:
    d = (a - b) % period
    return min(d, period - d)
