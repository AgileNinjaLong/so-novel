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
  mode: 'search',
  searching: false,
  timer: null,
};

/* ---------------- 请求封装 ---------------- */

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
  box.appendChild(el('div', '', `${p.name} · ${p.upstream}`));
  box.appendChild(el('div', p.ready ? 'ok' : 'bad',
    p.ready ? '就绪 ' + (p.status_detail || '') : p.status_detail));
}

/* ---------------- 能力与模式 ---------------- */

function applyCapabilities() {
  const p = currentPlugin();
  if (!p) return;
  const caps = p.capabilities;

  $('#modeTabs').classList.toggle('hidden', !caps.search);
  if (!caps.search) state.mode = 'link';

  const fmt = $('#fmtSelect');
  fmt.innerHTML = '';
  caps.formats.forEach((f) => {
    const opt = el('option', '', f);
    opt.value = f;
    fmt.appendChild(opt);
  });

  $('#searchHint').textContent = caps.input_hint;
  $('#linkHint').textContent = caps.input_hint;

  resetSelection(true);
  $('#searchResults').innerHTML = '';
  $('#searchMeta').textContent = '';
  const remembered = localStorage.getItem(`novel.q.${state.activeSource}`);
  if (remembered && caps.search) $('#searchBox').value = remembered;
  setMode(caps.search ? 'search' : 'link');
}

function setMode(mode) {
  const p = currentPlugin();
  if (mode === 'search' && !(p && p.capabilities.search)) mode = 'link';
  state.mode = mode;
  $('#searchPane').classList.toggle('hidden', mode !== 'search');
  $('#linkPane').classList.toggle('hidden', mode !== 'link');
  $('#modeTabs').querySelectorAll('.tab').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
}

/* ---------------- 事件 ---------------- */

function bindEvents() {
  $('#switchBtn').addEventListener('click', () => askSwitch());
  $('#sourceSelect').addEventListener('change', () => askSwitch());

  $('#modeTabs').addEventListener('click', (e) => {
    const btn = e.target.closest('.tab');
    if (btn) setMode(btn.dataset.mode);
  });

  $('#searchBtn').addEventListener('click', doSearch);
  $('#searchBox').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
  $('#searchBox').addEventListener('input', () => {
    const has = $('#searchBox').value.trim().length > 0;
    $('#clearSearch').classList.toggle('hidden', !has);
  });
  $('#clearSearch').addEventListener('click', () => {
    $('#searchBox').value = '';
    $('#clearSearch').classList.add('hidden');
    $('#searchResults').innerHTML = '';
    $('#searchMeta').textContent = '';
    resetSelection();
    $('#searchBox').focus();
  });

  $('#enqueueBtn').addEventListener('click', enqueue);
  $('#refreshBtn').addEventListener('click', refresh);
  $('#cleanupBtn').addEventListener('click', cleanup);
  $('#bulkDeleteBtn').addEventListener('click', bulkDelete);
  $('#checkAll').addEventListener('change', () => {
    const on = $('#checkAll').checked;
    document.querySelectorAll('.row-check').forEach((cb) => { cb.checked = on; });
    updateBulkBar();
  });
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

/* ---------------- 来源切换 ---------------- */

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
    showMsg(result.message + (result.canceled && result.canceled.length
      ? `（取消 ${result.canceled.length} 个排队任务）` : ''), 'ok');
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

function setSearching(flag) {
  state.searching = flag;
  const btn = $('#searchBtn');
  btn.disabled = flag;
  btn.textContent = flag ? '搜索中…' : '搜索';
}

async function doSearch() {
  const typed = $('#searchBox').value.trim();
  if (!typed) { showSearchMeta('请输入书名', 'bad'); return; }
  if (/^https?:\/\//i.test(typed)) {
    setMode('link');
    $('#urlBox').value = typed;
    showMsg('已识别为链接，直接在下方选择格式后加入队列', 'ok');
    return;
  }
  const p = currentPlugin();
  if (!p || !p.capabilities.search) {
    setMode('link');
    $('#urlBox').value = typed;
    return;
  }

  localStorage.setItem(`novel.q.${state.activeSource}`, typed);
  setSearching(true);
  $('#searchResults').innerHTML = '';
  showSearchMeta(`正在搜索「${typed}」…`);
  $('#clearSearch').classList.remove('hidden');
  try {
    const data = await api(`/api/search?q=${encodeURIComponent(typed)}`);
    renderResults(data.items || [], typed);
  } catch (err) {
    showSearchMeta(`搜索失败：${err.message}`, 'bad');
  } finally {
    setSearching(false);
  }
}

function showSearchMeta(text, kind) {
  const box = $('#searchMeta');
  box.textContent = text || '';
  box.className = 'search-meta' + (kind ? ' ' + kind : '');
}

function renderResults(items, query) {
  const box = $('#searchResults');
  box.innerHTML = '';
  resetSelection();
  if (!items.length) {
    showSearchMeta(`没有找到「${query}」相关结果，试试其它关键词或直接粘贴详情页链接`);
    return;
  }
  showSearchMeta(`找到 ${items.length} 个结果 · 点击「选择」后可加入下载队列`);
  items.forEach((item) => {
    const card = el('div', 'result-item');

    const main = el('div', 'result-main');
    main.appendChild(el('div', 'result-title', item.title || '（无标题）'));

    const sub = el('div', 'result-sub');
    if (item.author) sub.appendChild(el('span', 'result-author', item.author));
    const extraSource = item.extra && item.extra.source;
    if (extraSource) sub.appendChild(el('span', 'badge', String(extraSource)));
    if (!extraSource && item.extra && item.extra.book_id) {
      sub.appendChild(el('span', 'badge', 'ID ' + item.extra.book_id));
    }
    if (sub.childNodes.length) main.appendChild(sub);

    const extraBits = [];
    if (item.extra && item.extra.latest_chapter) extraBits.push('最新：' + item.extra.latest_chapter);
    if (item.extra && item.extra.updated) extraBits.push('更新：' + item.extra.updated);
    if (extraBits.length) main.appendChild(el('div', 'result-extra', extraBits.join('　')));
    card.appendChild(main);

    const pickBtn = el('button', 'btn small pick-btn', '选择');
    pickBtn.addEventListener('click', () => selectItem(item, card, pickBtn));
    card.appendChild(pickBtn);
    box.appendChild(card);
  });
}

function selectItem(item, cardEl, btn) {
  $('#searchResults').querySelectorAll('.result-item').forEach((n) => {
    n.classList.remove('selected');
    const b = n.querySelector('.pick-btn');
    if (b) b.textContent = '选择';
  });
  cardEl.classList.add('selected');
  btn.textContent = '已选择';
  state.picked = item;
  $('#pickTitle').textContent = `《${item.title}》` + (item.author ? ` · ${item.author}` : '');
  $('#titleBox').value = item.title || '';
  showMsg('已选择，确认格式后加入队列', 'ok');
}

function resetSelection(clearTitle) {
  state.picked = null;
  $('#pickTitle').textContent = '尚未选择书籍';
  if (clearTitle !== false) $('#titleBox').value = '';
}

/* ---------------- 入队 ---------------- */

async function enqueue() {
  const p = currentPlugin();
  if (!p) return;
  const fmt = $('#fmtSelect').value;
  if (!fmt) return showMsg('请选择导出格式', 'bad');
  let ref = '';
  let title = $('#titleBox').value.trim();

  if (state.mode === 'link' || !p.capabilities.search) {
    ref = $('#urlBox').value.trim();
    if (!ref) return showMsg('请粘贴书籍详情页链接', 'bad');
  } else if (state.picked) {
    ref = state.picked.book_ref;
    title = title || state.picked.title;
  } else {
    const typed = $('#searchBox').value.trim();
    if (/^\d{6,}$/.test(typed)) {
      ref = typed;
      title = title || `book ${typed}`;
    } else {
      return showMsg('请先搜索并选择一本书，或切换到「粘贴链接」模式', 'bad');
    }
  }

  $('#enqueueBtn').disabled = true;
  try {
    const data = await api('/api/tasks', {
      method: 'POST',
      body: { source: state.activeSource, title, book_ref: ref, fmt },
    });
    const pos = data.queue_position;
    showMsg(`已加入队列${pos ? `，排队第 ${pos} 位` : ''}`, 'ok');
    resetSelection();
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
  } catch (_) { /* 未登录会自动跳转 */ }
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
  $('#countBadge').textContent =
    `运行 ${snap.counts.running || 0} · 排队 ${snap.counts.queued || 0} · 待接收 ${snap.counts.ready || 0}`;

  tasks.forEach((t) => {
    const tr = document.createElement('tr');
    tr.dataset.id = t.id;

    const checkCell = el('td', 'check-cell');
    checkCell.dataset.label = '选择';
    if (t.can_delete) {
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'row-check';
      cb.value = t.id;
      cb.addEventListener('change', updateBulkBar);
      checkCell.appendChild(cb);
    }
    tr.appendChild(checkCell);
    const status = el('td', 'status-cell');
    status.dataset.label = '状态';
    status.appendChild(statusTag(t));
    tr.appendChild(status);

    const titleCell = el('td', 'title-cell');
    titleCell.dataset.label = '书名';
    titleCell.appendChild(el('div', 't', t.title));
    if (t.message) {
      const m = el('div', 'm clamp', t.message);
      m.title = t.message;
      titleCell.appendChild(m);
    }
    if (t.status === 'ready') {
      const ttl = (state.meta && state.meta.app.file_ttl_min) || 120;
      titleCell.appendChild(el('div', 'm warn-text',
        `文件已就绪，仅保留 ${ttl} 分钟；未接收将自动删除（可重新下载）`));
    }
    if (t.error && t.status === 'failed') {
      const e = el('div', 'm clamp', t.error);
      e.title = t.error;
      titleCell.appendChild(e);
    }
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
      const btn = el('button', 'btn small primary', '接收文件');
      btn.addEventListener('click', () => receiveTask(t, btn));
      actions.appendChild(btn);
    }
    if (t.can_retry) {
      const retry = el('button', 'btn small ghost', '重新下载');
      retry.addEventListener('click', () => retryTask(t.id));
      actions.appendChild(retry);
    }
    if (t.can_delete) {
      const del = el('button', 'btn small danger', '删除');
      del.addEventListener('click', () => deleteTask(t));
      actions.appendChild(del);
    }
    if (!t.can_cancel && !t.can_pause && !t.can_receive && !t.can_retry && !t.can_delete) {
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

async function receiveTask(t, btn) {
  const ttl = (state.meta && state.meta.app.file_ttl_min) || 120;
  const open = await showReceiveDialog(t, ttl);
  if (!open) return;

  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '接收中…';
  showMsg('正在接收文件，请稍候…', 'ok');
  try {
    const resp = await fetch(`/api/tasks/${t.id}/download`, { credentials: 'same-origin' });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { detail = (await resp.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const blob = await resp.blob();
    if (!blob.size) throw new Error('收到的文件为空');
    const filename = filenameFromDisposition(resp.headers.get('content-disposition'))
      || `${t.title || 'book'}.${t.fmt || 'txt'}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);

    await api(`/api/tasks/${t.id}/ack`, { method: 'POST' });
    showMsg(`已接收「${filename}」，服务器临时文件已删除`, 'ok');
  } catch (err) {
    showMsg(
      `未接收成功：${err.message}。文件仍保留在服务器，可在 ${ttl} 分钟内重试；超时后自动删除，需要重新下载。`,
      'bad'
    );
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
    await refresh();
  }
}

function showReceiveDialog(t, ttl) {
  return new Promise((resolve) => {
    const modal = $('#receiveModal');
    $('#receiveText').textContent =
      `即将接收《${t.title}》（${fmtSize(t.size_bytes)}）。\n\n` +
      `· 文件会下载到你本机；完整接收成功后，服务器才会删除该文件。\n` +
      `· 若取消或中断，文件仍会保留 ${ttl} 分钟供你重试。\n` +
      `· 超过 ${ttl} 分钟仍未接收，服务器会自动删除，届时只能「重新下载」。`;
    modal.classList.remove('hidden');

    const cleanup = (value) => {
      modal.classList.add('hidden');
      $('#receiveOk').removeEventListener('click', onOk);
      $('#receiveCancel').removeEventListener('click', onCancel);
      resolve(value);
    };
    const onOk = () => cleanup(true);
    const onCancel = () => cleanup(false);
    $('#receiveOk').addEventListener('click', onOk);
    $('#receiveCancel').addEventListener('click', onCancel);
  });
}

function fmtSize(bytes) {
  const n = Number(bytes || 0);
  if (!n) return '大小未知';
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(2)} MB`;
}

function filenameFromDisposition(header) {
  if (!header) return '';
  const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8) {
    try { return decodeURIComponent(utf8[1]); } catch (_) { /* ignore */ }
  }
  const plain = header.match(/filename="([^"]*)"/i);
  return plain ? plain[1] : '';
}

async function deleteTask(t) {
  const note = t.status === 'ready'
    ? '该任务的文件还在服务器待接收，删除会一并丢弃。'
    : '';
  if (!confirm(`删除「${t.title}」的下载记录？\n${note}`)) return;
  try {
    const data = await api(`/api/tasks/${t.id}`, { method: 'DELETE' });
    if (data && data.pending) showMsg('正在取消，请稍后再点一次删除', 'bad');
    else showMsg('已删除记录', 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

function selectedIds() {
  return Array.from(document.querySelectorAll('.row-check:checked')).map((cb) => cb.value);
}

function updateBulkBar() {
  const ids = selectedIds();
  const btn = $('#bulkDeleteBtn');
  btn.classList.toggle('hidden', ids.length === 0);
  $('#bulkCount').textContent = ids.length ? `（${ids.length}）` : '';
  const all = document.querySelectorAll('.row-check');
  const allChecked = all.length > 0 && ids.length === all.length;
  $('#checkAll').checked = allChecked;
}

async function bulkDelete() {
  const ids = selectedIds();
  if (!ids.length) return;
  if (!confirm(`删除选中的 ${ids.length} 条下载记录？待接收的文件会被丢弃。`)) return;
  try {
    const data = await api('/api/tasks/bulk-delete', { method: 'POST', body: { ids } });
    showMsg(`已删除 ${data.removed} 条记录${data.skipped.length ? `，${data.skipped.length} 条正在取消` : ''}`, 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function pauseTask(id) {
  if (!confirm('暂停会丢弃当前进度，之后只能「重新下载」（重新排队）。继续？')) return;
  try {
    const data = await api(`/api/tasks/${id}/pause`, { method: 'POST' });
    showMsg(data.was_running ? '正在暂停…' : '已暂停', 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function cancelTask(id) {
  try {
    await api(`/api/tasks/${id}`, { method: 'DELETE' });
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function retryTask(id) {
  try {
    const data = await api(`/api/tasks/${id}/retry`, { method: 'POST' });
    showMsg(`已重新排队${data.queue_position ? `，第 ${data.queue_position} 位` : ''}`, 'ok');
    await refresh();
  } catch (err) { showMsg(err.message, 'bad'); }
}

async function cleanup() {
  if (!confirm('删除「失败 / 已取消 / 已过期」的任务记录？已接收的下载不受影响。')) return;
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
