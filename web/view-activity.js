/* Chi tiết hoạt động kiểu WHOOP (#home/activity/<ngày>/<id>): vòng strain, chỉ số, nhịp tim trong khung giờ hoạt động, vùng tim + nguồn strain. */
(function () {
  'use strict';
  const { h, fmt, ring, hrChart } = window.GH;
  const GHA = window.GHA;
  const { S, C, icon, isNum, actName, chartCard, tile, go, getDetail, views } = GHA;

  function viewActivity(d) {
    const a = d.activities.find(x => x.id === S.param);   // render (app.js) đã về Strain nếu không có
    const [hh, mm] = a.start.split(':').map(Number);
    const end = hh * 60 + mm + a.duration_min;   // phút kể từ nửa đêm; > 1440 = kéo qua nửa đêm
    const name = actName(a), type = actName({ type: a.type });
    const ringNode = ring({ frac: (a.strain || 0) / 21, color: C.strain, text: isNum(a.strain) ? fmt.n(a.strain, 1) : '—', size: 220 });
    ringNode.setAttribute('aria-label', `Strain hoạt động ${a.strain ?? 'chưa có'} trên 21`);
    // [nhãn, giá trị để lọc thiếu, đơn vị, số lẻ, chữ hiển thị nếu khác fmt.n]
    const tiles = [
      ['Thời lượng', a.duration_min, 'phút'],
      ['Calories', a.calories, 'kcal'],
      ['Quãng đường', a.distance_km, 'km', 2],
      ['Nhịp tim TB / tối đa', a.avg_hr ?? a.max_hr, 'bpm', 0, `${fmt.n(a.avg_hr)} / ${fmt.n(a.max_hr)}`],
      ['Hiệu quả aerobic (TE)', a.aerobic_te, '/ 5', 1],
      ['Tải tập luyện', a.training_load, ''],
    ].filter(([, v]) => isNum(v)).map(([k, v, unit, dec, text]) => tile(k, text ?? fmt.n(v, dec), unit));
    const hr = chartCard('Nhịp tim trong hoạt động', end > 1440 ? 'Hoạt động kéo qua nửa đêm — biểu đồ dừng ở 24:00.' : null, box => {
      box.classList.add('loading');
      getDetail(d.date).then(det => {
        box.classList.remove('loading');
        const t = det && (det.activities || []).find(x => x.id === a.id);   // start_min/end_min chỉ có ở file chi tiết
        if (!t) { box.replaceChildren(h('p', { class: 'muted', text: 'Không có chi tiết nhịp tim.' })); return; }
        // bỏ activities: cả khung là hoạt động này, tô nền xanh + nhãn strain chỉ lặp lại vòng phía trên
        hrChart(box, { detail: { ...det, activities: [] }, from: t.start_min, to: Math.min(1440, t.end_min) });
      });
    }, null);
    return [
      h('button', { class: 'back-btn', type: 'button', onclick: () => go({ sub: S.backSub }) }, icon('left'), 'Quay lại'),
      h('div', { class: 'hero' },
        h('h1', { class: 'act-name', text: name }),
        h('p', { class: 'act-meta', text: [type !== name ? type : null, `${a.start}–${fmt.clock(end)}${end > 1440 ? ' (hôm sau)' : ''}`].filter(Boolean).join(' · ') }),
        ringNode,
        h('div', { class: 'zone-label' }, h('span', { class: 'dot', style: { background: C.strain } }), 'Strain hoạt động')),
      tiles.length ? h('div', { class: 'tiles t3', style: { marginBottom: '12px' } }, tiles) : null,
      h('div', { class: 'grid grid-2' }, hr, a.zones_min ? GHA.zonesCard(a, 'Thời gian trong vùng tim', 'Vùng theo % dự trữ nhịp tim (HRR)') : null),
    ];
  }

  views.activity = viewActivity;
})();
