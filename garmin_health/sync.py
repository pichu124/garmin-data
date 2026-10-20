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

from . import normalize as nz
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
# sync --quick (cron 30 phút). Garmin trả dữ liệu THEO CẢ NGÀY (mọi điểm của ngày tính tới lúc hỏi) và mỗi
# (ngày, loại) là MỘT file ghi đè ⇒ lượt sau tự chứa phần mới hơn lượt trước: không sót, không trùng.
# hôm nay, mọi lượt: tổng ngày / nhịp tim / stress chạy suốt ngày; sleep vì giấc trưa (trừ vào nhu cầu đêm nay)
TODAY_KINDS = ("summary", "heart_rates", "stress", "sleep")
# hôm nay, tới khi có: HRV đêm qua chốt một lần; Training Readiness app lấy số lúc thức dậy (AFTER_WAKEUP_RESET)
ONCE_KINDS = ("hrv", "readiness")
# hôm qua, tới khi lượt đầy đủ hôm nay xong: phần 23:30–24:00 và phần đồng hồ đẩy muộn
YESTERDAY_KINDS = ("summary", "heart_rates", "stress")
# max_metrics (VO2max) chỉ đổi sau buổi chạy/đi bộ đủ điều kiện ⇒ để lượt đầy đủ sáng hôm sau lấy
_HAS = {
    "hrv": lambda raw: nz.hrv(raw)["last_night"] is not None,
    "readiness": lambda raw: nz.readiness(raw)["score"] is not None,
}


def plan_quick(store: RawStore, state: dict, today: date) -> list[tuple[str, str]]:
    """(ngày, loại) cần tải trong lượt nhanh.

    - hôm nay: TODAY_KINDS luôn tải lại; ONCE_KINDS tới khi đã có số;
    - hôm qua: YESTERDAY_KINDS tới khi lượt ĐẦY ĐỦ của hôm nay chạy xong (nó tải lại 3 ngày)
      ⇒ không sót 23:30–24:00 hay phần đồng hồ đẩy muộn sáng hôm sau.
    """
    t, y = today.isoformat(), (today - timedelta(days=1)).isoformat()
    jobs = [(t, k) for k in TODAY_KINDS] + [(t, k) for k in ONCE_KINDS if not _HAS[k](store.load(k, t))]
    if (state.get("full_sync_day") or "") < t:
        jobs += [(y, k) for k in YESTERDAY_KINDS]
    return jobs


class AuthRequired(RuntimeError):
    """Chưa có token hợp lệ — cần chạy `python run.py login`."""


class RateLimited(RuntimeError):
    """Garmin vẫn báo 429 sau khi đã đợi — dừng hẳn, đừng gọi tiếp hàng trăm lần."""


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
    quick: bool = False,
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
    if quick:   # 5–10 lượt gọi: đủ nhẹ cho cron 30 phút; ngày cũ/lỗ hổng để lượt đầy đủ buổi sáng lo
        jobs = plan_quick(store, read_json(paths.sync_state, {}) or {}, today)
        targets = sorted({d for d, _ in jobs})
    else:
        targets, refresh_from = plan_days(store, today=today, backfill=settings["backfill_days"], start=start)
        jobs = [(d, k) for d in targets for k in DAILY_KINDS if force or d >= refresh_from or not store.has(k, d)]
        # lượt trước lỗi (mạng/5xx) thì KHÔNG lưu file ⇒ mọi cặp (ngày, loại) còn thiếu
        # từ ngày cũ nhất đã có đều được thử lại, kể cả khi nằm ngoài cửa sổ tải lại
        have = store.days()
        if have and targets:
            first, stop = date.fromisoformat(have[0]), date.fromisoformat(targets[0])
            gaps = [((first + timedelta(days=i)).isoformat(), k) for i in range((stop - first).days) for k in DAILY_KINDS]
            jobs = [j for j in gaps if not store.has(j[1], j[0])] + jobs
    total = len(jobs) + (1 if quick else 2)
    errors: list[str] = []
    done = 0
    log(f"[sync] {'nhanh: ' if quick else ''}{len(targets)} ngày ({targets[0] if targets else '-'} → {today}), {len(jobs)} lượt gọi")

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
                if name == "GarminConnectTooManyRequestsError":
                    if attempt == 2:
                        raise RateLimited("Garmin đang giới hạn tốc độ — dữ liệu đã tải vẫn được giữ, chạy lại sau ~1 giờ") from exc
                    log(f"[sync] Garmin báo quá nhiều yêu cầu — đợi {RATE_LIMIT_WAIT_S}s rồi thử lại")
                    time.sleep(RATE_LIMIT_WAIT_S)
                    continue
                errors.append(f"{label}: {name}: {str(exc)[:160]}")
                return _FAILED
        return _FAILED

    aborted = None
    try:
        for day, kind in jobs:
            obj = call(lambda: FETCHERS[kind](client, day), f"{kind} {day}")
            if obj is not _FAILED:
                store.save(kind, day, obj)
            done += 1
            if progress:
                progress(done, total, f"{day} · {kind}")
            if pause:
                time.sleep(pause)

        if jobs or targets:
            first_day = min([d for d, _ in jobs] + targets[:1])
            acts = call(lambda: client.get_activities_by_date(first_day, today.isoformat()), "activities")
            for act in acts if isinstance(acts, list) else []:
                store.save_activity(act)
            log(f"[sync] {len(acts) if isinstance(acts, list) else 0} hoạt động")
        done += 1
        if not quick:   # hồ sơ (HRmax, vùng tim) hiếm khi đổi — lượt đầy đủ mỗi sáng là đủ
            for name, fn in (("user_settings", client.get_user_profile), ("hr_zones", client.get_heart_rate_zones)):
                obj = call(fn, name)
                if obj is not _FAILED:
                    store.save_profile(name, obj)
            done += 1
    except RateLimited as exc:
        aborted = str(exc)
        errors.append(aborted)
        log(f"[sync] ✗ {aborted}")
    if progress:
        progress(done, total, "xong")

    result = {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": len(targets),
        "calls": len(jobs),
        "errors": errors[-20:],
        "error_count": len(errors),
        "aborted": aborted,
    }
    state = read_json(paths.sync_state, {}) or {}
    state.update(last_sync=result["finished_at"], last_result=result)
    if not quick and not errors:   # lượt đầy đủ trọn vẹn ⇒ hôm qua đã chốt, lượt nhanh thôi tải lại hôm qua
        state["full_sync_day"] = today.isoformat()
    write_json(paths.sync_state, state)
    if errors:
        log(f"[sync] {len(errors)} lỗi, ví dụ: {errors[0]}")
    return result


class _Failed:
    pass


_FAILED = _Failed()
