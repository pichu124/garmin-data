/* Hồi phục: vòng hồi phục, các yếu tố đóng góp, HRV · nhịp tim nghỉ · nhịp thở 30 ngày. */
(function () {
  'use strict';
  const { h, fmt, barChart } = window.GH;
  const { S, C, val, isNum, prevAvg, dateLabel, zoneOf, card, chartCard, tableOf, lastN, go, recoveryRing, vitalLine, explainCard, views } = window.GHA;

  function viewRecovery(d) {
    const out = [];
    const r = d.recovery;
    const z = zoneOf(d);
    const ringNode = recoveryRing(d, 220);
    ringNode.setAttribute('aria-label', `Hồi phục ${val(r, 'score') ?? 'chưa có'}%`);
    out.push(h('div', { class: 'hero' }, ringNode,
      z ? h('div', { class: 'zone-label' }, h('span', { class: 'dot', style: { background: z.color } }), z.label) : null,
      h('p', { class: 'msg', text: z ? z.msg : r && r.calibrating ? 'Đang hiệu chỉnh baseline (cần ≥4 đêm).' : 'Chưa có dữ liệu đêm qua.' })));
    out.push(explainCard(d, 'recovery'));
    out.push(contributorsCard(d));
    const days = lastN(30);
    out.push(h('div', { class: 'grid grid-2' },
      chartCard('Hồi phục 30 ngày', 'Màu theo vùng: xanh ≥67 · vàng 34–66 · đỏ ≤33', box => barChart(box, {
        data: days.map(x => ({ key: x.date, label: fmt.day(x.date), value: val(x, 'recovery', 'score'), color: (zoneOf(x) || {}).color || C.neutral,
          title: `${dateLabel(x.date)} · ${fmt.day(x.date)}`, rows: [{ color: (zoneOf(x) || {}).color, label: 'Hồi phục', value: isNum(val(x, 'recovery', 'score')) ? `${x.recovery.score}%` : '—' }], onClick: () => go({ date: x.date }) })),
        yMax: 100, ticks: [0, 33, 66, 100], highlight: d.date, valueLabel: v => `${v}%`,
      }), () => tableOf(['Ngày', 'Hồi phục', 'HRV', 'RHR'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.n(val(x, 'recovery', 'score')), fmt.n(val(x, 'vitals', 'hrv'), 1), fmt.n(val(x, 'vitals', 'rhr'))]))),
      vitalLine('HRV (ms)', 'Dải xanh = ngưỡng bình thường của bạn (baseline 30 ngày)', 'hrv', C.green, days, 0),
    ));
    out.push(h('div', { class: 'grid grid-2' },
      vitalLine('Nhịp tim nghỉ (bpm)', 'Thấp hơn baseline thường là dấu hiệu hồi phục tốt', 'rhr', C.neutral, days, 0),
      vitalLine('Nhịp thở khi ngủ (lần/phút)', 'Tăng bất thường có thể báo hiệu ốm', 'resp', C.sleep, days, 1)));
    return out;
  }

  function contributorsCard(d) {
    const r = d.recovery || {};
    const c = r.contributions || {};
    const i = S.idx[d.date];
    const items = [
      ['hrv', 'HRV', val(d, 'vitals', 'hrv'), 'ms', x => val(x, 'vitals', 'hrv'), 0],
      ['rhr', 'Nhịp tim nghỉ', val(d, 'vitals', 'rhr'), 'bpm', x => val(x, 'vitals', 'rhr'), 0],
      ['sleep', 'Hiệu suất ngủ', val(d, 'sleep', 'performance'), '%', x => val(x, 'sleep', 'performance'), 0],
      ['resp', 'Nhịp thở', val(d, 'vitals', 'resp'), '', x => val(x, 'vitals', 'resp'), 1],
      ['spo2', 'SpO2', val(d, 'vitals', 'spo2'), '%', x => val(x, 'vitals', 'spo2'), 1],
    ];
    const rows = items.map(([k, label, v, unit, get, dec]) => {
      const pts = c[k];
      const avg = prevAvg(i, get);
      const why = isNum(avg) ? `TB 30 ngày ${fmt.n(avg, dec)}${unit && unit !== '%' ? ' ' + unit : unit}` : 'chưa đủ baseline';
      const ptsText = isNum(pts) ? `${pts > 0 ? '+' : '−'}${fmt.n(Math.abs(pts), 0)}` : '·';
      return h('div', { class: 'contrib' },
        h('div', {}, h('div', { class: 'what', text: label }), h('div', { class: 'why', text: why })),
        h('div', { class: 'val' }, isNum(v) ? `${fmt.n(v, dec)} ${unit}` : '—'),
        h('div', { class: `pts ${isNum(pts) ? (pts >= 0 ? 'good' : 'bad') : 'muted'}`, title: 'Điểm hồi phục thay đổi so với khi chỉ số này ở đúng baseline', text: ptsText }));
    });
    const note = r.inputs && r.inputs.length && !r.inputs.includes('hrv') ? h('p', { class: 'note', text: 'Không có HRV đêm qua — điểm dựa trên nhịp tim nghỉ và giấc ngủ.' }) : null;
    return card('Vì sao hôm nay như vậy?', 'Cột phải: số điểm hồi phục mà chỉ số đó cộng/trừ so với baseline của bạn', h('div', {}, rows), note);
  }

  views.recovery = viewRecovery;
})();
