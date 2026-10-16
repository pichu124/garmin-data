from garmin_health import normalize as nz

M = 60_000


def test_stress_minutes_uses_garmin_thresholds():
    series = [(i * 3 * M, v) for i, v in enumerate([10, 25, 26, 50, 51, 75, 76, 100])]
    assert nz.stress_minutes(series) == {"rest": 6, "low": 6, "medium": 6, "high": 6}


def test_stress_minutes_skips_negative_and_gaps():
    # -1/-2 = không đo/đang vận động; khoảng trống 2 giờ chỉ tính 1 nhịp mẫu
    series = [(0, 20), (3 * M, -1), (6 * M, -2), (9 * M, 60), (129 * M, 60)]
    assert nz.stress_minutes(series) == {"rest": 3, "low": 0, "medium": 6, "high": 0}
    assert nz.stress_minutes([(0, -1), (3 * M, -2)]) is None
    assert nz.stress_minutes([]) is None
