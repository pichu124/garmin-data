/* Trang đăng nhập (server trả thay index.html khi đã đặt mật khẩu web mà chưa có phiên). */
(function () {
  'use strict';
  const form = document.getElementById('login');
  const msg = document.getElementById('msg');
  const btn = form.querySelector('button');
  form.addEventListener('submit', async e => {
    e.preventDefault();
    btn.disabled = true;
    msg.textContent = 'Đang kiểm tra…';
    try {
      const r = await fetch('api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: form.password.value }) });
      if (r.ok) { location.reload(); return; }   // giữ #route: tải lại thì server trả app
      msg.textContent = (await r.json().catch(() => ({}))).error || `HTTP ${r.status}`;
      form.password.select();
    } catch (err) {
      msg.textContent = 'Mất kết nối tới máy chủ';
    }
    btn.disabled = false;
  });
})();
