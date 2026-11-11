'use strict';

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const state = {
  meta: null,
  me: null,
  snapshot: null,
  activeSource: null,
  pendingSource: null,
  picked: null,
  timer: null,
};

/* ---------------- 基础请求 ---------------- */

async function api(url, opts = {}) {
  const options = { ...opts, headers: { ...(opts.headers || {}) }, credentials: 'same-origin' };
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  const res = await fetch(url, options);
  if (res.status === 401) {
    location.href = '/login';
    throw new Error('未登录');
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
  if (!res.ok) {
    const message = (data && (data.detail || data.message)) || `请求失败（${res.status}）`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

/* ---------------- 启动 ---------------- */

async function boot() {
  await loadMeta();
  bindEvents();
  await refresh();
  const poll = (state.meta && state.meta.app.poll_ms) || 1500;
  state.timer = setInterval(refresh, poll);
}

async function loadMeta() {
  const meta = await api('/api/meta');
  state.meta = meta;
  state.me = meta.user;
  state.activeSource = meta.app.active_source;

  renderUser();
  const sel = $('#sourceSelect');
  sel.innerHTML = '';
  meta.plugins.forEach((p) => {
    const opt = el('option', '', `${p.name}${p.ready ? '' : '（不可用）'}`);
    opt.value = p.id;
    opt.disabled = !p.ready;
    sel.appendChild(opt);
  });
  sel.value = meta.app.active_source;
  $('#cleanupBtn').classList.toggle('hidden', !(state.me && state.me.role === 'admin'));
  $('#adminBtn').classList.toggle('hidden', !(state.me && state.me.role === 'admin'));
  renderAccountStatus();
  renderSourceStatus();
  applyCapabilities();
}

function renderUser() {
  const me = state.me;
  if (!me) return;
  $('#userName').textContent = me.username;
  const chip = $('#userChip');
  chip.className = 'user-chip';
  let text = me.username;
  if (me.role === 'admin') text += ' · 管理员';
  if (me.permanent) text += ' · 永久';
  else if (me.remaining_days > 0) text += ` · 剩 ${me.remaining_days} 天`;
  else text += ' · 未开通';
  $('#userName').textContent = text;
  if (!me.active) chip.classList.add('warn');
  if (me.status === 'banned') chip.classList.add('bad');
}

function renderAccountStatus() {
  const me = state.me;
  const banner = $('#accountBanner');
  if (!me) return;
  if (me.status === 'banned') {
    banner.textContent = '账号已被管理员禁用，请联系管理员。';
    banner.classList.remove('hidden');
    return;
  }
  if (!me.active) {
    banner.textContent = '账号未开通或已过期，暂时无法提交下载。请联系管理员开通时长。';
    banner.classList.remove('hidden');
    return;
  }
  banner.classList.add('hidden');
}

function currentPlugin() {
  if (!state.meta) return null;
  return state.meta.plugins.find((p) => p.id === state.activeSource) || null;
}

function renderSourceStatus() {
  const p = currentPlugin();
  const box = $('#sourceStatus');
  box.innerHTML = '';
  if (!p) return;
  const line = el('div');
  line.appendChild(el('strong', '', p.name));
  line.appendChild(document.createTextNode(' · ' + p.upstream));
  box.appendChild(line);
  box.appendChild(el('div', p.ready ? 'ok' : 'bad', p.ready ? '就绪 ' + (p.status_detail || '') : p.status_detail));
  if (p.capabilities.notes) box.appendChild(el('div', '', p.capabilities.notes));
}

function applyCapabilities() {
  const p = currentPlugin();
  if (!p) return;
  const caps = p.capabilities;
  $('#inputTitle').textContent = `提交下载 · ${p.name}`;
  $('#inputHint').textContent = caps.input_hint;
  $('#searchMode').classList.toggle('hidden', !caps.search);
  $('#urlMode').classList.toggle('hidden', caps.search);

  const fmt = $('#fmtSelect');
  fmt.innerHTML = '';
  caps.formats.forEach((f) => {
    const opt = el('option', '', f);
    opt.value = f;
    fmt.appendChild(opt);
  });
  state.picked = null;
  $('#enqueueMsg').textContent = '';
  $('#searchResults').innerHTML = '';
}

/* ---------------- 事件 ---------------- */

function bindEvents() {
  $('#switchBtn').addEventListener('click', () => askSwitch());
  $('#sourceSelect').addEventListener('change', () => askSwitch());
  $('#searchBtn').addEventListener('click', doSearch);
  $('#searchBox').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
  $('#enqueueBtn').addEventListener('click', enqueue);
  $('#refreshBtn').addEventListener('click', refresh);
  $('#cleanupBtn').addEventListener('click', cleanup);
  $('#modalCancel').addEventListener('click', closeModal);
  $('#modalAfter').addEventListener('click', () => applySwitch('after_current'));
  $('#modalNow').addEventListener('click', () => applySwitch('cancel_now'));
  $('#logoutBtn').addEventListener('click', logout);
  $('#adminBtn').addEventListener('click', () => { location.href = '/admin'; });
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
  location.href = '/login';
}

function askSwitch() {
  const target = $('#sourceSelect').value;
  if (!target || target === state.activeSource) return;
  state.pendingSource = target;
  const p = state.meta.plugins.find((x) => x.id === target);
  const running = state.snapshot && state.snapshot.running;
  const queueLen = (state.snapshot && state.snapshot.queue_length) || 0;

  if (!running) { applySwitch('cancel_now'); return; }
  $('#modalText').textContent =
    `当前正在下载「${running.title}」（来源：${sourceName(running.source)}），队列中还有 ${queueLen} 个任务。\n\n` +
    `切换到「${p.name}」后，同一时间只会使用新来源（这是全局设置，会影响所有用户）：\n` +
    `· 「等当前任务结束后切换」：当前这本下完自动切换，旧来源的排队任务会被取消。\n` +
    `· 「立即取消并切换」：立刻中断当前下载并切换，旧来源的排队任务同样取消。`;
  $('#modal').classList.remove('hidden');
}

async function applySwitch(mode) {
  const target = state.pendingSource;
  if (!target) { closeModal(); return; }
  closeModal();
  try {
    const result = await api('/api/source', { method: 'POST', body: { source: target, mode } });
    state.activeSource = result.active_source;
    $('#sourceSelect').value = result.active_source;
    applyCapabilities();
    showMsg(result.message + (result.canceled && result.canceled.length ? `（取消 ${result.canceled.length} 个排队任务）` : ''), 'ok');
    await loadMeta();
    await refresh();
  } catch (err) {
    showMsg(err.message, 'bad');
  } finally {
    state.pendingSource = null;
  }
}

function closeModal() {
  $('#modal').classList.add('hidden');
  $('#sourceSelect').value = state.activeSource;
}

/* ---------------- 搜索 ---------------- */

async function doSearch() {
  const q = $('#searchBox').value.trim();
  if (!q) return;
  const box = $('#searchResults');
  box.innerHTML = '<li class="muted">搜索中…</li>';
  try {
    const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
    box.innerHTML = '';
    if (!data.items.length) { box.appendChild(el('li', 'muted', '没有找到结果')); return; }
    data.items.forEach((item) => {
      const li = el('li');
      const left = el('div');
      left.appendChild(el('div', 'name', item.title));
      left.appendChild(el('div', 'meta', item.author || ''));
      const pick = el('button', 'btn small', '选择');
      pick.addEventListener('click', () => {
        state.picked = item;
        $('#titleBox').value = item.title;
        showMsg(`已选择《${item.title}》，可直接加入队列`, 'ok');
      });
      li.appendChild(left);
      li.appendChild(pick);
      box.appendChild(li);
    });
  } catch (err) {
    box.innerHTML = '';
    box.appendChild(el('li', 'muted', '搜索失败：' + err.message));
  }
}

/* ---------------- 提交 ---------------- */

async function enqueue() {
  const p = currentPlugin();
  if (!p) return;
  const fmt = $('#fmtSelect').value;
  let ref = '';
  let title = $('#titleBox').value.trim();

  if (p.capabilities.search) {
    if (state.picked) {
      ref = state.picked.book_ref;
      title = title || state.picked.title;
    } else {
      const typed = $('#searchBox').value.trim();
      if (/^https?:\/\//i.test(typed)) {
        // 搜索框里直接粘贴详情页链接，跳过搜索
        ref = typed;
        title = title || typed;
      } else if (/^\d{6,}$/.test(typed)) {
        ref = typed;
        title = title || `book ${typed}`;
      } else {
        return showMsg('请先搜索并选择一本书，或直接把详情页链接粘到搜索框', 'bad');
      }
    }
  } else {
    ref = $('#urlBox').value.trim();
    if (!ref) return showMsg('请粘贴书籍详情页链接', 'bad');
  }
  if (!fmt) return showMsg('请选择导出格式', 'bad');

  $('#enqueueBtn').disabled = true;
  try {
    const data = await api('/api/tasks', { method: 'POST', body: { source: state.activeSource, title, book_ref: ref, fmt } });
    const pos = data.queue_position;
    showMsg(`已加入队列${pos ? `，排队第 ${pos} 位` : ''}`, 'ok');
    state.picked = null;
    $('#titleBox').value = '';
    $('#urlBox').value = '';
    await refresh();
  } catch (err) {
    showMsg(err.message, 'bad');
  } finally {
    $('#enqueueBtn').disabled = false;
  }
}

/* ---------------- 队列 ---------------- */

async function refresh() {
  try {
    const snap = await api('/api/state');
    state.snapshot = snap;
    if (snap.active_source !== state.activeSource) {
      state.activeSource = snap.active_source;
      $('#sourceSelect').value = snap.active_source;
      renderSourceStatus();
      applyCapabilities();
    } else {
      renderSourceStatus();
    }
    renderBanner(snap);
    renderTasks(snap);
  } catch (err) { /* 未登录会被 api() 跳转 */ }
}

function renderBanner(snap) {
  const banner = $('#switchBanner');
  const pending = snap.pending_switch;
  if (!pending) { banner.classList.add('hidden'); return; }
  banner.classList.remove('hidden');
  banner.textContent =
    `待切换：当前任务完成后自动切换到「${sourceName(pending.source)}」（请求时间 ${pending.requested_at}）。切换生效前不能向当前来源提交新任务。`;
}

function renderTasks(snap) {
  const tbody = $('#taskBody');
  tbody.innerHTML = '';
  const tasks = snap.tasks || [];
  $('#emptyQueue').classList.toggle('hidden', tasks.length > 0);
  $('#countBadge').textContent = `运行 ${snap.counts.running || 0} · 排队 ${snap.counts.queued || 0} · 待接收 ${snap.counts.ready || 0}`;

  tasks.forEach((t) => {
    const tr = document.createElement('tr');

    const status = el('td', 'status-cell');
    status.dataset.label = '状态';
    status.appendChild(statusTag(t));
    tr.appendChild(status);

    const titleCell = el('td', 'title-cell');
    titleCell.dataset.label = '书名';
    titleCell.appendChild(el('div', 't', t.title));
    if (t.message) titleCell.appendChild(el('div', 'm', t.message));
    if (t.error && t.status === 'failed') titleCell.appendChild(el('div', 'm', t.error));
    tr.appendChild(titleCell);

    const src = el('td', 'source-cell', sourceName(t.source));
    src.dataset.label = '来源';
    tr.appendChild(src);

    const who = el('td', 'user-cell', (t.user || '匿名') + (t.mine ? '（我）' : ''));
    who.dataset.label = '提交者';
    tr.appendChild(who);

    const prog = el('td', 'progress-cell');
    prog.dataset.label = '进度';
    const bar = el('div', 'bar');
    const fill = el('span');
    fill.style.width = `${Math.max(0, Math.min(100, t.progress || 0))}%`;
    bar.appendChild(fill);
    prog.appendChild(bar);
    let label = `${Math.round(t.progress || 0)}%`;
    if (t.chapters_total) label += ` · ${t.chapters_done}/${t.chapters_total} 章`;
    if (t.size_bytes) label += ` · ${(t.size_bytes / 1048576).toFixed(2)} MB`;
    prog.appendChild(el('div', 'p', label));
    tr.appendChild(prog);

    const actions = el('td', 'action-cell');
    actions.dataset.label = '操作';
    if (t.can_pause) {
      const pause = el('button', 'btn small', '暂停');
      pause.addEventListener('click', () => pauseTask(t.id));
      actions.appendChild(pause);
    }
    if (t.can_cancel) {
      const cancel = el('button', 'btn small', '取消');
      cancel.addEventListener('click', () => cancelTask(t.id));
      actions.appendChild(cancel);
    }
    if (t.can_receive) {
      const a = el('a', 'btn small primary', '接收文件');
      a.href = `/api/tasks/${t.id}/download`;
      actions.appendChild(a);
    }
    if (t.can_retry) {
      const retry = el('button', 'btn small ghost', '重新下载');
      retry.addEventListener('click', () => retryTask(t.id));
      actions.appendChild(retry);
    }
    if (!t.can_cancel && !t.can_pause && !t.can_receive && !t.can_retry) {
      actions.appendChild(el('span', 'muted', '—'));
    }
    tr.appendChild(actions);
    tbody.appendChild(tr);
  });
}

function statusTag(t) {
  const map = {
    queued: ['queued', '排队中'],
    running: ['running', '下载中'],
    ready: ['ready', '待接收'],
    delivered: ['delivered', '已接收'],
    paused: ['paused', '已暂停'],
    expired: ['expired', '已过期'],
    failed: ['failed', '失败'],
    canceled: ['canceled', '已取消'],
  };
  const [cls, text] = map[t.status] || ['queued', t.status];
  let label = text;
  if (t.status === 'queued' && t.queue_position) label += ` · 第 ${t.queue_position} 位`;
  return el('span', 'tag ' + cls, label);
}

async function pauseTask(id) {
  if (!confirm('暂停会丢弃当前进度，之后只能「重新下载」（重新排队）。继续？')) return;
  try {
    const data = await api(`/api/tasks/${id}/pause`, { method: 'POST' });
    showMsg(data.was_running ? '正在暂停…' : '已暂停', 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function retryTask(id) {  try {
    const data = await api(`/api/tasks/${id}/retry`, { method: 'POST' });
    showMsg(`已重新排队${data.queue_position ? `，第 ${data.queue_position} 位` : ''}`, 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function cancelTask(id) {
  try {
    await api(`/api/tasks/${id}`, { method: 'DELETE' });
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function cleanup() {
  if (!confirm('删除所有「失败」和「已取消」的任务记录（已完成的下载会保留）？')) return;
  try {
    const data = await api('/api/cleanup', { method: 'POST', body: {} });
    showMsg(`已清理 ${data.removed} 条记录`, 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

/* ---------------- 工具 ---------------- */

function sourceName(id) {
  if (!state.meta) return id;
  const p = state.meta.plugins.find((x) => x.id === id);
  return p ? p.name : id;
}

function showMsg(text, kind) {
  const box = $('#enqueueMsg');
  box.textContent = text || '';
  box.className = 'msg' + (kind ? ' ' + kind : '');
}

boot();
