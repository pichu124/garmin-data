"""Đồng bộ với client Garmin GIẢ (không gọi mạng)."""
from datetime import date

import pytest

from garmin_health import sync as gsync
from garmin_health.config import default_paths, read_json
from garmin_health.raw_store import DAILY_KINDS, RawStore


class GarminConnectNotFoundError(Exception):
    pass


class GarminConnectAuthenticationError(Exception):
    pass


class FakeClient:
    def __init__(self, fail_kind=None, auth_fail=False):
        self.calls = []
        self.fail_kind = fail_kind
        self.auth_fail = auth_fail

    def _hit(self, kind, d):
        self.calls.append((kind, d))
        if self.auth_fail:
            raise GarminConnectAuthenticationError("401")
        if kind == self.fail_kind:
            raise GarminConnectNotFoundError("404")
        return {"kind": kind, "date": d}

    def get_user_summary(self, d): return self._hit("summary", d)
    def get_heart_rates(self, d): return self._hit("heart_rates", d)
    def get_sleep_data(self, d): return self._hit("sleep", d)
    def get_hrv_data(self, d): return self._hit("hrv", d)
    def get_stress_data(self, d): return self._hit("stress", d)
    def get_training_readiness(self, d): return self._hit("readiness", d)
    def get_max_metrics(self, d): return self._hit("max_metrics", d)
    def get_activities_by_date(self, a, b): return [{"activityId": 1, "startTimeGMT": f"{b} 01:00:00"}]
    def get_user_profile(self): return {"userData": {"gender": "MALE"}}
    def get_heart_rate_zones(self): return [{"sport": "DEFAULT", "maxHeartRateUsed": 190}]


TODAY = date(2026, 10, 15)


def test_first_sync_backfills_and_saves_everything(tmp_path):
    paths = default_paths(tmp_path)
    client = FakeClient(fail_kind="hrv")
    result = gsync.sync(paths, client=client, days=5, today=TODAY, pause=0, log=lambda *_: None)
    store = RawStore(paths.raw)
    assert store.days() == ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]
    assert store.load("summary", "2026-10-11") == {"kind": "summary", "date": "2026-10-11"}
    assert store.has("hrv", "2026-10-12") and store.load("hrv", "2026-10-12") is None   # 404 ⇒ lưu rỗng
    assert result["error_count"] == 0 and len(list(store.activities())) == 1
    assert store.load_profile("hr_zones")[0]["maxHeartRateUsed"] == 190
    assert read_json(paths.sync_state)["last_sync"]


def test_incremental_only_refreshes_recent_days(tmp_path):
    paths = default_paths(tmp_path)
    gsync.sync(paths, client=FakeClient(), days=20, today=TODAY, pause=0, log=lambda *_: None)
    client = FakeClient()
    gsync.sync(paths, client=client, today=date(2026, 10, 17), pause=0, log=lambda *_: None)
    fetched_days = sorted({d for _, d in client.calls})
    assert fetched_days[0] == "2026-10-12" and fetched_days[-1] == "2026-10-17"   # ngày cuối − 3
    assert len(client.calls) == len(fetched_days) * len(DAILY_KINDS)


def test_auth_error_raises_auth_required(tmp_path):
    with pytest.raises(gsync.AuthRequired):
        gsync.sync(default_paths(tmp_path), client=FakeClient(auth_fail=True), days=2, today=TODAY, pause=0, log=lambda *_: None)


def test_plan_days_first_run_uses_backfill(tmp_path):
    store = RawStore(tmp_path)
    days, refresh_from = gsync.plan_days(store, today=TODAY, backfill=90)
    assert len(days) == 90 and days[-1] == "2026-10-15" and refresh_from == "2026-10-12"


class HTTPError(Exception):
    pass


class GarminConnectTooManyRequestsError(Exception):
    pass


class FlakyClient(FakeClient):
    """Lỗi mạng đúng 1 lần cho một (loại, ngày)."""

    def __init__(self, bad):
        super().__init__()
        self.bad = set(bad)

    def _hit(self, kind, d):
        if (kind, d) in self.bad:
            self.bad.discard((kind, d))
            self.calls.append((kind, d))
            raise HTTPError("502")
        return super()._hit(kind, d)


def test_failed_old_day_is_retried_on_next_sync(tmp_path):
    paths = default_paths(tmp_path)
    gsync.sync(paths, client=FlakyClient({("sleep", "2026-09-20")}), days=30, today=TODAY, pause=0, log=lambda *_: None)
    store = RawStore(paths.raw)
    assert not store.has("sleep", "2026-09-20")          # lỗi ⇒ KHÔNG lưu rỗng
    client = FakeClient()
    gsync.sync(paths, client=client, today=date(2026, 10, 16), pause=0, log=lambda *_: None)
    assert ("sleep", "2026-09-20") in client.calls and store.has("sleep", "2026-09-20")
    assert ("summary", "2026-09-20") not in client.calls  # loại đã có thì không tải lại


def test_persistent_rate_limit_stops_quickly(tmp_path, monkeypatch):
    monkeypatch.setattr(gsync, "RATE_LIMIT_WAIT_S", 0)

    class Limited(FakeClient):
        def _hit(self, kind, d):
            self.calls.append((kind, d))
            if len(self.calls) > 5:
                raise GarminConnectTooManyRequestsError("429")
            return {"ok": True}

    client = Limited()
    result = gsync.sync(default_paths(tmp_path), client=client, days=90, today=TODAY, pause=0, log=lambda *_: None)
    assert result["aborted"] and len(client.calls) <= 7


SLEEP = {"dailySleepDTO": {"sleepStartTimestampGMT": 1760466000000, "sleepEndTimestampGMT": 1760493600000, "sleepTimeSeconds": 26000}}


def quiet(**kw):
    return dict(pause=0, log=lambda *_: None, **kw)


def test_plan_quick_fetches_only_what_can_still_change(tmp_path):
    store = RawStore(tmp_path)
    t, y = "2026-10-15", "2026-10-14"
    jobs = gsync.plan_quick(store, {}, TODAY)
    # chưa có HRV/Readiness sáng nay, chưa có lượt đầy đủ hôm nay ⇒ hôm nay 6 loại + hôm qua 3 loại
    assert jobs == [(t, k) for k in gsync.TODAY_KINDS + gsync.ONCE_KINDS] + [(y, k) for k in gsync.YESTERDAY_KINDS]
    store.save("sleep", t, SLEEP)
    store.save("hrv", t, {"hrvSummary": {"lastNightAvg": 55}})
    store.save("readiness", t, [{"score": 70, "inputContext": "AFTER_WAKEUP_RESET"}])
    yesterday = [(y, k) for k in gsync.YESTERDAY_KINDS]
    assert gsync.plan_quick(store, {"full_sync_day": y}, TODAY) == [(t, k) for k in gsync.TODAY_KINDS] + yesterday
    only_today = gsync.plan_quick(store, {"full_sync_day": t}, TODAY)
    assert only_today == [(t, k) for k in gsync.TODAY_KINDS]   # sleep vẫn tải lại: giấc trưa ghi vào ngày đó
    assert "max_metrics" not in {k for _, k in jobs}
    store.save("hrv", t, {"hrvSummary": {}})   # Garmin trả khung rỗng khi đồng hồ chưa đẩy số đêm qua
    assert (t, "hrv") in gsync.plan_quick(store, {"full_sync_day": t}, TODAY)


def test_full_sync_marks_day_only_when_complete(tmp_path):
    paths = default_paths(tmp_path)
    gsync.sync(paths, client=FakeClient(), days=5, **quiet(today=TODAY))
    assert read_json(paths.sync_state)["full_sync_day"] == "2026-10-15"
    paths2 = default_paths(tmp_path / "b")

    class Flaky(FakeClient):
        def get_stress_data(self, d):
            raise RuntimeError("mạng chập chờn")

    gsync.sync(paths2, client=Flaky(), days=2, **quiet(today=TODAY))
    assert "full_sync_day" not in read_json(paths2.sync_state)   # có lỗi ⇒ lượt nhanh vẫn tải lại hôm qua


def test_quick_sync_skips_profile_and_old_gaps(tmp_path):
    paths = default_paths(tmp_path)
    gsync.sync(paths, client=FakeClient(), days=5, **quiet(today=TODAY))
    RawStore(paths.raw).path("sleep", "2026-10-11").unlink()   # lỗ hổng cũ: lượt đầy đủ tải bù, lượt nhanh thì không
    client = FakeClient()
    extra = []
    client.get_activities_by_date = lambda a, b: extra.append(("activities", a, b)) or []
    client.get_user_profile = lambda: extra.append("profile") or {}
    result = gsync.sync(paths, client=client, quick=True, **quiet(today=TODAY))
    # đồ giả không có HRV/Readiness thật ⇒ vẫn thử; hôm qua đã chốt bởi lượt đầy đủ hôm nay
    assert sorted(client.calls) == sorted((k, "2026-10-15") for k in gsync.TODAY_KINDS + gsync.ONCE_KINDS)
    assert extra == [("activities", "2026-10-15", "2026-10-15")]   # không gọi hồ sơ
    assert result["days"] == 1 and result["error_count"] == 0
    assert not RawStore(paths.raw).has("sleep", "2026-10-11")


def test_quick_snapshots_never_miss_or_duplicate(tmp_path):
    """Lượt 9:30 thấy tới 9:30, lượt 10:00 thấy tới 10:00 ⇒ file cuối có đúng mọi điểm, mỗi điểm một lần."""
    paths = default_paths(tmp_path)
    day0 = 1760461200000   # 2026-10-15 00:00 giờ VN (GMT+7)
    points = lambda until_min: [[day0 + m * 60000, 60 + m % 30] for m in range(0, until_min + 1, 2)]  # noqa: E731

    class Growing(FakeClient):
        upto = 9 * 60 + 30

        def get_heart_rates(self, d):
            self.calls.append(("heart_rates", d))
            return {"heartRateValues": points(self.upto) if d == "2026-10-15" else []}

    client = Growing()
    gsync.sync(paths, client=client, quick=True, **quiet(today=TODAY))
    client.upto = 10 * 60          # thêm dữ liệu sau 9:30:01
    gsync.sync(paths, client=client, quick=True, **quiet(today=TODAY))
    from garmin_health import normalize as nz

    samples = nz.heart_rates(RawStore(paths.raw).load("heart_rates", "2026-10-15"))["samples"]
    assert [t for t, _ in samples] == [p[0] for p in points(10 * 60)]
    assert len({t for t, _ in samples}) == len(samples)


def test_cli_passes_quick_flag(tmp_path, monkeypatch):
    import run

    seen = {}
    monkeypatch.setattr(gsync, "sync", lambda paths, **kw: seen.update(kw) or {"error_count": 0})
    monkeypatch.setattr(run.builder, "build", lambda paths: None)
    assert run.main(["sync", "--quick", "--data-dir", str(tmp_path)]) == 0
    assert seen["quick"] is True and seen["days"] is None
