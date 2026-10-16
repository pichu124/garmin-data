/* Xu hướng: trung bình theo khoảng, so với kỳ trước, biểu đồ dài hạn, tổng kết tuần. */
(function () {
  'use strict';
  const { h, fmt, barChart } = window.GH;
  const { S, C, val, isNum, zoneOf, card, chartCard, tableOf, lastN, tile, go, vitalLine, views } = window.GHA;

  function viewTrends() {
    const out = [];
    const ranges = [[7, '7 ngày'], [30, '30 ngày'], [90, '3 tháng'], [180, '6 tháng']];
    out.push(h('div', { class: 'range', role: 'group', 'aria-label': 'Khoảng thời gian' }, ranges.map(([n, label]) =>
      h('button', { type: 'button', 'aria-pressed': String(S.range === n), onclick: () => go({ range: n }) }, label))));
    const days = lastN(S.range, S.days[S.days.length - 1].date);
    const prev = S.days.slice(Math.max(0, S.days.length - 2 * S.range), Math.max(0, S.days.length - S.range));
    const avg = (arr, get) => { const v = arr.map(get).filter(isNum); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
    const g = {
      rec: x => val(x, 'recovery', 'score'), strain: x => (x.partial ? null : val(x, 'strain', 'score')), sleep: x => val(x, 'sleep', 'hours'),
      perf: x => val(x, 'sleep', 'performance'), hrv: x => val(x, 'vitals', 'hrv'), rhr: x => val(x, 'vitals', 'rhr'),
    };
    const deltaText = (key, dec, unit = '') => {
      const a = avg(days, g[key]), b = avg(prev, g[key]);
      if (!isNum(a) || !isNum(b) || prev.length < S.range / 2) return 'kỳ trước: —';
      const dlt = a - b;
      if (Math.abs(dlt) < 0.5 * 10 ** -dec) return '≈ kỳ trước';
      return `${dlt >= 0 ? '▲' : '▼'} ${fmt.n(Math.abs(dlt), dec)}${unit} so với kỳ trước`;
    };
    out.push(h('div', { class: 'tiles t4', style: { marginBottom: '12px' } },
      tile('Hồi phục TB', fmt.n(avg(days, g.rec)), '%', deltaText('rec', 0, '%')),
      tile('Strain TB', fmt.n(avg(days, g.strain), 1), '', deltaText('strain', 1)),
      tile('Giờ ngủ TB', fmt.dur(avg(days, g.sleep)), 'h', deltaText('sleep', 2, 'h')),
      tile('Hiệu suất ngủ TB', fmt.n(avg(days, g.perf)), '%', deltaText('perf', 0, '%')),
      tile('HRV TB', fmt.n(avg(days, g.hrv), 1), 'ms', deltaText('hrv', 1, ' ms')),
      tile('Nhịp tim nghỉ TB', fmt.n(avg(days, g.rhr), 1), 'bpm', deltaText('rhr', 1)),
      zoneTile(days)));
    const hl = null;
    out.push(h('div', { class: 'grid grid-2' },
      chartCard('Hồi phục', null, box => barChart(box, {
        data: days.map(x => ({ key: x.date, label: fmt.day(x.date), value: g.rec(x), color: (zoneOf(x) || {}).color || C.neutral, title: fmt.day(x.date),
          rows: [{ color: (zoneOf(x) || {}).color, label: 'Hồi phục', value: isNum(g.rec(x)) ? `${g.rec(x)}%` : '—' }], onClick: () => go({ tab: 'home', sub: 'recovery', date: x.date }) })),
        yMax: 100, ticks: [0, 33, 66, 100], highlight: hl,
      }), () => tableOf(['Ngày', 'Hồi phục'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.n(g.rec(x))]))),
      chartCard('Strain', 'Dải xanh nhạt = vùng tối ưu', box => barChart(box, {
        data: days.map(x => ({ key: x.date, label: fmt.day(x.date), value: val(x, 'strain', 'score'), color: C.strain, band: val(x, 'strain', 'target'), title: fmt.day(x.date),
          rows: [{ color: C.strain, label: 'Strain', value: fmt.n(val(x, 'strain', 'score'), 1) }], onClick: () => go({ tab: 'home', sub: 'strain', date: x.date }) })),
        yMax: 21, ticks: [0, 7, 14, 21], highlight: hl,
      }), () => tableOf(['Ngày', 'Strain'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.n(val(x, 'strain', 'score'), 1)])))));
    out.push(h('div', { class: 'grid grid-2' },
      chartCard('Giờ ngủ vs nhu cầu', 'Vạch trắng = nhu cầu', box => barChart(box, {
        data: days.map(x => ({ key: x.date, label: fmt.day(x.date), value: g.sleep(x), color: C.sleep, marker: val(x, 'need', 'total_h'), title: fmt.day(x.date),
          rows: [{ color: C.sleep, label: 'Đã ngủ', value: fmt.dur(g.sleep(x)) }, { color: '#e2e8f0', label: 'Cần', value: fmt.dur(val(x, 'need', 'total_h')) }],
          onClick: () => go({ tab: 'home', sub: 'sleep', date: x.date }) })),
        yMax: 11, ticks: [0, 4, 8], fmtY: v => `${v}h`, highlight: hl,
      }), () => tableOf(['Ngày', 'Ngủ', 'Cần'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.dur(g.sleep(x)), fmt.dur(val(x, 'need', 'total_h'))]))),
      vitalLine('HRV (ms)', 'Dải xanh = ngưỡng bình thường', 'hrv', C.green, days, 0)));
    out.push(h('div', { class: 'grid grid-2' },
      vitalLine('Nhịp tim nghỉ (bpm)', null, 'rhr', C.neutral, days, 0),
      strainRecoveryCard()));
    out.push(weeklyCard());
    return out;
  }
  function zoneTile(days) {
    const counts = { green: 0, yellow: 0, red: 0 };
    days.forEach(x => { const z = val(x, 'recovery', 'zone'); if (z) counts[z] += 1; });
    const total = counts.green + counts.yellow + counts.red || 1;
    return h('div', { class: 'tile' }, h('div', { class: 'k', text: 'Ngày xanh · vàng · đỏ' }),
      h('div', { class: 'v', text: `${counts.green} · ${counts.yellow} · ${counts.red}` }),
      h('div', { class: 'stack', role: 'img', 'aria-label': `${counts.green} ngày xanh, ${counts.yellow} vàng, ${counts.red} đỏ`, style: { margin: '6px 0 0', height: '8px' } },
        ['green', 'yellow', 'red'].map(z => h('span', { style: { width: `${(counts[z] / total) * 100}%`, background: C[z] } }))));
  }
  // Strain hôm trước ảnh hưởng hồi phục hôm sau thế nào (toàn bộ dữ liệu)
  function strainRecoveryCard() {
    const bins = [[0, 10, '< 10'], [10, 14, '10–14'], [14, 18, '14–18'], [18, 22, '≥ 18']];
    const rows = bins.map(([lo, hi, label]) => {
      const recs = [];
      for (let i = 1; i < S.days.length; i++) {
        const s = val(S.days[i - 1], 'strain', 'score'), r = val(S.days[i], 'recovery', 'score');
        if (isNum(s) && isNum(r) && s >= lo && s < hi && !S.days[i - 1].partial) recs.push(r);
      }
      return { label, n: recs.length, avg: recs.length ? recs.reduce((a, b) => a + b, 0) / recs.length : null };
    });
    return chartCard('Strain hôm trước → Hồi phục', 'Hồi phục trung bình sáng hôm sau, theo mức strain (toàn bộ dữ liệu)', box => barChart(box, {
      data: rows.map(r => ({ key: r.label, label: r.label, value: isNum(r.avg) ? Math.round(r.avg) : null, color: C.strain,
        title: `Strain ${r.label}`, rows: [{ color: C.strain, label: 'Hồi phục TB', value: isNum(r.avg) ? `${Math.round(r.avg)}%` : '—' }, { label: 'Số ngày', value: String(r.n) }] })),
      yMax: 100, ticks: [0, 33, 66, 100], labelAll: true, valueLabel: v => `${v}%`,
    }), () => tableOf(['Strain hôm trước', 'Hồi phục TB', 'Số ngày'], rows.map(r => [r.label, fmt.n(r.avg), String(r.n)])));
  }
  function weeklyCard() {
    const weeks = (S.summary.insights.weekly || []).slice(-Math.ceil(S.range / 7) - 1).reverse();
    return card('Tổng kết theo tuần', 'Trung bình thứ Hai → Chủ nhật', h('div', { class: 'table-scroll' },
      tableOf(['Tuần', 'Hồi phục', 'Strain', 'Ngủ', 'HS ngủ', 'HRV', 'RHR', 'X·V·Đ'], weeks.map(w => [fmt.day(w.week), fmt.n(w.recovery), fmt.n(w.strain, 1),
        fmt.dur(w.sleep_h), fmt.n(w.sleep_perf), fmt.n(w.hrv, 1), fmt.n(w.rhr, 1), `${w.green}·${w.yellow}·${w.red}`]))));
  }

  views.trends = viewTrends;
})();
