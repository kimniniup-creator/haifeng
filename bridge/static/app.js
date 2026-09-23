(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { token: localStorage.getItem('haifeng.bridgeToken') || '', sessionId: null, imageId: null, requestId: null, busy: false, imageUrl: null };
  const working = new Set(['queued', 'capturing', 'media_ready', 'thinking', 'answer_ready', 'responding']);
  const successful = new Set(['completed', 'completed_with_errors']);
  const setText = (node, value) => { node.textContent = value || ''; };
  const hide = (node, value) => node.classList.toggle('hidden', value);
  const auth = () => state.token ? { Authorization: `Bearer ${state.token}` } : {};
  const errorText = (error) => errorCodeText(String(error && error.message || ''));

  function errorCodeText(code) {
    if (code.includes('BRIDGE_TOKEN_NOT_CONFIGURED')) return '本机服务尚未准备好连接令牌。请在设置中填写。';
    if (code.includes('UNAUTHORIZED')) return '本机连接令牌不正确。请在设置中更新。';
    if (code.includes('IMAGE_TOO_LARGE')) return '照片超过 10 MB，请换一张小一些的图片。';
    if (code.includes('IMAGE_INVALID') || code.includes('IMAGE_FORMAT_UNSUPPORTED')) return '请使用可打开的 JPG 或 PNG 照片。';
    if (code.includes('LUMA_NOT_CONFIGURED')) return '眼镜连接还未配置。你可以先上传照片。';
    if (code.includes('LUMA_CAPTURE_FAILED')) return '眼镜没有拍到照片。请确认眼镜已连接后再试。';
    if (code.includes('LUMA_CAPTURE_TIMEOUT')) return '等待眼镜照片超时。照片没有被保存。';
    if (code.includes('MODEL_NOT_CONFIGURED')) return '还没有配置支持图片的模型。照片已经保留，可以先去设置完成配置。';
    if (code.includes('MODEL_') || code.includes('VISION_')) return '模型这次没有完成回应。你的文字没有被清空，可以稍后重试。';
    if (code.includes('CANCELLED') || code.includes('INTERRUPTED')) return '这次操作已停止。';
    if (code.includes('SESSION_NOT_FOUND')) return '这个片段已不存在，请新建一个片段。';
    if (code.includes('IMAGE_NOT_FOUND')) return '这张照片已不可用，请重新选择。';
    if (code.includes('Failed to fetch')) return '无法连接本机海风服务。请确认服务正在运行。';
    return '这次没有完成。你的内容还在，可以稍后再试。';
  }

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { ...auth(), ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.error_code || `HTTP_${response.status}`);
    return body;
  }

  function setBusy(value, message = '') {
    state.busy = value;
    ['send', 'capture', 'new-session', 'clear-image', 'photo-input', 'rename-open', 'delete-open', 'settings-open'].forEach((id) => { $(id).disabled = value; });
    document.querySelectorAll('.session-item').forEach((button) => { button.disabled = value; });
    document.querySelector('.photo-actions').classList.toggle('is-disabled', value);
    hide($('stop'), !value);
    setText($('request-state'), message);
  }

  function setImage(imageId, description = '') {
    state.imageId = imageId || null;
    hide($('photo-preview'), !imageId); hide($('photo-empty'), Boolean(imageId)); hide($('clear-image'), !imageId); hide($('reuse-note'), !imageId);
    $('photo-stage').classList.toggle('empty-stage', !imageId);
    setText($('image-caption'), imageId ? '这一张，正在被好好留下。' : '今天，有什么想留下？');
    setText($('image-meta'), description);
  }

  async function showImage(imageId) {
    const response = await fetch(`/v1/images/${encodeURIComponent(imageId)}?session_id=${encodeURIComponent(state.sessionId || '')}`, { headers: auth() });
    if (!response.ok) throw new Error('IMAGE_NOT_FOUND');
    const blob = await response.blob();
    if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
    state.imageUrl = URL.createObjectURL(blob);
    $('photo-preview').src = state.imageUrl;
  }

  function appendMessage(role, content) {
    if (!content) return null;
    const item = document.createElement('article'); const label = document.createElement('span'); const body = document.createElement('div');
    item.className = `message ${role}`; label.className = 'message-label'; label.textContent = role === 'user' ? '你' : '海风'; body.textContent = content;
    item.append(label, body); $('message-list').append(item); item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return item;
  }

  function sessionTitle(session) { return session.name || session.title || '没有名字的片段'; }
  function renderSessions(sessions) {
    const list = $('session-list'); list.replaceChildren();
    if (!sessions || !sessions.length) { const empty = document.createElement('p'); empty.className = 'empty-list'; empty.textContent = '还没有留下的片段。'; list.append(empty); return; }
    sessions.forEach((session) => {
      const button = document.createElement('button'); const name = document.createElement('span'); const date = document.createElement('span');
      button.type = 'button'; button.className = 'session-item'; button.disabled = state.busy; button.setAttribute('aria-current', session.session_id === state.sessionId ? 'page' : 'false');
      name.className = 'session-item-title'; name.textContent = sessionTitle(session); date.className = 'session-item-time';
      date.textContent = session.last_activity_at || session.created_at ? new Date(session.last_activity_at || session.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : '';
      button.append(name, date); button.addEventListener('click', () => openSession(session.session_id)); list.append(button);
    });
  }
  async function loadSessions() { ['rename-open', 'delete-open'].forEach(id => { $(id).disabled = !state.sessionId || state.busy; }); try { const data = await api('/v1/sessions'); renderSessions(data.sessions || data); } catch (_) { renderSessions([]); } }

  function sourceTime(image) {
    const source = image.source === 'manual_upload' ? '本地照片' : '眼镜';
    return `${source} · ${image.captured_at ? new Date(image.captured_at).toLocaleString('zh-CN') : '刚刚'}`;
  }
  async function openSession(id) {
    if (!id || state.busy) return;
    try {
      const data = await api(`/v1/sessions/${encodeURIComponent(id)}`); state.sessionId = data.session_id || id; state.requestId = null; $('message-list').replaceChildren();
      (data.messages || []).forEach((entry) => appendMessage(entry.role === 'assistant' ? 'assistant' : 'user', entry.text));
      const image = data.current_image || data.image || (data.images || []).at(-1);
      if (image && image.image_id) { setImage(image.image_id, sourceTime(image)); await showImage(image.image_id); } else setImage(null);
      $('session-name').value = data.name || ''; await loadSessions();
    } catch (error) { setText($('request-state'), errorText(error)); }
  }
  async function createSession() {
    if (state.busy) return;
    setBusy(true, '正在新建片段…');
    try { const data = await api('/v1/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); state.sessionId = data.session_id; state.requestId = null; $('message-list').replaceChildren(); setImage(null); $('message-input').value = ''; setText($('request-state'), ''); $('session-name').value = ''; await loadSessions(); $('message-input').focus(); } catch (error) { setText($('request-state'), errorText(error)); }
    finally { setBusy(false, $('request-state').textContent); }
  }

  function statusLine(data) {
    const model = data.model || {}; const robot = data.robot || {}; const modelState = model.configured ? '模型已就绪' : '模型未配置';
    const robotState = robot.connected ? 'Reachy 已连接' : 'Reachy 未连接';
    const audio = robot.audio_available === false ? '音频不可用' : robot.audio_status ? `音频：${robot.audio_status}` : '';
    return [modelState, robotState, audio].filter(Boolean).join(' · ');
  }
  async function refreshStatus() {
    try { const data = await api('/v1/status'); setText($('connection-state'), statusLine(data)); $('connection-state').className = `connection-state ${data.model && data.model.configured && data.robot && data.robot.connected ? 'ready' : ''}`; }
    catch (_) { setText($('connection-state'), '需要连接令牌'); $('connection-state').className = 'connection-state error'; }
  }
  async function bootstrap() { try { const data = await api('/v1/bootstrap'); if (data.token) { state.token = data.token; localStorage.setItem('haifeng.bridgeToken', state.token); } } catch (_) {} await refreshStatus(); await loadSessions(); }

  async function upload(file) {
    if (state.busy) return; if (!state.sessionId) await createSession(); if (!state.sessionId) return;
    setBusy(true, '正在安放这张照片…');
    try { const form = new FormData(); form.append('file', file); const data = await api(`/v1/images?session_id=${encodeURIComponent(state.sessionId)}&source=manual_upload`, { method: 'POST', body: form }); setImage(data.image_id, sourceTime(data)); await showImage(data.image_id); await loadSessions(); setText($('request-state'), '照片已保存。'); }
    catch (error) { setText($('request-state'), errorText(error)); }
    finally { setBusy(false, $('request-state').textContent); }
  }

  async function poll(requestId, onUpdate = () => {}) {
    state.requestId = requestId;
    for (let count = 0; count < 180; count += 1) {
      const result = await api(`/v1/requests/${encodeURIComponent(requestId)}`);
      onUpdate(result);
      if (result.status === 'capturing') setText($('photo-progress-text'), '眼镜正在拍下眼前这一刻…');
      if (result.status === 'thinking') setText($('request-state'), '海风正在看，也在读你的文字…');
      if (result.status === 'responding') setText($('request-state'), '文字已保存，正在送到 Reachy…');
      if (!working.has(result.status)) return result;
      await new Promise((resolve) => setTimeout(resolve, 650));
    }
    throw new Error('REQUEST_TIMEOUT');
  }
  function robotResult(result) {
    const robot = result.robot || result; const statuses = [];
    if (robot.motion_status) statuses.push(robot.motion_status === 'completed' ? '动作已完成' : 'Reachy 动作未完成，请检查独立电源');
    if (robot.audio_status) statuses.push(robot.audio_status === 'played_unverified' ? '已送到 Reachy 音频设备，现场声音待确认' : robot.audio_status === 'completed' ? '已请求 Reachy 播报' : (robot.audio_status === 'disabled' ? '本次未启用播报' : 'Reachy 播报未完成'));
    if (robot.audio_verified === false && robot.audio_status !== 'played_unverified') statuses.push('现场声音待确认');
    return statuses.length ? `已保存。${statuses.join('；')}。` : '已保存。';
  }
  function requireSuccess(result) { if (!successful.has(result.status)) throw new Error(result.error_code || result.status || 'REQUEST_FAILED'); }
  async function capture() {
    if (state.busy) return; if (!state.sessionId) await createSession(); if (!state.sessionId) return;
    setBusy(true, '正在连接眼镜…'); hide($('photo-progress'), false);
    try { const queued = await api('/v1/glasses/captures', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: state.sessionId, client_request_id: `capture_${Date.now()}` }) }); const result = await poll(queued.request_id); requireSuccess(result); if (!result.image_id) throw new Error(result.error_code || 'LUMA_CAPTURE_FAILED'); setImage(result.image_id, '眼镜 · 刚刚'); await showImage(result.image_id); setText($('request-state'), '照片已保存。现在可以写给海风。'); await loadSessions(); }
    catch (error) { setText($('request-state'), errorText(error)); }
    finally { hide($('photo-progress'), true); state.requestId = null; setBusy(false, $('request-state').textContent); }
  }
  async function send(event) {
    event.preventDefault(); const input = $('message-input'); const value = input.value.trim(); if (!value || state.busy) return; if (!state.sessionId) await createSession(); if (!state.sessionId) return;
    setBusy(true, '海风正在读…'); input.value = value; let optimistic = null; let answerShown = false;
    try { const queued = await api('/v1/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: state.sessionId, client_request_id: `message_${Date.now()}`, text: value, image_id: state.imageId }) }); optimistic = appendMessage('user', value); const result = await poll(queued.request_id, (update) => { if (update.answer_text && !answerShown) { appendMessage('assistant', update.answer_text); answerShown = true; input.value = ''; } }); requireSuccess(result); input.value = ''; if (result.answer_text && !answerShown) appendMessage('assistant', result.answer_text); setText($('request-state'), robotResult(result)); await loadSessions(); }
    catch (error) { if (!answerShown) { if (optimistic) optimistic.remove(); input.value = value; } setText($('request-state'), (answerShown ? '文字已保存。' : '') + errorText(error)); }
    finally { state.requestId = null; setBusy(false, $('request-state').textContent); }
  }
  async function stop() { const id = state.requestId; if (!id) return; try { await api(`/v1/requests/${encodeURIComponent(id)}/cancel`, { method: 'POST' }); setText($('request-state'), '正在停止这次操作…'); } catch (error) { setText($('request-state'), errorText(error)); } }

  async function openSettings() { $('bridge-token').value = state.token; setText($('settings-status'), ''); try { const data = await api('/v1/settings'); const model = data.model || data; $('model-base-url').value = model.base_url || ''; $('model-name').value = model.model || model.vision_model || ''; } catch (_) {} $('settings-dialog').showModal(); }
  async function saveSettings(event) { event.preventDefault(); const token = $('bridge-token').value.trim(); if (token) { state.token = token; localStorage.setItem('haifeng.bridgeToken', token); } try { await api('/v1/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: $('model-base-url').value.trim(), api_key: $('model-api-key').value, model: $('model-name').value.trim() }) }); $('model-api-key').value = ''; $('settings-dialog').close(); await refreshStatus(); } catch (error) { setText($('settings-status'), errorText(error)); } }
  async function renameSession(event) { event.preventDefault(); if (!state.sessionId) return; const name = $('session-name').value.trim(); try { await api(`/v1/sessions/${encodeURIComponent(state.sessionId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }); $('rename-dialog').close(); await loadSessions(); } catch (error) { setText($('rename-status'), errorText(error)); } }
  async function deleteSession() { if (!state.sessionId) return; const id = state.sessionId; try { await api(`/v1/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }); $('delete-dialog').close(); state.sessionId = null; state.requestId = null; $('message-list').replaceChildren(); setImage(null); $('message-input').value = ''; setText($('request-state'), '这个片段已删除。'); await loadSessions(); } catch (error) { setText($('delete-status'), errorText(error)); } }

  $('photo-input').addEventListener('change', (event) => { const file = event.target.files[0]; if (file) upload(file); event.target.value = ''; });
  $('new-session').addEventListener('click', createSession); $('capture').addEventListener('click', capture); $('clear-image').addEventListener('click', () => { if (!state.busy) { setImage(null); setText($('request-state'), '这次将只发送文字。'); } }); $('message-form').addEventListener('submit', send); $('stop').addEventListener('click', stop);
  $('settings-open').addEventListener('click', openSettings); $('settings-close').addEventListener('click', () => $('settings-dialog').close()); $('settings-cancel').addEventListener('click', () => $('settings-dialog').close()); $('settings-form').addEventListener('submit', saveSettings);
  $('rename-open').addEventListener('click', () => { if (state.sessionId) { setText($('rename-status'), ''); $('rename-dialog').showModal(); } }); $('rename-cancel').addEventListener('click', () => $('rename-dialog').close()); $('rename-form').addEventListener('submit', renameSession);
  $('delete-open').addEventListener('click', () => { if (state.sessionId) { setText($('delete-status'), ''); $('delete-dialog').showModal(); } }); $('delete-cancel').addEventListener('click', () => $('delete-dialog').close()); $('delete-confirm').addEventListener('click', deleteSession);
  bootstrap();
})();
