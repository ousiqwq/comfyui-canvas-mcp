// UI only: observing status must never edit, save or queue the current graph.
export const FRONTEND_VERSION = '0.1.1';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const seconds = value => value == null ? '—' : `${Math.floor(value / 60)} 分 ${Math.floor(value % 60)} 秒`;
const time = value => value ? new Date(value).toLocaleTimeString() : '—';
const STATES = {connecting:'连接中', connected:'已连接', disconnected:'重连中'};

export function createStatusUI({app, api, clientId, snapshot}) {
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = new URL('./status-ui.css', import.meta.url).href;
  document.head.append(style);

  const badge = element('button', 'canvas-mcp-status-link');
  badge.type = 'button';
  badge.setAttribute('aria-label', 'Canvas MCP 状态与详情');
  badge.setAttribute('aria-haspopup', 'dialog');
  const dot = element('span', 'canvas-mcp-dot', '●');
  dot.setAttribute('aria-hidden', 'true');
  const label = element('span');
  badge.append(dot, label);

  const dialog = element('dialog', 'canvas-mcp-dialog');
  dialog.setAttribute('aria-labelledby', 'canvas-mcp-dialog-title');
  const header = element('header', 'canvas-mcp-dialog-header');
  const heading = element('div');
  const title = element('h2', '', 'Canvas MCP');
  title.id = 'canvas-mcp-dialog-title';
  heading.append(title, element('p', 'canvas-mcp-muted', '实时画布插件 · 与官方 Comfy MCP 共用一个入口'));
  const close = element('button', 'canvas-mcp-icon-button', '×');
  close.type = 'button';
  close.setAttribute('aria-label', '关闭插件详情');
  close.onclick = () => dialog.close();
  header.append(heading, close);

  const body = element('div', 'canvas-mcp-dialog-body');
  const status = element('div', 'canvas-mcp-connection');
  const connectionTitle = element('strong');
  const connectionNote = element('p', 'canvas-mcp-muted');
  status.append(connectionTitle, connectionNote);
  body.append(status);

  const fields = {};
  function section(name, entries) {
    const section = element('section', 'canvas-mcp-section');
    const list = element('dl', 'canvas-mcp-fields');
    for (const [key, label] of entries) {
      const value = element('dd');
      fields[key] = value;
      list.append(element('dt', '', label), value);
    }
    section.append(element('h3', '', name), list);
    body.append(section);
  }
  section('连接与页面', [
    ['client', '本页 Client ID'], ['bridge', '桥接接口'], ['latency', '状态请求耗时'],
    ['connectedFor', '本次连接时长'], ['uptime', '桥接运行时长'], ['clients', '在线画布页面'],
    ['agent', 'Agent / MCP 客户端'],
  ]);
  section('当前画布', [
    ['workflow', '工作流'], ['graph', '当前图 ID'], ['counts', '节点 / 连线 / 分组'],
    ['view', '选中节点 / 缩放'], ['revision', '画布版本'], ['visibility', '页面状态'],
  ]);
  section('插件与官方 MCP', [
    ['version', '前端 / 桥接版本'], ['official', '官方依赖基线'], ['tools', '工具入口'],
    ['transport', '连接方式'], ['activity', '本页请求统计'], ['pending', '正在执行 / 等待'],
  ]);
  const peerSection = element('section', 'canvas-mcp-section');
  peerSection.append(element('h3', '', '已连接画布'));
  const peers = element('ul', 'canvas-mcp-peers');
  peerSection.append(peers);
  body.append(peerSection);
  const historySection = element('section', 'canvas-mcp-section');
  historySection.append(element('h3', '', '最近操作'));
  historySection.append(element('p', 'canvas-mcp-muted', '只保留本页最近 20 次请求摘要；刷新页面即清空，不记录提示词、参数或输出。'));
  const history = element('ol', 'canvas-mcp-history');
  historySection.append(history);
  body.append(historySection);
  const capabilities = element('details', 'canvas-mcp-section');
  capabilities.append(element('summary', '', '查看功能范围与状态说明'));
  capabilities.append(element('p', '', '画布：节点与连线、参数、分组、布局、子图、标签页、保存、撤销、执行、截图。扩展：模型目录、节点包、工作流分析、媒体工作流恢复、环境快照、运行服务。官方工具保留无头执行、模型下载及输出获取。'));
  capabilities.append(element('p', 'canvas-mcp-muted', '绿色状态只表示本页与 ComfyUI 桥接连通。stdio MCP 客户端是否启动，需在客户端测试连接；有最近调用也不代表客户端现在仍在线。此面板只读取状态，不修改画布。'));
  body.append(capabilities);

  const footer = element('footer', 'canvas-mcp-dialog-footer');
  const feedback = element('span', 'canvas-mcp-feedback');
  feedback.setAttribute('role', 'status');
  function button(text, action) {
    const node = element('button', 'canvas-mcp-button', text);
    node.type = 'button';
    node.onclick = action;
    return node;
  }
  const copyFallback = element('textarea', 'canvas-mcp-copy-fallback');
  copyFallback.hidden = true;
  copyFallback.readOnly = true;
  copyFallback.setAttribute('aria-label', '待复制的插件诊断信息');
  body.append(copyFallback);
  async function copy(text) {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable');
      await navigator.clipboard.writeText(text);
      feedback.textContent = '已复制';
    } catch {
      // Clipboard API is not available on most LAN HTTP pages.
      copyFallback.hidden = false;
      copyFallback.value = text;
      copyFallback.focus();
      copyFallback.select();
      const copied = document.execCommand('copy');
      feedback.textContent = copied ? '已请求复制；下方文本也可按 Ctrl+C 复制' : '已选中文本，请按 Ctrl+C 复制';
    }
  }
  const refresh = button('刷新状态', () => fetchStatus());
  footer.append(feedback, button('复制 Client ID', () => copy(clientId)),
    button('复制诊断', () => {
      const data = snapshot();
      copy(JSON.stringify({frontend:FRONTEND_VERSION, bridge:server?.version, client_id:clientId,
        connection:data.state, status_error:statusError || null, stats:data.stats,
        canvas:data.canvas, online_canvases:server?.clients?.length ?? null}, null, 2));
    }), refresh);
  dialog.append(header, body, footer);
  document.body.append(badge, dialog);

  let server = null, latency = null, statusError = '', lastFetch = 0, polling = false;
  let layoutSignature = '', historySignature = '', peersSignature = '';
  const set = (key, value) => {
    const text = value == null || value === '' ? '—' : String(value);
    if (fields[key].textContent !== text) fields[key].textContent = text;
  };

  function position() {
    const canvas = app.canvas;
    const rect = canvas.canvas.getBoundingClientRect();
    const pos = canvas.fpsInfoLocation ?? canvas.viewport;
    const lines = (canvas.graph ? 5 : 1) + (canvas.info_text ? 1 : 0);
    const sidebar = document.querySelector('.side-toolbar-container')?.getBoundingClientRect();
    let left = rect.left + (pos?.[0] || 10) + 5;
    if (sidebar?.width && sidebar.left <= left && sidebar.right > left) left = sidebar.right + 5;
    const top = canvas.show_info
      ? rect.top + (pos?.[1] || rect.height - (lines + 1) * 13) - 10
      : rect.bottom - 25;
    const signature = `${left}:${top}:${rect.width}:${rect.height}`;
    if (signature !== layoutSignature) {
      badge.style.left = `${Math.max(4, Math.min(left, innerWidth - 110))}px`;
      badge.style.top = `${Math.max(rect.top + 4, top)}px`;
      badge.hidden = rect.width === 0 || rect.height === 0;
      layoutSignature = signature;
    }
  }

  function render() {
    position();
    const data = snapshot(dialog.open);
    badge.dataset.state = data.state;
    label.textContent = `MCP: ${STATES[data.state]}`;
    badge.title = `Canvas MCP · ${STATES[data.state]}\n点击查看连接、画布与插件详情`;
    if (!dialog.open) return;
    connectionTitle.textContent = `浏览器桥接${STATES[data.state]}`;
    status.dataset.state = data.state;
    connectionNote.textContent = statusError
      ? `状态接口暂不可用：${statusError}`
      : data.state === 'connected' ? '本页可接收实时画布命令。关闭面板不影响连接。' : '等待桥接连接，断开后每 2 秒自动重连。';
    const local = data.canvas;
    set('client', clientId);
    set('bridge', api.apiURL('/canvas-mcp/status'));
    set('latency', latency == null ? '尚未读取' : `${latency} ms（HTTP 往返）`);
    set('connectedFor', data.connectedAt ? seconds((Date.now() - data.connectedAt) / 1000) : '—');
    set('uptime', seconds(server?.uptime_seconds));
    set('clients', server ? `${server.clients.length} 个${server.clients.length > 1 ? ' · Agent 需绑定目标 Client ID' : ''}${statusError ? '（上次结果）' : ''}` : '尚未读取');
    set('agent', data.stats.completed ? `最近调用 ${time(data.stats.lastRequestAt)}；当前在线状态需客户端确认` : '尚无本页调用；请在 MCP 客户端测试连接');
    set('workflow', local?.workflow);
    set('graph', local?.graph_id);
    set('counts', local ? `${local.node_count} / ${local.link_count} / ${local.group_count}` : '—');
    set('view', local ? `${local.selected_count} / ${Math.round(local.zoom * 100)}%` : '—');
    set('revision', local?.revision);
    set('visibility', document.hidden ? '后台页面' : '前台页面');
    set('version', `${FRONTEND_VERSION} / ${server?.version ?? '尚未读取'}`);
    set('official', 'comfy-mcp 0.10.0（固定依赖版本，非运行时探测）');
    set('tools', '39 个官方 + 15 个扩展；实际数量以客户端 tools/list 为准');
    set('transport', '客户端 stdio → 官方 MCP + 画布工具 → ComfyUI WebSocket → 本页');
    set('activity', `已处理 ${data.stats.completed} · 失败 ${data.stats.failed} · 缓存命中 ${data.stats.cached} · 断线 ${data.stats.disconnects}`);
    set('pending', `${data.active || '空闲'} / 本页排队 ${data.queued} · 桥接待响应 ${server?.pending_requests ?? '—'}`);

    const peerKey = JSON.stringify(server?.clients);
    if (peerKey !== peersSignature) {
      peers.replaceChildren();
      for (const peer of server?.clients ?? []) {
        const row = element('li');
        row.append(element('strong', '', peer.client_id === clientId ? '本页' : '其他页面'),
          element('span', '', `${peer.workflow || '未命名'} · ${peer.node_count ?? '—'} 个节点`),
          element('code', '', peer.client_id));
        peers.append(row);
      }
      if (!peers.childElementCount) peers.append(element('li', 'canvas-mcp-muted', '尚无在线画布信息'));
      peersSignature = peerKey;
    }
    const historyKey = JSON.stringify(data.recent);
    if (historyKey !== historySignature) {
      history.replaceChildren();
      for (const request of [...data.recent].reverse()) {
        const row = element('li');
        row.append(element('time', 'canvas-mcp-muted', time(request.at)),
          element('code', '', request.action),
          element('span', request.ok ? 'canvas-mcp-ok' : 'canvas-mcp-error', request.cached ? '缓存' : request.ok ? '成功' : '失败'),
          element('span', 'canvas-mcp-muted', `${request.duration} ms`));
        if (request.error) row.append(element('p', 'canvas-mcp-request-error', request.error));
        history.append(row);
      }
      if (!history.childElementCount) history.append(element('li', 'canvas-mcp-muted', '本页尚未收到画布请求'));
      historySignature = historyKey;
    }
  }

  async function fetchStatus() {
    if (polling) return;
    polling = true;
    refresh.disabled = true;
    const started = performance.now();
    try {
      const response = await fetch(api.apiURL('/canvas-mcp/status'), {cache:'no-store', signal:AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      server = await response.json();
      latency = Math.round(performance.now() - started);
      statusError = '';
    } catch (error) {
      statusError = error.message;
    } finally {
      lastFetch = Date.now();
      polling = false;
      refresh.disabled = false;
      render();
    }
  }

  badge.onclick = () => { dialog.showModal(); badge.setAttribute('aria-expanded', 'true'); render(); fetchStatus(); };
  dialog.addEventListener('close', () => { badge.setAttribute('aria-expanded', 'false'); badge.focus(); });
  dialog.addEventListener('keydown', event => event.stopPropagation());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  window.addEventListener('resize', position);
  setInterval(() => {
    render();
    if (dialog.open && !document.hidden && Date.now() - lastFetch >= 5000) fetchStatus();
  }, 1000);
  render();
  return {update:render};
}
