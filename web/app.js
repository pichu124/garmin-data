/* Garmin Health — SPA kiểu WHOOP: Tổng quan (Ngủ · Hồi phục · Strain), Xu hướng, Sức khoẻ, Nhật ký.
 * Khung: topbar, nav, render, router, đồng bộ, cài đặt, khởi động. Lõi ở core.js, màn hình ở view-*.js. */
(function () {
  'use strict';
  const { h, fmt, tip } = window.GH;
  const GHA = window.GHA;
  const { S, C, icon, go, day, dateLabel, zoneOf, isNum, post, loadSummary, setSummary, takeMounts } = GHA;
  const app = document.getElementById('app');

  // ---------- điều hướng ----------
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
      const full = S.date.split('-').reverse().join('/');
      mid = h('div', { class: 'datebar' },
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Ngày trước', disabled: i === 0 ? true : null, onclick: () => go({ date: S.days[i - 1].date }) }, icon('left')),
        h('button', { class: 'label', type: 'button', 'aria-haspopup': 'dialog', 'aria-label': `Chọn ngày trên lịch, đang xem ${dateLabel(S.date)} ${full}`, onclick: openCalendar },
          dateLabel(S.date), h('small', { text: full })),
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
    takeMounts();   // bỏ hàm vẽ còn sót của lần render trước
    const main = h('main', { class: 'app' });
    if (!S.summary || !S.days.length) {
      main.append(topbarEmpty(), viewEmpty());
      app.replaceChildren(main);
      return;
    }
    main.append(topbar());
    if (S.staticMode) main.append(h('div', { class: 'sample-note' }, h('span', { text: 'Xem thử · dữ liệu mẫu, không phải số đo thật' })));
    if (S.tab === 'home') main.append(homeTabs());
    main.append(...GHA.views[S.tab === 'home' ? S.sub : S.tab](day()));
    app.replaceChildren(main, bottomnav());
    for (const fn of takeMounts()) {   // một biểu đồ lỗi không được làm trắng các biểu đồ sau
      try { fn(); } catch (e) { console.error(e); }
    }
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

  // ---------- lịch tháng: ô tô theo vùng recovery, chọn ngày ----------
  function openCalendar() {
    let [y, mo] = S.date.split('-').map(Number);
    const first = S.days[0].date.slice(0, 7), last = S.days[S.days.length - 1].date.slice(0, 7);
    const ym = () => `${y}-${String(mo).padStart(2, '0')}`;
    const back = h('div', { class: 'sheet-backdrop', onclick: e => { if (e.target === back) close(); } });
    const close = () => { back.remove(); app.inert = false; app.querySelector('.datebar .label')?.focus(); };
    const prevBtn = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Tháng trước', onclick: () => shift(-1) }, icon('left'));
    const nextBtn = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Tháng sau', onclick: () => shift(1) }, icon('right'));
    const title = h('h2', { 'aria-live': 'polite' });
    const grid = h('div', { class: 'cal-grid' });
    function shift(k) {
      mo += k;
      if (mo < 1) { mo = 12; y--; }
      if (mo > 12) { mo = 1; y++; }
      paint();
      if ((k < 0 ? prevBtn : nextBtn).disabled) (k < 0 ? nextBtn : prevBtn).focus();   // nút vừa bấm bị tắt ⇒ đừng để mất focus
    }
    function paint() {
      title.textContent = `Tháng ${mo}/${y}`;
      prevBtn.disabled = ym() <= first;
      nextBtn.disabled = ym() >= last;
      const cells = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map(w => h('span', { class: 'wd', 'aria-hidden': 'true', text: w }));
      for (let k = (new Date(y, mo - 1, 1).getDay() + 6) % 7; k > 0; k--) cells.push(h('span'));   // cột đầu là T2
      for (let dd = 1, n = new Date(y, mo, 0).getDate(); dd <= n; dd++) {
        const date = `${ym()}-${String(dd).padStart(2, '0')}`;
        const x = S.days[S.idx[date]], z = x && zoneOf(x);
        const what = !x ? 'không có dữ liệu' : z ? `hồi phục ${x.recovery.score}%, ${z.label}` : 'chưa có điểm hồi phục';
        cells.push(h('button', { class: 'cal-day', type: 'button', disabled: x ? null : true, 'aria-current': date === S.date ? 'date' : null,
          'aria-label': `${fmt.weekday(date)} ${dd}/${mo}: ${what}`, style: { borderColor: z ? z.color : null },
          onclick: () => { go({ date }); close(); } }, String(dd)));
      }
      grid.replaceChildren(...cells);
    }
    const legend = [[C.green, 'Hồi phục tốt'], [C.yellow, 'Hồi phục vừa'], [C.red, 'Cần nghỉ ngơi'], [null, 'Chưa có điểm']];
    back.append(h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Chọn ngày' },
      h('div', { class: 'cal-head' }, prevBtn, title, nextBtn), grid,
      h('div', { class: 'legend l4 cal-legend' }, legend.map(([c, k]) => h('div', { class: 'item' }, h('span', { class: 'sw', style: { borderColor: c } }), h('span', { class: 'k', text: k })))),
      h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', onclick: close }, 'Đóng'))));
    // chặn phím lan ra document: ←/→ ở đó đổi ngày phía sau lịch
    back.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Escape') close(); });
    document.body.append(back);
    app.inert = true;   // modal thật: Tab không lọt ra trang phía sau
    paint();
    grid.querySelector('[aria-current=date]').focus();
  }

  // ---------- khởi động ----------
  GHA.render = render;   // go() trong core.js gọi lại
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
