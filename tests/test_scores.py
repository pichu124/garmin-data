import math

import pytest

from garmin_health import recovery as rec
from garmin_health import sleep_score as sl
from garmin_health import strain as st
from garmin_health.stats import Baseline, baseline, circular_diff_minutes, circular_mean_minutes


def _samples(minutes, hr, start=0):
    return [(start + i * 120_000, hr) for i in range(minutes // 2)]


def _day_strain(*blocks, rhr=50, hr_max=190):
    samples, t = [], 0
    for minutes, hr in blocks:
        samples += _samples(minutes, hr, t)
        t += minutes * 60_000
    return st.strain_from_load(st.cardio_load(samples, rhr=rhr, hr_max=hr_max)[0])


def test_strain_calibration_anchors():
    resting_day = _day_strain((600, 55), (480, 70), (90, 100))      # sinh hoạt + 1,5h đi bộ
    run_day = _day_strain((600, 55), (480, 70), (90, 100), (60, 150))     # + chạy 60' vừa sức
    hard_day = _day_strain((600, 55), (480, 70), (150, 165))
    assert 2 <= resting_day <= 7
    assert 11 <= run_day <= 15
    assert 17.5 <= hard_day <= 20.5
    assert 0 <= _day_strain((1440, 52)) < 0.5                     # cả ngày nằm nghỉ


def test_strain_is_monotonic_and_capped():
    vals = [st.strain_from_load(x) for x in (0, 10, 100, 300, 1000, 10_000)]
    assert vals == sorted(vals) and vals[0] == 0 and vals[-1] <= 21


def test_gaps_do_not_inflate_load():
    samples = [(0, 160), (6 * 3_600_000, 160)]   # 2 mẫu cách 6 giờ ⇒ chỉ tính ~2 phút mỗi mẫu
    zones = st.cardio_load(samples, rhr=50, hr_max=190).zones
    assert sum(zones) == pytest.approx(4.0)


def test_walking_day_load_shows_as_light_minutes():
    samples = _samples(600, 55) + _samples(90, 100, 600 * 60_000)   # HR 100 ≈ 36% HRR: dưới Vùng 1
    c = st.cardio_load(samples, rhr=50, hr_max=190)
    assert c.load > 0 and c.zones[1:] == [0.0] * 5
    assert c.light_min == pytest.approx(90.0)
    assert c.load_by_zone[0] == pytest.approx(c.load)


def test_strain_target_follows_recovery():
    assert st.strain_target(None) is None
    lo_red, hi_red = st.strain_target(20)
    lo_green, hi_green = st.strain_target(90)
    assert hi_red < 10 and lo_green >= 14


def test_hr_max_priority():
    assert st.estimate_hr_max(configured=180, garmin=190, birth_year=1990, year=2026, observed=[])[1] == "cài đặt"
    assert st.estimate_hr_max(configured=None, garmin=190, birth_year=1990, year=2026, observed=[])[0] == 190
    v, src = st.estimate_hr_max(configured=None, garmin=None, birth_year=1990, year=2026, observed=[230, 199, 197])
    assert (v, src) == (197, "dữ liệu")   # 230 bị loại (spike), 199 là max nhưng dùng giá trị cao thứ hai
    assert st.estimate_hr_max(configured=None, garmin=None, birth_year=1990, year=2026, observed=[150])[1] == "tuổi"


def test_sleep_need_components():
    need = sl.sleep_need(baseline_h=7.75, prev_strain=21, shortfalls_h=[2.0, 2.0, 2.0], nap_h=0.5)
    assert need["strain_h"] == pytest.approx(1.0)
    assert need["debt_h"] == pytest.approx(1.5)            # chạm trần
    assert need["nap_h"] == pytest.approx(-0.5)
    assert need["total_h"] == pytest.approx(7.75 + 1 + 1.5 - 0.5)
    assert sl.sleep_need(baseline_h=8, prev_strain=6, shortfalls_h=[], nap_h=0)["total_h"] == 8


def test_consistency_handles_midnight_wrap():
    assert sl.consistency([23 * 60 + 50, 10], [6 * 60, 6 * 60]) >= 95   # 23:50 và 00:10 là gần nhau
    assert sl.consistency([22 * 60, 2 * 60], [6 * 60, 10 * 60]) < 30
    assert sl.consistency([600], [900]) is None
    assert circular_diff_minutes(circular_mean_minutes([1430, 10]), 0) < 1e-6


def test_sleep_performance_caps_and_reweights():
    full = sl.performance(slept_h=9, need_h=8, efficiency=95, consistency_pct=90)
    assert full["sufficiency"] == 100 and full["score"] <= 100
    no_cons = sl.performance(slept_h=6, need_h=8, efficiency=90, consistency_pct=None)
    assert no_cons["score"] == round((0.7 * 75 + 0.15 * 90) / 0.85)


def test_planner_bedtime_wraps_past_midnight():
    opts = sl.plan_bedtimes(need_h=8, wake_min=6 * 60, efficiency=90)
    assert opts[0]["bedtime_min"] == round((6 * 60 - 8 / 0.9 * 60) % 1440)
    assert [o["key"] for o in opts] == ["peak", "perform", "get_by"]


BASES = {"hrv_ln": Baseline(math.log(60), 0.12, 30), "rhr": Baseline(52, 2, 30), "resp": Baseline(14.5, 0.4, 30), "spo2": Baseline(96, 0.8, 30)}


def test_recovery_neutral_day_near_population_mean():
    r = rec.compute(hrv=60, rhr=52, sleep_perf=80, resp=14.5, spo2=96, bases=BASES)
    assert 55 <= r["score"] <= 61 and r["zone"] == "yellow"


def test_recovery_direction_and_zones():
    good = rec.compute(hrv=78, rhr=48, sleep_perf=95, resp=14.4, spo2=96, bases=BASES)
    bad = rec.compute(hrv=42, rhr=58, sleep_perf=60, resp=16.5, spo2=93, bases=BASES)
    assert good["zone"] == "green" and bad["zone"] == "red"
    assert good["contributions"]["hrv"] > 0 > bad["contributions"]["hrv"]
    assert bad["contributions"]["resp"] < 0          # nhịp thở tăng mạnh bị phạt
    assert "resp" not in good["contributions"]       # trong ngưỡng ⇒ không phạt


def test_recovery_without_hrv_reweights_and_calibrating():
    r = rec.compute(hrv=None, rhr=48, sleep_perf=90, resp=None, spo2=None, bases=BASES)
    assert r["inputs"] == ["rhr", "sleep"] and r["score"] > 60
    cal = rec.compute(hrv=60, rhr=52, sleep_perf=80, resp=None, spo2=None, bases={})
    assert cal["score"] is None and cal["calibrating"] is True


def test_baseline_floor_and_min_days():
    assert baseline([50, 50, 50], sd_floor=1) is None
    b = baseline([50, 50, 50, 50], sd_floor=1.5)
    assert b.sd == 1.5 and b.n == 4


def test_health_monitor_status():
    hm = rec.health_monitor({"rhr": 60, "hrv": None}, {"rhr": Baseline(52, 2, 30), "hrv": Baseline(60, 5, 30)})
    assert hm["rhr"]["status"] == "high" and hm["rhr"]["hi"] == 55.0
    assert hm["hrv"]["status"] is None and hm["hrv"]["lo"] == 52.5
