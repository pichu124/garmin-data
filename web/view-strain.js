/* Strain: vòng strain, vùng tim, hoạt động, nhịp tim trong ngày, strain 30 ngày. */
(function () {
  'use strict';
  const { h, fmt, barChart } = window.GH;
  const { C, val, isNum, card, chartCard, tableOf, lastN, tile, go, strainRing, activityList, hrCard, explainCard, views } = window.GHA;

  function viewStrain(d) {
    const out = [];
    const st = d.strain || {};
    const ringNode = strainRing(d, 220);
    ringNode.setAttribute('aria-label', `Strain ${st.score ?? 'chưa có'} trên 21`);
    out.push(h('div', { class: 'hero' }, ringNode,
      h('div', { class: 'zone-label' }, h('span', { class: 'dot', style: { background: C.strain } }), d.partial ? 'Strain đến hiện tại' : 'Strain trong ngày'),
      h('p', { class: 'msg', text: st.target ? `Vùng tối ưu theo hồi phục hôm nay: ${fmt.n(st.target[0], 1)}–${fmt.n(st.target[1], 1)} (cung trắng)` : 'Thang 0–21 (logarit): càng lên cao càng khó tăng.' })));
    out.push(explainCard(d, 'strain'));
    out.push(h('div', { class: 'grid grid-2' }, zonesCard(st, 'Thời gian trong vùng tim', 'Vùng theo % dự trữ nhịp tim (HRR)'), card('Hoạt động', null, activityList(d, false))));
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
  const LIGHT = 'var(--text-3)';   // xám trung tính sẵn có: "Nhẹ" chưa phải vùng tập
  const LEVELS = [['Nhẹ', LIGHT], ...C.zones.map((c, i) => [`Vùng ${i + 1}`, c])];
  // st: d.strain (hoặc hoạt động) — zones_min [Z1..Z5], light_min (20–50% HRR), load_pct [nhẹ, Z1..Z5]; thiếu khoá ⇒ ẩn phần đó
  function zonesCard(st, title, sub) {
    const zones = st.zones_min;
    if (!zones) return card(title, sub, h('p', { class: 'muted', text: 'Không có dữ liệu nhịp tim.' }));
    const light = isNum(st.light_min) ? st.light_min : null;
    const max = Math.max(1, light ?? 0, ...zones);
    const names = ['50–60%', '60–70%', '70–80%', '80–90%', '90–100%'];
    // chung một thang phút (so được Nhẹ với vùng); > 0 phút tối thiểu 2% để không biến mất cạnh hàng Nhẹ hàng trăm phút
    const row = (name, m, color, tip) => h('div', { class: 'zone' },
      h('span', { class: 'n', text: name }),
      h('div', { class: 'bar', title: tip }, h('span', { style: { width: `${m > 0 ? Math.max(2, (m / max) * 100) : 0}%`, background: color } })),
      h('span', { class: 't', text: fmt.durMin(m) }));
    const lp = st.load_pct;
    return card(title, sub,
      h('div', { class: 'zones' }, light === null ? null : row('Nhẹ', light, LIGHT, '20–50% · đi lại, việc nhà'), zones.map((m, i) => row(`Vùng ${i + 1}`, m, C.zones[i], names[i]))),
      h('p', { class: 'note', text: [...(light === null ? [] : ['Nhẹ 20–50% (đi lại, việc nhà)']), ...names.map((n, i) => `V${i + 1} ${n}`)].join(' · ') }),
      lp ? [
        h('h3', { class: 'section-title', text: 'Nguồn strain' }),
        h('div', { class: 'stack', role: 'img', 'aria-label': `Nguồn strain: ${LEVELS.map(([n], i) => `${n} ${lp[i]}%`).join(', ')}` },
          LEVELS.map(([n, c], i) => (lp[i] > 0 ? h('span', { style: { width: `${lp[i]}%`, background: c }, title: `${n}: ${lp[i]}%` }) : null))),
        h('div', { class: 'legend l3' }, LEVELS.map(([n, c], i) => h('div', { class: 'item' },
          h('span', { class: 'sw', style: { background: c } }), h('span', { class: 'k', text: n }), h('span', { class: 'v', text: `${lp[i]}%` })))),
        h('p', { class: 'note', text: '% tải tim mạch theo mức — mỗi phút ở vùng cao đóng góp nhiều hơn.' }),
      ] : null);
  }

  views.strain = viewStrain;
  window.GHA.zonesCard = zonesCard;   // trang hoạt động dùng lại
})();
