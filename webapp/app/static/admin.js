'use strict';

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

async function api(url, opts = {}) {
  const options = { ...opts, headers: { ...(opts.headers || {}) }, credentials: 'same-origin' };
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  const res = await fetch(url, options);
  if (res.status === 401) { location.href = '/login'; throw new Error('未登录'); }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `请求失败（${res.status}）`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

let overview = null;

async function loadMe() {
  const me = await api('/api/auth/me');
  const chip = document.getElementById('adminName');
  const role = me.user.role === 'admin' ? '管理员' : '用户';
  chip.textContent = `${me.user.username} · ${role}`;
}

async function load() {
  overview = await api('/api/admin/overview');
  renderKey();
  renderStats();
  renderUsers();
  renderTasks();
}

function renderKey() {
  const key = overview.registration_key;
  $('#keyBox').textContent = key || '尚未生成（当前无法注册）';
  $('#keyMeta').textContent = key
    ? `生成时间：${overview.registration_key_created_at || '—'}　长度：${key.length}`
    : '注册入口已关闭';
}

function renderStats() {
  const counts = overview.task_counts || {};
  $('#userCount').textContent = overview.user_count;
  $('#queueInfo').textContent = `${overview.queue_length} / ${counts.running || 0}`;
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  $('#taskCount').textContent = total;
  $('#userBadge').textContent = `共 ${overview.user_count} 人`;
  $('#taskBadge').textContent = `共 ${total} 条`;
}

function validityText(user) {
  if (user.permanent) return '永久有效';
  if (user.remaining_days > 0) return `剩余 ${user.remaining_days} 天`;
  return '未开通/已过期';
}

function renderUsers() {
  const box = $('#userList');
  box.innerHTML = '';
  overview.users.forEach((user) => {
    const card = el('div', 'user-card');
    const head = el('div', 'head');
    head.appendChild(el('span', 'name', user.username));
    const tags = el('div', 'tag-row');
    tags.appendChild(el('span', 'badge ' + (user.role === 'admin' ? 'info' : ''), user.role === 'admin' ? '管理员' : '用户'));
    tags.appendChild(el('span', 'badge ' + (user.status === 'active' ? 'ok' : 'bad'), user.status === 'active' ? '正常' : '已禁用'));
    tags.appendChild(el('span', 'badge ' + (user.permanent ? 'ok' : user.remaining_days > 0 ? 'ok' : 'warn'), validityText(user)));
    head.appendChild(tags);
    card.appendChild(head);

    const meta = el('div', 'meta',
      `注册：${(user.created_at || '').slice(0, 10)}　最后登录：${(user.last_login_at || '—').slice(0, 10)}　任务：${user.task_count}`);
    card.appendChild(meta);

    const ops = el('div', 'ops');
    const presets = [[1, '+1 天'], [31, '+31 天'], [124, '+124 天'], [372, '+372 天'], [999999, '永久']];
    presets.forEach(([days, label]) => {
      const btn = el('button', 'btn small', label);
      if (user.permanent && days < 999999) btn.disabled = true;
      btn.addEventListener('click', () => grant(user.id, days));
      ops.appendChild(btn);
    });
    const toggle = el('button', 'btn small ghost', user.status === 'active' ? '禁用' : '启用');
    toggle.addEventListener('click', () => setStatus(user.id, user.status === 'active' ? 'banned' : 'active'));
    ops.appendChild(toggle);

    if (user.role !== 'admin') {
      const del = el('button', 'btn small danger', '删除');
      del.addEventListener('click', () => removeUser(user));
      ops.appendChild(del);
    }
    card.appendChild(ops);
    box.appendChild(card);
  });
}

async function grant(userId, days) {
  try {
    const data = await api(`/api/admin/users/${userId}/grant`, { method: 'POST', body: { days } });
    showUserMsg(`已为 ${data.user.username} 叠加 ${days >= 999999 ? '永久' : days + ' 天'}：${validityText(data.user)}`, 'ok');
    await load();
  } catch (err) { showUserMsg(err.message, 'bad'); }
}

async function setStatus(userId, status) {
  try {
    await api(`/api/admin/users/${userId}/status`, { method: 'POST', body: { status } });
    showUserMsg(status === 'banned' ? '已禁用该用户（其登录会话已失效）' : '已启用该用户', 'ok');
    await load();
  } catch (err) { showUserMsg(err.message, 'bad'); }
}

async function removeUser(user) {
  if (!confirm(`确认删除用户「${user.username}」及其全部记录？此操作不可恢复。`)) return;
  try {
    await api(`/api/admin/users/${user.id}`, { method: 'DELETE' });
    showUserMsg(`已删除用户 ${user.username}`, 'ok');
    await load();
  } catch (err) { showUserMsg(err.message, 'bad'); }
}

function renderTasks() {
  const tbody = $('#taskBody');
  tbody.innerHTML = '';
  const tasks = overview.tasks || [];
  $('#emptyTasks').classList.toggle('hidden', tasks.length > 0);
  tasks.forEach((t) => {
    const tr = document.createElement('tr');

    const status = el('td', 'status-cell');
    status.dataset.label = '状态';
    status.appendChild(el('span', 'tag ' + t.status, statusLabel(t)));
    tr.appendChild(status);

    const title = el('td', 'title-cell');
    title.dataset.label = '书名';
    title.appendChild(el('div', 't', t.title));
    if (t.message) title.appendChild(el('div', 'm', t.message));
    tr.appendChild(title);

    const src = el('td', 'source-cell', t.source);
    src.dataset.label = '来源';
    tr.appendChild(src);

    const who = el('td', 'user-cell', t.user || '匿名');
    who.dataset.label = '提交者';
    tr.appendChild(who);

    const prog = el('td', 'progress-cell');
    prog.dataset.label = '进度';
    const bar = el('div', 'bar');
    const fill = el('span');
    fill.style.width = `${Math.max(0, Math.min(100, t.progress || 0))}%`;
    bar.appendChild(fill);
    prog.appendChild(bar);
    prog.appendChild(el('div', 'p', `${Math.round(t.progress || 0)}%${t.chapters_total ? ` · ${t.chapters_done}/${t.chapters_total}` : ''}`));
    tr.appendChild(prog);

    const ops = el('td', 'action-cell');
    ops.dataset.label = '操作';
    if (t.can_cancel) {
      const btn = el('button', 'btn small danger', '取消');
      btn.addEventListener('click', () => cancelTask(t.id));
      ops.appendChild(btn);
    }
    if (t.can_download) {
      const a = el('a', 'btn small primary', '下载');
      a.href = `/api/tasks/${t.id}/download`;
      ops.appendChild(a);
    }
    if (!t.can_cancel && !t.can_download) {
      ops.appendChild(el('span', 'muted', '—'));
    }
    tr.appendChild(ops);
    tbody.appendChild(tr);
  });
}

function statusLabel(t) {
  const map = { queued: '排队中', running: '下载中', success: '已完成', failed: '失败', canceled: '已取消' };
  return map[t.status] || t.status;
}

async function cancelTask(id) {
  try {
    await api(`/api/admin/tasks/${id}/cancel`, { method: 'POST' });
    showTaskMsg('已请求取消', 'ok');
    await load();
  } catch (err) { showTaskMsg(err.message, 'bad'); }
}

function showUserMsg(text, kind) {
  const box = $('#userMsg');
  box.textContent = text || '';
  box.className = 'msg' + (kind ? ' ' + kind : '');
}

function showTaskMsg(text, kind) {
  const box = $('#taskMsg');
  box.textContent = text || '';
  box.className = 'msg' + (kind ? ' ' + kind : '');
}

$('#rotateKeyBtn').addEventListener('click', async () => {
  if (!confirm('生成新密钥后旧密钥立即失效（已注册用户不受影响）。继续？')) return;
  try {
    const data = await api('/api/admin/key', { method: 'POST' });
    $('#keyMsg').textContent = '已生成新注册密钥';
    $('#keyMsg').className = 'msg ok';
    await load();
  } catch (err) { $('#keyMsg').textContent = err.message; $('#keyMsg').className = 'msg bad'; }
});

$('#clearKeyBtn').addEventListener('click', async () => {
  if (!confirm('清空注册密钥后，任何人都无法再注册。继续？')) return;
  try {
    await api('/api/admin/key', { method: 'DELETE' });
    $('#keyMsg').textContent = '已清空，注册已关闭';
    $('#keyMsg').className = 'msg ok';
    await load();
  } catch (err) { $('#keyMsg').textContent = err.message; $('#keyMsg').className = 'msg bad'; }
});

$('#refreshBtn').addEventListener('click', load);
$('#logoutBtn').addEventListener('click', async () => {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
  location.href = '/login';
});

loadMe().catch(() => {});
load().then(() => {
  if (overview && overview.active_source) {
    // 仅用于展示来源
  }
}).catch((err) => {
  document.body.insertAdjacentHTML('afterbegin', `<div class="banner bad" style="margin:14px">${err.message}</div>`);
});
