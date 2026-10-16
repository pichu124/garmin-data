/* Ngủ: hiệu suất, nhu cầu ngủ, giai đoạn, biểu đồ giấc ngủ, kế hoạch ngủ đêm nay. */
(function () {
  'use strict';
  const { h, fmt, barChart, hypnogram, STAGES } = window.GH;
  const { S, C, getDetail, val, isNum, card, chartCard, tableOf, lastN, tile, go, sleepRing, views } = window.GHA;

  function viewSleep(d) {
    const out = [];
    const sl = d.sleep;
    const ringNode = sleepRing(d, 220);
    ringNode.setAttribute('aria-label', `Hiệu suất ngủ ${sl ? sl.performance : 'chưa có'}%`);
    out.push(h('div', { class: 'hero' }, ringNode,
      h('div', { class: 'zone-label' }, h('span', { class: 'dot', style: { background: C.sleep } }), 'Hiệu suất ngủ'),
      h('p', { class: 'msg', text: sl ? `Ngủ ${fmt.dur(sl.hours)} / cần ${fmt.dur(sl.need_h)} · ${sl.onset} → ${sl.wake}` : 'Không có dữ liệu giấc ngủ đêm qua.' })));
    const need = d.need;
    const needCard = card('Nhu cầu ngủ', 'Cách tính giống WHOOP: nền + strain hôm qua + nợ ngủ − ngủ trưa', h('div', {},
      needRow('Nhu cầu nền', need.baseline_h), needRow('+ Strain hôm qua', need.strain_h), needRow('+ Nợ ngủ', need.debt_h), needRow('− Ngủ trưa', need.nap_h),
      h('div', { class: 'need-row total' }, h('span', { text: 'Tổng cần ngủ' }), h('b', { text: fmt.dur(need.total_h) }))));
    if (sl) {
      const stages = sl.stages;
      const total = STAGES.reduce((a, s) => a + (stages[s.key] || 0), 0) || 1;
      const stageCard = card('Giai đoạn ngủ', `Phục hồi (sâu + REM): ${sl.restorative_pct ?? '—'}% thời gian ngủ`,
        h('div', { class: 'stack', role: 'img', 'aria-label': STAGES.map(s => `${s.label} ${stages[s.key]} phút`).join(', ') },
          STAGES.map(s => h('span', { style: { width: `${(stages[s.key] / total) * 100}%`, background: s.color }, title: `${s.label}: ${fmt.durMin(stages[s.key])}` }))),
        h('div', { class: 'legend l4' }, STAGES.map(s => h('div', { class: 'item' }, h('span', { class: 'sw', style: { background: s.color } }), h('span', { class: 'k', text: s.label }),
          h('span', { class: 'v' }, fmt.durMin(stages[s.key]), h('small', { text: `${Math.round((stages[s.key] / total) * 100)}%` }))))));
      out.push(h('div', { class: 'grid grid-2' }, needCard, stageCard));
      out.push(chartCard('Biểu đồ giấc ngủ', `${sl.onset} → ${sl.wake} · ${sl.awake_count ?? 0} lần thức giấc`, box => {
        getDetail(d.date).then(det => { if (det && det.sleep) hypnogram(box, { sleep: det.sleep }); else box.replaceChildren(h('p', { class: 'muted', text: 'Không có chi tiết giai đoạn.' })); });
      }, null));
      out.push(h('div', { class: 'tiles t4', style: { marginBottom: '12px' } },
        tile('Trên giường', fmt.dur(sl.in_bed_h), 'h'), tile('Hiệu quả', fmt.n(sl.efficiency), '%', 'ngủ / nằm'),
        tile('Độ đều', fmt.n(sl.consistency), '%', 'giờ giấc 4 đêm'), tile('Nhịp thở', fmt.n(sl.resp, 1), 'lần/ph'),
        tile('SpO2', fmt.n(sl.spo2, 1), '%'), tile('Garmin Sleep Score', fmt.n(sl.garmin_score), ''),
        tile('Đáp ứng nhu cầu', fmt.n(sl.sufficiency), '%'), tile('Nợ ngủ mang sang', fmt.dur(need.debt_h), 'h')));
    } else out.push(needCard);
    if (S.idx[d.date] === S.days.length - 1 && S.summary.planner) out.push(plannerCard(S.summary.planner));
    const days = lastN(30);
    out.push(chartCard('Giờ ngủ vs nhu cầu (30 ngày)', 'Cột = giờ ngủ thực · vạch trắng = nhu cầu đêm đó', box => barChart(box, {
      data: days.map(x => ({ key: x.date, label: fmt.day(x.date), value: val(x, 'sleep', 'hours'), color: C.sleep, marker: val(x, 'need', 'total_h'),
        title: fmt.day(x.date), rows: [{ color: C.sleep, label: 'Đã ngủ', value: fmt.dur(val(x, 'sleep', 'hours')) }, { color: '#e2e8f0', label: 'Cần', value: fmt.dur(val(x, 'need', 'total_h')) },
          { label: 'Hiệu suất', value: isNum(val(x, 'sleep', 'performance')) ? `${x.sleep.performance}%` : '—' }], onClick: () => go({ date: x.date }) })),
      yMax: 11, ticks: [0, 4, 8], fmtY: v => `${v}h`, highlight: d.date, valueLabel: v => fmt.dur(v),
    }), () => tableOf(['Ngày', 'Ngủ', 'Cần', 'Hiệu suất', 'Hiệu quả'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.dur(val(x, 'sleep', 'hours')),
      fmt.dur(val(x, 'need', 'total_h')), fmt.n(val(x, 'sleep', 'performance')), fmt.n(val(x, 'sleep', 'efficiency'))]))));
    return out;
  }
  // dấu +/− nằm ở nhãn; giá trị luôn hiện trị tuyệt đối (nap_h lưu số âm)
  const needRow = (label, hrs) => h('div', { class: 'need-row' }, h('span', { text: label }), h('b', { text: fmt.dur(Math.abs(hrs || 0)) }));
  function plannerCard(p) {
    return card('Kế hoạch ngủ đêm nay', `Để dậy lúc ${p.wake} (${p.wake_source}) · cần ${fmt.dur(p.need.total_h)} giấc ngủ`,
      h('div', { class: 'planner' }, p.options.map(o => h('div', { class: 'plan' },
        h('div', {}, h('div', { class: 'l', text: `${o.label} · ${o.pct}%` }), h('div', { class: 's', text: `nằm ${fmt.dur(o.in_bed_h)} trên giường` })),
        h('div', { class: 't', text: o.bedtime })))),
      h('p', { class: 'note', text: `Đã trừ hao thời gian thức trong đêm (hiệu quả ngủ ${p.efficiency ?? 90}%). Đổi giờ dậy trong ⚙ Cài đặt.` }));
  }

  views.sleep = viewSleep;
})();
