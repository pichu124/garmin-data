"""raw/ → processed/: tính Recovery · Strain · Sleep cho từng ngày rồi ghi JSON cho web.

    processed/summary.json        mọi ngày (điểm, chỉ số, hoạt động) + profile + insights
    processed/days/<ngày>.json    chuỗi trong ngày (HR, stress, body battery, hypnogram)

Đọc tuần tự từ ngày cũ nhất vì nhu cầu ngủ phụ thuộc strain HÔM QUA và nợ ngủ
3 đêm trước, còn Recovery cần baseline 30 ngày trước đó.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import insights
from . import normalize as nz
from . import recovery as rec
from . import sleep_score as sl
from . import strain as st
from .config import Paths, load_journal, load_settings, write_json
from .raw_store import RawStore
from .stats import baseline, median, window

VERSION = 1
DAY_MS = nz.DAY_MS
FALLBACK_RHR = 60.0
DEFAULT_WAKE_MIN = 6 * 60 + 30


def _days_between(first: str, last: str) -> list[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def _local_tz_ms() -> int:
    return int(time.localtime().tm_gmtoff * 1000)


def _hhmm(minutes: float | None) -> str | None:
    if minutes is None:
        return None
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _r(x: float | None, nd: int = 0):
    if x is None:
        return None
    return round(x, nd) if nd else int(round(x))


def normalize_day(store: RawStore, day: str) -> dict:
    raw = {kind: store.load(kind, day) for kind in ("summary", "heart_rates", "sleep", "hrv", "stress", "readiness", "max_metrics")}
    return {
        "tz": nz.tz_offset_ms(raw["heart_rates"], raw["stress"], raw["sleep"], raw["summary"]),
        "summary": nz.summary(raw["summary"]),
        "hr": nz.heart_rates(raw["heart_rates"]),
        "sleep": nz.sleep(raw["sleep"]),
        "nap_s": nz.nap_seconds(raw["sleep"]),
        "hrv": nz.hrv(raw["hrv"]),
        "stress": nz.stress(raw["stress"]),
        "readiness": nz.readiness(raw["readiness"]),
        "vo2max": nz.vo2max(raw["max_metrics"]),
    }


def resolve_profile(store: RawStore, settings: dict, activities: list[dict], year: int) -> dict:
    garmin = nz.profile(store.load_profile("user_settings"), store.load_profile("hr_zones"))
    hr_max, source = st.estimate_hr_max(
        configured=settings.get("hr_max"),
        garmin=garmin["hr_max"],
        birth_year=garmin["birth_year"],
        year=year,
        observed=[a["max_hr"] for a in activities if a.get("max_hr")],
    )
    return {
        "hr_max": hr_max,
        "hr_max_source": source,
        "sex": settings.get("sex") or garmin["sex"],
        "sleep_baseline_h": settings["sleep_baseline_h"],
        "garmin_wake_min": garmin["wake_min"],
    }


def _minute_of(t: int, tz: int, day_start_local: int) -> float:
    """phút so với nửa đêm địa phương của ngày (âm = tối hôm trước)."""
    return round((t + tz - day_start_local) / 60000, 1)


MAX_TZ_DRIFT_MS = 2 * 3_600_000


def _sleep_tz(s: dict, day_tz: int) -> int:
    """Lệch giờ của chính giấc ngủ (từ cặp Local/GMT của nó) thay cho lệch giờ lúc nửa đêm.

    Ngày đổi giờ mùa hè/đi máy bay, offset lúc 00:00 sai 1 giờ so với lúc thức dậy.
    Một số tài khoản Garmin (connect.garmin.cn) bị cộng múi giờ HAI lần vào bản
    Local ⇒ chỉ tin khi lệch so với offset ngày không quá 2 giờ.
    """
    if s.get("start_local") is None:
        return day_tz
    off = round((s["start_local"] - s["start"]) / 900_000) * 900_000
    return off if abs(off - day_tz) <= MAX_TZ_DRIFT_MS else day_tz


def _sleep_block(s: dict, tz: int) -> dict:
    slept_h = s["sleep_s"] / 3600
    in_bed_h = (s["end"] - s["start"]) / 3_600_000
    onset = ((s["start"] + tz) % DAY_MS) / 60000
    wake = ((s["end"] + tz) % DAY_MS) / 60000
    return {
        "hours": round(slept_h, 2),
        "in_bed_h": round(in_bed_h, 2),
        "efficiency": round(min(100.0, 100 * slept_h / in_bed_h)) if in_bed_h > 0 else None,
        "onset_min": onset,
        "wake_min": wake,
        "onset": _hhmm(onset),
        "wake": _hhmm(wake),
        "stages": {k: round(s[f"{k}_s"] / 60) for k in ("awake", "light", "deep", "rem")},
        "restorative_pct": _r(100 * (s["deep_s"] + s["rem_s"]) / s["sleep_s"]) if s["sleep_s"] else None,
        "resp": _r(s["resp"], 1),
        "spo2": _r(s["spo2"], 1),
        "awake_count": _r(s["awake_count"]),
        "garmin_score": _r(s["garmin_score"]),
    }


def _load_fields(c: st.CardioLoad) -> dict:
    """Phút Vùng 1–5, phút "nhẹ" (20–50% HRR) và % tải [nhẹ, Z1..Z5] — tổng đúng 100."""
    pct = None
    if c.load > 0:
        pct = [round(100 * x / c.load) for x in c.load_by_zone]
        pct[pct.index(max(pct))] += 100 - sum(pct)   # sai số làm tròn dồn vào phần lớn nhất
    return {"zones_min": [round(z) for z in c.zones[1:]], "light_min": round(c.light_min), "load_pct": pct}


def _activity_block(act: dict, samples, *, rhr: float, profile: dict, day_local: int) -> dict:
    t0 = act["start"]
    t1 = t0 + int(act["duration_s"] * 1000)
    start_min = round((act["start_local"] - day_local) / 60000, 1)   # theo giờ Local của chính hoạt động
    c = st.cardio_load(samples, rhr=rhr, hr_max=profile["hr_max"], sex=profile["sex"], t0=t0, t1=t1)
    return {
        "id": act["id"],
        "name": act["name"],
        "type": act["type"],
        "start": _hhmm((act["start_local"] % DAY_MS) / 60000),
        "start_min": start_min,
        "end_min": round(start_min + act["duration_s"] / 60, 1),
        "duration_min": round(act["duration_s"] / 60),
        "strain": st.strain_from_load(c.load) if c.load > 0 else None,
        **_load_fields(c),
        "avg_hr": _r(act["avg_hr"]),
        "max_hr": _r(act["max_hr"]),
        "calories": _r(act["calories"]),
        "distance_km": round(act["distance_m"] / 1000, 2) if act.get("distance_m") else None,
        "aerobic_te": _r(act["aerobic_te"], 1),
        "training_load": _r(act["training_load"]),
    }


def compute_days(norm: dict[str, dict], acts_by_day: dict[str, list[dict]], profile: dict, journal: dict, today: str) -> list[dict]:
    dates = list(norm)
    out: list[dict] = []
    hist = {"hrv": [], "rhr": [], "resp": [], "spo2": []}
    last_tz = _local_tz_ms()
    last_rhr = None
    last_vo2 = None
    for i, d in enumerate(dates):
        n = norm[d]
        tz = n["tz"] if n["tz"] is not None else last_tz
        last_tz = tz
        day_local = nz.date_ms(d)
        day0 = day_local - tz
        s = n["sleep"]

        rhr = n["summary"]["rhr"] or n["hr"]["rhr"] or (s or {}).get("rhr")
        hrv = n["hrv"]["last_night"] or (s or {}).get("hrv")
        resp = (s or {}).get("resp")
        spo2 = (s or {}).get("spo2")
        # baseline 30 ngày TRƯỚC hôm nay — dùng cho Recovery và cho %HRR của Strain
        bases = {
            "hrv_ln": baseline(window(hist["hrv"], i), sd_floor=rec.SD_FLOORS["hrv_ln"], transform=_ln),
            "rhr": baseline(window(hist["rhr"], i), sd_floor=rec.SD_FLOORS["rhr"]),
            "resp": baseline(window(hist["resp"], i), sd_floor=rec.SD_FLOORS["resp"]),
            "spo2": baseline(window(hist["spo2"], i), sd_floor=rec.SD_FLOORS["spo2"]),
        }
        # RHR nền, không phải RHR đêm qua: một đêm RHR thấp không được thổi phồng strain cả ngày
        rhr_for_load = bases["rhr"].mean if bases["rhr"] else (rhr or last_rhr or FALLBACK_RHR)
        last_rhr = rhr or last_rhr

        # --- Strain ---
        samples = n["hr"]["samples"]
        strain_block = None
        if samples:
            c = st.cardio_load(samples, rhr=rhr_for_load, hr_max=profile["hr_max"], sex=profile["sex"], t0=day0, t1=day0 + DAY_MS)
            strain_block = {"score": st.strain_from_load(c.load), "load": round(c.load, 1), **_load_fields(c)}
        # hoạt động vắt qua nửa đêm cần cả mẫu HR của ngày sau
        next_samples = norm[dates[i + 1]]["hr"]["samples"] if i + 1 < len(dates) else []
        act_samples = samples + next_samples
        activities = [
            _activity_block(a, act_samples, rhr=rhr_for_load, profile=profile, day_local=day_local)
            for a in sorted(acts_by_day.get(d, []), key=lambda a: a["start"])
        ]
        summ = n["summary"]
        if strain_block is not None or summ["calories"]:
            strain_block = {**(strain_block or {"score": None, "load": None, "zones_min": None}),
                            "calories": _r(summ["calories"]), "active_calories": _r(summ["active_calories"]),
                            "steps": _r(summ["steps"]), "distance_km": round(summ["distance_m"] / 1000, 1) if summ["distance_m"] else None}

        # --- Sleep: nhu cầu dựa trên strain hôm qua + nợ ngủ 3 đêm ---
        prev = out[i - 1] if i else None
        shortfalls = []
        for k in (1, 2, 3):
            if i - k >= 0:
                past = out[i - k]
                sb = past.get("sleep")
                need_wo_debt = past["need"]["total_h"] - past["need"]["debt_h"]
                shortfalls.append(max(0.0, need_wo_debt - sb["hours"]) if sb else None)
        prev_nap_h = (norm[dates[i - 1]]["nap_s"] / 3600) if i else 0.0
        need = sl.sleep_need(
            baseline_h=profile["sleep_baseline_h"],
            prev_strain=((prev or {}).get("strain") or {}).get("score"),
            shortfalls_h=shortfalls,
            nap_h=prev_nap_h,
        )
        sleep_block = None
        if s:
            stz = _sleep_tz(s, tz)
            sleep_block = _sleep_block(s, stz)
            nights = [x["sleep"] for x in out[max(0, i - sl.CONSISTENCY_NIGHTS + 1) : i] if x.get("sleep")] + [sleep_block]
            cons = sl.consistency([x["onset_min"] for x in nights], [x["wake_min"] for x in nights])
            perf = sl.performance(slept_h=sleep_block["hours"], need_h=need["total_h"],
                                  efficiency=sleep_block["efficiency"], consistency_pct=cons)
            sleep_block.update(consistency=cons, performance=perf["score"], sufficiency=perf["sufficiency"],
                               need_h=need["total_h"], start_min=_minute_of(s["start"], stz, day_local),
                               end_min=_minute_of(s["end"], stz, day_local))

        # --- Recovery: so với baseline 30 ngày TRƯỚC hôm nay ---
        recovery = None
        if hrv is not None or s is not None:
            recovery = rec.compute(hrv=hrv, rhr=rhr if s or hrv else None,
                                   sleep_perf=(sleep_block or {}).get("performance"), resp=resp, spo2=spo2, bases=bases)
        health_bases = {k: baseline(window(hist[k], i), sd_floor=rec.HEALTH_SD_FLOORS[k]) for k in hist}
        vitals = {"hrv": _r(hrv, 1), "rhr": _r(rhr), "resp": _r(resp, 1), "spo2": _r(spo2, 1)}
        for k, v in (("hrv", hrv), ("rhr", rhr), ("resp", resp), ("spo2", spo2)):
            hist[k].append(v)
        if strain_block is not None:
            strain_block["target"] = st.strain_target((recovery or {}).get("score"))

        last_vo2 = n["vo2max"] or last_vo2
        out.append({
            "date": d,
            "partial": d == today,
            "recovery": recovery,
            "strain": strain_block,
            "sleep": sleep_block,
            "need": need,
            "vitals": vitals,
            "health": rec.health_monitor(vitals, health_bases),
            "garmin": {
                "bb_high": _r(summ["bb_high"]), "bb_low": _r(summ["bb_low"]),
                "bb_charged": _r(summ["bb_charged"]), "bb_drained": _r(summ["bb_drained"]),
                "stress_avg": _r(summ["stress_avg"]), "stress_min": nz.stress_minutes(n["stress"]["stress"]),
                "readiness": _r(n["readiness"]["score"]),
                "readiness_level": n["readiness"]["level"], "hrv_status": n["hrv"]["status"],
                "hrv_weekly": _r(n["hrv"]["weekly"]), "vo2max": last_vo2,
                "sleep_score": (sleep_block or {}).get("garmin_score"), "intensity_min": _r(summ["intensity_min"]),
            },
            "activities": activities,
            "journal": journal["entries"].get(d),
            "_tz": tz,
        })
    return out


def _ln(x: float) -> float:
    return math.log(x)


def day_detail(day: dict, n: dict, next_n: dict | None = None) -> dict:
    """Chuỗi thời gian trong ngày, trục = phút kể từ nửa đêm địa phương."""
    tz, d = day["_tz"], day["date"]
    day_local = nz.date_ms(d)

    def mins(points, lo=-720, hi=1440, tz_override=None):
        out = []
        for t, v in points:
            m = _minute_of(t, tz if tz_override is None else tz_override, day_local)
            if lo <= m <= hi:
                out.append([m, round(v, 1)])
        return out

    s = n["sleep"]
    sleep = None
    if s:
        stz = _sleep_tz(s, tz)
        sleep = {
            "start_min": _minute_of(s["start"], stz, day_local),
            "end_min": _minute_of(s["end"], stz, day_local),
            "levels": [[_minute_of(a, stz, day_local), _minute_of(b, stz, day_local), stage] for a, b, stage in s["levels"]],
            "hr": mins(s["hr"], tz_override=stz),
            "hrv": mins(n["hrv"]["readings"] or s["hrv_series"], tz_override=stz),
        }
    next_sleep = (next_n or {}).get("sleep")
    next_start = _minute_of(next_sleep["start"], _sleep_tz(next_sleep, tz), day_local) if next_sleep else None
    return {
        "date": d,
        "next_sleep_start_min": next_start if next_start is not None and 0 <= next_start < 1440 else None,
        "hr": mins(n["hr"]["samples"], 0, 1440),
        "stress": mins(n["stress"]["stress"], 0, 1440),
        "body_battery": mins(n["stress"]["body_battery"], 0, 1440),
        "sleep": sleep,
        "activities": [
            {"id": a["id"], "name": a["name"], "type": a["type"], "strain": a["strain"],
             "start_min": a["start_min"], "end_min": a["end_min"]}
            for a in day["activities"]
        ],
    }


def planner(days: list[dict], profile: dict, settings: dict, *, nap_h: float = 0.0) -> dict | None:
    """Sleep Planner cho ĐÊM NAY (sau ngày mới nhất)."""
    if not days:
        return None
    last = days[-1]
    nights = [d["sleep"] for d in days[-14:] if d.get("sleep")]
    shortfalls = []
    for past in reversed(days[-3:]):
        sb = past.get("sleep")
        need_wo_debt = past["need"]["total_h"] - past["need"]["debt_h"]
        shortfalls.append(max(0.0, need_wo_debt - sb["hours"]) if sb else None)
    need = sl.sleep_need(
        baseline_h=profile["sleep_baseline_h"],
        prev_strain=(last.get("strain") or {}).get("score"),
        shortfalls_h=shortfalls,
        nap_h=nap_h,   # ngủ trưa HÔM NAY được trừ vào nhu cầu đêm nay
    )
    if settings.get("target_wake"):
        hh, mm = settings["target_wake"].split(":")
        wake_min, wake_src = int(hh) * 60 + int(mm), "cài đặt"
    elif nights:
        wake_min, wake_src = median(n["wake_min"] for n in nights), "trung vị 14 đêm"
    elif profile.get("garmin_wake_min") is not None:
        wake_min, wake_src = profile["garmin_wake_min"], "Garmin"
    else:
        wake_min, wake_src = DEFAULT_WAKE_MIN, "mặc định"
    eff = median(n["efficiency"] for n in nights) if nights else None
    return {
        "for_date": (date.fromisoformat(last["date"]) + timedelta(days=1)).isoformat(),
        "need": need,
        "wake": _hhmm(wake_min),
        "wake_source": wake_src,
        "efficiency": _r(eff),
        "options": [{**o, "bedtime": _hhmm(o["bedtime_min"])} for o in sl.plan_bedtimes(need_h=need["total_h"], wake_min=wake_min, efficiency=eff)],
    }


def build(paths: Paths, *, now: datetime | None = None, log=print) -> dict:
    store = RawStore(paths.raw)
    settings = load_settings(paths)
    journal = load_journal(paths)
    raw_days = store.days()
    now = now or datetime.now(timezone.utc)

    acts = [a for a in (nz.activity(x) for x in store.activities()) if a]
    acts_by_day: dict[str, list[dict]] = {}
    for a in acts:
        acts_by_day.setdefault(a["date"], []).append(a)

    first = min(raw_days + list(acts_by_day)) if (raw_days or acts_by_day) else None
    last = max(raw_days + list(acts_by_day)) if (raw_days or acts_by_day) else None
    dates = _days_between(first, last) if first else []
    norm = {d: normalize_day(store, d) for d in dates}
    latest_tz = next((norm[d]["tz"] for d in reversed(dates) if norm[d]["tz"] is not None), _local_tz_ms())
    today = (now + timedelta(milliseconds=latest_tz)).date().isoformat()

    profile = resolve_profile(store, settings, acts, now.year)
    days = compute_days(norm, acts_by_day, profile, journal, today)

    details_dir = paths.processed / "days"
    for i, day in enumerate(days):
        next_n = norm[days[i + 1]["date"]] if i + 1 < len(days) else None
        write_json(details_dir / f"{day['date']}.json", day_detail(day, norm[day["date"]], next_n), compact=True)
    for day in days:
        day.pop("_tz", None)
        for a in day["activities"]:
            a.pop("start_min", None)
            a.pop("end_min", None)

    summary = {
        "version": VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "today": today,
        "profile": {k: v for k, v in profile.items() if k != "garmin_wake_min"},
        "planner": planner(days, profile, settings, nap_h=norm[dates[-1]]["nap_s"] / 3600 if dates else 0.0),
        "settings": settings,
        "journal_questions": journal["questions"],
        "insights": {
            "journal": insights.journal_impact(days, journal["questions"]),
            "weekly": insights.weekly(days),
        },
        "days": days,
    }
    write_json(paths.processed / "summary.json", summary, compact=True)
    log(f"[build] {len(days)} ngày ({first} → {last}), {len(acts)} hoạt động, HRmax {profile['hr_max']:.0f} ({profile['hr_max_source']})")
    return summary


def coverage(summary: dict) -> dict[str, Any]:
    """Đếm ngày có từng loại dữ liệu — cho lệnh `doctor`."""
    days = summary.get("days", [])
    count = lambda f: sum(1 for d in days if f(d))  # noqa: E731
    return {
        "days": len(days),
        "recovery": count(lambda d: (d.get("recovery") or {}).get("score") is not None),
        "sleep": count(lambda d: d.get("sleep")),
        "strain": count(lambda d: (d.get("strain") or {}).get("score") is not None),
        "hrv": count(lambda d: (d.get("vitals") or {}).get("hrv") is not None),
        "activities": sum(len(d.get("activities") or []) for d in days),
    }
