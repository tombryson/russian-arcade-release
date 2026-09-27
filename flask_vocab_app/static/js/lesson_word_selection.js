/* Tap words on the original page; selection persists before card generation. */
(() => {
  const t=(en,ru)=>document.documentElement.lang==='ru'?ru:en;
  const mounted=new WeakSet();
  function mount(root) {
    if(mounted.has(root))return;mounted.add(root);
    const endpoint=root.dataset.endpoint, page=Number(root.dataset.page);
    const layer=root.querySelector('[data-word-layer]'), list=root.querySelector('[data-pending-list]');
    const status=root.querySelector('[data-selection-status]'), ocrStatus=root.querySelector('[data-ocr-status]');
    const create=root.querySelector('[data-create-selected]');
    let picks=[],words=[],busy=false,ocrBusy=false,areaMode=false,area=null,drag=null,dialog=null;
    const json=async(url,body)=>{
      const response=await fetch(url,body===undefined ? {headers:{Accept:'application/json'}} : {method:'POST',headers:{Accept:'application/json','Content-Type':'application/json','X-CSRF-Token':root.dataset.csrf},body:JSON.stringify(body)});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.error==='string'?data.error:t('Could not save. Please retry.','Не удалось сохранить. Попробуйте ещё раз.'));
      return data;
    };
    const node=(tag,text,className)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(className)n.className=className;return n;};
    function paint() {
      if(!root.isConnected)return;
      const pending=picks.filter(p=>p.status==='pending');
      root.querySelector('[data-pending-count]').textContent=String(pending.length);
      const shortcut=root.querySelector('[data-top-pending]');if(shortcut)shortcut.textContent=String(pending.length);
      const waiting=picks.filter(p=>p.status!=='saved');
      root.querySelector('[data-pending-empty]').hidden=waiting.length>0;
      create.disabled=busy||!pending.length;
      create.textContent=pending.length===1 ? t('Create 1 card','Создать карточку') : pending.length ? t(`Create ${Math.min(10,pending.length)} cards`,`Создать карточки: ${Math.min(10,pending.length)}`) : t('Create cards','Создать карточки');
      list.replaceChildren();
      for(const pick of waiting) {
        const article=node('article',null,'lesson-pending-word');
        const heading=node('div',null,'lesson-pending-word-heading');
        const name=node('strong',pick.surface);name.lang='ru';heading.append(name);
        const caption=pick.status==='preparing'?t('Preparing','Создаётся'):t(`Page ${pick.page}`,`Страница ${pick.page}`);
        article.append(heading,node('small',caption));
        if(pick.status==='pending') {
          const remove=node('button','×','lesson-remove-word');remove.type='button';remove.disabled=busy;remove.setAttribute('aria-label',t(`Remove ${pick.surface}`,`Убрать ${pick.surface}`));
          remove.addEventListener('click',()=>mutate({page:pick.page,token:pick.token_key,selected:false}));heading.append(remove);
          const details=node('details'),summary=node('summary',t('Context & reading','Контекст и распознавание'));
          const context=node('p',pick.context);context.lang='ru';
          const label=node('label',t('Word on the page','Слово на странице'));
          const input=node('input');input.type='text';input.value=pick.surface;input.lang='ru';input.maxLength=100;input.className='form-control';label.append(input);
          const save=node('button',t('Save reading','Сохранить слово'),'btn btn-outline-secondary');save.type='button';save.disabled=busy;save.addEventListener('click',()=>mutate({action:'edit',id:pick.id,surface:input.value}));
          details.append(summary);
          if(pick.region_id){const crop=node('img',null,'lesson-word-crop');crop.src=`${endpoint}/${pick.page}/crop/${encodeURIComponent(pick.region_id)}`;crop.alt=t('Selected word on the page','Выбранное слово на странице');crop.loading='lazy';details.append(crop);}
          details.append(context,label,save);article.append(details);
        } else if(pick.batch_id) {
          const link=node('a',t('Open set →','Открыть набор →'));link.href='/#generate/'+encodeURIComponent(pick.batch_id);article.append(link);
        }
        if(pick.error)article.append(node('p',pick.error,'lesson-card-note'));
        list.append(article);
      }
      for(const button of layer.querySelectorAll('button')) {
        const pick=picks.find(p=>p.page===page&&p.token_key===button.dataset.token);
        button.setAttribute('aria-pressed',String(!!pick));button.classList.toggle('is-selected',!!pick);
        if(pick){button.textContent=pick.surface;button.setAttribute('aria-label',t(`Select ${pick.surface}`,`Выбрать ${pick.surface}`));}
        button.title=pick?.status==='saved' ? `${pick.surface} · ${t('In your lesson cards','В карточках урока')}` : button.textContent;
        button.disabled=busy||!!pick&&pick.status!=='pending';
      }
      root.querySelectorAll('.lesson-word-controls button,.lesson-word-controls select').forEach(el=>el.disabled=busy);
    }
    async function mutate(body) {
      if(busy)return;busy=true;status.textContent=t('Saving…','Сохраняем…');paint();
      try {const data=await json(endpoint,body);picks=data.picks;status.textContent=t('Saved','Сохранено');return true;}
      catch(error){status.textContent=error.message;return false;}
      finally{busy=false;paint();}
    }
    function addWord(word) {
      const button=node('button',word.surface||t('Unread word','Нераспознанное слово'),'lesson-ocr-word');button.type='button';button.dataset.token=word.key;
      button.setAttribute('aria-label',t(`Select ${word.surface}`,`Выбрать ${word.surface}`));button.title=word.surface;
      Object.assign(button.style,{left:`${word.x*100}%`,top:`${word.y*100}%`,width:`${word.width*100}%`,height:`${word.height*100}%`});
      button.addEventListener('click',()=>{
        if(areaMode||busy)return;
        const selected=picks.some(p=>p.page===page&&p.token_key===word.key);
        if(word.needs_check&&!word.remembered)checkWord(word,button);
        else void mutate({page,token:word.key,selected:!selected});
      });layer.append(button);
    }
    function checkWord(word,opener) {
      if(!root.isConnected)return;
      dialog?.remove();dialog=node('dialog',null,'lesson-reading-dialog');
      const heading=node('h3',t('Check this word','Проверьте слово'));heading.id='lesson-reading-title';dialog.setAttribute('aria-labelledby',heading.id);
      const crop=node('img',null,'lesson-word-crop');crop.src=`${endpoint}/${page}/crop/${encodeURIComponent(word.key)}`;crop.alt=t('Selected word on the page','Выбранное слово на странице');
      const form=node('form');const label=node('label',t('Word on the page','Слово на странице'));
      const input=node('input');input.type='text';input.value=word.surface;input.lang='ru';input.maxLength=100;input.required=true;input.className='form-control';label.append(input);
      const feedback=node('p');feedback.setAttribute('role','status');
      const buttons=node('div',null,'lesson-reading-actions');
      const save=node('button',t('Save word','Сохранить слово'),'btn btn-primary');save.type='submit';
      const cancel=node('button',t('Cancel','Отмена'),'btn btn-outline-secondary');cancel.type='button';cancel.addEventListener('click',()=>dialog.close());buttons.append(save,cancel);
      const accept=async surface=>{
        if(busy)return;
        if(!/^[А-Яа-яЁё][А-Яа-яЁё\u0301]*(?:-[А-Яа-яЁё][А-Яа-яЁё\u0301]*)*$/.test(surface.trim())){feedback.textContent=t('Enter one Russian word.','Введите одно русское слово.');input.focus();return;}
        dialog.querySelectorAll('button,input').forEach(el=>el.disabled=true);feedback.textContent=t('Saving…','Сохраняем…');
        if(await mutate({page,token:word.key,selected:true,surface:surface.trim(),confirmed:true})){
          word.surface=surface.trim();word.needs_check=false;word.remembered=true;
          if(!words.some(w=>w.key===word.key)){words.push(word);addWord(word);paint();}
          dialog.close();
        }else{feedback.textContent=status.textContent;dialog.querySelectorAll('button,input').forEach(el=>el.disabled=false);}
      };
      form.addEventListener('submit',event=>{event.preventDefault();void accept(input.value);});
      dialog.append(heading,crop);
      if(word.suggestions?.length){
        const suggestions=node('div',null,'lesson-reading-suggestions');suggestions.append(node('p',t('Did you mean…','Возможно, это…')));
        for(const suggestion of word.suggestions){const use=node('button',suggestion.surface,'btn btn-outline-secondary');use.type='button';use.lang='ru';use.setAttribute('aria-label',t(`Use ${suggestion.surface}`,`Использовать ${suggestion.surface}`));use.addEventListener('click',()=>accept(suggestion.surface));suggestions.append(use);}
        dialog.append(suggestions);
      }
      form.append(label,feedback,buttons);dialog.append(form);root.append(dialog);
      dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
      dialog.addEventListener('close',()=>{dialog.remove();opener?.focus({preventScroll:true});});
      dialog.showModal();input.focus({preventScroll:true});
    }
    const sheet=root.querySelector('.lesson-word-sheet'),areaButton=root.querySelector('[data-select-area]');
    const areaActions=root.querySelector('[data-area-actions]'),selectionBox=root.querySelector('[data-area-box]');
    const draw=()=>{
      if(!selectionBox)return;selectionBox.hidden=!area;
      if(area)Object.assign(selectionBox.style,{left:`${area.x*100}%`,top:`${area.y*100}%`,width:`${area.width*100}%`,height:`${area.height*100}%`});
      root.querySelector('[data-read-area]').disabled=!area||busy;
    };
    function selectArea(enabled){
      areaMode=enabled;area=enabled?{x:.35,y:.4,width:.3,height:.08}:null;sheet.classList.toggle('is-selecting-area',enabled);areaButton.setAttribute('aria-pressed',String(enabled));areaActions.hidden=!enabled;draw();
    }
    areaButton?.addEventListener('click',()=>selectArea(!areaMode));
    root.querySelector('[data-cancel-area]')?.addEventListener('click',()=>selectArea(false));
    const point=event=>{const r=sheet.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))};};
    sheet.addEventListener('pointerdown',event=>{
      if(!areaMode||busy||event.button!==0)return;event.preventDefault();
      drag={start:point(event),box:area?{...area}:null,handle:event.target.dataset.corner||null};sheet.setPointerCapture(event.pointerId);
      if(!drag.handle)area={...drag.start,width:0,height:0};draw();
    });
    sheet.addEventListener('pointermove',event=>{
      if(!drag)return;const p=point(event);let start=drag.start;
      if(drag.handle&&drag.box){const b=drag.box;start={x:drag.handle.includes('w')?b.x+b.width:b.x,y:drag.handle.includes('n')?b.y+b.height:b.y};}
      area={x:Math.min(p.x,start.x),y:Math.min(p.y,start.y),width:Math.abs(p.x-start.x),height:Math.abs(p.y-start.y)};draw();
    });
    sheet.addEventListener('pointerup',event=>{if(!drag)return;drag=null;if(sheet.hasPointerCapture(event.pointerId))sheet.releasePointerCapture(event.pointerId);if(area.width<.002||area.height<.002)area=null;draw();});
    sheet.addEventListener('pointercancel',()=>{drag=null;area=null;draw();});
    sheet.addEventListener('keydown',event=>{
      const corner=event.target.dataset.corner;if(!areaMode||!area||!corner||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
      event.preventDefault();const step=event.shiftKey ? .02 : .005;
      const start={x:corner.includes('w')?area.x+area.width:area.x,y:corner.includes('n')?area.y+area.height:area.y};
      const end={x:corner.includes('w')?area.x:area.x+area.width,y:corner.includes('n')?area.y:area.y+area.height};
      end.x=Math.max(0,Math.min(1,end.x+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0)));end.y=Math.max(0,Math.min(1,end.y+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0)));
      area={x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),width:Math.abs(end.x-start.x),height:Math.abs(end.y-start.y)};draw();
    });
    root.querySelector('[data-read-area]')?.addEventListener('click',async()=>{
      if(!area||busy)return;busy=true;paint();draw();status.textContent=t('Reading your selection…','Распознаём выделенное слово…');
      try{const word=await json(endpoint+'/area',{page,box:area});if(!root.isConnected)return;selectArea(false);status.textContent='';checkWord(word,areaButton);}
      catch(error){status.textContent=error.message;}
      finally{busy=false;paint();draw();}
    });
    async function readPage() {
      if(ocrBusy)return;ocrBusy=true;root.querySelector('[data-ocr-retry]').hidden=true;
      ocrStatus.textContent=t('Making the words selectable…','Готовим слова для выбора…');
      try {
        const data=await json(`${endpoint}/${page}`);
        if(!root.isConnected)return;layer.replaceChildren();
        words=data.words;words.forEach(addWord);
        ocrStatus.textContent=data.words.length?t('Tap words to highlight them. Check unclear readings against the page.','Нажмите на слова, чтобы выделить их. Неясные места сверяйте со страницей.'):t('No selectable words were found on this page. Try another page.','На этой странице слова не распознаны. Попробуйте другую страницу.');paint();
      } catch(error){ocrStatus.textContent=error.message;root.querySelector('[data-ocr-retry]').hidden=false;}
      finally{ocrBusy=false;}
    }
    root.querySelector('[data-ocr-retry]').addEventListener('click',load);
    root.querySelector('[data-word-zoom]').addEventListener('click',event=>{
      const enlarged=root.querySelector('.lesson-word-sheet').classList.toggle('is-enlarged');
      event.currentTarget.setAttribute('aria-pressed',String(enlarged));event.currentTarget.textContent=enlarged?t('Fit page','По ширине'):t('Enlarge page','Увеличить страницу');
    });
    root.addEventListener('click',event=>{if(busy&&event.target.closest('a'))event.preventDefault();});
    root.addEventListener('htmx:beforeRequest',event=>{if(busy&&event.detail.elt?.matches('[data-lesson-page-nav]'))event.preventDefault();});
    create.addEventListener('click',async()=>{
      if(busy)return;busy=true;paint();status.textContent=t('Starting your cards…','Начинаем создавать карточки…');
      try{const result=await json(endpoint+'/create',{});location.assign(result.url);}
      catch(error){busy=false;status.textContent=error.message;paint();}
    });
    async function load() {
      try {const data=await json(endpoint);picks=data.picks;paint();await readPage();}
      catch(error){status.textContent=error.message;root.querySelector('[data-ocr-retry]').hidden=false;}
    }
    void load();
  }
  const init=()=>document.querySelectorAll('[data-word-selector]').forEach(mount);
  document.addEventListener('DOMContentLoaded',init);document.addEventListener('htmx:afterSwap',init);document.addEventListener('htmx:historyRestore',init);
  if(document.readyState!=='loading')init();
})();
