"""Giải thích + lời khuyên theo quy tắc cho từng ngày (không AI): câu chữ sinh từ chính các số app đã tính.

Mỗi phần {"lines": [...], "advice": [...]}: lines = chuyện gì xảy ra và vì sao, advice = nên làm gì.
build ghi vào processed/days/<ngày>.json → "explain"; giao diện và connector MCP đọc lại từ đó.
Số theo kiểu EN (1,234.5), giờ ngủ dạng 7h48 — khớp với giao diện.
"""
from __future__ import annotations

import math

from . import sleep_score as sl
from . import strain as st
from .stats import mean

ZONE_LABEL = {"green": "Hồi phục tốt", "yellow": "Hồi phục vừa", "red": "Cần nghỉ ngơi"}
DRIVER_MIN_PTS = 3          # yếu tố cộng/trừ dưới 3 điểm hồi phục thì không nêu
MAX_DRIVERS = 3
# thói quen thường kéo hồi phục xuống (câu hỏi nhật ký mặc định)
NEGATIVE_HABITS = ("alcohol", "late_meal", "caffeine_late", "screen_bed", "stress_work", "sick")
LOW_EFFICIENCY = 85
LOW_CONSISTENCY = 70
RESTORATIVE_GAP = 8         # điểm % ngủ sâu + REM dưới mức thường ngày mới nêu
SHORT_SLEEP_H = 0.25
MIN_NOTE_H = 0.08           # < 5 phút thì không nêu
MIN_HISTORY = 4             # giống baseline: cần ≥4 ngày trước mới so "mức thường ngày"
STRESS_MIN_FLOOR = 60       # phút stress vừa + cao
STRESS_RATIO = 1.5
# %HRR giữa Vùng 2 và Vùng 3 — dùng ước lượng số phút tập còn thiếu
ZONE2_X, ZONE3_X = 0.65, 0.75
LOW_SPO2 = 92


def _n(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def _dur(hours: float) -> str:
    m = int(round(hours * 60))
    return f"{m // 60}h{m % 60:02d}"


def _mins(hours: float) -> str:
    m = int(round(abs(hours) * 60))
    return f"{m} phút" if m < 60 else f"{m // 60}h{m % 60:02d}"


def _get(d: dict | None, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _section(lines: list[str], advice: list[str]) -> dict:
    return {"lines": [x for x in lines if x], "advice": [x for x in advice if x]}


# ---------- hồi phục ----------
def _driver_line(key: str, day: dict, pts: float) -> str | None:
    v, hm = day.get("vitals") or {}, day.get("health") or {}
    sign = f"{'+' if pts > 0 else '−'}{_n(abs(pts))} điểm"

    def vs(val, mean_, unit, dec, unusual=False):
        if mean_ is None or val is None or val == mean_:
            return ""
        if unusual:
            return f", {'cao' if val > mean_ else 'thấp'} bất thường so với mức thường ngày ({_n(mean_, dec)}{unit})"
        return f", {'cao hơn' if val > mean_ else 'thấp hơn'} mức thường ngày ({_n(mean_, dec)}{unit})"

    if key == "hrv" and v.get("hrv") is not None:
        return f"HRV {_n(v['hrv'])} ms{vs(v['hrv'], _get(hm, 'hrv', 'mean'), ' ms', 0)} → {sign}."
    if key == "rhr" and v.get("rhr") is not None:
        return f"Nhịp tim nghỉ {_n(v['rhr'])} bpm{vs(v['rhr'], _get(hm, 'rhr', 'mean'), ' bpm', 0)} → {sign}."
    if key == "sleep":
        perf = _get(day, "sleep", "performance")
        if perf is None:
            return None
        side = "trên" if perf >= 80 else "dưới"
        return f"Hiệu suất ngủ {perf}% ({side} mốc trung tính 80%) → {sign}."
    if key == "resp" and v.get("resp") is not None:
        return f"Nhịp thở khi ngủ {_n(v['resp'], 1)} lần/phút{vs(v['resp'], _get(hm, 'resp', 'mean'), '', 1, True)} → {sign}."
    if key == "spo2" and v.get("spo2") is not None:
        return f"SpO2 khi ngủ {_n(v['spo2'], 1)}%{vs(v['spo2'], _get(hm, 'spo2', 'mean'), '%', 1, True)} → {sign}."
    return None


def _drivers(day: dict) -> list[tuple[str, float]]:
    """Các yếu tố cộng/trừ ≥3 điểm hồi phục, lớn nhất trước."""
    contrib = sorted((_get(day, "recovery", "contributions") or {}).items(), key=lambda kv: -abs(kv[1]))
    return [(k, p) for k, p in contrib if abs(p) >= DRIVER_MIN_PTS][:MAX_DRIVERS]


def recovery(day: dict, *, journal_impact=(), questions=()) -> dict:
    r = day.get("recovery") or {}
    score = r.get("score")
    if score is None:
        if r.get("calibrating"):
            return _section(["Đang hiệu chỉnh baseline cá nhân — cần ít nhất 4 đêm có HRV/nhịp tim nghỉ để chấm điểm."],
                            ["Đeo đồng hồ khi ngủ mỗi đêm."])
        return _section(["Chưa có dữ liệu giấc ngủ/HRV cho sáng ngày này."], ["Đeo đồng hồ khi ngủ để có điểm hồi phục."])

    lines = [f"Hồi phục {score}% — {ZONE_LABEL.get(r.get('zone'), '')}."]
    drivers = _drivers(day)
    lines += [_driver_line(k, day, p) for k, p in drivers]
    if not drivers:
        lines.append("Các chỉ số đều gần mức thường ngày của bạn — không yếu tố nào kéo lệch nhiều.")
    if r.get("inputs") and "hrv" not in r["inputs"]:
        lines.append("Không có HRV đêm qua — điểm dựa vào nhịp tim nghỉ và giấc ngủ.")

    labels = {q["key"]: q["label"] for q in questions}
    answered = day.get("journal") or {}
    habits = [k for k in NEGATIVE_HABITS if answered.get(k) and k in labels]
    if habits:
        lines.append(f"Nhật ký hôm qua: {', '.join(labels[k] for k in habits)}.")
    hurts = {x["key"]: x for x in journal_impact if x.get("significant") and (x.get("recovery_diff") or 0) < 0}
    personal = [hurts[k] for k in habits if k in hurts]
    for x in personal[:2]:
        lines.append(f"Với bạn, sau những ngày “{x['label']}” hồi phục thấp hơn trung bình {_n(abs(x['recovery_diff']))} điểm.")

    target = _get(day, "strain", "target")
    rng = f" {_n(target[0], 1)}–{_n(target[1], 1)}" if target else ""
    zone = r.get("zone")
    advice = [{
        "green": f"Cơ thể sẵn sàng: có thể tập nặng hoặc cường độ cao, nhắm strain{rng}.",
        "yellow": f"Tập vừa sức (aerobic nhẹ, kỹ thuật), nhắm strain{rng}; tránh dồn cường độ cao.",
        "red": f"Ưu tiên phục hồi: đi bộ nhẹ, giãn cơ, yoga{f'; giữ strain dưới {_n(target[1], 1)}' if target else ''}.",
    }.get(zone)]
    worst = next((k for k, p in drivers if p < 0), None)
    if worst == "sleep":
        advice.append("Giấc ngủ kéo điểm xuống nhiều nhất — đêm nay ưu tiên ngủ đủ (xem Kế hoạch ngủ).")
    if any(k in ("resp", "spo2") and p < 0 for k, p in drivers):
        advice.append("Nhịp thở/SpO2 lệch khỏi mức thường ngày có thể là dấu hiệu cơ thể đang chống bệnh — theo dõi thêm, nghỉ nếu thấy mệt.")
    if personal:
        advice.append(f"Dữ liệu của bạn cho thấy “{personal[0]['label']}” làm hồi phục giảm rõ — hạn chế vào tối trước những ngày cần sung sức.")
    return _section(lines, advice[:3])


# ---------- giấc ngủ ----------
def sleep(day: dict, prev: list[dict], *, planner: dict | None = None) -> dict:
    s, need = day.get("sleep"), day.get("need") or {}
    advice: list[str] = []
    if planner and planner.get("options"):
        opts = {o["key"]: o for o in planner["options"]}
        peak, perform = opts.get("peak"), opts.get("perform")
        if peak and perform:
            advice.append(f"Đêm nay: lên giường lúc {peak['bedtime']} để ngủ đủ 100% nhu cầu ({_dur(planner['need']['total_h'])}), "
                          f"muộn nhất {perform['bedtime']} để đạt 85% — dậy lúc {planner['wake']}.")
        if (planner["need"].get("debt_h") or 0) >= 0.5:
            advice.append(f"Đang nợ ngủ {_mins(planner['need']['debt_h'])} — ngủ sớm hơn 1–2 đêm tới để trả dần.")
    if not s:
        return _section(["Không có dữ liệu giấc ngủ đêm qua."], ["Đeo đồng hồ khi ngủ để có điểm giấc ngủ.", *advice])

    lines = [f"Ngủ {_dur(s['hours'])} / cần {_dur(s['need_h'])} — đáp ứng {s['sufficiency']}% nhu cầu, hiệu suất ngủ {s['performance']}%."]
    parts = []
    if (need.get("strain_h") or 0) >= MIN_NOTE_H:
        parts.append(f"strain hôm qua +{_mins(need['strain_h'])}")
    if (need.get("debt_h") or 0) >= MIN_NOTE_H:
        parts.append(f"nợ ngủ +{_mins(need['debt_h'])}")
    if (need.get("nap_h") or 0) <= -MIN_NOTE_H:
        parts.append(f"ngủ trưa −{_mins(need['nap_h'])}")
    if parts:
        lines.append(f"Nhu cầu = nền {_dur(need['baseline_h'])}, {', '.join(parts)}.")
    short = s["need_h"] - s["hours"]
    if short >= SHORT_SLEEP_H:
        lines.append(f"Thiếu {_mins(short)} so với nhu cầu — phần thiếu cộng vào nợ ngủ các đêm tới.")
    eff, cons = s.get("efficiency"), s.get("consistency")
    if eff is not None and eff < LOW_EFFICIENCY:
        awake = _get(s, "stages", "awake")
        lines.append(f"Hiệu quả ngủ {eff}%: nằm {_dur(s['in_bed_h'])} nhưng ngủ {_dur(s['hours'])}"
                     f"{f' ({awake} phút thức)' if awake is not None else ''}.")
        advice.append("Chỉ lên giường khi buồn ngủ, tránh dùng điện thoại trên giường để tăng hiệu quả ngủ.")
    if cons is not None and cons < LOW_CONSISTENCY:
        lines.append(f"Giờ giấc chưa đều (độ đều {cons}%): giờ ngủ/dậy lệch nhau nhiều giữa các đêm.")
        advice.append("Cố định giờ đi ngủ và thức dậy (lệch dưới 30 phút), kể cả cuối tuần.")
    rest = s.get("restorative_pct")
    hist = [_get(x, "sleep", "restorative_pct") for x in prev]
    hist = [x for x in hist if x is not None]
    if rest is not None and len(hist) >= MIN_HISTORY:
        avg = mean(hist)
        if rest <= avg - RESTORATIVE_GAP:
            lines.append(f"Ngủ sâu + REM {rest}% — thấp hơn mức thường ngày của bạn ({_n(avg)}%).")
    return _section(lines, advice[:3])


# ---------- strain ----------
def _level(score: float) -> str:
    return "nhẹ" if score < 10 else "vừa" if score < 14 else "cao" if score < 18 else "rất cao"


def _load_of(strain: float) -> float:
    """Ngược của strain_from_load."""
    strain = min(strain, st.STRAIN_MAX - 0.05)
    return -st.STRAIN_K * math.log(1 - strain / st.STRAIN_MAX)


def minutes_to_reach(current: float, goal: float, x: float, sex: str | None = None) -> int:
    """Số phút ở %HRR = x để strain đi từ current lên goal (làm tròn lên bội số 5)."""
    rate = st.trimp_per_min(x, sex)
    gap = max(0.0, _load_of(goal) - _load_of(current))
    return 5 * math.ceil(gap / rate / 5) if gap > 0 else 0


def strain(day: dict, *, sex: str | None = None) -> dict:
    s = day.get("strain") or {}
    score = s.get("score")
    if score is None:
        return _section(["Chưa có dữ liệu nhịp tim cả ngày để tính strain."], [])
    partial = day.get("partial")
    lines = [f"Strain đến hiện tại {_n(score, 1)} (mức {_level(score)})." if partial
             else f"Strain cả ngày {_n(score, 1)} — mức {_level(score)}."]
    advice: list[str] = []
    target = s.get("target")
    if target:
        lo, hi = target
        rng = f"{_n(lo, 1)}–{_n(hi, 1)}"
        if score < lo:
            lines.append(f"Còn {_n(lo - score, 1)} nữa để vào vùng tối ưu {rng} theo hồi phục sáng nay." if partial
                         else f"Dưới vùng tối ưu {rng} theo hồi phục sáng hôm đó.")
            if partial:
                m2, m3 = minutes_to_reach(score, lo, ZONE2_X, sex), minutes_to_reach(score, lo, ZONE3_X, sex)
                advice.append(f"Để vào vùng tối ưu: khoảng {m2} phút ở Vùng 2 (chạy/đạp nhẹ, nói chuyện được) hoặc {m3} phút ở Vùng 3.")
        elif score <= hi:
            lines.append(f"Trong vùng tối ưu {rng} ✓ — đủ kích thích tập luyện mà không quá sức.")
            if partial:
                advice.append("Đã đủ tải cho hôm nay — có thể dừng ở đây hoặc chỉ vận động nhẹ.")
        else:
            lines.append(f"Vượt vùng tối ưu {rng} — tải cao hơn mức cơ thể sẵn sàng.")
            advice.append("Dừng tập nặng, ăn uống đủ và ngủ sớm để hồi phục kịp." if partial
                          else "Hôm sau nên chủ động nhẹ lại và ngủ đủ để cơ thể bắt kịp.")
    acts = sorted((a for a in day.get("activities") or [] if a.get("strain") is not None), key=lambda a: -a["strain"])
    if acts:
        a = acts[0]
        lines.append(f"Đóng góp lớn nhất: {a.get('name') or a.get('type')} {a.get('duration_min')} phút (strain {_n(a['strain'], 1)}).")
    elif (s.get("light_min") or 0) >= 60:
        lines.append(f"Không có buổi tập — strain đến từ đi lại, việc nhà ({_n(s['light_min'])} phút ở mức nhẹ).")
    extra = sl.strain_adjustment_h(score)
    if extra >= MIN_NOTE_H:
        lines.append(f"Strain này làm nhu cầu ngủ đêm {'nay' if partial else 'đó'} tăng thêm {_mins(extra)}.")
    return _section(lines, advice)


# ---------- sức khoẻ ----------
# (khoá, nhãn, đơn vị, số lẻ, hướng tốt khi lệch ngưỡng)
VITALS = (("hrv", "HRV", " ms", 0, "high"), ("rhr", "Nhịp tim nghỉ", " bpm", 0, "low"),
          ("resp", "Nhịp thở khi ngủ", " lần/phút", 1, None), ("spo2", "SpO2 khi ngủ", "%", 1, "high"))


def _vital_alerts(day: dict) -> list[tuple[str, str, str]]:
    """(khoá, high|low, câu) cho chỉ số lệch ngưỡng cá nhân theo hướng xấu."""
    hm = day.get("health") or {}
    out = []
    for k, label, unit, dec, fav in VITALS:
        m = hm.get(k) or {}
        if m.get("status") in (None, "in", fav):
            continue
        word = "cao hơn" if m["status"] == "high" else "thấp hơn"
        out.append((k, m["status"], f"{label} {_n(m['value'], dec)}{unit} — {word} ngưỡng bình thường của bạn "
                                    f"({_n(m['lo'], dec)}–{_n(m['hi'], dec)})."))
    return out


def health(day: dict, prev: list[dict]) -> dict:
    hm = day.get("health") or {}
    measured = [k for k, *_ in VITALS if _get(hm, k, "status")]
    if not measured:
        return _section(["Chưa đủ dữ liệu để dựng ngưỡng cá nhân (cần ≥4 đêm)."], [])
    alerts = _vital_alerts(day)
    bad = {k: status for k, status, _ in alerts}
    lines, advice = [line for *_, line in alerts], []
    if not bad and len(measured) == 1:   # "Cả 1 chỉ số" nghe sai — gọi đúng tên chỉ số
        label = next(lb for k, lb, *_ in VITALS if k == measured[0])
        lines.append(f"{label} nằm trong ngưỡng bình thường của bạn (hoặc lệch theo hướng tốt) ✓.")
    elif not bad:
        lines.append(f"Cả {len(measured)} chỉ số nằm trong ngưỡng bình thường của bạn (hoặc lệch theo hướng tốt) ✓.")
    if bad.get("rhr") == "high" and (bad.get("resp") == "high" or bad.get("hrv") == "low"):
        other = "nhịp thở tăng" if bad.get("resp") == "high" else "HRV giảm"
        lines.append(f"Nhịp tim nghỉ tăng cùng lúc với {other} thường gặp khi cơ thể chống bệnh, thiếu ngủ, sau rượu bia hoặc tập quá sức.")
        advice.append("Nghỉ ngơi, uống đủ nước, tránh tập nặng hôm nay; nếu kéo dài vài ngày hoặc có triệu chứng (sốt, đau họng) nên đi khám.")
    elif "resp" in bad:
        advice.append("Theo dõi thêm 1–2 đêm: nhịp thở lệch kéo dài có thể là dấu hiệu sắp ốm.")
    spo2 = _get(hm, "spo2", "value")
    if bad.get("spo2") == "low" and spo2 is not None and spo2 < LOW_SPO2:
        advice.append(f"SpO2 khi ngủ dưới {LOW_SPO2}% nếu lặp lại nhiều đêm nên được bác sĩ kiểm tra.")

    sm = _get(day, "garmin", "stress_min")
    if sm and not day.get("partial"):   # hôm nay còn đang cộng dồn — so với cả ngày là sai
        cur = (sm.get("medium") or 0) + (sm.get("high") or 0)
        hist = [(x.get("medium") or 0) + (x.get("high") or 0)
                for x in (_get(p, "garmin", "stress_min") for p in prev if not p.get("partial")) if x]
        if len(hist) >= MIN_HISTORY:
            avg = mean(hist)
            if cur >= max(STRESS_MIN_FLOOR, STRESS_RATIO * avg):
                lines.append(f"Stress vừa + cao {_n(cur)} phút, nhiều hơn thường ngày ({_n(avg)} phút).")
                advice.append("Chèn vài quãng nghỉ ngắn: 5 phút thở chậm (thở ra dài hơn hít vào) hoặc đi bộ ngoài trời.")
    return _section(lines, advice[:3])


# ---------- tổng hợp ----------
def day(days: list[dict], i: int, *, planner: dict | None = None, journal_impact=(), questions=(), sex: str | None = None) -> dict:
    """Giải thích cho days[i]; planner chỉ truyền cho ngày mới nhất (kế hoạch ngủ ĐÊM NAY)."""
    d = days[i]
    prev = days[max(0, i - 30):i]
    sec = {
        "recovery": recovery(d, journal_impact=journal_impact, questions=questions),
        "sleep": sleep(d, prev, planner=planner),
        "strain": strain(d, sex=sex),
        "health": health(d, prev),
    }
    score, zone = _get(d, "recovery", "score"), _get(d, "recovery", "zone")
    title = f"{ZONE_LABEL[zone]} · {score}%" if score is not None and zone in ZONE_LABEL else "Chưa có điểm hồi phục"
    shown = {k for k, _ in _drivers(d)}   # chỉ số đã nêu ở phần hồi phục thì không nhắc lại
    health_alerts = [line for k, _, line in _vital_alerts(d) if k not in shown]
    lines = sec["recovery"]["lines"][1:3] + sec["sleep"]["lines"][:1] + health_alerts[:1]
    advice = (sec["recovery"]["advice"][:1] + [x for x in sec["strain"]["advice"] if x.startswith("Để vào")]
              + [x for x in sec["sleep"]["advice"] if x.startswith("Đêm nay")] + sec["health"]["advice"][:1])
    sec["outlook"] = {"title": title, **_section(lines, list(dict.fromkeys(advice))[:4])}
    return sec
