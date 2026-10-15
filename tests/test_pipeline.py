"""Pipeline end-to-end trên dữ liệu mẫu đúng định dạng Garmin: raw → điểm → JSON cho web."""
import json
import statistics

from garmin_health import build
from garmin_health.config import read_json, save_journal_entry, save_settings

from conftest import NOW


def test_outputs_written_and_cover_days(demo_summary):
    paths, summary = demo_summary
    cov = build.coverage(summary)
    assert cov["days"] >= 115 and cov["sleep"] == cov["days"] and cov["activities"] > 50
    assert cov["recovery"] >= cov["days"] - 5          # chỉ vài ngày đầu hiệu chỉnh
    assert (paths.processed / "summary.json").is_file()
    assert json.loads((paths.processed / "summary.json").read_text(encoding="utf-8"))["version"] == build.VERSION


def test_distributions_look_like_whoop(demo_summary):
    _, summary = demo_summary
    recs = [d["recovery"]["score"] for d in summary["days"] if (d["recovery"] or {}).get("score") is not None]
    strains = [d["strain"]["score"] for d in summary["days"] if not d["partial"] and (d["strain"] or {}).get("score") is not None]
    assert 45 <= statistics.mean(recs) <= 70 and statistics.pstdev(recs) > 12
    assert {"green", "yellow", "red"} <= {d["recovery"]["zone"] for d in summary["days"] if d["recovery"] and d["recovery"]["zone"]}
    assert 6 <= statistics.mean(strains) <= 14 and max(strains) <= 21


def test_first_days_are_calibrating(demo_summary):
    _, summary = demo_summary
    first = summary["days"][0]["recovery"]
    assert first["score"] is None and first["calibrating"]


def test_long_run_scores_higher_than_yoga(demo_summary):
    _, summary = demo_summary
    acts = [a for d in summary["days"] for a in d["activities"] if a["strain"] is not None]
    by_type = {}
    for a in acts:
        by_type.setdefault(a["name"], []).append(a["strain"])
    assert statistics.mean(by_type["Chạy dài cuối tuần"]) > statistics.mean(by_type["Yoga"]) + 4


def test_journal_finds_alcohol_effect(demo_summary):
    _, summary = demo_summary
    alcohol = next(x for x in summary["insights"]["journal"] if x["key"] == "alcohol")
    assert alcohol["recovery_diff"] < -10 and alcohol["significant"]


def test_day_detail_axes(demo_summary):
    paths, summary = demo_summary
    d = summary["days"][-2]["date"]
    det = read_json(paths.processed / "days" / f"{d}.json")
    assert det["hr"] and all(0 <= m <= 1440 for m, _ in det["hr"])
    assert det["sleep"]["start_min"] < 0 < det["sleep"]["end_min"]       # ngủ từ tối hôm trước
    assert {lv[2] for lv in det["sleep"]["levels"]} <= {"deep", "light", "rem", "awake"}
    assert det["next_sleep_start_min"] is None or 1080 <= det["next_sleep_start_min"] < 1440


def test_planner_and_today(demo_summary):
    _, summary = demo_summary
    assert summary["today"] == "2026-10-15"
    p = summary["planner"]
    assert p["for_date"] == "2026-10-16" and len(p["options"]) == 3
    bed = [o["bedtime_min"] for o in p["options"]]
    assert (bed[1] - bed[0]) % 1440 < 180      # mức thấp hơn ⇒ đi ngủ muộn hơn


def test_settings_and_journal_change_rebuild(tmp_path, demo_summary):
    import shutil

    src, _ = demo_summary
    shutil.copytree(src.data, tmp_path / "d")
    from garmin_health.config import default_paths

    paths = default_paths(tmp_path / "d")
    base = build.build(paths, now=NOW, log=lambda *_: None)
    save_settings(paths, {"sleep_baseline_h": 9})
    more = build.build(paths, now=NOW, log=lambda *_: None)
    assert more["days"][-1]["need"]["total_h"] > base["days"][-1]["need"]["total_h"]
    day = more["days"][-1]["date"]
    save_journal_entry(paths, day, {"alcohol": True, "unknown_key": True, "sauna": None})
    again = build.build(paths, now=NOW, log=lambda *_: None)
    assert again["days"][-1]["journal"] == {"alcohol": True}


def test_empty_raw_builds_empty_summary(tmp_path):
    from garmin_health.config import default_paths

    summary = build.build(default_paths(tmp_path), now=NOW, log=lambda *_: None)
    assert summary["days"] == [] and summary["planner"] is None
