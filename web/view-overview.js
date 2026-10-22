/* Tổng quan kiểu WHOOP — vòng lặp mỗi ngày quanh 3 trụ: Hồi phục (sáng nay sẵn sàng tới đâu ⇒ nên tập nặng tới đâu)
 * → Strain (tải tập hôm nay so với mục tiêu) → Ngủ (đêm nay lên giường lúc nào). Số lấy ngay từ summary; phần huấn luyện
 * chi tiết (vì sao, số phút cần tập, cảnh báo sức khoẻ) từ explain.coach trong days/<ngày>.json (explain.py). */
(function () {
  'use strict';
  const { h, fmt } = window.GH;
  const { S, ZONE, icon, val, isNum, prevAvg, trendBadge, zoneOf, card, go, mount, getDetail, recoveryRing, strainRing, sleepRing, activityList, hrCard, views } = window.GHA;

  // thang cường độ: vùng hồi phục → mức tập khuyên dùng
  const LEVELS = [['red', 'Nhẹ', 'phục hồi'], ['yellow', 'Vừa', 'duy trì'], ['green', 'Nặng', 'tăng sức']];
  // giống explain.CALIBRATING / NO_RECOVERY
  const CALIBRATING = ['Đang hiệu chỉnh', 'Cần ít nhất 4 đêm đeo đồng hồ khi ngủ để biết mức sẵn sàng của riêng bạn.'];
  const NO_RECOVERY = ['Chưa có điểm hồi phục', 'Không có dữ liệu giấc ngủ/HRV đêm trước — đeo đồng hồ khi ngủ.'];
  // hướng "tốt" khi lệch ngưỡng cá nhân (giống view-health)
  const FAV = { hrv: 'high', rhr: 'low', resp: null, spo2: 'high' };

  function viewOverview(d) {
    const slots = { why: h('div', { class: 'why' }), next: h('p', { class: 'next' }), alerts: h('span', { class: 'alerts' }) };
    mount(() => getDetail(d.date).then(det => fillCoach(d, det && det.explain && det.explain.coach, slots)));
    return [
      readyCard(d, slots.why),
      h('div', { class: 'grid grid-2' }, strainCard(d, slots.next), sleepCard(d)),
      healthStrip(d, slots.alerts),
      h('div', { class: 'grid grid-2' }, card('Hoạt động', null, activityList(d, false)), keyStats(d)),
      hrCard(d),
    ];
  }

  // ① Hồi phục → một câu trả lời: hôm nay tập nặng tới đâu
  function readyCard(d, why) {
    const z = zoneOf(d), r = d.recovery || {};
    const [verdict, msg] = z ? [z.verdict, z.msg] : r.calibrating ? CALIBRATING : NO_RECOVERY;
    const ringNode = recoveryRing(d, 150);
    ringNode.setAttribute('aria-hidden', 'true');
    const lv = LEVELS.find(([k]) => k === r.zone);
    return h('section', { class: 'card ready' },
      h('h2', { text: d.date === S.summary.today ? 'Hôm nay nên tập thế nào?' : 'Ngày này nên tập thế nào?' }),
      h('div', { class: 'ready-body' },
        h('button', { class: 'ready-ring', type: 'button', 'aria-label': `Hồi phục ${r.score ?? 'chưa có'}% — xem chi tiết`, onclick: () => go({ sub: 'recovery' }) },
          ringNode, h('span', { class: 'name', text: 'Hồi phục' })),
        h('div', { class: 'ready-text' },
          h('div', { class: 'verdict', style: z ? { color: z.color } : null, text: verdict }),
          h('p', { class: 'msg', text: msg }),
          lv ? h('div', { class: 'levels', role: 'img', 'aria-label': `Mức tập khuyên dùng: ${lv[1]}` },
            LEVELS.map(([k, name, sub]) => h('div', { class: `level${k === r.zone ? ' on' : ''}`, style: k === r.zone ? { background: ZONE[k].color } : null },
              h('b', { text: name }), h('small', { text: sub })))) : null)),
      why);
  }

  // đầu thẻ trụ: vòng nhỏ + tên + dòng phụ, bấm để sang tab chi tiết
  // line: mảng chữ; mỗi phần không bị ngắt dòng giữa chừng (vd "11.2–14.2")
  function pillarHead(sub, ringNode, title, line) {
    ringNode.setAttribute('aria-hidden', 'true');
    return h('button', { class: 'pillar-head', type: 'button', onclick: () => go({ sub }) },
      ringNode, h('span', {}, h('span', { class: 'h2', text: title }), h('span', { class: 'line' }, line.map((t, i) => h('span', { text: i ? ` · ${t}` : t })))),
      icon('right', { class: 'chev' }));
  }

  // ② Strain: tải tập so với vùng tối ưu theo hồi phục sáng nay
  function strainCard(d, next) {
    const st = d.strain || {}, t = st.target, cur = st.score || 0;
    const line = isNum(st.score) ? [`Strain ${fmt.n(st.score, 1)}`, ...(t ? [`mục tiêu ${fmt.n(t[0], 1)}–${fmt.n(t[1], 1)}`] : [])] : ['Chưa có dữ liệu nhịp tim'];
    return h('section', { class: 'card pillar' },
      pillarHead('strain', strainRing(d, 60), d.partial ? 'Tải tập hôm nay' : 'Tải tập', line),
      t ? h('div', {},
        h('div', { class: 'progress', role: 'img', 'aria-label': `Strain ${fmt.n(cur, 1)} trên mục tiêu ${fmt.n(t[0], 1)} đến ${fmt.n(t[1], 1)}` },
          h('div', { class: 'band', style: { left: `${(t[0] / 21) * 100}%`, width: `${((t[1] - t[0]) / 21) * 100}%` } }),
          h('div', { class: 'fill', style: { width: `${(Math.min(21, cur) / 21) * 100}%` } })),
        h('div', { class: 'progress-scale' }, h('span', { text: '0' }), h('span', { text: 'vùng tối ưu' }), h('span', { text: '21' }))) : null,
      next);
  }

  // ③ Ngủ: đêm qua so với nhu cầu, đêm nay lên giường lúc nào (kế hoạch chỉ có cho ngày mới nhất)
  function sleepCard(d) {
    const sl = d.sleep, latest = S.idx[d.date] === S.days.length - 1;
    const p = latest ? S.summary.planner : null;
    const opt = k => (p ? p.options.find(o => o.key === k) : null);
    const perform = opt('perform'), peak = opt('peak');
    const night = latest ? 'Đêm qua' : 'Đêm trước';
    const line = sl ? [`${night} ${fmt.dur(sl.hours)}`, `cần ${fmt.dur(sl.need_h)}`] : [`${night}: không có dữ liệu`];
    const kids = [pillarHead('sleep', sleepRing(d, 60), perform ? 'Ngủ đêm nay' : 'Giấc ngủ', line)];
    if (perform && peak) {
      kids.push(h('div', { class: 'bed' }, h('span', { class: 'sec', text: 'Lên giường trước' }), h('b', { text: perform.bedtime }), h('small', { text: `đạt ${perform.pct}% nhu cầu` })),
        h('p', { class: 'next', text: `Lý tưởng ${peak.bedtime} để ngủ đủ ${fmt.dur(p.need.total_h)} · dậy ${p.wake}` }));
    } else if (sl) {
      kids.push(h('p', { class: 'next', text: `Hiệu suất ngủ ${sl.performance}% · ${sl.onset} → ${sl.wake}` }));
    }
    const debt = p ? p.need.debt_h : val(d, 'need', 'debt_h');
    if (isNum(debt) && debt >= 0.25) kids.push(h('p', { class: 'note', text: `Nợ ngủ ${fmt.dur(debt)}${p ? ' — ngủ sớm hơn 1–2 đêm để trả dần' : ''}` }));
    return h('section', { class: 'card pillar' }, kids);
  }

  // Health Monitor gói thành một dòng; lệch ngưỡng thì hiện câu cảnh báo (explain.coach.health)
  function healthStrip(d, alerts) {
    const hm = d.health || {};
    const measured = Object.keys(FAV).filter(k => hm[k] && hm[k].status);
    const ok = measured.filter(k => hm[k].status === 'in' || hm[k].status === FAV[k]).length;
    const fine = measured.length > 0 && ok === measured.length;
    const text = !measured.length ? 'Sức khoẻ: chưa đủ dữ liệu để dựng ngưỡng cá nhân'
      : fine ? `Sức khoẻ: ${ok}/${measured.length} chỉ số trong ngưỡng của bạn ✓` : `Sức khoẻ: ${measured.length - ok}/${measured.length} chỉ số lệch ngưỡng của bạn`;
    return h('button', { class: `card health-strip${!measured.length ? ' none' : fine ? '' : ' warn'}`, type: 'button', onclick: () => go({ tab: 'health' }) },
      h('span', { class: 'dot' }), h('span', { class: 'txt' }, h('span', { text }), alerts), icon('right', { class: 'chev' }));
  }

  function fillCoach(d, co, { why, next, alerts }) {
    if (!co) return;   // file chi tiết cũ chưa build lại: giữ phần số, bỏ phần lời
    const chips = co.why.map(w => h('span', { class: `chip ${w.good ? 'good' : 'bad'}` }, w.text,
      isNum(w.pts) ? h('b', { text: `${w.pts > 0 ? '+' : '−'}${Math.abs(w.pts)}` }) : null));
    if (chips.length) why.replaceChildren(h('span', { class: 'why-title', text: 'Vì sao' }), h('div', { class: 'chips' }, chips));
    else if (co.zone) why.replaceChildren(h('p', { class: 'muted', text: 'Các chỉ số đều gần mức thường ngày của bạn.' }));
    if (co.strain) next.textContent = co.strain.text;
    else if (!isNum(val(d, 'strain', 'score'))) next.textContent = 'Chưa có nhịp tim cả ngày để tính strain.';
    alerts.replaceChildren(...co.health.map(t => h('span', { class: 'alert', text: t })));
  }

  function keyStats(d) {
    const i = S.idx[d.date];
    const items = [
      ['HRV', val(d, 'vitals', 'hrv'), 'ms', x => val(x, 'vitals', 'hrv'), true, 0],
      ['Nhịp tim nghỉ', val(d, 'vitals', 'rhr'), 'bpm', x => val(x, 'vitals', 'rhr'), false, 0],
      ['Nhịp thở', val(d, 'vitals', 'resp'), 'lần/ph', x => val(x, 'vitals', 'resp'), null, 1],
      ['Giờ ngủ', val(d, 'sleep', 'hours'), 'h', x => val(x, 'sleep', 'hours'), true, 'dur'],
      ['Calories', val(d, 'strain', 'calories'), 'kcal', x => (x.partial ? null : val(x, 'strain', 'calories')), null, 0, true],
      ['Số bước', val(d, 'strain', 'steps'), '', x => (x.partial ? null : val(x, 'strain', 'steps')), true, 0, true],
    ];
    // cumulative: số cộng dồn trong ngày — hôm nay đang dở thì so với cả ngày TB30 là sai, bỏ mũi tên
    const rows = items.map(([label, v, unit, get, up, dec, cumulative]) => {
      const avg = prevAvg(i, get);
      const show = dec === 'dur' ? fmt.dur(v) : fmt.n(v, dec);
      const showAvg = dec === 'dur' ? fmt.dur(avg) : fmt.n(avg, dec);
      return h('div', { class: 'stat-row' },
        h('span', { class: 'label', text: label }),
        h('span', { class: 'value' }, show, unit && isNum(v) ? h('small', { text: unit }) : null),
        h('span', { class: 'base' }, cumulative && d.partial ? h('span', { class: 'trend flat', text: 'đến hiện tại' }) : trendBadge(v, avg, up, dec === 'dur' ? 1 : dec), h('br'), `TB30: ${showAvg}`));
    });
    return card('Chỉ số chính', 'So với trung bình 30 ngày trước', h('div', { class: 'stats' }, rows));
  }

  views.overview = viewOverview;
})();
