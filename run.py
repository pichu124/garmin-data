"""Garmin Health — tải dữ liệu Garmin và phân tích kiểu WHOOP.

    python run.py login              đăng nhập Garmin (một lần; lưu token)
    python run.py sync [--days 180]  tải dữ liệu mới + tính điểm
    python run.py serve [--lan]      mở giao diện http://127.0.0.1:8765
    python run.py demo               xem thử bằng dữ liệu mẫu (không cần Garmin)
    python run.py build              tính lại điểm từ dữ liệu đã tải
    python run.py doctor             kiểm tra dữ liệu đang có

Mọi lệnh nhận --data-dir (mặc định ./data, hoặc biến GARMIN_DATA_DIR).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from garmin_health import build as builder
from garmin_health.config import ROOT, default_paths, load_dotenv, read_json


def _utf8_console() -> None:
    # Windows console mặc định cp1252 ⇒ in tiếng Việt lỗi UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def cmd_login(args) -> int:
    from garmin_health.sync import login_interactive

    name = login_interactive(args.email)
    print(f"✓ Đã đăng nhập: {name}. Token lưu ở ~/.garminconnect — lần sau không cần mật khẩu.")
    return 0


def cmd_sync(args) -> int:
    from garmin_health.sync import AuthRequired, sync

    paths = default_paths(args.data_dir)
    try:
        result = sync(paths, days=args.days, start=date.fromisoformat(args.start) if args.start else None, force=args.force)
    except AuthRequired as exc:
        print(f"✗ Chưa đăng nhập hoặc token hết hạn: {exc}\n  → chạy: python run.py login")
        return 2
    builder.build(paths)
    return 1 if result["error_count"] else 0


def cmd_build(args) -> int:
    builder.build(default_paths(args.data_dir))
    return 0


def cmd_serve(args) -> int:
    from garmin_health.server import serve

    paths = default_paths(args.data_dir)
    if not (paths.processed / "summary.json").is_file() and paths.raw.is_dir():
        builder.build(paths)
    serve(paths, host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, open_browser=args.open)
    return 0


def cmd_demo(args) -> int:
    from garmin_health import demo
    from garmin_health.server import serve

    paths = default_paths(args.data_dir or ROOT / "data-demo")
    demo.generate(paths, days=args.days)
    builder.build(paths)
    if args.no_serve:
        return 0
    serve(paths, host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, open_browser=args.open)
    return 0


def cmd_doctor(args) -> int:
    paths = default_paths(args.data_dir)
    summary = read_json(paths.processed / "summary.json")
    state = read_json(paths.sync_state, {}) or {}
    print(f"Thư mục dữ liệu : {paths.data}")
    print(f"Đồng bộ lần cuối: {state.get('last_sync') or 'chưa'}")
    if not summary:
        print("Chưa có dữ liệu đã xử lý — chạy: python run.py sync")
        return 1
    cov = builder.coverage(summary)
    days = summary["days"]
    print(f"Khoảng ngày     : {days[0]['date']} → {days[-1]['date']} ({cov['days']} ngày)")
    for key, label in (("recovery", "Recovery"), ("sleep", "Giấc ngủ"), ("strain", "Strain"), ("hrv", "HRV")):
        print(f"  {label:<10}: {cov[key]}/{cov['days']} ngày")
    print(f"  Hoạt động : {cov['activities']}")
    prof = summary["profile"]
    print(f"HRmax {prof['hr_max']:.0f} ({prof['hr_max_source']}) · nhu cầu ngủ nền {prof['sleep_baseline_h']}h")
    if cov["hrv"] < cov["days"] * 0.5:
        print("⚠ Ít đêm có HRV — đồng hồ cần đeo khi ngủ và hỗ trợ HRV Status; Recovery sẽ dựa vào RHR + giấc ngủ.")
        return 1
    return 0


def main(argv=None) -> int:
    _utf8_console()
    load_dotenv()
    ap = argparse.ArgumentParser(description="Garmin Health — phân tích kiểu WHOOP")
    ap.add_argument("--data-dir", help="thư mục dữ liệu (mặc định ./data)")
    # cho phép đặt --data-dir cả SAU tên lệnh (python run.py serve --data-dir X)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    _sub = ap.add_subparsers(dest="cmd", required=True)

    class _Sub:
        def add_parser(self, *a, **kw):
            return _sub.add_parser(*a, parents=[common], **kw)

    sub = _Sub()

    p = sub.add_parser("login", help="đăng nhập Garmin Connect")
    p.add_argument("--email")
    p.set_defaults(fn=cmd_login)

    p = sub.add_parser("sync", help="tải dữ liệu mới + tính điểm")
    p.add_argument("--days", type=int, help="tải lại N ngày gần nhất")
    p.add_argument("--start", help="tải từ ngày YYYY-MM-DD")
    p.add_argument("--force", action="store_true", help="tải lại cả ngày đã có")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("build", help="tính lại điểm từ dữ liệu đã tải")
    p.set_defaults(fn=cmd_build)

    for name, fn, helptext in (("serve", cmd_serve, "mở giao diện web"), ("demo", cmd_demo, "chạy với dữ liệu mẫu")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--lan", action="store_true", help="cho điện thoại cùng Wi-Fi truy cập")
        p.add_argument("--open", action="store_true", help="tự mở trình duyệt")
        if name == "demo":
            p.add_argument("--days", type=int, default=150)
            p.add_argument("--no-serve", action="store_true")
        p.set_defaults(fn=fn)

    p = sub.add_parser("doctor", help="kiểm tra dữ liệu đang có")
    p.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
