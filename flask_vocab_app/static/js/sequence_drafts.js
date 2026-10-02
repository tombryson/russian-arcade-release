/* Autosave only the owned Reading and Writing editors opened by a lesson. */
(() => {
  const key=Symbol.for('russian-arcade.sequence-drafts');
  if(document[key]){document[key]();return;}
  const controllers=new WeakMap();
  const appUrl=url=>window.arcadeUrl?window.arcadeUrl(url):url;
  const headers=()=>Object.fromEntries([['Accept','application/json'],['X-CSRF-Token',document.querySelector('meta[name="csrf-token"]')?.content],['X-Profile-ID',document.querySelector('meta[name="learning-profile"]')?.content],['X-Account-Scope',document.querySelector('meta[name="learning-account"]')?.content]].filter(([,value])=>value));
  function init(){
    for(const form of document.querySelectorAll('[data-sequence-draft]')){
      if(controllers.has(form))continue;
      const writing=form.dataset.sequenceDraft==='writing';
      const t=(en,ru)=>form.dataset.draftLanguage==='ru'?ru:en;
      const fields=()=>writing?[form.elements.user_response]:[...form.querySelectorAll('textarea[name="answers[]"]')];
      const values=()=>fields().map(field=>field.value);
      let acknowledged=JSON.stringify(fields().map(field=>field.dataset.savedValue??field.defaultValue)),taskRevision=Number(writing?form.elements.revision.value:form.elements.task_revision.value),pending=null,inFlight=null,timer=null,halted=false,reviewing=false,leaveTo=null;
      const status=writing?form.querySelector('.sentence-draft-status'):form.querySelector('[data-sequence-draft-status]');
      const recovery=document.createElement('div');recovery.className='sequence-draft-recovery';recovery.setAttribute('role','alert');recovery.hidden=true;form.append(recovery);
      const dirty=()=>JSON.stringify(values())!==acknowledged||!!pending;
      function reviewControls(){if(form.dataset.reviewPending==='true')for(const button of form.querySelectorAll('button[type="submit"]'))if(!button.getAttribute('formaction'))button.disabled=true;}
      function setStatus(text){if(status)status.textContent=text;}
      function markSaved(snapshot){
        acknowledged=JSON.stringify(snapshot);
        fields().forEach((field,index)=>{field.dataset.savedValue=snapshot[index]??'';});
        const workspace=form.closest('.reading-workspace');if(workspace)workspace.dataset.dirty=dirty()?'true':'false';
        setStatus(dirty()?t('Unsaved changes','Есть несохранённые изменения'):t('Saved','Сохранено'));
      }
      function button(label,handler){const value=document.createElement('button');value.type='button';value.className='sentence-text-button';value.textContent=label;value.addEventListener('click',handler);return value;}
      function fail(message,conflict=false){
        recovery.hidden=false;recovery.replaceChildren();
        const text=document.createElement('p');text.textContent=message;recovery.append(text);
        setStatus(t('Save not confirmed','Сохранение не подтверждено'));
        if(!halted)recovery.append(button(t('Retry save','Повторить сохранение'),()=>void flush().then(saved=>{if(saved&&leaveTo)navigate();})));
        if(conflict){
          const copy=document.createElement('textarea');copy.readOnly=true;copy.value=values().join('\n\n');copy.setAttribute('aria-label',t('Copy your unsaved text','Скопируйте несохранённый текст'));recovery.append(copy);
          recovery.append(button(t('Load saved version','Загрузить сохранённую версию'),()=>{if(window.confirm(t('Copy your unsaved text first. Reload the saved version?','Сначала скопируйте несохранённый текст. Загрузить сохранённую версию?'))){pending=null;markSaved(values());window.location.reload();}}));
        }
        if(leaveTo){
          recovery.append(button(t('Stay here','Остаться'),()=>{leaveTo=null;recovery.hidden=true;}));
          recovery.append(button(t('Leave without saving','Выйти без сохранения'),()=>{pending=null;markSaved(values());navigate();}));
        }
      }
      function navigate(){const destination=leaveTo;leaveTo=null;if(destination)window.location.assign(appUrl(destination));}
      async function flush(){
        clearTimeout(timer);
        if(!form.isConnected||halted)return false;
        if(inFlight){if(!await inFlight)return false;return flush();}
        if(reviewing||form.dataset.busy==='true')return false;
        if(!dirty())return true;
        if(form.dataset.reviewPending==='true'){
          halted=true;
          fail(t('Your submitted reply is saved. Finish its feedback before editing. Copy any new text before reloading.','Отправленный ответ сохранён. Завершите его проверку перед редактированием. Перед перезагрузкой скопируйте новый текст.'),true);
          return false;
        }
        const snapshot=values();
        if(!pending){
          const revision=Number(writing?form.elements.revision.value:form.elements.task_revision.value);
          const body=writing?new FormData(form):{submission_id:crypto.randomUUID(),expected_revision:revision,expected_draft_revision:Number(form.dataset.draftRevision||0),response:{answers:snapshot}};
          if(writing)body.set('submission_id',crypto.randomUUID());
          pending={snapshot,body,url:writing?'/writing/save':`/api/v1/comprehension/tasks/${encodeURIComponent(form.elements.task_id.value)}/draft`};
        }
        const command=pending;setStatus(t('Saving…','Сохраняем…'));recovery.hidden=true;
        const request=(async()=>{
          try{
            const response=await fetch(appUrl(command.url),{method:'POST',credentials:'same-origin',headers:{...headers(),...(!writing?{'Content-Type':'application/json'}:{})},body:writing?command.body:JSON.stringify(command.body)});
            const result=await response.json();
            if(!form.isConnected)return false;
            if(!response.ok){
              const conflict=response.status===409;
              halted=conflict||[401,403,404].includes(response.status);
              if(halted)pending=null;
              fail(result.error?.code==='review_pending'?t('Your submitted reply is saved. Finish its feedback before editing. Copy any new text before reloading.','Отправленный ответ сохранён. Завершите его проверку перед редактированием. Перед перезагрузкой скопируйте новый текст.'):conflict?t('This task changed. Copy your text before loading the saved version.','Задание изменилось. Скопируйте текст перед загрузкой сохранённой версии.'):result.error?.message||result.error||t('Your draft could not be saved. Your text is still here.','Не удалось сохранить черновик. Текст остался на странице.'),conflict);
              return false;
            }
            if(!Number.isInteger(result.revision)||!writing&&!Number.isInteger(result.draft_revision))throw new Error('Invalid draft acknowledgement');
            if(writing)form.elements.revision.value=result.revision;
            else{form.elements.task_revision.value=result.revision;form.dataset.draftRevision=result.draft_revision;}
            pending=null;markSaved(command.snapshot);return true;
          }catch(_){if(form.isConnected)fail(t('Your draft could not be saved. Your text is still here.','Не удалось сохранить черновик. Текст остался на странице.'));return false;}
          finally{inFlight=null;}
        })();
        inFlight=request;const saved=await request;
        if(saved&&dirty())return flush();
        return saved;
      }
      const control={dirty,flush,get reviewing(){return reviewing;},set reviewing(value){reviewing=value;},leave:async href=>{leaveTo=href;if(await flush())navigate();else if(form.isConnected&&!reviewing)fail(t('Save your draft before leaving this activity.','Сохраните черновик перед выходом из задания.'),halted);},settled:()=>{reviewing=false;reviewControls();const revision=Number(writing?form.elements.revision.value:form.elements.task_revision.value);if(!writing&&revision!==taskRevision)form.dataset.draftRevision='0';taskRevision=revision;acknowledged=JSON.stringify(fields().map(field=>field.dataset.savedValue??field.defaultValue));if(leaveTo)void control.leave(leaveTo);else if(dirty()&&!pending&&!halted)timer=setTimeout(()=>void flush(),800);}};
      controllers.set(form,control);
      form.addEventListener('input',event=>{
        if(!fields().includes(event.target))return;
        clearTimeout(timer);setStatus(t('Unsaved changes','Есть несохранённые изменения'));
        if(!pending&&!halted&&!reviewing)timer=setTimeout(()=>void flush(),800);
      });
      form.addEventListener('sequence:editor-settled',()=>control.settled());
      markSaved(JSON.parse(acknowledged));reviewControls();
    }
  }
  document.addEventListener('submit',event=>{
    if(event.sequenceDraftReady)return;
    const submitted=event.target;
    const form=submitted.matches('[data-sequence-draft]')?submitted:submitted.matches('[data-writing-model-answer]')?submitted.closest('.writing-workspace')?.querySelector('[data-sequence-draft]'):null;
    const control=form&&controllers.get(form);if(!control)return;
    event.preventDefault();event.stopImmediatePropagation();
    if(control.reviewing)return;
    const submitter=event.submitter;
    const onlySave=submitted===form&&submitter?.getAttribute('formaction')&&new URL(submitter.getAttribute('formaction'),window.location.href).pathname.endsWith('/writing/save');
    if(form.dataset.reviewPending==='true'&&!onlySave)return;
    void control.flush().then(saved=>{
      if(!saved||!form.isConnected||onlySave||control.reviewing)return;
      if(submitted===form)control.reviewing=true;
      const next=new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter});next.sequenceDraftReady=true;submitted.dispatchEvent(next);
    });
  },true);
  document.addEventListener('click',event=>{
    const link=event.target instanceof Element?event.target.closest('a[href]'):null;
    if(!link||event.defaultPrevented||event.button||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.target||link.hasAttribute('download'))return;
    const form=document.querySelector('[data-sequence-draft]'),control=form&&controllers.get(form);
    if(!control?.dirty())return;
    const destination=new URL(link.href,window.location.href);if(destination.href===window.location.href)return;
    event.preventDefault();event.stopImmediatePropagation();void control.leave(destination.href);
  },true);
  document.addEventListener('htmx:afterRequest',event=>{
    const form=event.detail?.elt?.closest?.('[data-sequence-draft]');
    if(form){
      if(form.closest('.reading-workspace')?.querySelector('[data-reading-review-pending]'))form.dataset.reviewPending='true';
      controllers.get(form)?.settled();
    }
  });
  document[key]=init;document.addEventListener('DOMContentLoaded',init);document.addEventListener('htmx:afterSwap',init);document.addEventListener('htmx:historyRestore',init);init();
})();
