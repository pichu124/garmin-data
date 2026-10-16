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


def test_stress_series_keeps_zero_as_rest():
    # Garmin: 0 = stress thấp nhất (nghỉ) hợp lệ; -1/-2 = không đo/đang vận động
    t0 = 1_760_000_000_000
    raw = {"stressValuesArray": [[t0, 0], [t0 + 3 * M, 0], [t0 + 6 * M, -1], [t0 + 9 * M, 10]]}
    pts = nz.stress(raw)["stress"]
    assert [v for _, v in pts] == [0, 0, 10]
    assert nz.stress_minutes(pts)["rest"] == 9   # 3 + 3 (khoảng 6' > 5' chỉ tính 1 nhịp) + 3; bỏ số 0 thì chỉ còn 3
