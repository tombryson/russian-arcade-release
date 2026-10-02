/* Durable preparation: resume saved progress, never repeat an uncertain call. */
(() => {
  for (const root of document.querySelectorAll('[data-situation-preparation]')) {
    if (root.dataset.initialized) continue;
    root.dataset.initialized = 'true';
    let state = JSON.parse(root.querySelector('[data-situation-state]').textContent), busy = false, stopped = false;
    const t = (en, ru) => root.dataset.language === 'ru' ? ru : en;
    const url = path => window.arcadeUrl ? window.arcadeUrl(path) : path;
    const status = root.querySelector('[data-situation-status]'), spinner = root.querySelector('[data-situation-spinner]'), retry = root.querySelector('[data-situation-retry]');
    const base = '/api/v1/curriculum/situations/' + state.id;
    const headers = {'Content-Type':'application/json', 'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content || ''};
    for (const [meta, header] of [['learning-profile','X-Profile-ID'],['learning-account','X-Account-Scope']]) {
      const value = document.querySelector(`meta[name="${meta}"]`)?.content;
      if (value !== undefined) headers[header] = value;
    }
    function render() {
      const failed = state.state === 'failed';
      root.setAttribute('aria-busy', String(!failed));
      spinner.hidden = failed; retry.hidden = !failed || !state.retryable;
      status.textContent = failed ? state.error === 'allowance_unavailable'
        ? t('The AI allowance is unavailable. Your saved work is kept. You can return to the lesson.', 'Лимит ИИ недоступен. Задание сохранено. Можно вернуться к уроку.')
        : state.stage === 'audio' ? t('The recording could not be prepared. Try again with the same activity.', 'Запись не удалось подготовить. Повторите попытку с тем же заданием.')
        : t('Preparation stopped. Your progress is saved.', 'Подготовка остановилась. Прогресс сохранён.')
        : state.stage === 'audio' ? t('Recording your message…', 'Записываем сообщение…')
        : state.stage === 'publish' ? t('Getting your practice ready…', 'Открываем задание…')
        : t('Preparing a new situation…', 'Готовим новое задание…');
    }
    async function request(method, explicitRetry=false) {
      if (busy || stopped) return;
      busy = true; retry.disabled = true;
      if (explicitRetry) { state = {...state,state:'running',error:null}; render(); }
      try {
        const response = await fetch(url(base + (method === 'POST' ? '/prepare' : '')), {
          method, headers, credentials:'same-origin', cache:'no-store',
          ...(method === 'POST' ? {body:JSON.stringify({retry:explicitRetry})} : {})
        });
        const value = await response.json();
        if (stopped) return;
        if (!response.ok) {
          stopped = true; spinner.hidden = true; retry.hidden = true; root.setAttribute('aria-busy','false');
          status.textContent = value.error?.message || t('Reopen the lesson to continue.', 'Откройте урок заново.');
          return;
        }
        state = value; render();
        if (state.state === 'ready') { stopped = true; window.location.replace(url(state.url)); return; }
      } catch (_) {
        if (stopped) return;
        // The server may still be preparing. Read its status before allowing
        // another paid operation, rather than retrying this POST.
        state = {...state,state:'running'};
        status.textContent = t('Reconnecting to your saved activity…','Подключаемся к сохранённому заданию…');
      } finally { busy = false; retry.disabled = false; }
      if (!stopped && state.state !== 'failed') window.setTimeout(() => void request(state.state === 'pending' ? 'POST' : 'GET'), state.state === 'pending' ? 0 : 2000);
    }
    retry.addEventListener('click', () => void request('POST',true));
    window.addEventListener('pagehide', () => {stopped=true;}, {once:true});
    render();
    if (state.state !== 'failed') void request(state.state === 'pending' ? 'POST' : 'GET');
  }
})();
