"""Sao lưu phần KHÔNG tải lại được từ Garmin: settings.json + journal.json.

Raw Garmin không cần sao lưu (`sync --days N` tải lại); auth.json cố ý bỏ ra (băm mật
khẩu + khoá cookie không nên nằm trong file mang đi nơi khác — mất thì đặt lại).
"""
from __future__ import annotations

import os
import zipfile
from datetime import date
from pathlib import Path

from .config import Paths

PREFIX = "garmin-backup-"


def backup(paths: Paths, *, out: str | os.PathLike | None = None, keep: int = 30, today: date | None = None) -> Path | None:
    """Ghi <out>/garmin-backup-YYYY-MM-DD.zip (chạy lại trong ngày thì ghi đè), giữ `keep` file mới nhất.

    None nếu chưa có gì để sao lưu.
    """
    files = [p for p in (paths.settings, paths.journal) if p.is_file()]
    if not files:
        return None
    out = Path(out).expanduser() if out else paths.backups
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{PREFIX}{(today or date.today()).isoformat()}.zip"
    tmp = target.with_name(f".{target.name}.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.name)
    os.replace(tmp, target)
    if keep > 0:
        for old in sorted(out.glob(f"{PREFIX}*.zip"))[:-keep]:
            old.unlink()
    return target
