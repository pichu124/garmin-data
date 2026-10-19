/* Garmin Health — lõi SPA: trạng thái S, dữ liệu, tiện ích, thẻ dùng chung, điều hướng → window.GHA.
 * Dữ liệu: /data/summary.json + /data/days/<ngày>.json (server.py), hoặc window.GH_DATA (bản xem thử tĩnh).
 * Mỗi màn hình (view-*.js) đăng ký GHA.views[key] = d => mảng node; app.js dựng khung rồi gọi view. */
(function () {
  'use strict';
  const { h, svg, fmt, ring, lineChart, hrChart } = window.GH;

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
    param: null, backSub: 'strain',   // trang hoạt động: id hoạt động, tab mà nút quay lại trở về
    staticMode: !!window.GH_DATA, sync: null,
    auth: false,   // server có mật khẩu web (api/status) ⇒ Cài đặt hiện nút Đăng xuất
  };
  // hàm vẽ chờ chạy sau khi node đã vào DOM (biểu đồ cần đo kích thước); render lấy ra bằng takeMounts
  let mounts = [];
  const mount = fn => mounts.push(fn);
  const takeMounts = () => { const fns = mounts; mounts = []; return fns; };

  // ---------- dữ liệu ----------
  // 401 = phiên đăng nhập hết hạn ⇒ tải lại trang, server sẽ trả trang đăng nhập
  function authGate(r) {
    if (r.status === 401) { location.reload(); throw new Error('Cần đăng nhập lại'); }
    return r;
  }
  async function loadSummary() {
    if (window.GH_DATA) { setSummary(window.GH_DATA.summary); return true; }
    const r = authGate(await fetch('data/summary.json', { cache: 'no-store' }));
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
    else { try { const r = authGate(await fetch(`data/days/${date}.json`, { cache: 'no-store' })); d = r.ok ? await r.json() : null; } catch (e) { d = null; } }
    S.details.set(date, d);
    return d;
  }
  async function post(url, body) {
    const r = authGate(await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }));
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
  const tile = (k, v, unit, dsub) => h('div', { class: 'tile' }, h('div', { class: 'k', text: k }), h('div', { class: 'v' }, v, unit && v !== '—' ? h('small', { text: unit }) : null), dsub ? h('div', { class: 'd', text: dsub }) : null);

  // ---------- điều hướng ----------
  function go(patch) {
    Object.assign(S, patch);
    const parts = [S.tab];
    if (S.tab === 'home') parts.push(S.sub);
    if (S.tab !== 'trends' && S.date) parts.push(S.date);
    if (S.tab === 'home' && S.sub === 'activity') parts.push(S.param);
    const hash = '#' + parts.join('/');
    try { if (location.hash !== hash) history.replaceState(null, '', hash); } catch (e) { /* khung nhúng có thể chặn */ }
    GHA.render();
    window.scrollTo({ top: 0 });
  }

  // ---------- thành phần dùng chung giữa các màn hình ----------
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
      rows.push(h('button', { class: 'act', type: 'button', onclick: () => go({ backSub: S.sub, sub: 'activity', param: a.id }) },
        h('div', { class: `badge ${isNum(a.strain) ? 'strain' : 'none'}`, text: isNum(a.strain) ? fmt.n(a.strain, 1) : '—' }),
        h('div', {}, h('div', { class: 'title', text: actName(a) }),
          h('div', { class: 'meta', text: [a.start, `${a.duration_min} phút`, a.distance_km ? `${fmt.n(a.distance_km, 2)} km` : null].filter(Boolean).join(' · ') })),
        h('div', { class: 'right' }, h('div', { text: isNum(a.avg_hr) ? `${a.avg_hr} bpm` : '' }), h('div', { class: 'muted', text: isNum(a.calories) ? `${fmt.n(a.calories)} kcal` : '' }))));
    }
    if (!rows.length) return h('p', { class: 'muted', text: 'Không ghi nhận hoạt động.' });
    return h('div', { class: 'acts' }, rows);
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

  function vitalLine(title, sub, key, color, days, dec) {
    return chartCard(title, sub, box => lineChart(box, {
      data: days.map(x => ({ key: x.date, label: fmt.day(x.date), title: fmt.day(x.date), value: val(x, 'vitals', key), lo: val(x, 'health', key, 'lo'), hi: val(x, 'health', key, 'hi') })),
      color, fmtY: v => fmt.n(v, dec), name: title.split(' (')[0],
    }), () => tableOf(['Ngày', 'Giá trị', 'Ngưỡng'], days.slice().reverse().map(x => [fmt.day(x.date), fmt.n(val(x, 'vitals', key), dec),
      isNum(val(x, 'health', key, 'lo')) ? `${fmt.n(x.health[key].lo, dec)}–${fmt.n(x.health[key].hi, dec)}` : '—'])));
  }

  const GHA = window.GHA = {
    S, C, icon, mount, takeMounts, authGate, loadSummary, setSummary, getDetail, post,
    day, val, isNum, prevAvg, trendBadge, dateLabel, zoneOf, actName, card, chartCard, tableOf, lastN, tile, go,
    recoveryRing, strainRing, sleepRing, activityList, hrCard, vitalLine,
    render: null,   // app.js gán
    views: {},      // view-*.js đăng ký: views[key] = d => mảng node (key: overview, sleep, recovery, strain, activity, trends, health, journal)
    zonesCard: null,   // view-strain.js gán; view-activity.js dùng lại
  };
})();
