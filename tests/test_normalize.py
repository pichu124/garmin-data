from garmin_health import normalize as nz


def test_parse_ts_formats():
    a = nz.parse_ts("2026-10-14T22:30:00.0")
    assert a == nz.parse_ts("2026-10-14 22:30:00") == nz.parse_ts(a)
    assert nz.parse_ts(None) is None and nz.parse_ts("rác") is None and nz.parse_ts(True) is None


def test_tz_offset_rounds_to_quarter_hour():
    raw = {"startTimestampGMT": "2026-10-13T17:00:00.0", "startTimestampLocal": "2026-10-14T00:00:30.0"}
    assert nz.tz_offset_ms(None, raw) == 7 * 3_600_000
    assert nz.tz_offset_ms({}, None) is None


def test_series_drops_missing_and_sentinels():
    rows = [[3, 60], [1, None], [2, -1], [4, 0], "x", [5]]
    assert nz.series(rows) == [(3, 60.0)]


def test_sleep_needs_window_and_maps_stages():
    t0 = nz.parse_ts("2026-10-13T16:00:00.0")
    raw = {
        "dailySleepDTO": {"sleepStartTimestampGMT": t0, "sleepEndTimestampGMT": t0 + 8 * 3_600_000,
                          "sleepTimeSeconds": 27000, "deepSleepSeconds": 5400, "remSleepSeconds": 6000,
                          "lightSleepSeconds": 15600, "awakeSleepSeconds": 1800, "averageRespirationValue": 14.2,
                          "sleepScores": {"overall": {"value": 81}}},
        "sleepLevels": [{"startGMT": "2026-10-13T16:00:00.0", "endGMT": "2026-10-13T16:30:00.0", "activityLevel": 0.0},
                        {"startGMT": "2026-10-13T16:30:00.0", "endGMT": "2026-10-13T16:40:00.0", "activityLevel": 3.0},
                        {"startGMT": "bad", "endGMT": "2026-10-13T16:40:00.0", "activityLevel": 1.0}],
    }
    s = nz.sleep(raw)
    assert [lv[2] for lv in s["levels"]] == ["deep", "awake"]
    assert s["garmin_score"] == 81 and s["resp"] == 14.2
    assert nz.sleep({"dailySleepDTO": {"sleepTimeSeconds": 0}}) is None
    assert nz.sleep(None) is None


def test_readiness_prefers_morning_entry():
    raw = [{"score": 40, "timestamp": "2026-10-14T20:00:00", "inputContext": "UPDATE_REALTIME_VARIABLES"},
           {"score": 72, "timestamp": "2026-10-14T06:00:00", "inputContext": "AFTER_WAKEUP_RESET", "level": "HIGH"}]
    assert nz.readiness(raw) == {"score": 72, "level": "HIGH"}
    assert nz.readiness([])["score"] is None


def test_body_battery_both_row_shapes():
    raw = {"bodyBatteryValuesArray": [[1, "MEASURED", 55, 2.0], [2, 60], [3, None]]}
    assert nz.stress(raw)["body_battery"] == [(1, 55.0), (2, 60.0)]


def test_vo2max_list_or_dict():
    assert nz.vo2max([{"generic": {"vo2MaxPreciseValue": 50.26}}]) == 50.3
    assert nz.vo2max({"generic": {"vo2MaxValue": 48}}) == 48
    assert nz.vo2max(None) is None


def test_activity_local_date_and_required_fields():
    a = nz.activity({"activityId": 9, "startTimeGMT": "2026-10-13 23:30:00", "startTimeLocal": "2026-10-14 06:30:00",
                     "duration": 1800.0, "activityType": {"typeKey": "running"}})
    assert a["date"] == "2026-10-14" and a["type"] == "running"
    assert nz.activity({"activityId": 9}) is None


def test_profile_prefers_default_zone():
    zones = [{"sport": "RUNNING", "maxHeartRateUsed": 195}, {"sport": "DEFAULT", "maxHeartRateUsed": 188}]
    p = nz.profile({"userData": {"gender": "FEMALE", "birthDate": "1990-01-02"}, "userSleep": {"wakeTime": 23400}}, zones)
    assert p == {"sex": "female", "birth_year": 1990, "hr_max": 188, "wake_min": 390}


def test_activity_hr_reads_descriptor_positions():
    from garmin_health import normalize as nz

    raw = {"metricDescriptors": [{"key": "sumDistance", "metricsIndex": 0}, {"key": "directHeartRate", "metricsIndex": 2},
                                 {"key": "directTimestamp", "metricsIndex": 1}],
           "activityDetailMetrics": [{"metrics": [5.0, 1.751536880e12, 151.0]}, {"metrics": [1.0, 1.751536877e12, 150.0]},
                                     {"metrics": [9.0, 1.751536883e12, None]}, {"metrics": [9.0]}, "rác"]}
    assert nz.activity_hr(raw) == [(1751536877000, 150.0), (1751536880000, 151.0)]
    assert nz.activity_hr({"metricDescriptors": [{"key": "directHeartRate", "metricsIndex": 0}]}) == []
    assert nz.activity_hr(None) == []
