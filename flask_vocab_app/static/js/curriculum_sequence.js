/* Owned lesson navigation. Opening this page never allocates a task. */
(() => {
  const key = Symbol.for('russian-arcade.curriculum-sequence');
  if (document[key]) { document[key](); return; }
  const appUrl = value => window.arcadeUrl ? window.arcadeUrl(value) : value;
  function init() {
    for (const player of document.querySelectorAll('[data-teaching-audio]')) {
      if (player.dataset.initialized) continue;
      player.dataset.initialized = 'true';
      const status = player.parentElement.querySelector('[data-teaching-audio-error]');
      player.addEventListener('play', () => {
        for (const other of document.querySelectorAll('[data-teaching-audio]')) if (other !== player) other.pause();
      });
      player.addEventListener('error', () => {if (status) status.hidden = false;});
      player.addEventListener('loadeddata', () => {if (status) status.hidden = true;});
      player.closest('details')?.addEventListener('toggle', event => {if (!event.currentTarget.open) player.pause();});
    }
    for (const root of document.querySelectorAll('[data-curriculum-sequence]')) {
      if (root.dataset.initialized) continue;
      root.dataset.initialized = 'true';
      const definition = JSON.parse(root.querySelector('[data-sequence-data]').textContent);
      const t = (en, ru) => root.dataset.language === 'ru' ? ru : en;
      const title = value => (root.dataset.language === 'ru' ? value.label_ru : value.label) || value.label || value.id;
      const list = root.querySelector('[data-sequence-steps]');
      const action = root.querySelector('[data-sequence-continue]');
      const status = root.querySelector('[data-sequence-status]');
      const errors = root.querySelector('[data-sequence-error]');
      const repeat = root.querySelector('[data-sequence-repeat]');
      const results = root.querySelector('[data-sequence-results]');
      const resultsBody = root.querySelector('[data-sequence-results-body]');
      let summaryLoaded=false,summaryBusy=false;
      let run = definition.run || null, busy = false, pending = null, blocked = false;
      const stateCopy = {not_started:t('Not started','Не начато'),draft:t('In progress','В работе'),submitted:t('Reply saved','Ответ сохранён'),reviewing:t('Feedback pending','Ожидается отзыв'),reviewed:t('Reviewed','Проверено'),review_unavailable:t('Feedback unavailable','Отзыв недоступен')};
      const unavailableCopy = {audio_unavailable:t('Audio unavailable','Аудио недоступно'),provider_unavailable:t('Service unavailable','Сервис недоступен'),unsupported_workspace:t('Unavailable in this workspace','Недоступно в этой рабочей области'),account_required:t('Choose a profile to continue','Выберите профиль'),budget_exhausted:t('AI allowance used','Лимит ИИ исчерпан')};
      const node = (tag, text) => { const element = document.createElement(tag); element.textContent = text; return element; };
      function render() {
        list.replaceChildren();
        for (const step of run?.steps || definition.steps) {
          const row = node('li', ''); row.dataset.stepId = step.id; row.id = `sequence-step-${step.id}`;
          row.append(node('strong', title(step)), node('span', (root.dataset.language === 'ru' ? step.reason_ru : step.reason) || step.reason || unavailableCopy[step.availability] || stateCopy[step.work_state] || ''));
          if (root.dataset.profileId && step.availability === 'available') {
            const open = node('button', step.id === 'transfer' && step.repeated ? t('Revisit the situation','Вернуться к ситуации') : step.work_state === 'reviewed' ? t('Revisit','Посмотреть') : step.id === 'transfer' ? t('Try a new situation','Попробовать новую ситуацию') : t('Open','Открыть'));
            open.type = 'button'; open.disabled = busy || blocked || !!pending;
            open.addEventListener('click', () => void openStep(step.id)); row.append(open);
          }
          list.append(row);
        }
        if (action) {
          action.disabled = busy || blocked || !!pending || !!run && !run.next_action && !run.completed;
          action.textContent = busy ? t('Opening…','Открываем…') : run?.completed ? definition.next_unit ? `${t('Next: ','Далее: ')}${root.dataset.language==='ru'?definition.next_unit.title_ru:definition.next_unit.title} →` : t('Practise again','Повторить урок') : run?.next_action ? `${t('Continue: ','Продолжить: ')}${title(run.next_action)} →` : t('Start lesson →','Начать урок →');
        }
        if(repeat){repeat.hidden=!run?.completed||!definition.next_unit;repeat.disabled=busy||blocked||!!pending;}
        if(results)results.hidden=!run?.completed;
        if (run?.completed) status.textContent = t('Lesson finished. Your responses and feedback are saved.','Урок завершён. Ваши ответы и отзывы сохранены.');
      }
      async function showSummary(){
        if(!resultsBody||!results?.open||!run?.completed||summaryLoaded||summaryBusy)return;
        summaryBusy=true;resultsBody.replaceChildren(node('p',t('Loading saved results…','Загружаем сохранённые результаты…')));
        try{
          const summary=await request('/api/v1/curriculum/summary');
          const rows=node('dl','');
          for(const domain of summary.domains||[]){
            const row=node('div','');row.append(node('dt',root.dataset.language==='ru'?domain.label_ru:domain.label));
            const value=node('dd',''),latest=domain.latest;
            value.append(node('span',!latest?t('Not assessed','Пока не проверено'):latest.outcome==='demonstrated_in_task'?t('Demonstrated in this task','Получилось в этом задании'):latest.outcome==='more_evidence_needed'?t('More evidence needed','Нужно больше примеров'):t('More practice needed','Есть что потренировать')));
            if(latest){value.append(node('small',`${latest.level} · ${(root.dataset.language==='ru'?latest.scope_label_ru:latest.scope_label)||t('This task','Это задание')} · ${latest.date}${latest.support?.length||latest.condition==='assisted'?t(' · With help',' · С помощью'):''}`));if(latest.condition==='unverified')value.append(node('small',t('Independent conditions were not checked.','Самостоятельность выполнения не проверялась.')));}
            if(domain.pending)value.append(node('small',domain.pending.state==='review_unavailable'?t('Reply saved; feedback is unavailable.','Ответ сохранён; отзыв пока недоступен.'):t('Reply saved; feedback pending.','Ответ сохранён; ожидается отзыв.')));
            row.append(value);rows.append(row);
          }
          resultsBody.replaceChildren(rows);summaryLoaded=true;
        }catch(error){const retry=node('button',t('Retry results','Повторить загрузку'));retry.type='button';retry.className='sentence-text-button';retry.addEventListener('click',()=>void showSummary());resultsBody.replaceChildren(node('p',error.message),retry);}
        finally{summaryBusy=false;}
      }
      async function request(url, body) {
        const meta = name => document.querySelector(`meta[name="${name}"]`)?.content;
        const profile = meta('learning-profile'), scope = meta('learning-account');
        const response = await fetch(appUrl(url), {method:body ? 'POST' : 'GET', credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json', ...(profile ? {'X-Profile-ID':profile} : {}), ...(scope ? {'X-Account-Scope':scope} : {}), ...(body ? {'Content-Type':'application/json','X-CSRF-Token':meta('csrf-token') || ''} : {})}, ...(body ? {body:JSON.stringify(body)} : {})});
        const result = await response.json();
        if (!response.ok) {const error = new Error(result.error?.message || t('The lesson could not open. Try again.','Не удалось открыть урок. Попробуйте ещё раз.')); error.code = result.error?.code; throw error;}
        return result;
      }
      function accept(value) {
        run = value; render();
        const url = new URL(window.location.href); url.searchParams.set('run', run.id);
        window.history.replaceState(window.history.state, '', url);
      }
      async function mutate(command) {
        pending = command;
        const result = await request(command.url, command.body);
        pending = null;
        return result;
      }
      function showError(error) {
        errors.hidden = false; errors.replaceChildren(node('span', error.message));
        if (['profile_changed','account_changed','access_required','csrf_failed','locked'].includes(error.code)) {blocked = true; pending = null;}
        if (['stale_revision','not_found'].includes(error.code)) pending = null;
        if (!blocked) {
          const retry = node('button', pending ? t('Try again','Повторить') : t('Reload saved lesson','Загрузить сохранённый урок')); retry.type = 'button';retry.className = 'btn btn-outline-primary';
          retry.addEventListener('click', () => pending ? void perform(pending.step, true) : void reload()); errors.append(retry);
        }
      }
      async function ensureRun(repeat = false, requestedStep = null) {
        if (run && !repeat) return;
        const result = await mutate({url:`/api/v1/curriculum/units/${encodeURIComponent(definition.unit_id)}/runs`, body:{submission_id:crypto.randomUUID(),sequence_id:definition.id}, step:requestedStep});
        accept(result);
      }
      async function perform(stepId, retry = false) {
        if (busy || blocked) return;
        const requestedStep = stepId;
        busy = true; errors.hidden = true; render();
        try {
          if (retry && pending) {
            const command = pending; const result = await mutate(command);
            if (result.run) accept(result.run); else if (!result.url) accept(result);
            if (result.url && !command.stay) {window.location.assign(appUrl(result.url)); return;}
          } else await ensureRun(!stepId && !!run?.completed, requestedStep);
          const next = requestedStep || run?.next_action?.step_id;
          if (!next) return;
          if (stepId === 'transfer' && run.completion_path !== 'challenge' && !run.completed) {
            const changed = await mutate({url:`/api/v1/curriculum/runs/${encodeURIComponent(run.id)}/navigation`, body:{submission_id:crypto.randomUUID(),expected_revision:run.revision,step_id:'transfer',completion_path:'challenge'},step:stepId,stay:true});
            accept(changed.run);
          }
          const result = await mutate({url:`/api/v1/curriculum/runs/${encodeURIComponent(run.id)}/steps/${encodeURIComponent(next)}/start`,body:{submission_id:crypto.randomUUID(),expected_revision:run.revision},step:next});
          if (result.run) accept(result.run);
          window.location.assign(appUrl(result.url));
        } catch (error) {showError(error);}
        finally {busy = false; render();}
      }
      async function reload() {
        if (!run || busy) return;
        busy = true; render();
        try {accept(await request(`/api/v1/curriculum/runs/${encodeURIComponent(run.id)}`));errors.hidden = true;}
        catch (error) {showError(error);} finally {busy = false;render();}
      }
      const openStep = stepId => perform(stepId);
      action?.addEventListener('click', () => run?.completed&&definition.next_unit?.url?window.location.assign(appUrl(definition.next_unit.url)):void perform(null));
      repeat?.addEventListener('click',()=>void perform(null));
      results?.addEventListener('toggle',()=>void showSummary());
      render();
      if (run) void reload();
    }
    if (window.location.hash === '#learn') {const details = document.getElementById('learn'); if (details) {details.open = true; details.scrollIntoView?.({block:'start'});}}
  }
  document[key] = init;
  document.addEventListener('htmx:beforeSwap', () => {for (const player of document.querySelectorAll('[data-teaching-audio]')) player.pause();});
  document.addEventListener('htmx:afterSwap', init); window.addEventListener('hashchange', init); init();
})();
