"""Chụp màn hình mọi màn hình của app (390px + 1280px) để soát giao diện.

    python scripts/shots.py http://127.0.0.1:8765 out_dir [--routes home/overview,trends]

Cần `pip install playwright`; dùng Chrome/Edge đã cài sẵn (không tải Chromium).
In ra lỗi console + tràn ngang (scrollWidth > innerWidth) cho từng ảnh.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROUTES = ["home/overview", "home/sleep", "home/recovery", "home/strain", "trends", "health", "journal"]
WIDTHS = {"m": (390, 844), "d": (1280, 900)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--routes", default=",".join(ROUTES))
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    problems = 0
    with sync_playwright() as p:
        for channel in ("chrome", "msedge", None):
            try:
                browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
                break
            except Exception:  # noqa: BLE001 — thử trình duyệt kế tiếp
                continue
        else:
            print("không mở được Chrome/Edge/Chromium", file=sys.stderr)
            return 2
        for tag, (w, hgt) in WIDTHS.items():
            page = browser.new_page(viewport={"width": w, "height": hgt}, device_scale_factor=1)
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            for route in args.routes.split(","):
                errors.clear()
                page.goto(f"{args.url.rstrip('/')}/#{route}")
                page.wait_for_timeout(700)
                name = f"{route.replace('/', '-')}_{tag}.png"
                page.screenshot(path=str(out / name), full_page=True)
                overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                note = []
                if overflow > 0:
                    note.append(f"tràn ngang {overflow}px")
                if errors:
                    note.append("console: " + " | ".join(errors[:3]))
                problems += bool(note)
                print(f"{name}: {'; '.join(note) or 'ok'}")
            page.close()
        browser.close()
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
