/* Nhật ký: câu hỏi mỗi sáng và thói quen ảnh hưởng tới hồi phục. */
(function () {
  'use strict';
  const { h, fmt } = window.GH;
  const { S, C, loadSummary, post, isNum, card, views } = window.GHA;

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

  views.journal = viewJournal;
})();
