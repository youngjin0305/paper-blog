'use strict';
const token = document.querySelector('meta[name="garden-token"]').content;
let toastTimer;
function toast(message, error = false) {
  const element = document.getElementById('toast');
  element.textContent = message;
  element.classList.toggle('error', error);
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 6500);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Garden-Token': token}, body: JSON.stringify(body)
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('서버 응답을 읽지 못했습니다. 서버가 실행 중인지 확인하세요.'); }
  if (!response.ok) throw new Error(result.error || '요청에 실패했습니다.');
  return result;
}
function dateLabel(value) {
  return value ? new Date(value).toLocaleString('ko-KR', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '첫 조사 대기';
}
let wasActive = false;
let settingsConfig;
async function refreshStatus() {
  try {
    const status = await api('/api/status');
    document.querySelectorAll('[data-research]').forEach(button => { button.disabled = status.active; });
    const label = document.getElementById('status-text');
    if (label) {
      label.textContent = status.active ? '논문을 조사하고 있어요' : status.schedule_enabled ? '자동 조사 활성화' : '수동 조사 모드';
      document.getElementById('status-dot').classList.toggle('muted', !status.active && !status.schedule_enabled);
      document.getElementById('status-detail').textContent = status.active ? '완료된 논문부터 순서대로 저장됩니다.' : status.runs.length ? status.runs[0].message : 'Google 로그인 후 첫 조사를 시작해 보세요.';
    }
    if (wasActive && !status.active && !document.getElementById('settings-form')) location.reload();
    wasActive = status.active;
    const history = document.getElementById('run-history');
    if (history) {
      history.replaceChildren();
      if (!status.runs.length) history.textContent = '아직 실행 기록이 없습니다. 로그인 후 첫 조사를 시작해 보세요.';
      const labels = {running: '조사 중', success: '완료', failed: '실패', partial: '일부 완료', interrupted: '중단'};
      for (const run of status.runs) {
        const row = document.createElement('div'); row.className = 'run-row';
        const badge = document.createElement('span'); badge.className = 'run-state ' + run.status; badge.textContent = labels[run.status] || run.status;
        const info = document.createElement('div');
        const title = document.createElement('strong'); title.textContent = (settingsConfig?.topics.find(t => t.id === run.topic_id)?.name || run.topic_id) + ' · ' + dateLabel(run.started);
        const message = document.createElement('p'); message.textContent = run.message || '논문을 찾고 요약하는 중입니다…';
        info.append(title, message); row.append(badge, info); history.append(row);
      }
      const summary = document.getElementById('schedule-summary');
      summary.textContent = status.schedule_enabled ? '다음 조사: ' + (settingsConfig?.topics || []).filter(t => t.enabled).map(t => t.name + ' ' + dateLabel(status.next_due[t.id])).join(' / ') : '자동 조사가 꺼져 있습니다. 수동 조사는 언제든 실행할 수 있습니다.';
    }
  } catch (error) {
    const label = document.getElementById('status-text');
    if (label) label.textContent = '서버 연결 확인 필요';
  }
}
document.querySelectorAll('[data-research]').forEach(button => button.addEventListener('click', async () => {
  button.disabled = true;
  try { const result = await api('/api/research', {topic_id: button.dataset.research || null}); toast(result.message); wasActive = true; }
  catch (error) { toast(error.message, true); }
  finally { await refreshStatus(); }
}));
document.getElementById('demo-button')?.addEventListener('click', async () => {
  try { await api('/api/demo', {}); location.reload(); } catch (error) { toast(error.message, true); }
});
document.getElementById('export-button')?.addEventListener('click', async event => {
  event.target.disabled = true;
  try { toast((await api('/api/export', {})).message); } catch (error) { toast(error.message, true); }
  finally { event.target.disabled = false; }
});
function addTopic(topic) {
  const editor = document.getElementById('topic-template').content.firstElementChild.cloneNode(true);
  for (const input of editor.querySelectorAll('[data-field]')) {
    if (input.type === 'checkbox') input.checked = topic[input.dataset.field];
    else input.value = topic[input.dataset.field] ?? '';
  }
  editor.querySelector('.remove-topic').addEventListener('click', () => {
    editor.remove(); renumber();
    toast('저장하면 분야가 목록에서 제거됩니다. 기존 Markdown과 글은 보존됩니다.');
  });
  document.getElementById('topic-editors').append(editor);
  renumber();
}
function renumber() {
  document.querySelectorAll('.topic-number').forEach((element, index) => { element.textContent = 'FIELD ' + String(index + 1).padStart(2, '0'); });
}
const form = document.getElementById('settings-form');
if (form) {
  const save = document.getElementById('save-button'); save.disabled = true;
  api('/api/config').then(config => {
    settingsConfig = config;
    document.getElementById('blog-title').value = config.title;
    document.getElementById('model').value = config.model;
    document.getElementById('schedule-enabled').checked = config.schedule_enabled;
    config.topics.forEach(addTopic); save.disabled = false; refreshStatus();
  }).catch(error => toast(error.message, true));
  document.getElementById('add-topic').addEventListener('click', () => addTopic({enabled:true, interval_hours:24, lookback_days:7, max_papers:5}));
  form.addEventListener('submit', async event => {
    event.preventDefault(); save.disabled = true;
    const topics = [...document.querySelectorAll('.topic-editor')].map(editor => Object.fromEntries([...editor.querySelectorAll('[data-field]')].map(input => [input.dataset.field, input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value])));
    try {
      await api('/api/config', {title:document.getElementById('blog-title').value, model:document.getElementById('model').value,
        schedule_enabled:document.getElementById('schedule-enabled').checked, topics});
      location.reload();
    } catch (error) { toast(error.message, true); save.disabled = false; }
  });
}
refreshStatus();
setInterval(refreshStatus, 5000);
