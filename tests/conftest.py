import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garmin_health import build, demo  # noqa: E402
from garmin_health.config import default_paths  # noqa: E402

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)  # 19:00 giờ VN


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    # .env máy thật không được lọt vào test
    for key in ("GARMIN_DATA_DIR", "GARMINTOKENS", "GARMIN_EMAIL", "GARMIN_PASSWORD", "GARMIN_IS_CN"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(scope="session")
def demo_summary(tmp_path_factory):
    paths = default_paths(tmp_path_factory.mktemp("demo"))
    demo.generate(paths, days=120, now=NOW, log=lambda *_: None)
    summary = build.build(paths, now=NOW, log=lambda *_: None)
    return paths, summary
