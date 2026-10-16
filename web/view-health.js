/* Sức khoẻ (Health Monitor): chỉ số so với ngưỡng cá nhân, chỉ số riêng của Garmin, Body Battery & stress. */
(function () {
  'use strict';
  const { h, svg, fmt, tip, sparkline } = window.GH;
  const { S, C, icon, getDetail, val, isNum, card, chartCard, lastN, tile, views } = window.GHA;

  function viewHealth(d) {
    const out = [];
    // hướng "tốt" khi lệch ngưỡng: HRV cao, RHR thấp, SpO2 cao; nhịp thở lệch hướng nào cũng đáng để ý
    const metrics = [
      ['hrv', 'HRV', 'ms', 0, C.green, 'high'], ['rhr', 'Nhịp tim nghỉ', 'bpm', 0, C.neutral, 'low'],
      ['resp', 'Nhịp thở', 'lần/phút', 1, C.sleep, null], ['spo2', 'SpO2 khi ngủ', '%', 1, C.strain, 'high'],
    ];
    const hm = d.health || {};
    const measured = metrics.filter(([k]) => hm[k] && hm[k].status);
    const inRange = measured.filter(([k]) => hm[k].status === 'in').length;
    out.push(card('Health Monitor', 'So với ngưỡng bình thường của chính bạn (baseline 30 ngày ± 1,5 độ lệch)',
      h('div', { class: 'hm-head' },
        h('span', { class: 'dot', style: { width: '14px', height: '14px', background: measured.length && inRange === measured.length ? C.green : C.yellow } }),
        h('span', { class: 'big', text: measured.length ? `${inRange}/${measured.length}` : '—' }),
        h('span', { class: 'sec', text: measured.length ? 'chỉ số trong ngưỡng' : 'chưa đủ dữ liệu để dựng ngưỡng' })),
      h('p', { class: 'note', text: 'Nhiệt độ da không có trong API Garmin nên không hiển thị.' })));
    const days = lastN(30);
    out.push(h('div', { class: 'hm grid grid-2' }, metrics.map(([k, label, unit, dec, color, fav]) => {
      const m = hm[k] || {};
      const status = m.status;
      const state = !status ? h('span', { class: 'state', text: 'chưa có ngưỡng' })
        : status === 'in' ? h('span', { class: 'state in' }, icon('check', { width: 14, height: 14, 'stroke-width': 3 }), 'Trong ngưỡng')
          : h('span', { class: `state ${status === fav ? 'fav' : 'out'}`, text: `${status === 'high' ? '▲ Cao hơn' : '▼ Thấp hơn'} ngưỡng${status === fav ? ' · tốt' : ''}` });
      return h('div', { class: 'hm-card' },
        h('div', { class: 'top' }, h('span', { class: 'name', text: label }), state),
        h('div', { class: 'val' }, fmt.n(m.value, dec), isNum(m.value) ? h('small', { text: unit }) : null),
        rangeBar(m, dec, color),
        sparkline({ values: days.map(x => val(x, 'vitals', k)), color, lo: m.lo, hi: m.hi }));
    })));
    const gm = d.garmin || {};
    out.push(h('h3', { class: 'section-title', text: 'Chỉ số riêng của Garmin' }));
    out.push(h('div', { class: 'tiles t4', style: { marginBottom: '12px' } },
      tile('Body Battery', isNum(gm.bb_high) ? `${gm.bb_low ?? '—'}–${gm.bb_high}` : '—', '', isNum(gm.bb_charged) ? `nạp +${gm.bb_charged} · xả −${gm.bb_drained ?? '—'}` : null),
      tile('Training Readiness', fmt.n(gm.readiness), '', gm.readiness_level ? readinessVi(gm.readiness_level) : null),
      tile('Garmin Sleep Score', fmt.n(gm.sleep_score), ''),
      tile('Stress TB', fmt.n(gm.stress_avg), '', 'thang 0–100 của Garmin'),
      tile('VO2 max', fmt.n(gm.vo2max, 1), ''),
      tile('HRV Status', gm.hrv_status ? hrvStatusVi(gm.hrv_status) : '—', '', isNum(gm.hrv_weekly) ? `TB 7 ngày ${gm.hrv_weekly} ms` : null),
      tile('Phút cường độ', fmt.n(gm.intensity_min), 'phút', 'vừa ×1 + mạnh ×2'),
      tile('HRmax đang dùng', fmt.n(S.summary.profile.hr_max), 'bpm', `nguồn: ${S.summary.profile.hr_max_source}`)));
    out.push(chartCard('Body Battery & Stress trong ngày', 'Xanh = Body Battery · tím = stress (Garmin, 0–100)', box => {
      getDetail(d.date).then(det => {
        if (!det || (!det.body_battery.length && !det.stress.length)) { box.replaceChildren(h('p', { class: 'muted', text: 'Không có dữ liệu.' })); return; }
        bbChart(box, det);
      });
    }, null));
    return out;
  }
  function rangeBar(m, dec, color) {
    if (!isNum(m.lo) || !isNum(m.value)) return h('div', { class: 'rangebar-scale' }, h('span', { text: 'Cần ≥4 ngày dữ liệu để dựng ngưỡng' }));
    const span = (m.hi - m.lo) || 1;
    const min = Math.min(m.lo - span * 0.6, m.value), max = Math.max(m.hi + span * 0.6, m.value);
    const pct = v => `${((v - min) / (max - min)) * 100}%`;
    return h('div', {},
      h('div', { class: 'rangebar', role: 'img', 'aria-label': `Giá trị ${fmt.n(m.value, dec)}, ngưỡng ${fmt.n(m.lo, dec)} đến ${fmt.n(m.hi, dec)}` },
        h('div', { class: 'track' }), h('div', { class: 'ok', style: { left: pct(m.lo), width: `calc(${pct(m.hi)} - ${pct(m.lo)})` } }),
        h('div', { class: 'pin', style: { left: pct(m.value), background: m.status === 'in' ? color : C.yellow } })),
      h('div', { class: 'rangebar-scale' }, h('span', { text: `ngưỡng ${fmt.n(m.lo, dec)}–${fmt.n(m.hi, dec)}` }), h('span', { text: `TB ${fmt.n(m.mean, dec)}` })));
  }
  const readinessVi = l => ({ PRIME: 'Rất sẵn sàng', HIGH: 'Cao', MODERATE: 'Vừa', LOW: 'Thấp', POOR: 'Kém' }[l] || l);
  const hrvStatusVi = s => ({ BALANCED: 'Cân bằng', UNBALANCED: 'Mất cân bằng', LOW: 'Thấp', POOR: 'Kém', NONE: '—' }[s] || s);
  function bbChart(box, det) {
    // hai chuỗi CÙNG thang 0–100 nên chung một trục (không phải dual-axis)
    const W = Math.max(260, box.clientWidth || 320), H = 170, pad = { l: 30, r: 8, t: 10, b: 22 };
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    const x = m => pad.l + (m / 1440) * pw, y = v => pad.t + ph - (v / 100) * ph;
    const g = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': 'Body Battery và stress trong ngày' });
    for (const t of [0, 25, 50, 75, 100]) { g.append(svg('line', { x1: pad.l, x2: W - pad.r, y1: y(t), y2: y(t), class: 'grid-line' }), svg('text', { x: pad.l - 6, y: y(t) + 4, 'text-anchor': 'end', class: 'axis-text' }, t)); }
    const bw = Math.max(1, pw / 480 - 0.5);
    for (const [m, v] of det.stress) g.append(svg('rect', { x: x(m), y: y(v), width: bw, height: y(0) - y(v), fill: C.sleep, 'fill-opacity': 0.55 }));
    let p = '', prev = null;
    for (const [m, v] of det.body_battery) { p += `${prev !== null && m - prev <= 15 ? 'L' : 'M'}${x(m)},${y(v)}`; prev = m; }
    g.append(svg('path', { d: p, fill: 'none', stroke: C.green, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    for (const hh of [0, 6, 12, 18, 24]) g.append(svg('text', { x: x(hh * 60), y: H - 6, 'text-anchor': hh === 0 ? 'start' : hh === 24 ? 'end' : 'middle', class: 'axis-text' }, `${String(hh).padStart(2, '0')}:00`));
    const hit = svg('rect', { x: pad.l, y: pad.t, width: pw, height: ph, class: 'hit' });
    const near = (arr, m) => arr.reduce((b, q) => (!b || Math.abs(q[0] - m) < Math.abs(b[0] - m) ? q : b), null);
    hit.addEventListener('pointermove', e => {
      const r = g.getBoundingClientRect();
      const m = (((e.clientX - r.left) * (W / r.width)) - pad.l) / pw * 1440;
      const bb = near(det.body_battery, m), st = near(det.stress, m);
      tip.show(e.clientX, e.clientY, fmt.clock(m), [{ color: C.green, label: 'Body Battery', value: bb ? String(bb[1]) : '—' }, { color: C.sleep, label: 'Stress', value: st ? String(st[1]) : '—' }]);
    });
    hit.addEventListener('pointerleave', () => tip.hide());
    g.append(hit);
    box.replaceChildren(g, h('div', { class: 'legend', style: { marginTop: '8px' } },
      h('div', { class: 'item' }, h('span', { class: 'sw', style: { background: C.green, height: '3px' } }), h('span', { class: 'k', text: 'Body Battery' })),
      h('div', { class: 'item' }, h('span', { class: 'sw', style: { background: C.sleep } }), h('span', { class: 'k', text: 'Stress' }))));
  }

  views.health = viewHealth;
})();
