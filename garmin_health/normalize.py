"""Raw JSON của Garmin Connect → bản ghi gọn, chịu được thiếu khoá/None.

Quy ước thời gian: mọi mốc là epoch ms theo GMT (int). Đổi sang giờ địa phương
bằng `tz_offset_ms` của ngày đó (Garmin trả cả bản Local lẫn GMT).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

# Garmin sleepLevels.activityLevel → giai đoạn ngủ
STAGE_BY_LEVEL = {0: "deep", 1: "light", 2: "rem", 3: "awake"}
DAY_MS = 86_400_000
_EPOCH = datetime(1970, 1, 1)


def parse_ts(value: Any) -> int | None:
    """'2024-01-01T22:30:00.0' | '2024-01-01 22:30:00' | epoch ms → epoch ms (coi như UTC)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace("T", " ")
    s = s.split(".")[0]
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return calendar.timegm(dt.timetuple()) * 1000


def date_ms(day: str) -> int:
    """Nửa đêm 'YYYY-MM-DD' dưới dạng epoch ms (naive, như UTC)."""
    d = date.fromisoformat(day)
    return calendar.timegm(d.timetuple()) * 1000


def ms_to_day(ms: int) -> str:
    """epoch ms (naive local) → 'YYYY-MM-DD'."""
    return (_EPOCH + timedelta(milliseconds=ms)).date().isoformat()


def num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # loại NaN


def pos(value: Any) -> float | None:
    """Số dương, còn lại None (Garmin dùng 0/-1/-2 cho 'không đo được')."""
    f = num(value)
    return f if f is not None and f > 0 else None


def _dig(obj: Any, *keys: Any) -> Any:
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return None
    return obj


def tz_offset_ms(*raws: Any) -> int | None:
    """Lệch giờ địa phương − GMT, suy từ cặp startTimestampLocal/GMT bất kỳ."""
    pairs = (
        ("startTimestampLocal", "startTimestampGMT"),
        ("sleepStartTimestampLocal", "sleepStartTimestampGMT"),
        ("wellnessStartTimeLocal", "wellnessStartTimeGmt"),
    )
    for raw in raws:
        for obj in (raw, _dig(raw, "dailySleepDTO")):
            if not isinstance(obj, dict):
                continue
            for local_key, gmt_key in pairs:
                local, gmt = parse_ts(obj.get(local_key)), parse_ts(obj.get(gmt_key))
                if local is not None and gmt is not None:
                    # làm tròn 15 phút — có múi giờ lệch 30/45 phút
                    return round((local - gmt) / 900_000) * 900_000
    return None


def series(rows: Any, value_index: int = 1) -> list[tuple[int, float]]:
    """[[ts, v], …] → [(ts, v)] bỏ điểm None/≤0, sắp theo thời gian."""
    out = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) <= value_index:
            continue
        t, v = parse_ts(row[0]), pos(row[value_index])
        if t is not None and v is not None:
            out.append((t, v))
    out.sort()
    return out


def heart_rates(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "samples": series(raw.get("heartRateValues")),
        "rhr": pos(raw.get("restingHeartRate")),
        "max": pos(raw.get("maxHeartRate")),
    }


def summary(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "rhr": pos(raw.get("restingHeartRate")),
        "steps": num(raw.get("totalSteps")),
        "calories": pos(raw.get("totalKilocalories")),
        "active_calories": num(raw.get("activeKilocalories")),
        "stress_avg": pos(raw.get("averageStressLevel")),
        "bb_high": pos(raw.get("bodyBatteryHighestValue")),
        "bb_low": pos(raw.get("bodyBatteryLowestValue")),
        "bb_charged": num(raw.get("bodyBatteryChargedValue")),
        "bb_drained": num(raw.get("bodyBatteryDrainedValue")),
        "spo2_avg": pos(raw.get("averageSpo2")),
        "resp_waking": pos(raw.get("avgWakingRespirationValue")),
        "intensity_min": (num(raw.get("moderateIntensityMinutes")) or 0)
        + 2 * (num(raw.get("vigorousIntensityMinutes")) or 0),
        "distance_m": num(raw.get("totalDistanceMeters")),
    }


def _timed_values(rows: Any, t_key: str, v_key: str) -> list[tuple[int, float]]:
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        t, v = parse_ts(row.get(t_key)), pos(row.get(v_key))
        if t is not None and v is not None:
            out.append((t, v))
    out.sort()
    return out


def sleep(raw: Any) -> dict | None:
    """Giấc ngủ KẾT THÚC vào sáng calendarDate. None nếu đêm đó không có dữ liệu."""
    raw = raw if isinstance(raw, dict) else {}
    dto = raw.get("dailySleepDTO") or {}
    start, end = parse_ts(dto.get("sleepStartTimestampGMT")), parse_ts(dto.get("sleepEndTimestampGMT"))
    sleep_s = pos(dto.get("sleepTimeSeconds"))
    if start is None or end is None or end <= start or not sleep_s:
        return None
    levels = []
    for row in raw.get("sleepLevels") or []:
        a, b = parse_ts(row.get("startGMT")), parse_ts(row.get("endGMT"))
        lvl = num(row.get("activityLevel"))
        if a is None or b is None or b <= a or lvl is None:
            continue
        stage = STAGE_BY_LEVEL.get(int(round(lvl)))
        if stage:
            levels.append((a, b, stage))
    levels.sort()
    spo2 = pos(dto.get("averageSpO2Value")) or pos(_dig(raw, "wellnessSpO2SleepSummaryDTO", "averageSPO2"))
    return {
        "start": start,
        "end": end,
        # bản Local riêng của giấc ngủ — đúng cả khi đổi giờ (DST) / đi khác múi giữa ngày
        "start_local": parse_ts(dto.get("sleepStartTimestampLocal")),
        "sleep_s": sleep_s,
        "deep_s": num(dto.get("deepSleepSeconds")) or 0.0,
        "light_s": num(dto.get("lightSleepSeconds")) or 0.0,
        "rem_s": num(dto.get("remSleepSeconds")) or 0.0,
        "awake_s": num(dto.get("awakeSleepSeconds")) or 0.0,
        "nap_s": num(dto.get("napTimeSeconds")) or 0.0,
        "resp": pos(dto.get("averageRespirationValue")),
        "spo2": spo2,
        "awake_count": num(dto.get("awakeCount")),
        "garmin_score": pos(_dig(dto, "sleepScores", "overall", "value")),
        "avg_stress": pos(dto.get("avgSleepStress")),
        "rhr": pos(raw.get("restingHeartRate")),
        "hrv": pos(raw.get("avgOvernightHrv")),
        "bb_change": num(raw.get("bodyBatteryChange")),
        "levels": levels,
        "hr": _timed_values(raw.get("sleepHeartRate"), "startGMT", "value"),
        "hrv_series": _timed_values(raw.get("hrvData"), "startGMT", "value"),
    }


def nap_seconds(raw: Any) -> float:
    """Ngủ trưa trong NGÀY calendarDate (có cả khi không có giấc đêm)."""
    return num(_dig(raw, "dailySleepDTO", "napTimeSeconds")) or 0.0


def hrv(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    s = raw.get("hrvSummary") or {}
    base = s.get("baseline") or {}
    return {
        "last_night": pos(s.get("lastNightAvg")),
        "weekly": pos(s.get("weeklyAvg")),
        "high_5min": pos(s.get("lastNight5MinHigh")),
        "status": s.get("status"),
        "base_low": pos(base.get("balancedLow")),
        "base_high": pos(base.get("balancedUpper")),
        "readings": _timed_values(raw.get("hrvReadings"), "readingTimeGMT", "hrvValue"),
    }


def stress(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    bb = []
    for row in raw.get("bodyBatteryValuesArray") or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        # [ts, "MEASURED", level, version] hoặc [ts, level]
        level = row[2] if len(row) >= 3 and isinstance(row[2], (int, float)) else row[1]
        t, v = parse_ts(row[0]), num(level)
        if t is not None and v is not None and v >= 0:
            bb.append((t, v))
    bb.sort()
    return {"stress": series(raw.get("stressValuesArray")), "body_battery": bb}


def readiness(raw: Any) -> dict:
    rows = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    rows = [r for r in rows if isinstance(r, dict) and pos(r.get("score")) is not None]
    if not rows:
        return {"score": None, "level": None}
    morning = [r for r in rows if r.get("inputContext") == "AFTER_WAKEUP_RESET"]
    pick = (morning or sorted(rows, key=lambda r: str(r.get("timestamp") or "")))[-1]
    return {"score": pos(pick.get("score")), "level": pick.get("level")}


def vo2max(raw: Any) -> float | None:
    rows = raw if isinstance(raw, list) else [raw]
    for row in rows:
        generic = _dig(row, "generic")
        v = pos(_dig(generic, "vo2MaxPreciseValue")) or pos(_dig(generic, "vo2MaxValue"))
        if v:
            return round(v, 1)
    return None


def activity(raw: Any) -> dict | None:
    if not isinstance(raw, dict) or raw.get("activityId") is None:
        return None
    start = parse_ts(raw.get("startTimeGMT"))
    start_local = parse_ts(raw.get("startTimeLocal"))
    duration = pos(raw.get("duration")) or pos(raw.get("elapsedDuration"))
    if start is None or start_local is None or not duration:
        return None
    return {
        "id": str(raw["activityId"]),
        "name": raw.get("activityName") or "",
        "type": _dig(raw, "activityType", "typeKey") or "other",
        "start": start,
        "start_local": start_local,
        "date": ms_to_day(start_local),
        "duration_s": duration,
        "distance_m": num(raw.get("distance")),
        "calories": num(raw.get("calories")),
        "avg_hr": pos(raw.get("averageHR")),
        "max_hr": pos(raw.get("maxHR")),
        "aerobic_te": num(raw.get("aerobicTrainingEffect")),
        "anaerobic_te": num(raw.get("anaerobicTrainingEffect")),
        "training_load": num(raw.get("activityTrainingLoad")),
    }


def profile(user_settings: Any, hr_zones: Any) -> dict:
    data = _dig(user_settings, "userData") or {}
    sex = str(data.get("gender") or "").lower() or None
    birth = data.get("birthDate")
    birth_year = int(birth[:4]) if isinstance(birth, str) and birth[:4].isdigit() else None
    hr_max = None
    for zone in hr_zones if isinstance(hr_zones, list) else []:
        if isinstance(zone, dict) and pos(zone.get("maxHeartRateUsed")):
            if hr_max is None or zone.get("sport") == "DEFAULT":
                hr_max = pos(zone.get("maxHeartRateUsed"))
    wake = num(_dig(user_settings, "userSleep", "wakeTime"))
    return {
        "sex": sex if sex in ("male", "female") else None,
        "birth_year": birth_year,
        "hr_max": hr_max,
        "wake_min": int(wake // 60) if wake is not None else None,
    }
