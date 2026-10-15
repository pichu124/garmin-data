"""Sinh dữ liệu MẪU đúng định dạng JSON của Garmin Connect.

Dùng để: xem giao diện khi chưa đăng nhập, chạy test end-to-end cả pipeline
(raw → normalize → điểm), và làm bản xem trước. Sinh lý có quy luật để các
phân tích có thứ mà tìm: strain cao ⇒ HRV đêm sau giảm, rượu ⇒ HRV↓ RHR↑,
một đợt ốm 3 ngày ⇒ nhịp thở↑ recovery đỏ, thể lực tăng dần theo tuần.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone

from .config import DEFAULT_JOURNAL_QUESTIONS, Paths, write_json
from .raw_store import RawStore

TZ_MS = 7 * 3_600_000          # Việt Nam UTC+7
HR_MAX, RHR_BASE, HRV_BASE = 188, 52.0, 58.0
STEP_MS = 120_000              # HR cả ngày mỗi 2 phút như Garmin

# (loại, tên, phút, %HRR mục tiêu) theo thứ trong tuần (0 = thứ Hai)
WEEK_PLAN = {
    0: None,
    1: ("running", "Chạy nhẹ", 45, 0.62),
    2: ("strength_training", "Tập tạ", 50, 0.50),
    3: ("running", "Chạy interval", 50, 0.78),
    4: ("yoga", "Yoga", 40, 0.32),
    5: ("running", "Chạy dài cuối tuần", 105, 0.68),
    6: ("cycling", "Đạp xe", 70, 0.60),
}


def _gmt_str(ms: int, sep: str = "T") -> str:
    dt = datetime(1970, 1, 1) + timedelta(milliseconds=ms)
    return dt.strftime(f"%Y-%m-%d{sep}%H:%M:%S") + (".0" if sep == "T" else "")


def _local_midnight_gmt(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000) - TZ_MS


class _Person:
    def __init__(self, rng: random.Random, n_days: int):
        self.rng = rng
        self.sick_start = rng.randint(n_days // 3, n_days - 20) if n_days > 40 else -99
        self.hrv_week: list[float] = []


def _behaviours(rng: random.Random, sick: bool) -> dict:
    return {
        "alcohol": rng.random() < 0.16,
        "late_meal": rng.random() < 0.25,
        "caffeine_late": rng.random() < 0.30,
        "screen_bed": rng.random() < 0.50,
        "stress_work": rng.random() < 0.30,
        "meditation": rng.random() < 0.30,
        "sauna": rng.random() < 0.08,
        "sick": sick,
    }


def _plan_workout(rng: random.Random, d: date, sick: bool):
    plan = WEEK_PLAN[d.weekday()]
    if plan is None or sick or rng.random() < 0.15:
        return None
    kind, name, minutes, hrr = plan
    minutes = max(20, int(minutes * rng.uniform(0.8, 1.2)))
    start_min = rng.choice([5 * 60 + 40, 6 * 60, 6 * 60 + 15, 17 * 60 + 30, 18 * 60])
    if d.weekday() >= 5:
        start_min = rng.choice([6 * 60, 6 * 60 + 30, 7 * 60])
    return {"type": kind, "name": name, "minutes": minutes, "hrr": hrr + rng.uniform(-0.04, 0.04), "start_min": start_min}


def generate(paths: Paths, *, days: int = 120, seed: int = 7, now: datetime | None = None, log=print) -> None:
    rng = random.Random(seed)
    store = RawStore(paths.raw)
    now = now or datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    today = (now + timedelta(milliseconds=TZ_MS)).date()
    dates = [today - timedelta(days=days - 1 - i) for i in range(days)]
    person = _Person(rng, days)

    store.save_profile("user_settings", {
        "userData": {"gender": "MALE", "birthDate": "1992-06-15", "weight": 68000.0, "height": 172.0},
        "userSleep": {"sleepTime": 23 * 3600, "wakeTime": 6 * 3600 + 30 * 60},
    })
    store.save_profile("hr_zones", [{"sport": "DEFAULT", "trainingMethod": "HR_RESERVE",
                                     "maxHeartRateUsed": HR_MAX, "restingHeartRateUsed": int(RHR_BASE)}])

    # 1) quyết định mọi đêm/ngày trước, vì HR của ngày d cần giờ đi ngủ của đêm d→d+1
    plan = []
    prev_strain_proxy = 0.0
    for i, d in enumerate(dates):
        sick = person.sick_start <= i < person.sick_start + 3
        beh = _behaviours(rng, sick)          # hành vi của HÔM QUA (hỏi sáng nay)
        fitness = i / max(1, days)            # thể lực tăng dần
        workout = _plan_workout(rng, d, sick)
        bed = 23 * 60 + 10 + rng.gauss(0, 35) + 35 * beh["late_meal"] + 25 * beh["screen_bed"] + 20 * beh["alcohol"]
        sleep_h = rng.gauss(7.3, 0.55) - 0.4 * beh["alcohol"] - 0.3 * beh["caffeine_late"] - 0.25 * beh["screen_bed"]
        sleep_h += 0.6 * (d.weekday() >= 5) + 0.5 * sick
        sleep_h = min(9.5, max(4.8, sleep_h))
        ln_hrv = (math.log(HRV_BASE) + 0.10 * fitness - 0.07 * (prev_strain_proxy - 10) / 5
                  - 0.20 * beh["alcohol"] - 0.06 * beh["late_meal"] - 0.07 * beh["stress_work"]
                  + 0.05 * beh["meditation"] - 0.35 * sick + 0.07 * (sleep_h - 7.3) + rng.gauss(0, 0.08))
        rhr = (RHR_BASE - 1.5 * fitness + 2.8 * beh["alcohol"] + 1.0 * beh["late_meal"]
               + 1.0 * (prev_strain_proxy - 10) / 5 + 6 * sick + rng.gauss(0, 1.1))
        plan.append({
            "date": d, "beh": beh, "sick": sick, "workout": workout, "bed_min": bed, "sleep_h": sleep_h,
            "hrv": math.exp(ln_hrv), "rhr": rhr, "resp": 14.4 + 1.6 * sick + rng.gauss(0, 0.25),
            "spo2": min(99.0, 96.2 - 1.2 * sick + rng.gauss(0, 0.6)),
        })
        prev_strain_proxy = 6 + (workout["minutes"] * workout["hrr"] ** 2 / 4 if workout else 0)

    journal = {"questions": DEFAULT_JOURNAL_QUESTIONS, "entries": {}}
    act_id = 20_000_000_000
    for i, p in enumerate(plan):
        d = p["date"]
        key = d.isoformat()
        day0 = _local_midnight_gmt(d)
        # đêm KẾT THÚC sáng d: đi ngủ tối d-1 (bed_min có thể > 24h ⇒ sau nửa đêm)
        sleep_start = day0 - 1440 * 60000 + int(p["bed_min"] * 60000)
        in_bed_min = p["sleep_h"] * 60 / rng.uniform(0.88, 0.94)
        sleep_end = sleep_start + int(in_bed_min * 60000)
        if sleep_end > now_ms:
            break
        nxt = plan[i + 1] if i + 1 < len(plan) else None
        next_bed = day0 + int(nxt["bed_min"] * 60000) if nxt else day0 + 1440 * 60000

        levels, sleep_hr, hrv_rows, stage_s = _sleep_night(rng, p, sleep_start, sleep_end)
        store.save("sleep", key, _sleep_raw(p, key, sleep_start, sleep_end, levels, sleep_hr, hrv_rows, stage_s))
        person.hrv_week = (person.hrv_week + [p["hrv"]])[-7:]
        store.save("hrv", key, _hrv_raw(p, key, hrv_rows, person.hrv_week, sleep_start, sleep_end))

        workout = p["workout"]
        act = None
        if workout:
            # buổi sáng mà dậy muộn hơn giờ tập ⇒ dời tới 20' sau khi dậy
            w_start = max(day0 + workout["start_min"] * 60000, sleep_end + 20 * 60000)
            if w_start + workout["minutes"] * 60000 <= now_ms:
                act_id += rng.randint(1000, 9000)
                act = {"id": act_id, "start": w_start, "end": w_start + workout["minutes"] * 60000, **workout}

        day_end = min(day0 + 1440 * 60000, now_ms)
        hr = _day_hr(rng, p, day0, day_end, sleep_end, next_bed, act)
        stress, bb = _stress_bb(rng, p, day0, day_end, sleep_end, next_bed, act)
        store.save("heart_rates", key, {
            "calendarDate": key,
            "startTimestampGMT": _gmt_str(day0), "startTimestampLocal": _gmt_str(day0 + TZ_MS),
            "restingHeartRate": round(p["rhr"]), "maxHeartRate": max(v for _, v in hr),
            "minHeartRate": min(v for _, v in hr),
            "heartRateValueDescriptors": [{"key": "timestamp", "index": 0}, {"key": "heartrate", "index": 1}],
            "heartRateValues": [[t, v] for t, v in hr],
        })
        store.save("stress", key, {
            "calendarDate": key, "startTimestampGMT": _gmt_str(day0), "startTimestampLocal": _gmt_str(day0 + TZ_MS),
            "avgStressLevel": round(sum(v for _, v in stress if v > 0) / max(1, sum(1 for _, v in stress if v > 0))),
            "stressValuesArray": [[t, v] for t, v in stress],
            "bodyBatteryValuesArray": [[t, "MEASURED", v, 2.0] for t, v in bb],
        })
        steps = int(rng.gauss(8500, 2200) + (workout["minutes"] * 140 if act and workout["type"] == "running" else 0))
        act_kcal = round(workout["minutes"] * (6 + 10 * workout["hrr"]) if act else 0)
        store.save("summary", key, {
            "calendarDate": key,
            "wellnessStartTimeGmt": _gmt_str(day0), "wellnessStartTimeLocal": _gmt_str(day0 + TZ_MS),
            "totalSteps": max(1500, steps), "totalDistanceMeters": max(1500, steps) * 0.75,
            "totalKilocalories": 1680 + steps * 0.04 + act_kcal, "activeKilocalories": steps * 0.04 + act_kcal,
            "restingHeartRate": round(p["rhr"]), "averageStressLevel": round(28 + 8 * p["beh"]["stress_work"] + rng.gauss(0, 4)),
            "bodyBatteryHighestValue": max(v for _, v in bb), "bodyBatteryLowestValue": min(v for _, v in bb),
            "bodyBatteryChargedValue": round(max(v for _, v in bb) - bb[0][1] + 5), "bodyBatteryDrainedValue": round(max(v for _, v in bb) - bb[-1][1]),
            "averageSpo2": round(p["spo2"]), "avgWakingRespirationValue": round(p["resp"] + 1.5, 1),
            "moderateIntensityMinutes": workout["minutes"] // 2 if act else rng.randint(0, 15),
            "vigorousIntensityMinutes": workout["minutes"] // 3 if act and workout["hrr"] > 0.65 else 0,
        })
        hrv_z = (math.log(p["hrv"]) - math.log(HRV_BASE)) / 0.12
        store.save("readiness", key, [{
            "calendarDate": key, "timestamp": _gmt_str(sleep_end), "inputContext": "AFTER_WAKEUP_RESET",
            "score": round(max(5, min(100, 60 + 18 * hrv_z + 6 * (p["sleep_h"] - 7.3)))),
            "level": "HIGH" if hrv_z > 0.6 else "MODERATE" if hrv_z > -0.6 else "LOW",
        }])
        store.save("max_metrics", key, [{"generic": {"calendarDate": key, "vo2MaxPreciseValue": round(49.0 + 2.2 * i / days, 1)}}])
        if act:
            store.save_activity(_activity_raw(rng, act, hr))
        if i > 0 and rng.random() < 0.9:
            journal["entries"][key] = {k: v for k, v in p["beh"].items()}
    write_json(paths.journal, journal)
    log(f"[demo] đã sinh {len(plan)} ngày dữ liệu mẫu vào {paths.data}")


def _sleep_night(rng, p, start, end):
    """Hypnogram theo chu kỳ ~90': đầu đêm nhiều deep, cuối đêm nhiều REM."""
    levels, t = [], start
    stage_s = {"deep": 0.0, "light": 0.0, "rem": 0.0, "awake": 0.0}
    latency = start + int(rng.uniform(6, 18) * 60000)   # nằm chờ ngủ
    levels.append((start, latency, "awake"))
    stage_s["awake"] += (latency - start) / 1000
    t = latency
    cycle = 0
    while t < end:
        frac = (t - start) / (end - start)
        seq = [("light", rng.uniform(15, 25)), ("deep", rng.uniform(25, 40) * (1 - frac) + 4),
               ("light", rng.uniform(10, 20)), ("rem", rng.uniform(8, 18) + 25 * frac)]
        if rng.random() < 0.6:
            seq.append(("awake", rng.uniform(3, 9) + 6 * p["beh"]["alcohol"]))
        for stage, minutes in seq:
            if t >= end:
                break
            seg_end = min(end, t + int(minutes * 60000))
            levels.append((t, seg_end, stage))
            stage_s[stage] += (seg_end - t) / 1000
            t = seg_end
        cycle += 1
    sleep_hr, hrv_rows = [], []
    for t in range(start, end, STEP_MS):
        stage = next((s for a, b, s in levels if a <= t < b), "light")
        bump = {"deep": -2, "light": 0, "rem": 3, "awake": 9}[stage]
        sleep_hr.append((t, round(p["rhr"] + 2 + bump + rng.gauss(0, 1.2))))
    for t in range(start, end, 300_000):
        hrv_rows.append((t, round(max(12, p["hrv"] * rng.uniform(0.75, 1.25)))))
    return levels, sleep_hr, hrv_rows, stage_s


def _sleep_raw(p, key, start, end, levels, sleep_hr, hrv_rows, stage_s):
    asleep = stage_s["deep"] + stage_s["light"] + stage_s["rem"]
    score = round(max(30, min(98, 64 + 8 * (asleep / 3600 - 6) + 40 * (stage_s["deep"] / asleep - 0.15) - 0.25 * stage_s["awake"] / 60)))
    lvl = {"deep": 0.0, "light": 1.0, "rem": 2.0, "awake": 3.0}
    return {
        "dailySleepDTO": {
            "calendarDate": key, "sleepTimeSeconds": int(asleep), "napTimeSeconds": 0,
            "sleepStartTimestampGMT": start, "sleepEndTimestampGMT": end,
            "sleepStartTimestampLocal": start + TZ_MS, "sleepEndTimestampLocal": end + TZ_MS,
            "deepSleepSeconds": int(stage_s["deep"]), "lightSleepSeconds": int(stage_s["light"]),
            "remSleepSeconds": int(stage_s["rem"]), "awakeSleepSeconds": int(stage_s["awake"]),
            "averageSpO2Value": round(p["spo2"], 1), "lowestSpO2Value": round(p["spo2"] - 4),
            "averageRespirationValue": round(p["resp"], 1),
            "awakeCount": sum(1 for *_, s in levels if s == "awake"),
            "avgSleepStress": round(14 + 6 * p["beh"]["alcohol"], 1),
            "sleepScores": {"overall": {"value": score, "qualifierKey": "GOOD" if score >= 80 else "FAIR"}},
        },
        "sleepLevels": [{"startGMT": _gmt_str(a), "endGMT": _gmt_str(b), "activityLevel": lvl[s]} for a, b, s in levels],
        "sleepHeartRate": [{"value": v, "startGMT": t} for t, v in sleep_hr],
        "hrvData": [{"value": v, "startGMT": t} for t, v in hrv_rows],
        "restingHeartRate": round(p["rhr"]),
        "avgOvernightHrv": round(p["hrv"], 1),
        "hrvStatus": "BALANCED",
    }


def _hrv_raw(p, key, hrv_rows, week, start, end):
    weekly = sum(week) / len(week)
    return {
        "hrvSummary": {
            "calendarDate": key, "weeklyAvg": round(weekly), "lastNightAvg": round(p["hrv"]),
            "lastNight5MinHigh": round(max(v for _, v in hrv_rows)),
            "baseline": {"lowUpper": round(HRV_BASE * 0.78), "balancedLow": round(HRV_BASE * 0.85), "balancedUpper": round(HRV_BASE * 1.15)},
            "status": "BALANCED" if weekly > HRV_BASE * 0.85 else "UNBALANCED",
        },
        "hrvReadings": [{"hrvValue": v, "readingTimeGMT": _gmt_str(t), "readingTimeLocal": _gmt_str(t + TZ_MS)} for t, v in hrv_rows],
        "sleepStartTimestampGMT": _gmt_str(start), "sleepEndTimestampGMT": _gmt_str(end),
    }


def _day_hr(rng, p, day0, day_end, wake, next_bed, act):
    out = []
    walk_until = 0
    for t in range(day0, day_end, STEP_MS):
        if t < wake or t >= next_bed:
            v = p["rhr"] + 2 + rng.gauss(0, 1.5)
        elif act and act["start"] <= t < act["end"]:
            ramp = min(1.0, (t - act["start"]) / 600_000)
            hrr = act["hrr"] * (0.6 + 0.4 * ramp)
            if act["type"] == "running" and "interval" in act["name"]:
                hrr += 0.12 * math.sin((t - act["start"]) / 240_000 * math.pi)
            v = p["rhr"] + hrr * (HR_MAX - p["rhr"]) + rng.gauss(0, 3)
        else:
            if t >= walk_until and rng.random() < 0.025:
                walk_until = t + rng.randint(4, 12) * 60000
            base = 74 + 6 * p["beh"]["stress_work"] + 8 * p["sick"]
            v = (rng.uniform(92, 108) if t < walk_until else base + rng.gauss(0, 4))
        out.append((t, int(round(v))))
    return out


def _stress_bb(rng, p, day0, day_end, wake, next_bed, act):
    stress, bb = [], []
    level = 25 + 45 * min(1, p["sleep_h"] / 8) + 20 * (p["hrv"] / HRV_BASE - 1)
    level = max(15, min(100, level - 25))   # thức dậy sẽ được nạp tiếp
    for t in range(day0, day_end, 180_000):
        asleep = t < wake or t >= next_bed
        in_act = act and act["start"] <= t < act["end"]
        if in_act:
            s = -2
            level -= 0.35 + 0.6 * act["hrr"]
        elif asleep:
            s = int(max(1, rng.gauss(14, 5)))
            level += 0.55 if t < wake else 0.2
        else:
            s = int(max(1, min(99, rng.gauss(30 + 15 * p["beh"]["stress_work"], 14))))
            level -= 0.05 + s / 900
        level = max(5.0, min(100.0, level))
        stress.append((t, s))
        bb.append((t, int(round(level))))
    return stress, bb


def _activity_raw(rng, act, hr):
    inside = [v for t, v in hr if act["start"] <= t < act["end"]] or [120]
    secs = (act["end"] - act["start"]) / 1000
    dist = {"running": secs / 60 * rng.uniform(150, 190), "cycling": secs / 60 * rng.uniform(380, 450)}.get(act["type"], 0)
    return {
        "activityId": act["id"], "activityName": act["name"],
        "activityType": {"typeKey": act["type"]},
        "startTimeLocal": _gmt_str(act["start"] + TZ_MS, " "), "startTimeGMT": _gmt_str(act["start"], " "),
        "duration": secs, "elapsedDuration": secs, "distance": round(dist, 1),
        "calories": round(secs / 60 * (6 + 10 * act["hrr"])),
        "averageHR": round(sum(inside) / len(inside)), "maxHR": max(inside),
        "aerobicTrainingEffect": round(min(5.0, 1.0 + 4 * act["hrr"] * secs / 5400), 1),
        "anaerobicTrainingEffect": round(min(5.0, 0.3 + 3 * max(0, act["hrr"] - 0.7) * 5), 1),
        "activityTrainingLoad": round(secs / 60 * act["hrr"] ** 2 * 3),
    }
