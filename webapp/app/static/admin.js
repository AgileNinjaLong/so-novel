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
  const role = me.user.role === 'admin' ? '管理员' : '用户';
  $('#adminName').textContent = `${me.user.username} · ${role}`;
}

async function load() {
  overview = await api('/api/admin/overview');
  renderStats();
  renderKeys();
  renderUsers();
  renderTasks();
  updateKeySummary();
}

function renderStats() {
  const counts = overview.task_counts || {};
  $('#userCount').textContent = overview.user_count;
  $('#queueInfo').textContent = `${overview.queue_length} / ${counts.running || 0}`;
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  $('#taskCount').textContent = total;
  $('#userBadge').textContent = `共 ${overview.user_count} 人`;
  $('#taskBadge').textContent = `共 ${total} 条`;
  const stats = overview.key_stats || {};
  $('#keyStatBadge').textContent =
    `未用 ${stats.unused || 0} · 已用 ${stats.used || 0} · 撤销 ${stats.revoked || 0}` +
    (overview.key_total > 50 ? ` · 共 ${overview.key_total} 把（显示最近 50）` : '');
}

/* ---------------- 密钥 ---------------- */

function keyStatusText(status) {
  return { unused: '未使用', used: '已使用', revoked: '已撤销' }[status] || status;
}

function renderKeys() {
  const box = $('#keyList');
  box.innerHTML = '';
  const keys = overview.keys || [];
  if (!keys.length) {
    box.appendChild(el('div', 'muted', '还没有密钥，先在上面生成一把。'));
    return;
  }
  keys.forEach((k) => {
    const card = el('div', 'user-card');
    const head = el('div', 'head');
    head.appendChild(el('span', 'name', k.bound ? `密钥 · ${k.username}` : '密钥 · 未绑定'));
    const tags = el('div', 'tag-row');
    tags.appendChild(el('span', 'badge ' + (k.status === 'unused' ? 'ok' : k.status === 'used' ? 'info' : 'warn'), keyStatusText(k.status)));
    tags.appendChild(el('span', 'badge', k.days_text));
    head.appendChild(tags);
    card.appendChild(head);

    const code = el('div', 'key-box', k.key);
    code.style.marginTop = '8px';
    card.appendChild(code);

    const creds = el('div', 'meta',
      k.bound
        ? `账号：${k.username}　密码：${k.password}`
        : '账号：待用户注册后绑定（注册时由用户自己设置账号密码）');
    creds.style.color = k.bound ? 'var(--text)' : 'var(--muted)';
    card.appendChild(creds);

    const meta = el('div', 'meta',
      `生成：${(k.created_at || '').slice(0, 16).replace('T', ' ')}` +
      (k.used_at ? `　注册：${String(k.used_at).slice(0, 16).replace('T', ' ')}` : '') +
      (k.used_by_name ? `　使用者：${k.used_by_name}` : '') +
      (k.note ? `　备注：${k.note}` : ''));
    card.appendChild(meta);

    const ops = el('div', 'ops');
    const copy = el('button', 'btn small', '复制密钥');
    copy.addEventListener('click', () => copyText(k.key, copy));
    ops.appendChild(copy);
    if (k.bound) {
      const copyAll = el('button', 'btn small', '复制账号+密码+密钥');
      copyAll.addEventListener('click', () => copyText(
        `账号：${k.username}\n密码：${k.password}\n密钥：${k.key}`, copyAll));
      ops.appendChild(copyAll);
    }
    if (k.status === 'unused') {
      const revoke = el('button', 'btn small ghost', '撤销');
      revoke.addEventListener('click', () => revokeKey(k));
      ops.appendChild(revoke);
    }
    const del = el('button', 'btn small danger', '删除');
    del.addEventListener('click', () => deleteKey(k));
    ops.appendChild(del);
    card.appendChild(ops);
    box.appendChild(card);
  });
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    const old = btn.textContent;
    btn.textContent = '已复制';
    setTimeout(() => { btn.textContent = old; }, 1200);
  } catch (_) {
    prompt('复制下面的内容：', text);
  }
}

function currentKeyDays() {
  const raw = $('#keyDays').value;
  if (raw === 'custom') {
    const custom = Number($('#keyCustomDays').value);
    return Number.isFinite(custom) && custom > 0 ? Math.min(65535, Math.floor(custom)) : 0;
  }
  return Number(raw);
}

function updateKeySummary() {
  const days = currentKeyDays();
  const count = Math.max(1, Math.min(20, Number($('#keyCount').value) || 1));
  const daysText = days === 999999 ? '永久' : days > 0 ? `${days} 天` : '（请填写自定义天数）';
  $('#keySummaryHint').textContent = `将生成 ${count} 把 · 每把 ${daysText}`;
}

async function genKeys() {
  const days = currentKeyDays();
  if (!days) {
    showKeyMsg('请选择有效期，或填写自定义天数（1-65535）', 'bad');
    return;
  }
  const count = Math.max(1, Math.min(20, Number($('#keyCount').value) || 1));
  const body = { days, count, note: $('#keyNote').value.trim() };
  $('#genKeyBtn').disabled = true;
  try {
    const data = await api('/api/admin/keys', { method: 'POST', body });
    showKeyMsg(`已生成 ${data.keys.length} 把密钥（每把 ${days === 999999 ? '永久' : days + ' 天'}）`, 'ok');
    await load();
  } catch (err) {
    showKeyMsg(err.message, 'bad');
  } finally {
    $('#genKeyBtn').disabled = false;
  }
}

async function revokeKey(k) {
  if (!confirm('撤销后这把密钥立即失效（未使用时）。继续？')) return;
  try {
    await api(`/api/admin/keys/${k.id}`, { method: 'DELETE' });
    showKeyMsg('已撤销', 'ok');
    await load();
  } catch (err) { showKeyMsg(err.message, 'bad'); }
}

async function deleteKey(k) {
  if (!confirm('从列表里彻底删除这条密钥记录？（已使用的账号不受影响）')) return;
  try {
    await api(`/api/admin/keys/${k.id}?hard=1`, { method: 'DELETE' });
    showKeyMsg('已删除记录', 'ok');
    await load();
  } catch (err) { showKeyMsg(err.message, 'bad'); }
}

function showKeyMsg(text, kind) {
  const box = $('#keyMsg');
  box.textContent = text || '';
  box.className = 'msg' + (kind ? ' ' + kind : '');
}

/* ---------------- 用户 ---------------- */

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
    tags.appendChild(el('span', 'badge ' + (user.permanent || user.remaining_days > 0 ? 'ok' : 'warn'), validityText(user)));
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

    const reset = el('button', 'btn small ghost', '重置密码');
    reset.addEventListener('click', () => resetPassword(user));
    ops.appendChild(reset);

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

async function resetPassword(user) {
  if (!confirm(`为「${user.username}」生成新密码？旧密码将立即失效。`)) return;
  try {
    const data = await api(`/api/admin/users/${user.id}/password`, { method: 'POST' });
    showUserMsg(`新密码（请转交用户）：${data.password}`, 'ok');
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

/* ---------------- 任务 ---------------- */

function statusLabel(t) {
  const map = {
    queued: '排队中', running: '下载中', ready: '待接收', delivered: '已接收',
    paused: '已暂停', failed: '失败', canceled: '已取消', expired: '已过期',
  };
  return map[t.status] || t.status;
}

const selectedTaskIds = new Set();

function renderTasks() {
  const tbody = $('#taskBody');
  tbody.innerHTML = '';
  selectedTaskIds.clear();
  const tasks = overview.tasks || [];
  $('#emptyTasks').classList.toggle('hidden', tasks.length > 0);
  $('#bulkTaskBtn').classList.add('hidden');
  if (!tasks.length) return;

  // 按提交者分组：多人可能下载同一本书，必须按用户区分，避免混淆与误删
  const groups = new Map();
  tasks.forEach((t) => {
    const key = t.user || '（未知用户）';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  });

  groups.forEach((rows, user) => {
    const head = document.createElement('tr');
    head.className = 'group-row';
    const cell = document.createElement('td');
    cell.colSpan = 6;
    const name = el('strong', '', `提交者：${user}`);
    cell.appendChild(name);
    cell.appendChild(el('span', 'badge info', `${rows.length} 条`));
    const books = new Set(rows.map((r) => r.title)).size;
    cell.appendChild(el('span', 'badge', `${books} 本书`));
    const delAll = el('button', 'btn small danger', '删除该用户记录');
    delAll.addEventListener('click', () => adminDeleteTasks(rows.map((r) => r.id), user));
    cell.appendChild(delAll);
    head.appendChild(cell);
    tbody.appendChild(head);

    rows.forEach((t) => {
      const tr = document.createElement('tr');
      tr.dataset.id = t.id;

      const checkCell = el('td', 'check-cell');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'row-check';
      cb.value = t.id;
      cb.disabled = !t.can_delete;
      cb.addEventListener('change', () => {
        if (cb.checked) selectedTaskIds.add(t.id);
        else selectedTaskIds.delete(t.id);
        $('#bulkTaskBtn').classList.toggle('hidden', selectedTaskIds.size === 0);
        $('#bulkTaskCount').textContent = selectedTaskIds.size ? `（${selectedTaskIds.size}）` : '';
      });
      checkCell.appendChild(cb);
      tr.appendChild(checkCell);

      const status = el('td', 'status-cell');
      status.dataset.label = '状态';
      status.appendChild(el('span', 'tag ' + t.status, statusLabel(t)));
      tr.appendChild(status);

      const title = el('td', 'title-cell');
      title.dataset.label = '书名';
      title.appendChild(el('div', 't', t.title));
      if (t.message) {
        const m = el('div', 'm clamp', t.message);
        m.title = t.message;
        title.appendChild(m);
      }
      tr.appendChild(title);

      const src = el('td', 'source-cell', t.source);
      src.dataset.label = '来源';
      tr.appendChild(src);

      const prog = el('td', 'progress-cell');
      prog.dataset.label = '进度';
      const bar = el('div', 'bar');
      const fill = el('span');
      fill.style.width = `${Math.max(0, Math.min(100, t.progress || 0))}%`;
      bar.appendChild(fill);
      prog.appendChild(bar);
      let label = `${Math.round(t.progress || 0)}%`;
      if (t.chapters_total) label += ` · ${t.chapters_done}/${t.chapters_total}`;
      if (t.size_bytes) label += ` · ${(t.size_bytes / 1048576).toFixed(2)} MB`;
      prog.appendChild(el('div', 'p', label));
      tr.appendChild(prog);

      const ops = el('td', 'action-cell');
      ops.dataset.label = '操作';
      if (t.can_cancel) {
        const btn = el('button', 'btn small danger', '取消');
        btn.addEventListener('click', () => cancelTask(t.id));
        ops.appendChild(btn);
      }
      if (t.can_receive) {
        const btn = el('button', 'btn small primary', '接收');
        btn.addEventListener('click', () => receiveTask(t, btn));
        ops.appendChild(btn);
      }
      if (t.can_delete) {
        const del = el('button', 'btn small ghost', '删除');
        del.addEventListener('click', () => adminDeleteTasks([t.id], t.user));
        ops.appendChild(del);
      }
      if (!t.can_cancel && !t.can_receive && !t.can_delete) {
        ops.appendChild(el('span', 'muted', '—'));
      }
      tr.appendChild(ops);
      tbody.appendChild(tr);
    });
  });
}

async function adminDeleteTasks(ids, userLabel) {
  const count = ids.length;
  const who = userLabel ? `（用户 ${userLabel}）` : '';
  if (!confirm(`删除 ${count} 条下载记录${who}？\n待接收的文件会被一并丢弃，已接收的记录只删除记录本身。`)) return;
  try {
    const data = await api('/api/admin/tasks/bulk-delete', { method: 'POST', body: { ids } });
    showTaskMsg(`已删除 ${data.removed} 条记录${data.skipped.length ? `，${data.skipped.length} 条正在取消` : ''}`, 'ok');
    await load();
  } catch (err) {
    showTaskMsg(err.message, 'bad');
  }
}

async function bulkDeleteTasks() {
  await adminDeleteTasks(Array.from(selectedTaskIds), '');
}
async function receiveTask(t, btn) {
  const ttl = (overview && overview.file_ttl_min) || 120;
  if (!confirm(`接收《${t.title}》？完整下载后服务器会删除临时文件；若失败则保留 ${ttl} 分钟可重试。`)) return;
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '接收中…';
  try {
    const resp = await fetch(`/api/tasks/${t.id}/download`, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    if (!blob.size) throw new Error('文件为空');
    const cd = resp.headers.get('content-disposition') || '';
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i);
    const name = m ? decodeURIComponent(m[1]) : `${t.title}.${t.fmt || 'txt'}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    await api(`/api/tasks/${t.id}/ack`, { method: 'POST' });
    showTaskMsg(`已接收「${name}」，服务器文件已删除`, 'ok');
  } catch (err) {
    showTaskMsg(`未接收成功：${err.message}（文件仍保留，可重试）`, 'bad');
  } finally {
    btn.disabled = false;
    btn.textContent = old;
    await load();
  }
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

/* ---------------- 绑定 ---------------- */

$('#genKeyBtn').addEventListener('click', genKeys);
$('#bulkTaskBtn').addEventListener('click', bulkDeleteTasks);
$('#keyDays').addEventListener('change', () => {
  const custom = $('#keyDays').value === 'custom';
  $('#keyCustomDays').classList.toggle('hidden', !custom);
  if (custom) { $('#keyCustomDays').focus(); }
  updateKeySummary();
});
$('#keyCustomDays').addEventListener('input', updateKeySummary);
$('#keyCount').addEventListener('input', updateKeySummary);
$('#refreshBtn').addEventListener('click', load);
$('#logoutBtn').addEventListener('click', async () => {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
  location.href = '/login';
});

loadMe().catch(() => {});
load().catch((err) => {
  document.body.insertAdjacentHTML('afterbegin', `<div class="banner bad" style="margin:14px">${err.message}</div>`);
});
