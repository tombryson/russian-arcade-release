/* Progressive enhancement: the lesson remains navigable without JavaScript. */
(() => {
  const t = (en, ru) => document.documentElement.lang === 'ru' ? ru : en;
  const editors = new WeakMap();
  const pagePositions = new WeakMap();
  let pollTimer;
  const request = async (url, data) => {
    const response = await fetch(url, {method:'POST',body:data,headers:{Accept:'application/json'}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || t('Could not save. Please try again.', 'Не удалось сохранить. Попробуйте ещё раз.'));
    return result;
  };
  const state = form => {
    if (!editors.has(form)) editors.set(form, {chain:Promise.resolve(),timer:null,checking:false});
    return editors.get(form);
  };
  const dirty = form => form && form.elements.answer.value !== form.elements.answer.dataset.saved;
  const save = form => {
    const s = state(form);
    clearTimeout(s.timer);
    s.chain = s.chain.catch(()=>{}).then(async () => {
      if (!form.isConnected || !dirty(form)) return;
      const status = form.querySelector('[data-draft-status]');
      const answer = form.elements.answer.value;
      status.textContent=t('Saving…','Сохраняем…');
      try {
        const data = new FormData(form);
        const result = await request(form.dataset.saveUrl,data);
        form.elements.draft_revision.value=result.revision;
        form.elements.answer.dataset.saved=answer;
        status.textContent=dirty(form) ? t('Unsaved changes','Есть несохранённые изменения') : t('Draft saved','Черновик сохранён');
      } catch (error) { status.textContent=error.message; throw error; }
    });
    return s.chain;
  };
  const prepareCards = async form => {
    if (!form.isConnected || form.dataset.busy) return;
    form.dataset.busy='1';
    const status=form.querySelector('[data-card-status]');
    const button=form.querySelector('button');button.disabled=true;
    status.textContent=t('Finding useful sentences and checking their word forms…','Ищем полезные предложения и проверяем формы слов…');
    try {
      const result=await request(form.action,new FormData(form));
      if (!form.isConnected) return;
      if (result.state==='ready') { location.assign(result.url);return; }
      if (result.state==='failed') throw new Error(result.error);
      setTimeout(()=>prepareCards(form),3000);
    } catch (error) { if(form.isConnected)status.textContent=error.message; }
    finally { delete form.dataset.busy;button.disabled=false;button.textContent=t('Retry preparation','Повторить подготовку'); }
  };
  const init = () => {
    const cards=document.querySelector('[data-auto-prepare]');
    if (cards) {cards.removeAttribute('data-auto-prepare');void prepareCards(cards);}
    clearTimeout(pollTimer);
    const root=document.querySelector('[data-lesson-poll]');
    if (!root) return;
    const poll=async () => {
      if (!root.isConnected) return;
      try {
        const response=await fetch(root.dataset.lessonPoll,{headers:{Accept:'application/json'}});
        if (!response.ok) throw new Error();
        const data=await response.json();
        if (data.state==='ready' || data.state==='failed' || data.retryable) {location.replace(data.url);return;}
        const stages={rendering:t('Opening the annotated pages','Открываем страницы с заметками'),reading:t('Reading your pages and notes','Читаем страницы и заметки'),planning:t('Preparing your exercises','Готовим задания'),checking:t('Checking the exercises against the lesson','Проверяем задания по материалу урока')};
        root.querySelector('[data-lesson-stage]').textContent=stages[data.stage] || stages.reading;
        root.querySelector('progress').value=data.pages_read;
        root.querySelector('[data-lesson-count]').textContent=`${data.pages_read} / ${data.page_total} `+t('pages read','страниц прочитано');
        root.querySelector('[data-lesson-status]').textContent='';
      } catch {root.querySelector('[data-lesson-status]').textContent=t('Connection interrupted. Retrying…','Связь прервалась. Повторяем…');}
      pollTimer=setTimeout(poll,3000);
    };
    pollTimer=setTimeout(poll,1500);
  };
  document.addEventListener('change',event=>{
    const selector=event.target.closest('select[data-lesson-page]');
    if (selector && !selector.disabled) selector.form.requestSubmit();
  });
  document.addEventListener('htmx:beforeSwap',event=>{
    const {requestConfig,xhr,target,shouldSwap}=event.detail;
    if (!shouldSwap || !requestConfig?.elt?.matches('[data-lesson-page-nav]')) return;
    const scroller=target.querySelector('.lesson-word-scroll');
    pagePositions.set(xhr,{
      x:window.scrollX,y:window.scrollY,
      enlarged:!!target.querySelector('.lesson-word-sheet.is-enlarged'),
      left:scroller?.scrollLeft || 0,top:scroller?.scrollTop || 0,
      minHeight:target.style.minHeight,
    });
    // Keep enough room while the new page and OCR controls replace the old ones.
    target.style.minHeight=`${target.getBoundingClientRect().height}px`;
  });
  document.addEventListener('htmx:afterSwap',event=>{
    const {xhr,target}=event.detail,position=pagePositions.get(xhr);
    if (!position) return;
    pagePositions.delete(xhr);
    if (position.enlarged) {
      target.querySelector('.lesson-word-sheet')?.classList.add('is-enlarged');
      const zoom=target.querySelector('[data-word-zoom]');
      if (zoom) {zoom.setAttribute('aria-pressed','true');zoom.textContent=t('Fit page','По ширине');}
    }
    const scroller=target.querySelector('.lesson-word-scroll');
    if (scroller) {scroller.scrollLeft=position.left;scroller.scrollTop=position.top;}
    target.style.minHeight=position.minHeight;
    window.scrollTo({left:position.x,top:position.y,behavior:'instant'});
  });
  document.addEventListener('input',event=>{
    if (event.target.closest('[data-lesson-cards-create]')) event.target.form.elements.last_page.setCustomValidity('');
    const form=event.target.closest('[data-lesson-editor]');
    if (!form || event.target.name!=='answer') return;
    const s=state(form);
    form.elements.submission_key.value=crypto.randomUUID();
    form.querySelector('[data-draft-status]').textContent=t('Unsaved changes','Есть несохранённые изменения');
    clearTimeout(s.timer);s.timer=setTimeout(()=>save(form).catch(()=>{}),750);
  });
  document.addEventListener('click',async event=>{
    const opener=event.target.closest('[data-open-lesson]');
    if (opener) {const details=document.querySelector(opener.getAttribute('href'));if(details)details.open=true;}
    const button=event.target.closest('[data-lesson-save]');
    if (button) {await save(button.closest('form')).catch(()=>{});return;}
    const link=event.target.closest('.lesson-page a[href]');
    const form=document.querySelector('[data-lesson-editor]');
    if (link && dirty(form) && !link.target && !event.ctrlKey && !event.metaKey && event.button===0) {
      event.preventDefault();
      try {await save(form);location.assign(link.href);} catch {form.elements.answer.focus();}
    }
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(form.matches('[data-lesson-cards-prepare]')) {
      event.preventDefault();void prepareCards(form);
    } else if(form.matches('[data-lesson-cards-create]')) {
      const first=Number(form.elements.first_page.value),last=Number(form.elements.last_page.value);
      if (last<first || last-first>=10) {event.preventDefault();form.elements.last_page.setCustomValidity(t('Choose up to 10 consecutive pages.','Выберите до 10 страниц подряд.'));form.elements.last_page.reportValidity();}
      else form.querySelector('button').disabled=true;
    } else if (form.matches('[data-lesson-editor]')) {
      event.preventDefault();const s=state(form);if(s.checking)return;s.checking=true;
      const status=form.querySelector('[data-check-status]');
      const textarea=form.elements.answer;textarea.readOnly=true;
      form.querySelectorAll('button').forEach(b=>b.disabled=true);form.setAttribute('aria-busy','true');
      try {await save(form);status.textContent=t('Checking your answer…','Проверяем ответ…');const result=await request(form.action,new FormData(form));location.assign(result.url);}
      catch(error){status.textContent=error.message;}
      finally{s.checking=false;textarea.readOnly=false;form.removeAttribute('aria-busy');form.querySelectorAll('button').forEach(b=>b.disabled=false);}
    } else if(form.matches('[data-lesson-bookmark]')) {
      event.preventDefault();try{await request(form.action,new FormData(form));form.querySelector('[role=status]').textContent=t('Place saved','Место сохранено');}catch(error){form.querySelector('[role=status]').textContent=error.message;}
    } else if(form.matches('[data-lesson-next]')) {
      const editor=document.querySelector('[data-lesson-editor]');
      if(dirty(editor)){event.preventDefault();try{await save(editor);HTMLFormElement.prototype.submit.call(form);}catch{editor.elements.answer.focus();}}
    } else if(form.matches('[data-lesson-upload]')) {
      form.querySelector('[data-upload-status]').textContent=t('Saving your material…','Сохраняем материал…');
      form.querySelector('button[type=submit]').disabled=true;
    }
  });
  window.addEventListener('beforeunload',event=>{if(dirty(document.querySelector('[data-lesson-editor]'))){event.preventDefault();event.returnValue='';}});
  document.addEventListener('DOMContentLoaded',init);
  document.addEventListener('htmx:afterSwap',init);
  document.addEventListener('htmx:historyRestore',init);
  if(document.readyState!=='loading')init();
})();
