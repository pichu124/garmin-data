"""Giải thích + lời khuyên theo quy tắc (explain.py): đúng số, đúng dấu, không lặp, có trong file chi tiết."""
import json

from garmin_health import explain

QUESTIONS = [{"key": "alcohol", "label": "Uống rượu bia"}, {"key": "meditation", "label": "Thiền / thở sâu"}]


def make_day(**over):
    d = {
        "date": "2026-10-10", "partial": False,
        "recovery": {"score": 45, "zone": "yellow", "calibrating": False, "inputs": ["hrv", "rhr", "sleep"],
                     "contributions": {"hrv": -12.3, "rhr": 1.0, "sleep": 4.2}},
        "vitals": {"hrv": 40.0, "rhr": 52, "resp": 14.5, "spo2": 96.0},
        "health": {
            "hrv": {"value": 40.0, "mean": 50.0, "lo": 41.0, "hi": 59.0, "status": "low"},
            "rhr": {"value": 52, "mean": 51.6, "lo": 49.0, "hi": 54.0, "status": "in"},
            "resp": {"value": 14.5, "mean": 14.4, "lo": 13.8, "hi": 15.0, "status": "in"},
            "spo2": {"value": 96.0, "mean": 96.1, "lo": 95.0, "hi": 97.2, "status": "in"},
        },
        "sleep": {"hours": 7.5, "need_h": 8.0, "in_bed_h": 8.0, "efficiency": 94, "consistency": 80, "performance": 88,
                  "sufficiency": 94, "restorative_pct": 45, "stages": {"awake": 30}},
        "need": {"total_h": 8.0, "baseline_h": 7.75, "strain_h": 0.25, "debt_h": 0.0, "nap_h": 0.0},
        "strain": {"score": 11.0, "target": [9.8, 12.8], "light_min": 120},
        "garmin": {"stress_min": {"rest": 600, "low": 300, "medium": 40, "high": 10}},
        "activities": [],
        "journal": None,
    }
    for k, v in over.items():
        d[k] = {**d[k], **v} if isinstance(v, dict) and isinstance(d.get(k), dict) else v
    return d


def text(sec):
    return " | ".join(sec["lines"] + sec["advice"])


def test_recovery_names_big_drivers_with_sign_and_baseline():
    sec = explain.recovery(make_day(), questions=QUESTIONS)
    assert sec["lines"][0] == "Hồi phục 45% — Hồi phục vừa."
    assert "HRV 40 ms, thấp hơn mức thường ngày (50 ms) → −12 điểm." in sec["lines"]
    assert "Hiệu suất ngủ 88% (trên mốc trung tính 80%) → +4 điểm." in sec["lines"]
    assert not any(x.startswith("Nhịp tim nghỉ") for x in sec["lines"])   # +1 điểm: quá nhỏ để nêu
    assert sec["advice"][0] == "Tập vừa sức (aerobic nhẹ, kỹ thuật), nhắm strain 9.8–12.8; tránh dồn cường độ cao."


def test_recovery_uses_personal_journal_impact():
    impact = [{"key": "alcohol", "label": "Uống rượu bia", "significant": True, "recovery_diff": -21.4},
              {"key": "meditation", "label": "Thiền / thở sâu", "significant": True, "recovery_diff": 9.0}]
    day = make_day(journal={"alcohol": True, "meditation": True})
    sec = explain.recovery(day, journal_impact=impact, questions=QUESTIONS)
    assert "Nhật ký hôm qua: Uống rượu bia." in sec["lines"]   # thói quen tốt không bị kể như yếu tố xấu
    assert "Với bạn, sau những ngày “Uống rượu bia” hồi phục thấp hơn trung bình 21 điểm." in sec["lines"]
    assert any("“Uống rượu bia” làm hồi phục giảm rõ" in x for x in sec["advice"])


def test_recovery_without_score():
    assert "hiệu chỉnh" in text(explain.recovery(make_day(recovery={"score": None, "calibrating": True})))
    assert "Chưa có dữ liệu" in text(explain.recovery(make_day(recovery=None)))


def test_red_zone_illness_signals():
    day = make_day(recovery={"score": 20, "zone": "red", "contributions": {"rhr": -9.0, "resp": -5.5}},
                   vitals={"rhr": 60, "resp": 17.2},
                   health={"rhr": {"value": 60, "mean": 52.0, "lo": 49.0, "hi": 55.0, "status": "high"},
                           "resp": {"value": 17.2, "mean": 14.4, "lo": 13.8, "hi": 15.0, "status": "high"}})
    rec = explain.recovery(day)
    assert "Nhịp thở khi ngủ 17.2 lần/phút, cao bất thường so với mức thường ngày (14.4) → −6 điểm." in rec["lines"]
    assert rec["advice"][0] == "Ưu tiên phục hồi: đi bộ nhẹ, giãn cơ, yoga; giữ strain dưới 12.8."
    assert any("chống bệnh" in x for x in rec["advice"])
    hl = explain.health(day, [])
    assert "Nhịp tim nghỉ 60 bpm — cao hơn ngưỡng bình thường của bạn (49–55)." in hl["lines"]
    assert any("nhịp thở tăng" in x for x in hl["lines"]) and any("đi khám" in x for x in hl["advice"])


def test_health_all_in_range_and_low_spo2():
    ok = make_day(health={"hrv": {"status": "in"}})
    assert explain.health(ok, [])["lines"] == ["Cả 4 chỉ số nằm trong ngưỡng bình thường của bạn (hoặc lệch theo hướng tốt) ✓."]
    low = make_day(health={"hrv": {"status": "in"}, "spo2": {"value": 90.5, "mean": 96.0, "lo": 94.5, "hi": 97.5, "status": "low"}})
    assert any("dưới 92%" in x for x in explain.health(low, [])["advice"])
    assert explain.health(make_day(health=None), [])["lines"][0].startswith("Chưa đủ dữ liệu")
    only_rhr = make_day(health={k: {"status": None} for k in ("hrv", "resp", "spo2")})   # đêm không đeo đồng hồ
    assert explain.health(only_rhr, [])["lines"][0] == "Nhịp tim nghỉ nằm trong ngưỡng bình thường của bạn (hoặc lệch theo hướng tốt) ✓."


def test_health_flags_unusual_stress_but_not_on_partial_day():
    prev = [make_day(garmin={"stress_min": {"medium": 30, "high": 5}}) for _ in range(5)]
    busy = make_day(health={"hrv": {"status": "in"}}, garmin={"stress_min": {"medium": 90, "high": 40}})
    assert "Stress vừa + cao 130 phút, nhiều hơn thường ngày (35 phút)." in explain.health(busy, prev)["lines"]
    assert not any("Stress" in x for x in explain.health({**busy, "partial": True}, prev)["lines"])


def test_sleep_need_shortfall_and_habits():
    day = make_day(sleep={"hours": 6.0, "need_h": 8.5, "efficiency": 78, "consistency": 55, "restorative_pct": 30,
                          "sufficiency": 71, "performance": 70},
                   need={"total_h": 8.5, "strain_h": 0.25, "debt_h": 0.5, "nap_h": -0.25})
    prev = [make_day() for _ in range(5)]   # ngủ sâu + REM 45%
    sec = explain.sleep(day, prev)
    assert sec["lines"][0] == "Ngủ 6h00 / cần 8h30 — đáp ứng 71% nhu cầu, hiệu suất ngủ 70%."
    assert "Nhu cầu = nền 7h45, strain hôm qua +15 phút, nợ ngủ +30 phút, ngủ trưa −15 phút." in sec["lines"]
    assert "Thiếu 2h30 so với nhu cầu — phần thiếu cộng vào nợ ngủ các đêm tới." in sec["lines"]
    assert "Ngủ sâu + REM 30% — thấp hơn mức thường ngày của bạn (45%)." in sec["lines"]
    assert len(sec["advice"]) == 2 and not any(x.startswith("Đêm nay") for x in sec["advice"])


def test_sleep_planner_only_when_given():
    planner = {"wake": "06:30", "need": {"total_h": 8.25, "debt_h": 0.75},
               "options": [{"key": "peak", "bedtime": "21:40"}, {"key": "perform", "bedtime": "22:55"}, {"key": "get_by", "bedtime": "00:05"}]}
    sec = explain.sleep(make_day(), [], planner=planner)
    assert sec["advice"][0] == "Đêm nay: lên giường lúc 21:40 để ngủ đủ 100% nhu cầu (8h15), muộn nhất 22:55 để đạt 85% — dậy lúc 06:30."
    assert sec["advice"][1] == "Đang nợ ngủ 45 phút — ngủ sớm hơn 1–2 đêm tới để trả dần."
    assert explain.sleep(make_day(sleep=None), [], planner=planner)["advice"][1].startswith("Đêm nay")


def test_minutes_to_reach_matches_strain_curve():
    from garmin_health.strain import strain_from_load, trimp_per_min

    m = explain.minutes_to_reach(0.0, 10.0, 0.65, "male")
    assert m == 80   # tải cần ≈ 113.8, Vùng 2 ≈ 1.45/phút ⇒ 78.5 → làm tròn lên 80
    assert strain_from_load(trimp_per_min(0.65, "male") * m) >= 10.0
    assert explain.minutes_to_reach(5.0, 10.0, 0.75) < explain.minutes_to_reach(5.0, 10.0, 0.65)
    assert explain.minutes_to_reach(12.0, 10.0, 0.65) == 0


def test_strain_partial_day_coaching():
    day = make_day(partial=True, strain={"score": 4.0, "target": [9.8, 12.8]})
    sec = explain.strain(day, sex="male")
    assert sec["lines"][0] == "Strain đến hiện tại 4.0 (mức nhẹ)."
    assert sec["lines"][1] == "Còn 5.8 nữa để vào vùng tối ưu 9.8–12.8 theo hồi phục sáng nay."
    assert sec["advice"][0].startswith("Để vào vùng tối ưu: khoảng ")
    done = explain.strain(make_day(strain={"score": 15.2}, activities=[
        {"name": "Chạy dài", "duration_min": 95, "strain": 13.1}, {"name": "Đi bộ", "duration_min": 30, "strain": 2.0}]))
    assert "Vượt vùng tối ưu 9.8–12.8 — tải cao hơn mức cơ thể sẵn sàng." in done["lines"]
    assert "Đóng góp lớn nhất: Chạy dài 95 phút (strain 13.1)." in done["lines"]
    assert "Strain này làm nhu cầu ngủ đêm đó tăng thêm 33 phút." in done["lines"]
    assert explain.strain(make_day(strain={"score": None}))["lines"][0].startswith("Chưa có")


def test_outlook_summarises_without_repeating_a_metric():
    day = make_day(health={"hrv": {"value": 40.0, "mean": 50.0, "lo": 41.0, "hi": 59.0, "status": "low"},
                           "spo2": {"value": 93.0, "mean": 96.0, "lo": 94.5, "hi": 97.5, "status": "low"}})
    out = explain.day([make_day(), day], 1)["outlook"]
    assert out["title"] == "Hồi phục vừa · 45%"
    assert not any("ngưỡng bình thường của bạn (41–59)" in x for x in out["lines"])   # HRV đã nêu ở phần hồi phục
    assert "SpO2 khi ngủ 93.0% — thấp hơn ngưỡng bình thường của bạn (94.5–97.5)." in out["lines"]
    assert len(out["advice"]) == len(set(out["advice"])) <= 4
    assert explain.day([make_day(recovery=None)], 0)["outlook"]["title"] == "Chưa có điểm hồi phục"


def test_build_writes_explain_into_day_details(demo_summary):
    paths, summary = demo_summary
    days = summary["days"]
    for i, d in enumerate(days):
        det = json.loads((paths.processed / "days" / f"{d['date']}.json").read_text(encoding="utf-8"))
        ex = det["explain"]
        assert set(ex) == {"outlook", "recovery", "sleep", "strain", "health"}
        for sec in ex.values():
            for line in sec["lines"] + sec["advice"]:
                assert line and "None" not in line and "nan" not in line.split()
        planned = any(x.startswith("Đêm nay") for x in ex["sleep"]["advice"])
        assert planned == (i == len(days) - 1)   # kế hoạch ngủ chỉ cho đêm nay
