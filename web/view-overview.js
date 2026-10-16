/* Tổng quan: 3 vòng Ngủ · Hồi phục · Strain, huấn luyện viên, hoạt động, chỉ số chính, nhịp tim trong ngày. */
(function () {
  'use strict';
  const { h, fmt } = window.GH;
  const { S, val, isNum, prevAvg, trendBadge, zoneOf, card, go, recoveryRing, strainRing, sleepRing, activityList, hrCard, views } = window.GHA;

  function dialButton(sub, name, svgNode, aria) {
    svgNode.setAttribute('aria-label', aria);
    return h('button', { class: 'dial', type: 'button', onclick: () => go({ sub }) }, svgNode, h('span', { class: 'name', text: name }));
  }

  function viewOverview(d) {
    const out = [];
    out.push(h('div', { class: 'dials' },
      dialButton('sleep', 'Ngủ', sleepRing(d, 132), `Hiệu suất ngủ ${val(d, 'sleep', 'performance') ?? 'chưa có'}%`),
      dialButton('recovery', 'Hồi phục', recoveryRing(d, 132), `Hồi phục ${val(d, 'recovery', 'score') ?? 'chưa có'}%`),
      dialButton('strain', 'Strain', strainRing(d, 132), `Strain ${val(d, 'strain', 'score') ?? 'chưa có'} trên 21`)));
    out.push(h('div', { class: 'grid grid-2' }, h('div', {}, coachCard(d), card('Hoạt động', null, activityList(d, true))), keyStats(d)));
    out.push(hrCard(d));
    return out;
  }

  function coachCard(d) {
    const z = zoneOf(d);
    const st = d.strain || {};
    const kids = [];
    if (z) kids.push(h('div', { class: 'line' }, h('span', { class: 'dot', style: { background: z.color } }), h('span', { class: 'big', text: `${z.label} · ${d.recovery.score}%` })), h('div', { class: 'sec', text: z.msg }));
    else if (val(d, 'recovery', 'calibrating')) kids.push(h('div', { class: 'sec', text: 'Đang hiệu chỉnh baseline cá nhân — cần ít nhất 4 đêm có HRV/nhịp tim nghỉ.' }));
    else kids.push(h('div', { class: 'sec', text: 'Chưa có dữ liệu giấc ngủ/HRV cho sáng ngày này — đeo đồng hồ khi ngủ.' }));
    if (st.target) {
      const [lo, hi] = st.target;
      const cur = st.score || 0;
      const status = cur < lo ? `Còn ${fmt.n(lo - cur, 1)} nữa để vào vùng tối ưu` : cur <= hi ? 'Đang trong vùng Strain tối ưu ✓' : `Vượt mục tiêu ${fmt.n(cur - hi, 1)} — cân nhắc nghỉ ngơi`;
      kids.push(h('div', { class: 'line' }, h('span', { class: 'sec', text: `Strain mục tiêu ${fmt.n(lo, 1)}–${fmt.n(hi, 1)}` })),
        h('div', { class: 'progress', role: 'img', 'aria-label': `Strain ${cur} trên mục tiêu ${lo} đến ${hi}` },
          h('div', { class: 'band', style: { left: `${(lo / 21) * 100}%`, width: `${((hi - lo) / 21) * 100}%` } }),
          h('div', { class: 'fill', style: { width: `${(Math.min(21, cur) / 21) * 100}%` } })),
        h('div', { class: 'progress-scale' }, h('span', { text: '0' }), h('span', { text: status }), h('span', { text: '21' })));
    }
    return card('Huấn luyện viên', null, h('div', { class: 'coach' }, kids));
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
      ['Body Battery cao nhất', val(d, 'garmin', 'bb_high'), '', x => val(x, 'garmin', 'bb_high'), true, 0],
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
