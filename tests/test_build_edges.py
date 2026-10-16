"""Ca biên của build: hoạt động qua nửa đêm, đổi giờ (DST), ngủ trưa, tuần có ngày dở."""
from datetime import datetime, timezone

from garmin_health import build, insights
from garmin_health import normalize as nz
from garmin_health.config import default_paths
from garmin_health.raw_store import RawStore

H = 3_600_000
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _gmt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0")


def _hr_day(store, day, tz, hr_at, rhr=50):
    day0 = nz.date_ms(day) - tz
    store.save("heart_rates", day, {
        "startTimestampGMT": _gmt(day0), "startTimestampLocal": _gmt(day0 + tz), "restingHeartRate": rhr,
        "heartRateValues": [[t, hr_at(t + tz - nz.date_ms(day))] for t in range(day0, day0 + 24 * H, 120_000)],
    })
    store.save("summary", day, {"restingHeartRate": rhr})


def test_activity_across_midnight_counts_both_sides(tmp_path):
    paths = default_paths(tmp_path)
    store = RawStore(paths.raw)
    tz = 7 * H
    _hr_day(store, "2026-10-10", tz, lambda m: 165 if m >= 23.5 * H else 60)
    _hr_day(store, "2026-10-11", tz, lambda m: 165 if m < 0.5 * H else 60)
    start = nz.date_ms("2026-10-10") + int(23.5 * H) - tz
    store.save_activity({"activityId": 1, "activityName": "Chạy đêm", "startTimeGMT": _gmt(start).replace("T", " ")[:19],
                         "startTimeLocal": _gmt(start + tz).replace("T", " ")[:19], "duration": 3600.0})
    s = build.build(paths, now=NOW, log=lambda *_: None)
    act = s["days"][0]["activities"][0]
    assert sum(act["zones_min"]) >= 58


def _walk_and_run(m):
    return 160 if 18 * H <= m < 18.5 * H else 100 if 8 * H <= m < 9.5 * H else 60


def _last_day(tmp_path, last_rhr):
    """5 ngày RHR 52 làm nền, ngày cuối cùng chuỗi HR (đi bộ 1.5h + chạy 30') với RHR `last_rhr`."""
    paths = default_paths(tmp_path)
    store = RawStore(paths.raw)
    tz = 7 * H
    days = [f"2026-10-0{i}" for i in range(1, 7)]
    for d in days:
        _hr_day(store, d, tz, _walk_and_run, rhr=last_rhr if d == days[-1] else 52)
    start = nz.date_ms(days[-1]) + 18 * H - tz
    store.save_activity({"activityId": 2, "activityName": "Chạy", "startTimeGMT": _gmt(start).replace("T", " ")[:19],
                         "startTimeLocal": _gmt(start + tz).replace("T", " ")[:19], "duration": 1800.0})
    store.save("stress", days[-1], {"stressValuesArray": [[start, 20], [start + 180_000, 80]]})
    return build.build(paths, now=NOW, log=lambda *_: None)["days"][-1]


def test_strain_uses_rhr_baseline_not_last_night(tmp_path):
    low, usual = _last_day(tmp_path / "low", 48), _last_day(tmp_path / "usual", 52)
    assert abs(low["strain"]["score"] - usual["strain"]["score"]) <= 0.1
    assert abs(low["activities"][0]["strain"] - usual["activities"][0]["strain"]) <= 0.1
    for block in (low["strain"], low["activities"][0]):
        assert len(block["load_pct"]) == 6 and abs(sum(block["load_pct"]) - 100) <= 1
    assert low["strain"]["light_min"] == 90 and low["strain"]["load_pct"][0] > 0
    assert low["activities"][0]["light_min"] == 0 and low["activities"][0]["load_pct"][3] == 100
    assert low["garmin"]["stress_min"] == {"rest": 3, "low": 0, "medium": 0, "high": 3}


def test_dst_day_uses_sleep_own_offset(tmp_path):
    paths = default_paths(tmp_path)
    store = RawStore(paths.raw)
    day = "2026-03-29"
    _hr_day(store, day, 1 * H, lambda m: 60)              # nửa đêm: CET (+1)
    end = nz.date_ms(day) + 5 * H                           # 05:00 GMT = 07:00 CEST (+2)
    start = end - 8 * H
    store.save("sleep", day, {"dailySleepDTO": {
        "sleepStartTimestampGMT": start, "sleepEndTimestampGMT": end,
        "sleepStartTimestampLocal": start + 2 * H, "sleepEndTimestampLocal": end + 2 * H,
        "sleepTimeSeconds": 27000, "napTimeSeconds": 3600}})
    s = build.build(paths, now=NOW, log=lambda *_: None)
    assert s["days"][0]["sleep"]["wake"] == "07:00"
    assert s["planner"]["need"]["nap_h"] == -1.0           # ngủ trưa hôm nay trừ vào đêm nay


def test_sleep_offset_doubled_by_garmin_is_ignored():
    s = {"start": 0, "start_local": 16 * H}                # cộng múi +8 hai lần
    assert build._sleep_tz(s, 8 * H) == 8 * H


def test_weekly_strain_skips_partial_today():
    days = [{"date": "2026-10-12", "strain": {"score": 12.0}}, {"date": "2026-10-13", "strain": {"score": 2.0}, "partial": True}]
    assert insights.weekly(days)[0]["strain"] == 12.0
