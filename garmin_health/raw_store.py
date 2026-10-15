"""Kho raw: lưu NGUYÊN VĂN JSON Garmin trả về, mỗi loại × mỗi ngày một file.

Giữ raw để tính lại điểm (đổi công thức, đổi cài đặt) mà không phải tải lại.
    raw/<kind>/<YYYY-MM-DD>.json   kind ∈ DAILY_KINDS
    raw/activities/<id>.json
    raw/profile/{user_settings,hr_zones}.json
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from .config import read_json, write_json

DAILY_KINDS = ("summary", "heart_rates", "sleep", "hrv", "stress", "readiness", "max_metrics")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMPTY = {"_empty": True}   # Garmin trả None/rỗng — vẫn lưu để khỏi tải lại


class RawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, kind: str, day: str) -> Path:
        if kind not in DAILY_KINDS or not _DAY_RE.match(day):
            raise ValueError(f"bad raw key {kind}/{day}")
        return self.root / kind / f"{day}.json"

    def save(self, kind: str, day: str, obj: Any) -> None:
        write_json(self.path(kind, day), EMPTY if obj in (None, {}, []) else obj, compact=True)

    def load(self, kind: str, day: str) -> Any:
        obj = read_json(self.path(kind, day))
        return None if obj == EMPTY else obj

    def has(self, kind: str, day: str) -> bool:
        return self.path(kind, day).is_file()

    def days(self) -> list[str]:
        found: set[str] = set()
        for kind in DAILY_KINDS:
            folder = self.root / kind
            if folder.is_dir():
                found.update(p.stem for p in folder.glob("*.json") if _DAY_RE.match(p.stem))
        return sorted(found)

    # --- hoạt động ---
    def save_activity(self, obj: dict) -> None:
        act_id = str(obj.get("activityId", ""))
        if not act_id.isdigit():
            return
        write_json(self.root / "activities" / f"{act_id}.json", obj, compact=True)

    def activities(self) -> Iterator[dict]:
        folder = self.root / "activities"
        if folder.is_dir():
            for p in sorted(folder.glob("*.json")):
                obj = read_json(p)
                if isinstance(obj, dict):
                    yield obj

    # --- hồ sơ ---
    def save_profile(self, name: str, obj: Any) -> None:
        if name in ("user_settings", "hr_zones") and obj is not None:
            write_json(self.root / "profile" / f"{name}.json", obj)

    def load_profile(self, name: str) -> Any:
        return read_json(self.root / "profile" / f"{name}.json")
