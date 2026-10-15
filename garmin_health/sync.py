"""Tải dữ liệu từ Garmin Connect về kho raw (thư viện `garminconnect` ≥ 0.3).

Đăng nhập một lần bằng `python run.py login` (email + mật khẩu + MFA nếu có)
⇒ token lưu ở ~/.garminconnect/garmin_tokens.json và tự gia hạn; các lần sau
(kể cả nút Đồng bộ trên web) chỉ dùng token, không cần mật khẩu.
"""
from __future__ import annotations

import getpass
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from .config import Paths, load_settings, read_json, token_dir, write_json
from .raw_store import DAILY_KINDS, RawStore

REFRESH_DAYS = 3      # luôn tải lại 3 ngày cuối: sleep/HRV/strain còn cập nhật muộn
PAUSE_S = 0.35        # nghỉ giữa các call cho lịch sự với Garmin
RATE_LIMIT_WAIT_S = 90

FETCHERS: dict[str, Callable] = {
    "summary": lambda c, d: c.get_user_summary(d),
    "heart_rates": lambda c, d: c.get_heart_rates(d),
    "sleep": lambda c, d: c.get_sleep_data(d),
    "hrv": lambda c, d: c.get_hrv_data(d),
    "stress": lambda c, d: c.get_stress_data(d),
    "readiness": lambda c, d: c.get_training_readiness(d),
    "max_metrics": lambda c, d: c.get_max_metrics(d),
}
assert set(FETCHERS) == set(DAILY_KINDS)


class AuthRequired(RuntimeError):
    """Chưa có token hợp lệ — cần chạy `python run.py login`."""


def _lib():
    try:
        import garminconnect  # noqa: F401
    except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise RuntimeError("Thiếu thư viện: pip install -r requirements.txt (cần Python ≥ 3.12)") from exc
    return garminconnect


def login_interactive(email: str | None = None) -> str:
    """Hỏi email/mật khẩu/MFA trên terminal, lưu token. Trả về tên hiển thị."""
    gc = _lib()
    email = email or os.getenv("GARMIN_EMAIL") or input("Email Garmin: ").strip()
    password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Mật khẩu Garmin (không hiện khi gõ): ")
    client = gc.Garmin(email, password, is_cn=os.getenv("GARMIN_IS_CN") == "1",
                       prompt_mfa=lambda: input("Mã MFA (email/app Garmin): ").strip())
    client.login(token_dir())
    return client.get_full_name() or email


def connect():
    """Đăng nhập chỉ bằng token đã lưu (không hỏi gì) — dùng cho đồng bộ nền."""
    gc = _lib()
    client = gc.Garmin(is_cn=os.getenv("GARMIN_IS_CN") == "1")
    try:
        client.login(token_dir())
    except gc.GarminConnectAuthenticationError as exc:
        raise AuthRequired(str(exc)) from exc
    return client


def plan_days(store: RawStore, *, today: date, backfill: int, start: date | None = None) -> tuple[list[str], str]:
    """(ngày cần tải, mốc tải-lại).

    Ngày D chỉ "chốt" khi đồng hồ đã sync xong sáng D+1 ⇒ những ngày tải lần
    trước còn dở phải tải lại: mọi ngày từ (ngày cuối đã có − REFRESH_DAYS) và
    (hôm nay − REFRESH_DAYS). Ngày cũ hơn mốc này đã có thì bỏ qua (trừ --force).
    """
    have = store.days()
    refresh_from = today - timedelta(days=REFRESH_DAYS)
    if have:
        refresh_from = min(refresh_from, date.fromisoformat(have[-1]) - timedelta(days=REFRESH_DAYS))
    if start is None:
        start = refresh_from if have else today - timedelta(days=backfill - 1)
    n = (today - start).days + 1
    return [(start + timedelta(days=i)).isoformat() for i in range(max(0, n))], refresh_from.isoformat()


def sync(
    paths: Paths,
    *,
    client=None,
    days: int | None = None,
    start: date | None = None,
    force: bool = False,
    today: date | None = None,
    pause: float = PAUSE_S,
    log=print,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict:
    client = client or connect()
    store = RawStore(paths.raw)
    settings = load_settings(paths)
    today = today or date.today()
    if days and start is None:
        start = today - timedelta(days=days - 1)
    targets, refresh_from = plan_days(store, today=today, backfill=settings["backfill_days"], start=start)

    jobs = [(d, k) for d in targets for k in DAILY_KINDS if force or d >= refresh_from or not store.has(k, d)]
    total = len(jobs) + 2
    errors: list[str] = []
    done = 0
    log(f"[sync] {len(targets)} ngày ({targets[0] if targets else '-'} → {today}), {len(jobs)} lượt gọi")

    def call(fn, label):
        nonlocal done
        for attempt in (1, 2):
            try:
                return fn()
            except Exception as exc:  # thư viện ném nhiều loại; phân loại theo tên lớp
                name = type(exc).__name__
                if name == "GarminConnectAuthenticationError":
                    raise AuthRequired(str(exc)) from exc
                if name == "GarminConnectNotFoundError":
                    return None
                if name == "GarminConnectTooManyRequestsError" and attempt == 1:
                    log(f"[sync] Garmin báo quá nhiều yêu cầu — đợi {RATE_LIMIT_WAIT_S}s rồi thử lại")
                    time.sleep(RATE_LIMIT_WAIT_S)
                    continue
                errors.append(f"{label}: {name}: {str(exc)[:160]}")
                return _FAILED
        return _FAILED

    for day, kind in jobs:
        obj = call(lambda: FETCHERS[kind](client, day), f"{kind} {day}")
        if obj is not _FAILED:
            store.save(kind, day, obj)
        done += 1
        if progress:
            progress(done, total, f"{day} · {kind}")
        if pause:
            time.sleep(pause)

    if targets:
        acts = call(lambda: client.get_activities_by_date(targets[0], targets[-1]), "activities")
        for act in acts if isinstance(acts, list) else []:
            store.save_activity(act)
        log(f"[sync] {len(acts) if isinstance(acts, list) else 0} hoạt động")
    done += 1
    for name, fn in (("user_settings", client.get_user_profile), ("hr_zones", client.get_heart_rate_zones)):
        obj = call(fn, name)
        if obj is not _FAILED:
            store.save_profile(name, obj)
    done += 1
    if progress:
        progress(done, total, "xong")

    result = {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": len(targets),
        "calls": len(jobs),
        "errors": errors[-20:],
        "error_count": len(errors),
    }
    state = read_json(paths.sync_state, {}) or {}
    state.update(last_sync=result["finished_at"], last_result=result)
    write_json(paths.sync_state, state)
    if errors:
        log(f"[sync] {len(errors)} lỗi, ví dụ: {errors[0]}")
    return result


class _Failed:
    pass


_FAILED = _Failed()
