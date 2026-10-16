/* Strain: vòng strain, vùng tim, hoạt động, nhịp tim trong ngày, strain 30 ngày. */
(function () {
  'use strict';
  const { h, fmt, barChart } = window.GH;
  const { C, val, card, chartCard, tableOf, lastN, tile, go, strainRing, activityList, hrCard, views } = window.GHA;

  function viewStrain(d) {
    const out = [];
    const st = d.strain || {};
    const ringNode = strainRing(d, 220);
    ringNode.setAttribute('aria-label', `Strain ${st.score ?? 'chưa có'} trên 21`);
    out.push(h('div', { class: 'hero' }, ringNode,
      h('div', { class: 'zone-label' }, h('span', { class: 'dot', style: { background: C.strain } }), d.partial ? 'Strain đến hiện tại' : 'Strain trong ngày'),
      h('p', { class: 'msg', text: st.target ? `Vùng tối ưu theo hồi phục hôm nay: ${fmt.n(st.target[0], 1)}–${fmt.n(st.target[1], 1)} (cung trắng)` : 'Thang 0–21 (logarit): càng lên cao càng khó tăng.' })));
    out.push(h('div', { class: 'grid grid-2' }, zonesCard(st.zones_min, 'Thời gian trong vùng tim', 'Vùng theo % dự trữ nhịp tim (HRR)'), card('Hoạt động', null, activityList(d, false))));
    out.push(h('div', { class: 'tiles t4', style: { marginBottom: '12px' } },
      tile('Calories', fmt.n(st.calories), 'kcal'), tile('Calo vận động', fmt.n(st.active_calories), 'kcal'),
      tile('Số bước', fmt.n(st.steps), ''), tile('Phút cường độ', fmt.n(val(d, 'garmin', 'intensity_min')), 'phút')));
    out.push(hrCard(d));
    const days = lastN(30);
    out.push(chartCard('Strain 30 ngày', 'Dải xanh nhạt = vùng strain tối ưu theo hồi phục sáng hôm đó', box => barChart(box, {
      data: days.map(x => ({ key: x.date, label: fmt.day(x.date), value: val(x, 'strain', 'score'), color: C.strain, band: val(x, 'strain', 'target'),
        title: fmt.day(x.date), rows: [{ color: C.strain, label: 'Strain', value: fmt.n(val(x, 'strain', 'score'), 1) },
          ...(val(x, 'strain', 'target') ? [{ label: 'Mục tiêu', value: `${fmt.n(x.strain.target[0], 1)}–${fmt.n(x.strain.target[1], 1)}` }] : [])], onClick: () => go({ date: x.date }) })),
      yMax: 21, ticks: [0, 7, 14, 21], highlight: d.date, valueLabel: v => fmt.n(v, 1),
    }), () => tableOf(['Ngày', 'Strain', 'Mục tiêu', 'Calo'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.n(val(x, 'strain', 'score'), 1),
      val(x, 'strain', 'target') ? `${fmt.n(x.strain.target[0], 1)}–${fmt.n(x.strain.target[1], 1)}` : '—', fmt.n(val(x, 'strain', 'calories'))]))));
    return out;
  }
  function zonesCard(zones, title, sub) {
    if (!zones) return card(title, sub, h('p', { class: 'muted', text: 'Không có dữ liệu nhịp tim.' }));
    const max = Math.max(1, ...zones);
    const names = ['50–60%', '60–70%', '70–80%', '80–90%', '90–100%'];
    return card(title, sub, h('div', { class: 'zones' }, zones.map((m, i) => h('div', { class: 'zone' },
      h('span', { class: 'n', text: `Vùng ${i + 1}` }),
      h('div', { class: 'bar', title: names[i] }, h('span', { style: { width: `${(m / max) * 100}%`, background: C.zones[i] } })),
      h('span', { class: 't', text: fmt.durMin(m) })))),
      h('p', { class: 'note', text: names.map((n, i) => `V${i + 1} ${n}`).join(' · ') }));
  }

  views.strain = viewStrain;
})();
