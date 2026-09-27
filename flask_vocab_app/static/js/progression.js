(() => {
  'use strict';
  const header=document.querySelector('.arcade-header');
  const sidebar=document.querySelector('#sidebar');
  const navigation=header || sidebar;
  if (navigation) {
    const mobileRows=sidebar ? [...sidebar.querySelectorAll('.sidebar-brand-row, .navbar-toggler')] : [];
    const measure=()=>{
      const measured=header ? header.getBoundingClientRect().height : window.innerWidth<992 ? mobileRows.reduce((height,row)=>height+row.getBoundingClientRect().height,0) : 0;
      const height=`${measured}px`;
      document.documentElement.style.setProperty('--arcade-header-height',height);
      document.documentElement.style.setProperty('--skill-header-height',height);
    };
    measure();
    if (typeof ResizeObserver!=='undefined') {
      const observer=new ResizeObserver(measure);
      (header ? [header] : mobileRows).forEach(row=>observer.observe(row));
    }
    window.addEventListener('resize',measure);
    if (sidebar) {
      sidebar.addEventListener('shown.bs.collapse',measure);
      sidebar.addEventListener('hidden.bs.collapse',measure);
    }
  }
  const badges=()=>document.querySelectorAll('[data-progression-badge]');
  if (!badges().length && !document.querySelector('[data-skill-rail]')) return;
  const originalFetch=window.fetch;
  let busy=false,queued=false,timer,lastData;
  const railStates=new WeakMap();
  function renderSkill(data,error=false) {
    document.querySelectorAll('[data-skill-rail]').forEach(rail=>{
      const t=(en,ru)=>rail.dataset.language==='ru' ? ru : en;
      const course=data?.course;
      const chapter=course?.chapters?.find(item=>item.id===course.current_chapter_id) || (course?.completed ? course.chapters.at(-1) : null);
      const preview=new URLSearchParams(window.location.search).get('progress-preview')==='50';
      const progress=preview ? .5 : chapter && Number.isFinite(chapter.progress) ? Math.max(0,Math.min(1,chapter.progress)) : 0;
      const previous=railStates.get(rail);
      const key=chapter ? `${data.profile_id}:${course.release_id ?? course.version}:${chapter.id}` : '';
      const moving=!!(!preview && chapter && previous?.key===key && progress>previous.progress);
      if (previous?.timer) clearTimeout(previous.timer);
      rail.classList.toggle('is-moving',moving);
      rail.classList.toggle('is-unavailable',!data && !preview);
      rail.style.setProperty('--skill-progress',String(progress));
      const chapterLabel=chapter ? t(`Chapter ${chapter.number} of ${course.chapters.length} · ${chapter.title}`,`Глава ${chapter.number} из ${course.chapters.length} · ${chapter.title_ru}`) : '';
      const label=preview ? t('50% layout preview; saved progress unchanged','Предпросмотр 50%; сохранённый прогресс не изменён') : chapter ? `${chapterLabel} · ${chapter.status==='passed' ? t('Milestone passed','Этап пройден') : t(`${Math.round(progress*100)}% prepared for checkpoint`,`${Math.round(progress*100)}% подготовки к проверке`)}` : data ? '' : t('Chapter progress unavailable','Прогресс главы недоступен');
      const stale=data && error ? t('Showing your last saved progress','Показан последний сохранённый прогресс') : '';
      const link=rail.querySelector('.skill-rail-link');
      link.setAttribute('href','/#journey');
      link.setAttribute('aria-label',[label,stale,t('Open your journey','Открыть путешествие')].filter(Boolean).join('. '));
      rail.querySelector('.skill-rail-runner').hidden=!data && !preview;
      const bar=rail.querySelector('[data-skill-bar]');
      bar.setAttribute('aria-label',t('Checkpoint preparation','Подготовка к проверке'));
      bar.hidden=!chapter && !preview;
      if (chapter || preview) {bar.setAttribute('aria-valuenow',String(Math.round(progress*100)));bar.setAttribute('aria-valuetext',label);}
      else {bar.removeAttribute('aria-valuenow');bar.removeAttribute('aria-valuetext');}
      railStates.set(rail,{key,progress,timer:moving ? setTimeout(()=>rail.classList.remove('is-moving'),800) : null});
    });
  }
  async function refresh() {
    if (busy) {queued=true;return;}
    busy=true;
    try {
      const response=await originalFetch.call(window,'/api/v1/progression',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
      if (response.status===401 || response.status===403) lastData=undefined;
      const data=await response.json();
      if (data.error?.code==='profile_changed') lastData=undefined;
      if (!response.ok) throw new Error('Progress unavailable');
      if (!Number.isFinite(data.balance)) throw new Error('Progress unavailable');
      lastData=data;
      badges().forEach(badge=>{
        const number=badge.querySelector('[data-progression-balance]');
        if (number) number.textContent=String(data.balance);
        badge.setAttribute('aria-label',`${badge.dataset.language==='ru' ? 'Лингокоины' : 'Lingo coins'}: ${data.balance}`);
      });
      renderSkill(data);
    } catch (_) {
      renderSkill(lastData,true);
      if (!lastData) badges().forEach(badge=>{badge.querySelector('[data-progression-balance]').textContent='—';badge.setAttribute('aria-label',badge.dataset.language==='ru' ? 'Лингокоины: недоступно' : 'Lingo coins: unavailable');});
    } finally {busy=false;if (queued) {queued=false;schedule();}}
  }
  function schedule() {clearTimeout(timer);timer=setTimeout(refresh,350);}
  window.addEventListener('lingo:progression',schedule);
  document.addEventListener('visibilitychange',()=>{if (document.visibilityState==='visible') schedule();});
  document.addEventListener('htmx:afterRequest',schedule);
  document.addEventListener('submit',()=>{setTimeout(schedule,1200);},true);
  // Existing activities use both fetch and HTMX. Refresh shared progress
  // after same-origin writes, preserving the response and the activity draft.
  window.fetch=function(input,options) {
    const result=originalFetch.apply(this,arguments);
    try {
      const request=input instanceof Request ? input : null;
      const url=new URL(request ? request.url : String(input),window.location.href);
      const method=(options?.method || request?.method || 'GET').toUpperCase();
      if (url.origin===window.location.origin && method!=='GET' && method!=='HEAD' && !/\/(?:heartbeat|connect)$/.test(url.pathname)) {
        void result.then(response=>{if (response.ok) schedule();}).catch(()=>{});
      }
    } catch (_) { /* Leave unfamiliar request objects untouched. */ }
    return result;
  };
  setInterval(()=>{if (document.visibilityState==='visible') void refresh();},30000);
  void refresh();
})();
