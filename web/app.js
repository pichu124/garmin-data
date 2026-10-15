/* Garmin Health — SPA kiểu WHOOP: Tổng quan (Ngủ · Hồi phục · Strain), Xu hướng, Sức khoẻ, Nhật ký.
 * Dữ liệu: /data/summary.json + /data/days/<ngày>.json (server.py), hoặc window.GH_DATA (bản xem thử tĩnh). */
(function () {
  'use strict';
  const { h, svg, fmt, tip, ring, barChart, lineChart, hrChart, hypnogram, sparkline, STAGES } = window.GH;

  const C = {
    green: '#16ec06', yellow: '#ffde00', red: '#ff0026',
    strain: '#0a84d6', sleep: '#a5b4fc', neutral: '#e6ebef', hrv: '#16ec06',
    zones: ['#9fd3f7', '#5fb4ef', '#2a95e3', '#0a74c4', '#0a4f8a'],
  };
  const ZONE = {
    green: { color: C.green, label: 'Hồi phục tốt', msg: 'Cơ thể đã sẵn sàng — hôm nay có thể đẩy cường độ cao.' },
    yellow: { color: C.yellow, label: 'Hồi phục vừa', msg: 'Hồi phục ở mức vừa — giữ cường độ vừa phải, ưu tiên kỹ thuật.' },
    red: { color: C.red, label: 'Cần nghỉ ngơi', msg: 'Cơ thể đang chịu tải — ưu tiên phục hồi: tập nhẹ, ngủ sớm, uống đủ nước.' },
  };
  const ACT_TYPES = {
    running: 'Chạy bộ', treadmill_running: 'Chạy máy', trail_running: 'Chạy địa hình', cycling: 'Đạp xe', indoor_cycling: 'Đạp xe trong nhà',
    road_biking: 'Đạp xe đường', strength_training: 'Tập tạ', yoga: 'Yoga', walking: 'Đi bộ', hiking: 'Leo núi',
    lap_swimming: 'Bơi', open_water_swimming: 'Bơi ngoài trời', swimming: 'Bơi', cardio: 'Cardio', hiit: 'HIIT',
    tennis: 'Tennis', badminton: 'Cầu lông', soccer: 'Bóng đá', pilates: 'Pilates', other: 'Khác',
  };
  const ICONS = {
    home: 'M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
    trends: 'M4 19h16M6 16V10m4 6V6m4 10v-4m4 4V8',
    health: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z',
    journal: 'M6 3h11a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm3 5h6m-6 4h6',
    sync: 'M20 11a8 8 0 0 0-14.6-4.5M4 4v3h3M4 13a8 8 0 0 0 14.6 4.5M20 20v-3h-3',
    gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.6 7.6 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.6 7.6 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z',
    left: 'M15 5l-7 7 7 7', right: 'M9 5l7 7-7 7', check: 'M5 12.5l4.5 4.5L19 7.5', up: 'M12 19V5m-6 6 6-6 6 6', down: 'M12 5v14m-6-6 6 6 6-6',
  };
  const icon = (name, extra = {}) => svg('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', ...extra }, svg('path', { d: ICONS[name] }));

  const S = {
    summary: null, days: [], idx: {}, details: new Map(),
    date: null, tab: 'home', sub: 'overview', range: 30,
    staticMode: !!window.GH_DATA, sync: null,
  };
  const app = document.getElementById('app');
  let mounts = [];
  const mount = fn => mounts.push(fn);

  // ---------- dữ liệu ----------
  async function loadSummary() {
    if (window.GH_DATA) { setSummary(window.GH_DATA.summary); return true; }
    const r = await fetch('data/summary.json', { cache: 'no-store' });
    if (!r.ok) { setSummary(null); return false; }
    setSummary(await r.json());
    return true;
  }
  function setSummary(s) {
    S.summary = s;
    S.days = s ? s.days : [];
    S.idx = Object.fromEntries(S.days.map((d, i) => [d.date, i]));
    S.details.clear();
    if (!S.date || !(S.date in S.idx)) S.date = S.days.length ? S.days[S.days.length - 1].date : null;
  }
  async function getDetail(date) {
    if (S.details.has(date)) return S.details.get(date);
    let d = null;
    if (window.GH_DATA) d = (window.GH_DATA.days || {})[date] || null;
    else { try { const r = await fetch(`data/days/${date}.json`, { cache: 'no-store' }); d = r.ok ? await r.json() : null; } catch (e) { d = null; } }
    S.details.set(date, d);
    return d;
  }
  async function post(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  // ---------- tiện ích ----------
  const day = () => S.days[S.idx[S.date]];
  const val = (o, ...k) => k.reduce((a, x) => (a === null || a === undefined ? a : a[x]), o);
  const isNum = v => v !== null && v !== undefined && !Number.isNaN(v);
  function prevAvg(i, get, n = 30) {
    const vs = S.days.slice(Math.max(0, i - n), i).map(get).filter(isNum);
    return vs.length >= 3 ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  }
  function trendBadge(v, avg, betterUp, decimals = 0) {
    if (!isNum(v) || !isNum(avg)) return h('span', { class: 'trend flat', text: '' });
    const diff = v - avg;
    const rel = Math.abs(diff) / (Math.abs(avg) || 1);
    if (rel < 0.02) return h('span', { class: 'trend flat', text: '≈' });
    const cls = betterUp === null ? 'flat' : (diff > 0) === betterUp ? 'good' : 'bad';
    return h('span', { class: `trend ${cls}`, 'aria-label': diff > 0 ? 'cao hơn trung bình' : 'thấp hơn trung bình' },
      icon(diff > 0 ? 'up' : 'down', { width: 12, height: 12, 'stroke-width': 3 }), fmt.n(Math.abs(diff), decimals));
  }
  function dateLabel(date) {
    if (!S.summary) return '';
    const today = S.summary.today;
    const diff = Math.round((new Date(today) - new Date(date)) / 864e5);
    if (diff === 0) return 'Hôm nay';
    if (diff === 1) return 'Hôm qua';
    return `${fmt.weekday(date)} ${fmt.day(date)}`;
  }
  const zoneOf = d => ZONE[val(d, 'recovery', 'zone')] || null;
  const actName = a => a.name || ACT_TYPES[a.type] || a.type;
  function card(title, sub, ...kids) {
    return h('section', { class: 'card' }, title ? h('h2', { text: title }) : null, sub ? h('p', { class: 'sub', text: sub }) : null, ...kids);
  }
  // thẻ biểu đồ có nút chuyển sang bảng (truy cập không cần hover)
  function chartCard(title, sub, draw, table) {
    const box = h('div', { class: 'chart' });
    let showTable = false;
    const toggle = h('button', { class: 'toggle', type: 'button', text: 'Bảng' });
    const paint = () => {
      toggle.textContent = showTable ? 'Biểu đồ' : 'Bảng';
      if (showTable) box.replaceChildren(h('div', { class: 'table-scroll' }, table()));
      else draw(box);
    };
    toggle.addEventListener('click', () => { showTable = !showTable; paint(); });
    mount(paint);
    return h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', { text: title }), table ? toggle : null), sub ? h('p', { class: 'sub', text: sub }) : null, box);
  }
  function tableOf(head, rows) {
    return h('table', { class: 'data' }, h('thead', {}, h('tr', {}, head.map(x => h('th', { text: x })))), h('tbody', {}, rows.map(r => h('tr', {}, r.map(c => h('td', { text: c }))))));
  }
  function lastN(n, endDate = S.date) {
    const end = S.idx[endDate] ?? S.days.length - 1;
    return S.days.slice(Math.max(0, end - n + 1), end + 1);
  }

  // ---------- điều hướng ----------
  function go(patch) {
    Object.assign(S, patch);
    const parts = [S.tab];
    if (S.tab === 'home') parts.push(S.sub);
    if (S.tab !== 'trends' && S.date) parts.push(S.date);
    const hash = '#' + parts.join('/');
    try { if (location.hash !== hash) history.replaceState(null, '', hash); } catch (e) { /* khung nhúng có thể chặn */ }
    render();
    window.scrollTo({ top: 0 });
  }
  function readHash() {
    const [tab, a, b] = location.hash.replace(/^#/, '').split('/');
    if (['home', 'trends', 'health', 'journal'].includes(tab)) S.tab = tab;
    if (S.tab === 'home' && ['overview', 'sleep', 'recovery', 'strain'].includes(a)) S.sub = a;
    const date = S.tab === 'home' ? b : a;
    if (date && date in S.idx) S.date = date;
  }

  // ---------- khung ----------
  function topbar() {
    const i = S.idx[S.date];
    const showDate = S.tab !== 'trends' && S.date;
    const syncBtn = h('button', { class: `icon-btn${S.sync && S.sync.running ? ' spinning' : ''}`, type: 'button', title: 'Đồng bộ Garmin', 'aria-label': 'Đồng bộ Garmin', onclick: startSync }, icon('sync'));
    let mid = h('div', { class: 'datebar' }, h('div', { class: 'label', text: S.tab === 'trends' ? 'Xu hướng' : 'Garmin Health' }));
    if (showDate) {
      const picker = h('input', { type: 'date', 'aria-label': 'Chọn ngày', value: S.date, min: S.days[0].date, max: S.days[S.days.length - 1].date,
        onchange: e => { if (e.target.value in S.idx) go({ date: e.target.value }); } });
      mid = h('div', { class: 'datebar' },
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Ngày trước', disabled: i === 0 ? true : null, onclick: () => go({ date: S.days[i - 1].date }) }, icon('left')),
        h('div', { class: 'label' }, dateLabel(S.date), h('small', { text: S.date.split('-').reverse().join('/') }), picker),
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Ngày sau', disabled: i === S.days.length - 1 ? true : null, onclick: () => go({ date: S.days[i + 1].date }) }, icon('right')));
    }
    return h('header', { class: 'topbar' }, syncBtn, mid,
      h('button', { class: 'icon-btn', type: 'button', title: 'Cài đặt', 'aria-label': 'Cài đặt', onclick: openSettings }, icon('gear')));
  }
  function bottomnav() {
    const items = [['home', 'Tổng quan'], ['trends', 'Xu hướng'], ['health', 'Sức khoẻ'], ['journal', 'Nhật ký']];
    return h('nav', { class: 'bottomnav', 'aria-label': 'Chính' }, items.map(([k, label]) =>
      h('button', { type: 'button', 'aria-current': S.tab === k ? 'page' : null, onclick: () => go({ tab: k, sub: k === 'home' ? 'overview' : S.sub }) }, icon(k === 'home' ? 'home' : k), label)));
  }
  function homeTabs() {
    const items = [['overview', 'Tổng quan'], ['sleep', 'Ngủ'], ['recovery', 'Hồi phục'], ['strain', 'Strain']];
    return h('div', { class: 'tabs', role: 'tablist' }, items.map(([k, label]) =>
      h('button', { type: 'button', role: 'tab', 'aria-selected': String(S.sub === k), onclick: () => go({ sub: k }) }, label)));
  }

  function render() {
    tip.hide();
    mounts = [];
    const main = h('main', { class: 'app' });
    if (!S.summary || !S.days.length) {
      main.append(topbarEmpty(), viewEmpty());
      app.replaceChildren(main);
      return;
    }
    main.append(topbar());
    if (S.staticMode) main.append(h('div', { class: 'sample-note' }, h('span', { text: 'Xem thử · dữ liệu mẫu, không phải số đo thật' })));
    if (S.tab === 'home') {
      main.append(homeTabs());
      const views = { overview: viewOverview, sleep: viewSleep, recovery: viewRecovery, strain: viewStrain };
      main.append(...[].concat(views[S.sub](day())));
    } else if (S.tab === 'trends') main.append(...viewTrends());
    else if (S.tab === 'health') main.append(...viewHealth(day()));
    else main.append(...viewJournal(day()));
    app.replaceChildren(main, bottomnav());
    for (const fn of mounts) fn();
  }
  function topbarEmpty() {
    return h('header', { class: 'topbar' }, h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Đồng bộ Garmin', onclick: startSync }, icon('sync')),
      h('div', { class: 'datebar' }, h('div', { class: 'label', text: 'Garmin Health' })), h('span'));
  }
  function viewEmpty() {
    return h('div', { class: 'empty' },
      h('h1', { text: 'Chưa có dữ liệu' }),
      h('p', { class: 'sec', text: 'Tải dữ liệu từ Garmin Connect về máy rồi app sẽ tính Recovery, Strain và Giấc ngủ.' }),
      h('ol', {},
        h('li', {}, 'Đăng nhập một lần: ', h('code', { text: 'python run.py login' })),
        h('li', {}, 'Tải dữ liệu: ', h('code', { text: 'python run.py sync' }), ' — hoặc bấm nút đồng bộ ↻ ở góc trái'),
        h('li', {}, 'Xem thử với dữ liệu mẫu: ', h('code', { text: 'python run.py demo' }))));
  }

  // ---------- TỔNG QUAN ----------
  function dialButton(sub, name, svgNode, aria) {
    svgNode.setAttribute('aria-label', aria);
    return h('button', { class: 'dial', type: 'button', onclick: () => go({ sub }) }, svgNode, h('span', { class: 'name', text: name }));
  }
  function recoveryRing(d, size) {
    const r = d.recovery;
    if (!r || r.score === null || r.score === undefined) return ring({ frac: 0, color: C.neutral, text: '—', sub: r && r.calibrating ? 'HIỆU CHỈNH' : null, size });
    return ring({ frac: r.score / 100, color: zoneOf(d).color, text: r.score, unit: '%', size });
  }
  function strainRing(d, size) {
    const st = d.strain || {};
    const t = st.target;
    return ring({ frac: (st.score || 0) / 21, color: C.strain, text: isNum(st.score) ? fmt.n(st.score, 1) : '—', size, band: t ? [t[0] / 21, t[1] / 21] : null, sub: d.partial ? 'ĐANG TÍNH' : null });
  }
  function sleepRing(d, size) {
    const sl = d.sleep;
    return ring({ frac: sl ? sl.performance / 100 : 0, color: C.sleep, text: sl ? sl.performance : '—', unit: sl ? '%' : '', size });
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

  function activityList(d, includeSleep) {
    const rows = [];
    const sl = d.sleep;
    if (includeSleep && sl) {
      rows.push(h('button', { class: 'act', type: 'button', onclick: () => go({ sub: 'sleep' }) },
        h('div', { class: 'badge sleep', text: `${sl.performance}%` }),
        h('div', {}, h('div', { class: 'title', text: 'Giấc ngủ' }), h('div', { class: 'meta', text: `${sl.onset} → ${sl.wake}` })),
        h('div', { class: 'right' }, h('div', { text: fmt.dur(sl.hours) }), h('div', { class: 'muted', text: 'giờ ngủ' }))));
    }
    for (const a of d.activities || []) {
      rows.push(h('div', { class: 'act' },
        h('div', { class: `badge ${isNum(a.strain) ? 'strain' : 'none'}`, text: isNum(a.strain) ? fmt.n(a.strain, 1) : '—' }),
        h('div', {}, h('div', { class: 'title', text: actName(a) }),
          h('div', { class: 'meta', text: [a.start, `${a.duration_min} phút`, a.distance_km ? `${fmt.n(a.distance_km, 2)} km` : null].filter(Boolean).join(' · ') })),
        h('div', { class: 'right' }, h('div', { text: isNum(a.avg_hr) ? `${a.avg_hr} bpm` : '' }), h('div', { class: 'muted', text: isNum(a.calories) ? `${fmt.n(a.calories)} kcal` : '' }))));
    }
    if (!rows.length) return h('p', { class: 'muted', text: 'Không ghi nhận hoạt động.' });
    return h('div', { class: 'acts' }, rows);
  }

  function keyStats(d) {
    const i = S.idx[d.date];
    const items = [
      ['HRV', val(d, 'vitals', 'hrv'), 'ms', x => val(x, 'vitals', 'hrv'), true, 0],
      ['Nhịp tim nghỉ', val(d, 'vitals', 'rhr'), 'bpm', x => val(x, 'vitals', 'rhr'), false, 0],
      ['Nhịp thở', val(d, 'vitals', 'resp'), 'lần/ph', x => val(x, 'vitals', 'resp'), null, 1],
      ['Giờ ngủ', val(d, 'sleep', 'hours'), 'h', x => val(x, 'sleep', 'hours'), true, 'dur'],
      ['Calories', val(d, 'strain', 'calories'), 'kcal', x => (x.partial ? null : val(x, 'strain', 'calories')), null, 0],
      ['Số bước', val(d, 'strain', 'steps'), '', x => (x.partial ? null : val(x, 'strain', 'steps')), true, 0],
      ['Body Battery cao nhất', val(d, 'garmin', 'bb_high'), '', x => val(x, 'garmin', 'bb_high'), true, 0],
    ];
    const rows = items.map(([label, v, unit, get, up, dec]) => {
      const avg = prevAvg(i, get);
      const show = dec === 'dur' ? fmt.dur(v) : fmt.n(v, dec);
      const showAvg = dec === 'dur' ? fmt.dur(avg) : fmt.n(avg, dec);
      return h('div', { class: 'stat-row' },
        h('span', { class: 'label', text: label }),
        h('span', { class: 'value' }, show, unit && isNum(v) ? h('small', { text: unit }) : null),
        h('span', { class: 'base' }, trendBadge(v, avg, up, dec === 'dur' ? 1 : dec), h('br'), `TB30: ${showAvg}`));
    });
    return card('Chỉ số chính', 'So với trung bình 30 ngày trước', h('div', { class: 'stats' }, rows));
  }

  function hrCard(d, title = 'Nhịp tim trong ngày') {
    return chartCard(title, 'Vùng tím: giấc ngủ · vùng xanh: hoạt động (số = strain)', box => {
      box.classList.add('loading');
      getDetail(d.date).then(det => {
        box.classList.remove('loading');
        if (!det) { box.replaceChildren(h('p', { class: 'muted', text: 'Không có chi tiết ngày này.' })); return; }
        hrChart(box, { detail: det });
      });
    }, null);
  }

  // ---------- HỒI PHỤC ----------
  function viewRecovery(d) {
    const out = [];
    const r = d.recovery;
    const z = zoneOf(d);
    const ringNode = recoveryRing(d, 220);
    ringNode.setAttribute('aria-label', `Hồi phục ${val(r, 'score') ?? 'chưa có'}%`);
    out.push(h('div', { class: 'hero' }, ringNode,
      z ? h('div', { class: 'zone-label' }, h('span', { class: 'dot', style: { background: z.color } }), z.label) : null,
      h('p', { class: 'msg', text: z ? z.msg : r && r.calibrating ? 'Đang hiệu chỉnh baseline (cần ≥4 đêm).' : 'Chưa có dữ liệu đêm qua.' })));
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
  function vitalLine(title, sub, key, color, days, dec) {
    return chartCard(title, sub, box => lineChart(box, {
      data: days.map(x => ({ key: x.date, label: fmt.day(x.date), title: fmt.day(x.date), value: val(x, 'vitals', key), lo: val(x, 'health', key, 'lo'), hi: val(x, 'health', key, 'hi') })),
      color, fmtY: v => fmt.n(v, dec), name: title.split(' (')[0],
    }), () => tableOf(['Ngày', 'Giá trị', 'Ngưỡng'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.n(val(x, 'vitals', key), dec),
      isNum(val(x, 'health', key, 'lo')) ? `${fmt.n(x.health[key].lo, dec)}–${fmt.n(x.health[key].hi, dec)}` : '—'])));
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

  // ---------- STRAIN ----------
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
  const tile = (k, v, unit, dsub) => h('div', { class: 'tile' }, h('div', { class: 'k', text: k }), h('div', { class: 'v' }, v, unit && v !== '—' ? h('small', { text: unit }) : null), dsub ? h('div', { class: 'd', text: dsub }) : null);

  // ---------- NGỦ ----------
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
  const needRow = (label, hrs) => h('div', { class: 'need-row' }, h('span', { text: label }), h('b', { text: `${hrs < 0 ? '−' : ''}${fmt.dur(Math.abs(hrs || 0))}` }));
  function plannerCard(p) {
    return card('Kế hoạch ngủ đêm nay', `Để dậy lúc ${p.wake} (${p.wake_source}) · cần ${fmt.dur(p.need.total_h)} giấc ngủ`,
      h('div', { class: 'planner' }, p.options.map(o => h('div', { class: 'plan' },
        h('div', {}, h('div', { class: 'l', text: `${o.label} · ${o.pct}%` }), h('div', { class: 's', text: `nằm ${fmt.dur(o.in_bed_h)} trên giường` })),
        h('div', { class: 't', text: o.bedtime })))),
      h('p', { class: 'note', text: `Đã trừ hao thời gian thức trong đêm (hiệu quả ngủ ${p.efficiency ?? 90}%). Đổi giờ dậy trong ⚙ Cài đặt.` }));
  }

  // ---------- XU HƯỚNG ----------
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

  // ---------- SỨC KHOẺ (Health Monitor) ----------
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

  // ---------- NHẬT KÝ ----------
  function viewJournal(d) {
    const out = [];
    const qs = S.summary.journal_questions || [];
    const answers = { ...(d.journal || {}) };
    const saveState = h('span', { class: 'muted', text: '' });
    let timer = null;
    const save = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        d.journal = { ...answers };
        if (S.staticMode) { saveState.textContent = 'Bản xem thử: không lưu lên máy chủ'; return; }
        saveState.textContent = 'Đang lưu…';
        try {
          await post('api/journal', { date: d.date, answers });
          const cur = S.date;
          await loadSummary(); S.date = cur;
          saveState.textContent = 'Đã lưu ✓';
        } catch (e) { saveState.textContent = `Lỗi: ${e.message}`; }
      }, 500);
    };
    const qRows = qs.map(q => {
      const seg = h('div', { class: 'seg', role: 'group', 'aria-label': q.label });
      const paint = () => seg.replaceChildren(
        ...[[true, 'Có'], [false, 'Không']].map(([v, label]) => h('button', { type: 'button', 'aria-pressed': String(answers[q.key] === v),
          onclick: () => { answers[q.key] = answers[q.key] === v ? undefined : v; if (answers[q.key] === undefined) delete answers[q.key]; paint(); save(); } }, label)));
      paint();
      return h('div', { class: 'q' }, h('span', { text: q.label }), seg);
    });
    out.push(card(`Sáng ${fmt.day(d.date)}: hôm qua bạn có…`, 'Trả lời mỗi sáng. Sau vài tuần app sẽ cho thấy thói quen nào làm Hồi phục tăng/giảm.',
      h('div', {}, qRows), h('div', { class: 'row-btns' }, saveState)));
    const imp = S.summary.insights.journal || [];
    const maxAbs = Math.max(10, ...imp.map(x => Math.abs(x.recovery_diff || 0)));
    out.push(card('Thói quen ảnh hưởng thế nào', 'Hồi phục TB khi trả lời Có so với Không · ★ = khác biệt đáng tin (|t| ≥ 2)',
      h('div', {}, imp.map(x => {
        const has = isNum(x.recovery_diff);
        const dlt = x.recovery_diff || 0;
        const w = (Math.abs(dlt) / maxAbs) * 50;
        return h('div', { class: 'impact' },
          h('div', { class: 'lbl' }, x.label, x.significant ? h('span', { class: 'pill sig', text: '★' }) : null,
            h('small', { text: has ? `Có ${x.n_yes} lần · TB ${fmt.n(x.recovery_yes)}% vs ${fmt.n(x.recovery_no)}%` : `Cần ≥3 lần Có và ≥3 lần Không (đang ${x.n_yes}/${x.n_no})` })),
          h('div', { class: 'bar', role: 'img', 'aria-label': has ? `Chênh ${fmt.n(dlt, 1)} điểm` : 'chưa đủ dữ liệu' },
            h('span', { class: 'mid' }), has ? h('span', { style: { left: dlt >= 0 ? '50%' : `${50 - w}%`, width: `${w}%`, background: dlt >= 0 ? C.green : C.red, opacity: x.significant ? 1 : 0.45 } }) : null),
          h('div', { class: 'v', text: has ? `${dlt >= 0 ? '+' : '−'}${fmt.n(Math.abs(dlt), 0)}%` : '—' }));
      })),
      h('p', { class: 'note', text: 'Tương quan, không phải nhân quả: ngày uống rượu cũng có thể là ngày ngủ muộn, tập nặng…' })));
    return out;
  }

  // ---------- đồng bộ ----------
  let toastNode = null;
  function toast(text, frac, sticky) {
    if (!toastNode) { toastNode = h('div', { class: 'toast', role: 'status', 'aria-live': 'polite' }); document.body.append(toastNode); }
    toastNode.hidden = false;
    const bar = isNum(frac) ? h('div', { class: 'bar' }, h('span', { style: { width: `${Math.round(frac * 100)}%` } })) : null;
    toastNode.replaceChildren(...[h('div', { text }), bar].filter(Boolean));   // replaceChildren(null) sẽ in chữ "null"
    clearTimeout(toastNode._t);
    if (!sticky) toastNode._t = setTimeout(() => { toastNode.hidden = true; }, 4000);
  }
  async function startSync() {
    if (S.staticMode) { toast('Bản xem thử dùng dữ liệu mẫu — chạy app trên máy để đồng bộ Garmin.'); return; }
    try { await post('api/sync'); } catch (e) { toast(`Không bắt đầu được: ${e.message}`); return; }
    pollSync();
  }
  async function pollSync() {
    let st;
    try { st = (await (await fetch('api/status', { cache: 'no-store' })).json()).sync; } catch (e) { toast('Mất kết nối tới máy chủ'); return; }
    S.sync = st;
    if (st.running) {
      toast(`Đồng bộ: ${st.label}`, st.total ? st.done / st.total : null, true);
      document.querySelectorAll('.topbar .icon-btn')[0]?.classList.add('spinning');
      setTimeout(pollSync, 1200);
      return;
    }
    if (st.error) toast(`✗ ${st.error}`, null, false);
    else { toast(`✓ ${st.label}`); const cur = S.date; await loadSummary(); S.date = cur in S.idx ? cur : S.days[S.days.length - 1]?.date; }
    render();
  }

  // ---------- cài đặt ----------
  function openSettings() {
    const s = (S.summary && S.summary.settings) || {};
    const prof = (S.summary && S.summary.profile) || {};
    const back = h('div', { class: 'sheet-backdrop', onclick: e => { if (e.target === back) back.remove(); } });
    const f = (label, input, hint) => h('div', { class: 'field' }, h('label', {}, label, input), hint ? h('span', { class: 'hint', text: hint }) : null);
    const need = h('input', { type: 'number', step: '0.25', min: '5', max: '11', value: s.sleep_baseline_h ?? 7.75 });
    const hrmax = h('input', { type: 'number', min: '130', max: '230', placeholder: `tự động (${fmt.n(prof.hr_max)})`, value: s.hr_max ?? '' });
    const wake = h('input', { type: 'time', value: s.target_wake ?? '' });
    const sex = h('select', {}, [['', 'Theo Garmin'], ['male', 'Nam'], ['female', 'Nữ']].map(([v, l]) => h('option', { value: v, selected: (s.sex || '') === v ? true : null }, l)));
    [need, hrmax, wake, sex].forEach(x => { x.style.display = 'block'; x.style.width = '100%'; x.style.marginTop = '4px'; });
    const msg = h('p', { class: 'note' });
    const days = S.days;
    back.append(h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Cài đặt' },
      h('h2', { text: 'Cài đặt' }),
      f('Nhu cầu ngủ nền (giờ)', need, 'WHOOP mặc định ~7,5–8,5 giờ; tăng nếu ngày ngủ đủ bạn vẫn mệt.'),
      f('Nhịp tim tối đa (bpm)', hrmax, `Dùng cho Strain. Để trống = tự động (hiện ${fmt.n(prof.hr_max)} từ ${prof.hr_max_source || '—'}).`),
      f('Giờ muốn thức dậy', wake, 'Cho Kế hoạch ngủ. Để trống = trung vị giờ dậy 14 đêm gần nhất.'),
      f('Giới tính (hệ số TRIMP)', sex),
      h('div', { class: 'row-btns' },
        h('button', { class: 'btn ghost', type: 'button', onclick: () => back.remove() }, 'Đóng'),
        h('button', { class: 'btn', type: 'button', disabled: S.staticMode ? true : null, onclick: async () => {
          msg.textContent = 'Đang lưu và tính lại…';
          try {
            await post('api/settings', { sleep_baseline_h: Number(need.value), hr_max: hrmax.value ? Number(hrmax.value) : null, target_wake: wake.value || null, sex: sex.value || null });
            const cur = S.date; await loadSummary(); S.date = cur; back.remove(); render(); toast('Đã lưu cài đặt ✓');
          } catch (e) { msg.textContent = `Lỗi: ${e.message}`; }
        } }, 'Lưu')),
      msg,
      h('p', { class: 'note', text: days.length ? `Dữ liệu: ${days[0].date} → ${days[days.length - 1].date} (${days.length} ngày) · cập nhật ${S.summary.generated_at.replace('T', ' ').slice(0, 16)} UTC` : '' }),
      h('p', { class: 'note', text: S.staticMode ? 'Đây là bản xem thử với dữ liệu mẫu.' : 'Xem trên điện thoại: chạy `python run.py serve --lan` rồi mở địa chỉ in ra trên cùng Wi-Fi.' })));
    back.addEventListener('keydown', e => { if (e.key === 'Escape') back.remove(); });
    document.body.append(back);
    need.focus();
  }

  // ---------- khởi động ----------
  let resizeT = null;
  window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(render, 200); });
  window.addEventListener('hashchange', () => { readHash(); render(); });
  document.addEventListener('keydown', e => {
    if (e.target.closest('input,select,textarea') || !S.days.length || S.tab === 'trends') return;
    const i = S.idx[S.date];
    if (e.key === 'ArrowLeft' && i > 0) go({ date: S.days[i - 1].date });
    if (e.key === 'ArrowRight' && i < S.days.length - 1) go({ date: S.days[i + 1].date });
  });
  (async () => {
    try { await loadSummary(); } catch (e) { setSummary(null); }
    readHash();
    render();
    if (!S.staticMode) {
      try { const st = (await (await fetch('api/status', { cache: 'no-store' })).json()).sync; if (st.running) pollSync(); } catch (e) { /* server tĩnh */ }
    }
  })();
})();
