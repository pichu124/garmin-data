/* Biểu đồ SVG tự vẽ (không thư viện ngoài ⇒ chạy offline) cho Garmin Health.
 * Quy ước mark (dataviz): cột ≤24px bo 4px đầu dữ liệu, line 2px, lưới hairline,
 * tooltip dùng textContent (nhãn là dữ liệu ngoài), mỗi biểu đồ có bảng thay thế ở app.js. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';

  function svg(tag, attrs, ...kids) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v);
    for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return n;
  }
  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(n.style, v);
      else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
      else if (k === 'text') n.textContent = v;
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return n;
  }

  // ---------- định dạng ----------
  const fmt = {
    n(v, d = 0) { return v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }); },
    dur(hours) { // 7.8 → "7:48"
      if (hours === null || hours === undefined) return '—';
      const m = Math.round(hours * 60);
      return `${Math.floor(m / 60)}:${String(Math.abs(m % 60)).padStart(2, '0')}`;
    },
    durMin(min) { return min === null || min === undefined ? '—' : fmt.dur(min / 60); },
    clock(min) { // phút trong ngày (có thể âm) → "23:10"
      if (min === null || min === undefined) return '—';
      const m = ((Math.round(min) % 1440) + 1440) % 1440;
      return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
    },
    day(iso) { const [y, m, d] = iso.split('-'); return `${d}/${m}`; },
    weekday(iso) { return ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'][new Date(iso + 'T00:00:00').getDay()]; },
  };

  // ---------- tooltip (một node dùng chung) ----------
  const tip = {
    node: null,
    ensure() {
      if (!this.node) { this.node = h('div', { class: 'tooltip', role: 'status', 'aria-live': 'polite' }); document.body.append(this.node); }
      return this.node;
    },
    show(x, y, title, rows) {
      const n = this.ensure();
      n.replaceChildren(h('div', { class: 'tt-title', text: title }),
        ...rows.map(r => h('div', { class: 'tt-row' },
          h('span', { class: 'key', style: { background: r.color || 'transparent' } }),
          h('span', { class: 'lbl', text: r.label }),
          h('b', { text: r.value }))));
      n.classList.add('show');
      const w = n.offsetWidth, hh = n.offsetHeight;
      let left = x + 14, top = y - hh - 10;
      if (left + w > window.innerWidth - 8) left = x - w - 14;
      if (top < 8) top = y + 16;
      n.style.left = `${Math.max(8, left)}px`;
      n.style.top = `${top}px`;
    },
    hide() { if (this.node) this.node.classList.remove('show'); },
  };
  window.addEventListener('scroll', () => tip.hide(), { passive: true });

  function niceTicks(lo, hi, count = 4) {
    const span = hi - lo || 1;
    const raw = span / count;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(s => s * mag).find(s => span / s <= count) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }

  // cột: bo 4px phía đầu dữ liệu, vuông ở đường gốc
  function barPath(x, y0, w, y1) {
    const hgt = y0 - y1;
    if (hgt <= 0) return '';
    const r = Math.min(4, w / 2, hgt);
    return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
  }

  // ---------- vòng (dial) kiểu WHOOP ----------
  function ring({ frac, color, text, unit, sub, size = 132, stroke = 11, band }) {
    const c = size / 2, r = c - stroke / 2 - 4;
    const C = 2 * Math.PI * r;
    const f = Math.max(0, Math.min(1, frac || 0));
    const g = svg('svg', { viewBox: `0 0 ${size} ${size}`, role: 'img' });
    g.append(svg('circle', { cx: c, cy: c, r, fill: 'none', stroke: color, 'stroke-opacity': 0.16, 'stroke-width': stroke }));
    if (band) { // khoảng mục tiêu (strain coach) — cung mảnh phía ngoài
      const rb = r + stroke / 2 + 3, Cb = 2 * Math.PI * rb;
      g.append(svg('circle', { cx: c, cy: c, r: rb, fill: 'none', stroke: '#e2e8f0', 'stroke-opacity': 0.75, 'stroke-width': 3,
        'stroke-dasharray': `${(band[1] - band[0]) * Cb} ${Cb}`, 'stroke-dashoffset': -band[0] * Cb, transform: `rotate(-90 ${c} ${c})`, 'stroke-linecap': 'round' }));
    }
    if (f > 0) g.append(svg('circle', { cx: c, cy: c, r, fill: 'none', stroke: color, 'stroke-width': stroke, 'stroke-linecap': 'round',
      'stroke-dasharray': `${f * C} ${C}`, transform: `rotate(-90 ${c} ${c})` }));
    const big = size * 0.27;
    const t = svg('text', { x: c, y: c + big * 0.35 - (sub ? size * 0.05 : 0), 'text-anchor': 'middle', class: 'ring-value', 'font-size': big },
      text, unit ? svg('tspan', { class: 'ring-unit', 'font-size': big * 0.45, dx: 1 }, unit) : null);
    g.append(t);
    if (sub) g.append(svg('text', { x: c, y: c + big * 0.35 + size * 0.12, 'text-anchor': 'middle', class: 'ring-sub', 'font-size': size * 0.075 }, sub));
    return g;
  }

  function width(container) { return Math.max(260, Math.floor(container.clientWidth || container.getBoundingClientRect().width || 320)); }

  // ---------- cột theo ngày ----------
  // data: [{key,label,value,color,band:[lo,hi],marker,title,rows}]
  function barChart(container, { data, height = 170, yMax, yMin = 0, ticks, fmtY = v => fmt.n(v), highlight, valueLabel, labelAll }) {
    const W = width(container), H = height;
    const pad = { l: 30, r: 6, t: 16, b: 22 };
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    const vals = data.flatMap(d => [d.value, d.band && d.band[1], d.marker]).filter(v => v !== null && v !== undefined);
    const hi = yMax ?? Math.max(1, ...vals) * 1.1;
    const y = v => pad.t + ph - ((v - yMin) / (hi - yMin)) * ph;
    const slot = pw / Math.max(1, data.length);
    const bw = Math.max(2, Math.min(24, slot - 2));
    const g = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img' });
    for (const t of ticks || niceTicks(yMin, hi, 4)) {
      g.append(svg('line', { x1: pad.l, x2: W - pad.r, y1: y(t), y2: y(t), class: 'grid-line' }));
      g.append(svg('text', { x: pad.l - 6, y: y(t) + 4, 'text-anchor': 'end', class: 'axis-text' }, fmtY(t)));
    }
    const every = Math.max(1, Math.ceil(data.length / Math.floor(pw / 34)));
    data.forEach((d, i) => {
      const cx = pad.l + slot * i + slot / 2;
      if (d.band) g.append(svg('rect', { x: cx - bw / 2 - 2, width: bw + 4, y: y(d.band[1]), height: Math.max(1, y(d.band[0]) - y(d.band[1])), rx: 3, fill: '#3aa7f0', 'fill-opacity': 0.18 }));
      if (d.value !== null && d.value !== undefined) {
        const p = barPath(cx - bw / 2, y(yMin), bw, y(Math.max(yMin, d.value)));
        if (p) g.append(svg('path', { d: p, fill: d.color, class: `bar-mark${d.key === highlight ? ' active' : ''}`, 'fill-opacity': highlight && d.key !== highlight ? 0.55 : 1 }));
      }
      if (d.marker !== null && d.marker !== undefined) g.append(svg('line', { x1: cx - bw / 2 - 3, x2: cx + bw / 2 + 3, y1: y(d.marker), y2: y(d.marker), stroke: '#e2e8f0', 'stroke-width': 2, 'stroke-linecap': 'round' }));
      if ((data.length - 1 - i) % every === 0) g.append(svg('text', { x: cx, y: H - 6, 'text-anchor': 'middle', class: 'axis-text' }, d.label));
      if ((labelAll || d.key === highlight) && d.value !== null && d.value !== undefined && valueLabel) {
        g.append(svg('text', { x: cx, y: y(d.value) - 6, 'text-anchor': 'middle', class: 'axis-text', fill: '#fff', style: 'fill:#fff;font-weight:700' }, valueLabel(d.value)));
      }
      const hit = svg('rect', { x: pad.l + slot * i, y: pad.t, width: slot, height: ph, class: 'hit' });
      hit.addEventListener('pointermove', e => tip.show(e.clientX, e.clientY, d.title || d.label, d.rows || [{ color: d.color, label: '', value: fmtY(d.value) }]));
      hit.addEventListener('pointerleave', () => tip.hide());
      if (d.onClick) { hit.style.cursor = 'pointer'; hit.addEventListener('click', d.onClick); }
      g.append(hit);
    });
    container.replaceChildren(g);
  }

  // ---------- đường theo ngày (có dải baseline) ----------
  // data: [{key,label,title,value,lo,hi}]
  function lineChart(container, { data, color, height = 170, fmtY = v => fmt.n(v), unit = '', name = '', bandLabel = 'Ngưỡng' }) {
    const W = width(container), H = height;
    const pad = { l: 34, r: 34, t: 14, b: 22 };
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    const vals = data.flatMap(d => [d.value, d.lo, d.hi]).filter(v => v !== null && v !== undefined);
    const g = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img' });
    if (!vals.length) { container.replaceChildren(h('p', { class: 'muted', text: 'Chưa có dữ liệu.' })); return; }
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const padV = (hi - lo) * 0.15 || 1; lo -= padV; hi += padV;
    const x = i => pad.l + (data.length === 1 ? pw / 2 : (pw * i) / (data.length - 1));
    const y = v => pad.t + ph - ((v - lo) / (hi - lo)) * ph;
    for (const t of niceTicks(lo, hi, 4)) {
      g.append(svg('line', { x1: pad.l, x2: W - pad.r, y1: y(t), y2: y(t), class: 'grid-line' }));
      g.append(svg('text', { x: pad.l - 6, y: y(t) + 4, 'text-anchor': 'end', class: 'axis-text' }, fmtY(t)));
    }
    // dải baseline: các đoạn liên tục có lo/hi
    let seg = [];
    const flushBand = () => {
      if (seg.length > 1) {
        const top = seg.map(i => `${x(i)},${y(data[i].hi)}`).join(' L');
        const bot = seg.slice().reverse().map(i => `${x(i)},${y(data[i].lo)}`).join(' L');
        g.append(svg('path', { d: `M${top} L${bot} Z`, fill: color, 'fill-opacity': 0.1 }));
      }
      seg = [];
    };
    data.forEach((d, i) => { if (d.lo !== null && d.lo !== undefined && d.hi !== null && d.hi !== undefined) seg.push(i); else flushBand(); });
    flushBand();
    // đường (đứt ở chỗ thiếu dữ liệu)
    let path = '', pen = false;
    data.forEach((d, i) => {
      if (d.value === null || d.value === undefined) { pen = false; return; }
      path += `${pen ? 'L' : 'M'}${x(i)},${y(d.value)}`; pen = true;
    });
    g.append(svg('path', { d: path, fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    let lastI = -1;   // findLastIndex thiếu trên Safari < 15.4
    for (let i = data.length - 1; i >= 0; i--) if (data[i].value !== null && data[i].value !== undefined) { lastI = i; break; }
    if (lastI >= 0) {
      g.append(svg('circle', { cx: x(lastI), cy: y(data[lastI].value), r: 4.5, fill: color, stroke: '#161f24', 'stroke-width': 2 }));
      g.append(svg('text', { x: x(lastI) + 8, y: y(data[lastI].value) + 4, class: 'axis-text', style: 'fill:#fff;font-weight:700' }, fmtY(data[lastI].value)));
    }
    const every = Math.max(1, Math.ceil(data.length / Math.floor(pw / 40)));
    data.forEach((d, i) => { if ((data.length - 1 - i) % every === 0) g.append(svg('text', { x: x(i), y: H - 6, 'text-anchor': 'middle', class: 'axis-text' }, d.label)); });
    // crosshair
    const cross = svg('line', { y1: pad.t, y2: pad.t + ph, stroke: '#7d8a93', 'stroke-width': 1, visibility: 'hidden' });
    const dot = svg('circle', { r: 4.5, fill: color, stroke: '#161f24', 'stroke-width': 2, visibility: 'hidden' });
    g.append(cross, dot);
    const hit = svg('rect', { x: pad.l, y: pad.t, width: pw, height: ph, class: 'hit' });
    hit.addEventListener('pointermove', e => {
      const r = g.getBoundingClientRect();
      const px = (e.clientX - r.left) * (W / r.width);
      const i = Math.max(0, Math.min(data.length - 1, Math.round(((px - pad.l) / pw) * (data.length - 1))));
      const d = data[i];
      cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
      if (d.value !== null && d.value !== undefined) { dot.setAttribute('cx', x(i)); dot.setAttribute('cy', y(d.value)); dot.setAttribute('visibility', 'visible'); } else dot.setAttribute('visibility', 'hidden');
      const rows = [{ color, label: name, value: d.value === null || d.value === undefined ? '—' : `${fmtY(d.value)}${unit}` }];
      if (d.lo !== null && d.lo !== undefined) rows.push({ label: bandLabel, value: `${fmtY(d.lo)}–${fmtY(d.hi)}` });
      tip.show(e.clientX, e.clientY, d.title || d.label, rows);
    });
    hit.addEventListener('pointerleave', () => { tip.hide(); cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); });
    g.append(hit);
    container.replaceChildren(g);
  }

  // ---------- nhịp tim trong ngày ----------
  function hrChart(container, { detail, height = 190, colorLine = '#e6ebef' }) {
    const W = width(container), H = height;
    const pad = { l: 30, r: 8, t: 22, b: 22 };
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    const pts = detail.hr || [];
    if (!pts.length) { container.replaceChildren(h('p', { class: 'muted', text: 'Không có dữ liệu nhịp tim ngày này.' })); return; }
    const vals = pts.map(p => p[1]);
    const lo = Math.max(30, Math.floor((Math.min(...vals) - 5) / 10) * 10), hi = Math.ceil((Math.max(...vals) + 5) / 10) * 10;
    const x = m => pad.l + (m / 1440) * pw;
    const y = v => pad.t + ph - ((v - lo) / (hi - lo)) * ph;
    const g = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img' });
    for (const t of niceTicks(lo, hi, 3)) {
      g.append(svg('line', { x1: pad.l, x2: W - pad.r, y1: y(t), y2: y(t), class: 'grid-line' }));
      g.append(svg('text', { x: pad.l - 6, y: y(t) + 4, 'text-anchor': 'end', class: 'axis-text' }, t));
    }
    // giấc ngủ: sáng sớm (đêm kết thúc hôm nay) + tối (đêm bắt đầu hôm nay)
    const nights = [];
    if (detail.sleep) nights.push([detail.sleep.start_min, detail.sleep.end_min]);
    if (detail.next_sleep_start_min !== null && detail.next_sleep_start_min !== undefined) nights.push([detail.next_sleep_start_min, 1440]);
    for (const [s, e] of nights) {
      const a = Math.max(0, s), b = Math.min(1440, e);
      if (b <= a) continue;
      g.append(svg('rect', { x: x(a), y: pad.t, width: x(b) - x(a), height: ph, fill: '#a5b4fc', 'fill-opacity': 0.1 }));
      if (x(b) - x(a) > 30) g.append(svg('text', { x: x(a) + 4, y: pad.t - 6, class: 'axis-text' }, 'Ngủ'));
    }
    for (const a of detail.activities || []) {
      const s = Math.max(0, a.start_min), e = Math.min(1440, a.end_min);
      if (e <= s) continue;
      g.append(svg('rect', { x: x(s), y: pad.t, width: Math.max(2, x(e) - x(s)), height: ph, fill: '#0a84d6', 'fill-opacity': 0.22 }));
      if (a.strain !== null && a.strain !== undefined) g.append(svg('text', { x: x(s), y: pad.t - 6, class: 'axis-text', style: 'fill:#3aa7f0;font-weight:700' }, fmt.n(a.strain, 1)));
    }
    let path = '', prev = null;
    for (const [m, v] of pts) { path += `${prev !== null && m - prev <= 10 ? 'L' : 'M'}${x(m).toFixed(1)},${y(v).toFixed(1)}`; prev = m; }
    g.append(svg('path', { d: path, fill: 'none', stroke: colorLine, 'stroke-width': 1.5, 'stroke-linejoin': 'round', 'stroke-opacity': 0.9 }));
    for (const hh of [0, 6, 12, 18, 24]) g.append(svg('text', { x: x(hh * 60), y: H - 6, 'text-anchor': hh === 0 ? 'start' : hh === 24 ? 'end' : 'middle', class: 'axis-text' }, `${String(hh).padStart(2, '0')}:00`));
    const cross = svg('line', { y1: pad.t, y2: pad.t + ph, stroke: '#7d8a93', 'stroke-width': 1, visibility: 'hidden' });
    const dot = svg('circle', { r: 4, fill: colorLine, stroke: '#161f24', 'stroke-width': 2, visibility: 'hidden' });
    g.append(cross, dot);
    const hit = svg('rect', { x: pad.l, y: pad.t, width: pw, height: ph, class: 'hit' });
    hit.addEventListener('pointermove', e => {
      const r = g.getBoundingClientRect();
      const m = (((e.clientX - r.left) * (W / r.width)) - pad.l) / pw * 1440;
      let best = pts[0];
      for (const p of pts) if (Math.abs(p[0] - m) < Math.abs(best[0] - m)) best = p;
      cross.setAttribute('x1', x(best[0])); cross.setAttribute('x2', x(best[0])); cross.setAttribute('visibility', 'visible');
      dot.setAttribute('cx', x(best[0])); dot.setAttribute('cy', y(best[1])); dot.setAttribute('visibility', 'visible');
      const act = (detail.activities || []).find(a => best[0] >= a.start_min && best[0] <= a.end_min);
      const rows = [{ color: colorLine, label: 'Nhịp tim', value: `${Math.round(best[1])} bpm` }];
      if (act) rows.push({ color: '#0a84d6', label: act.name || act.type, value: act.strain !== null && act.strain !== undefined ? fmt.n(act.strain, 1) : '' });
      tip.show(e.clientX, e.clientY, fmt.clock(best[0]), rows);
    });
    hit.addEventListener('pointerleave', () => { tip.hide(); cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); });
    g.append(hit);
    container.replaceChildren(g);
  }

  // ---------- hypnogram ----------
  const STAGES = [
    { key: 'awake', label: 'Thức', color: '#e2e8f0' },
    { key: 'rem', label: 'REM', color: '#a5b4fc' },
    { key: 'light', label: 'Ngủ nông', color: '#7b84f4' },
    { key: 'deep', label: 'Ngủ sâu', color: '#4f46e5' },
  ];
  function hypnogram(container, { sleep, height = 170 }) {
    const W = width(container), H = height;
    const pad = { l: 64, r: 8, t: 6, b: 22 };
    const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
    const s0 = sleep.start_min, s1 = sleep.end_min;
    const x = m => pad.l + ((m - s0) / (s1 - s0)) * pw;
    const rowH = ph / STAGES.length;
    const row = k => STAGES.findIndex(s => s.key === k);
    const g = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img' });
    STAGES.forEach((s, i) => {
      g.append(svg('line', { x1: pad.l, x2: W - pad.r, y1: pad.t + rowH * (i + 0.5), y2: pad.t + rowH * (i + 0.5), class: 'grid-line' }));
      g.append(svg('text', { x: pad.l - 8, y: pad.t + rowH * (i + 0.5) + 4, 'text-anchor': 'end', class: 'axis-text' }, s.label));
    });
    const levels = sleep.levels || [];
    levels.forEach((lv, i) => { // nối các bậc
      const nxt = levels[i + 1];
      if (nxt && Math.abs(nxt[0] - lv[1]) < 2) {
        const y1 = pad.t + rowH * (row(lv[2]) + 0.5), y2 = pad.t + rowH * (row(nxt[2]) + 0.5);
        g.append(svg('line', { x1: x(lv[1]), x2: x(lv[1]), y1, y2, stroke: '#3a4750', 'stroke-width': 1 }));
      }
    });
    for (const [a, b, k] of levels) {
      const st = STAGES[row(k)];
      if (!st) continue;
      const r = svg('rect', { x: x(a), y: pad.t + rowH * row(k) + 3, width: Math.max(1.5, x(b) - x(a) - 1), height: rowH - 6, rx: 2, fill: st.color });
      r.addEventListener('pointermove', e => tip.show(e.clientX, e.clientY, `${fmt.clock(a)}–${fmt.clock(b)}`, [{ color: st.color, label: st.label, value: `${Math.round(b - a)} phút` }]));
      r.addEventListener('pointerleave', () => tip.hide());
      g.append(r);
    }
    const first = Math.ceil(s0 / 60) * 60;
    const stepH = pw / ((s1 - s0) / 60) < 52 ? 2 : 1;   // nhãn giờ cách nhau ≥ ~50px
    for (let m = first; m <= s1; m += 60 * stepH) g.append(svg('text', { x: x(m), y: H - 6, 'text-anchor': 'middle', class: 'axis-text' }, fmt.clock(m)));
    container.replaceChildren(g);
  }

  // ---------- sparkline ----------
  function sparkline({ values, color, lo, hi, w = 240, hgt = 44 }) {
    const vs = values.filter(v => v !== null && v !== undefined);
    const g = svg('svg', { viewBox: `0 0 ${w} ${hgt}`, width: '100%', height: hgt, preserveAspectRatio: 'none', 'aria-hidden': 'true' });
    if (vs.length < 2) return g;
    let a = Math.min(...vs, lo ?? Infinity), b = Math.max(...vs, hi ?? -Infinity);
    const p = (b - a) * 0.12 || 1; a -= p; b += p;
    const x = i => (w * i) / (values.length - 1);
    const y = v => hgt - ((v - a) / (b - a)) * hgt;
    if (lo !== null && lo !== undefined && hi !== null && hi !== undefined) g.append(svg('rect', { x: 0, width: w, y: y(hi), height: y(lo) - y(hi), fill: '#16ec06', 'fill-opacity': 0.1 }));
    let d = '', pen = false;
    values.forEach((v, i) => { if (v === null || v === undefined) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i)},${y(v)}`; pen = true; });
    g.append(svg('path', { d, fill: 'none', stroke: color, 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke', 'stroke-linejoin': 'round' }));
    return g;
  }

  window.GH = { svg, h, fmt, tip, ring, barChart, lineChart, hrChart, hypnogram, sparkline, STAGES };
})();
