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
