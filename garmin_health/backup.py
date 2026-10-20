"""Sao lưu phần KHÔNG tải lại được: settings.json, journal.json, raw/heart_rates, raw/stress.

Garmin chỉ giữ nhịp tim và stress theo phút ~4–5 tháng (giấc ngủ, HRV, tổng ngày, buổi tập thì
giữ lâu) ⇒ bản trên máy này là bản duy nhất của phần cũ hơn. Phần còn lại `sync --start` tải lại được.
auth.json / mcp.json cố ý bỏ ra (băm mật khẩu, token — mất thì đặt lại).
"""
from __future__ import annotations

import os
import zipfile
from datetime import date
from pathlib import Path

from .config import Paths

PREFIX = "garmin-backup-"
IRREPLACEABLE_KINDS = ("heart_rates", "stress")


def backup(paths: Paths, *, out: str | os.PathLike | None = None, keep: int = 30, today: date | None = None) -> Path | None:
    """Ghi <out>/garmin-backup-YYYY-MM-DD.zip (chạy lại trong ngày thì ghi đè), giữ `keep` file mới nhất.

    None nếu chưa có gì để sao lưu.
    """
    files = [p for p in (paths.settings, paths.journal) if p.is_file()]
    files += [p for kind in IRREPLACEABLE_KINDS for p in sorted((paths.raw / kind).glob("*.json"))]
    if not files:
        return None
    out = Path(out).expanduser() if out else paths.backups
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{PREFIX}{(today or date.today()).isoformat()}.zip"
    tmp = target.with_name(f".{target.name}.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(paths.data).as_posix())   # giải nén vào thư mục dữ liệu là xong
    os.replace(tmp, target)
    if keep > 0:
        for old in sorted(out.glob(f"{PREFIX}*.zip"))[:-keep]:
            old.unlink()
    return target
