"""Đường dẫn, cài đặt người dùng và đọc file .env (không cần python-dotenv)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

# Cài đặt mặc định — người dùng sửa trong app (⚙) hoặc data/settings.json.
DEFAULT_SETTINGS: dict = {
    "sleep_baseline_h": 7.75,  # nhu cầu ngủ nền (giờ); WHOOP tính 7–9h tuỳ người
    "hr_max": None,            # None = tự lấy từ Garmin / tuổi / dữ liệu
    "sex": None,               # "male" | "female" | None = lấy từ Garmin
    "target_wake": None,       # "06:30" | None = giờ dậy trung vị 14 đêm gần nhất
    "backfill_days": 90,       # số ngày tải lần đầu
}

# Câu hỏi nhật ký (giống WHOOP Journal) — trả lời mỗi sáng về HÔM QUA.
DEFAULT_JOURNAL_QUESTIONS: list[dict] = [
    {"key": "alcohol", "label": "Uống rượu bia"},
    {"key": "late_meal", "label": "Ăn tối muộn (sau 21h)"},
    {"key": "caffeine_late", "label": "Cà phê / trà sau 14h"},
    {"key": "screen_bed", "label": "Dùng điện thoại trên giường"},
    {"key": "stress_work", "label": "Căng thẳng công việc"},
    {"key": "meditation", "label": "Thiền / thở sâu"},
    {"key": "sauna", "label": "Xông hơi / tắm nóng"},
    {"key": "sick", "label": "Ốm / mệt"},
]


def load_dotenv(path: Path | None = None) -> None:
    """Nạp KEY=VALUE từ .env vào os.environ (không ghi đè biến đã có)."""
    path = path or ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Paths:
    data: Path

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def settings(self) -> Path:
        return self.data / "settings.json"

    @property
    def journal(self) -> Path:
        return self.data / "journal.json"

    @property
    def sync_state(self) -> Path:
        return self.data / "raw" / "_sync.json"


def default_paths(data_dir: str | os.PathLike | None = None) -> Paths:
    data_dir = data_dir or os.getenv("GARMIN_DATA_DIR") or ROOT / "data"
    return Paths(Path(data_dir).expanduser())


def token_dir() -> str:
    return os.getenv("GARMINTOKENS") or str(Path("~/.garminconnect").expanduser())


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, obj, *, compact: bool = False) -> None:
    """Ghi nguyên tử (tmp + replace) để server không đọc phải file dở dang."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=1)
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: file đang được server đọc dở
            if attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def load_settings(paths: Paths) -> dict:
    stored = read_json(paths.settings, {}) or {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}}


def save_settings(paths: Paths, updates: dict) -> dict:
    """Chỉ nhận khoá đã biết, kiểm kiểu/miền giá trị — dữ liệu đến từ form web."""
    current = load_settings(paths)
    clean = validate_settings(updates)
    current.update(clean)
    write_json(paths.settings, current)
    return current


def validate_settings(updates: dict) -> dict:
    out: dict = {}
    if "sleep_baseline_h" in updates:
        v = float(updates["sleep_baseline_h"])
        if not 5.0 <= v <= 11.0:
            raise ValueError("Nhu cầu ngủ nền phải trong 5–11 giờ")
        out["sleep_baseline_h"] = round(v, 2)
    if "hr_max" in updates:
        v = updates["hr_max"]
        if v in (None, "", 0):
            out["hr_max"] = None
        else:
            v = int(v)
            if not 130 <= v <= 230:
                raise ValueError("Nhịp tim tối đa phải trong 130–230")
            out["hr_max"] = v
    if "sex" in updates:
        v = updates["sex"]
        if v not in (None, "", "male", "female"):
            raise ValueError("Giới tính: male | female")
        out["sex"] = v or None
    if "target_wake" in updates:
        v = updates["target_wake"]
        if v in (None, ""):
            out["target_wake"] = None
        else:
            hh, _, mm = str(v).partition(":")
            if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
                raise ValueError("Giờ dậy dạng HH:MM")
            out["target_wake"] = f"{int(hh):02d}:{int(mm):02d}"
    if "backfill_days" in updates:
        v = int(updates["backfill_days"])
        if not 7 <= v <= 1095:
            raise ValueError("Số ngày tải lần đầu: 7–1095")
        out["backfill_days"] = v
    return out


def load_journal(paths: Paths) -> dict:
    data = read_json(paths.journal, {}) or {}
    return {
        "questions": data.get("questions") or DEFAULT_JOURNAL_QUESTIONS,
        "entries": data.get("entries") or {},
    }


def save_journal_entry(paths: Paths, day: str, answers: dict) -> dict:
    journal = load_journal(paths)
    keys = {q["key"] for q in journal["questions"]}
    clean = {k: bool(v) for k, v in answers.items() if k in keys and v is not None}
    if clean:
        journal["entries"][day] = clean
    else:
        journal["entries"].pop(day, None)
    write_json(paths.journal, journal)
    return journal
