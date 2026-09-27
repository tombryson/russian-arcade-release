import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';

const script=readFileSync('../static/js/lesson_word_selection.js','utf8');
let dom,w,root,picks;
let page={words:[{key:'0',surface:'городах',x:.1,y:.2,width:.3,height:.1}]};
const pending={id:'pick',page:1,token_key:'0',surface:'городах',original:'городах.',context:'Анна живёт в новых городах.',status:'pending'};
beforeEach(()=>{
  dom=new JSDOM('<html lang="en"><body><div data-word-selector data-endpoint="/select" data-page="1" data-csrf="token"><form class="lesson-word-controls"><button type="button" data-word-zoom></button></form><p data-ocr-status></p><button data-ocr-retry hidden></button><div class="lesson-word-sheet"><div data-word-layer></div></div><span data-pending-count></span><p data-pending-empty></p><div data-pending-list></div><p data-selection-status></p><button data-create-selected></button></div></body></html>',{url:'http://localhost/lessons',runScripts:'outside-only'});
  page={words:[{key:'0',surface:'городах',x:.1,y:.2,width:.3,height:.1}]};
  w=dom.window;
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
  root=w.document.querySelector('[data-word-selector]');picks=[];
  w.fetch=vi.fn(async(url,options)=>{
    if(url==='/select/1')return {ok:true,json:async()=>page};
    if(options?.method==='POST'){
      const body=JSON.parse(options.body);
      if(body.action==='edit')picks=[{...pending,surface:body.surface}];
      else picks=body.selected?[{...pending,surface:body.surface||pending.surface}]:[];
    }
    return {ok:true,json:async()=>({picks})};
  });
});
afterEach(()=>dom.window.close());
async function init(){w.eval(script);await vi.waitFor(()=>expect(root.querySelector('[data-token="0"]')).not.toBeNull());}

it('positions the selectable word over its page coordinates and saves an explicit selection',async()=>{
  await init();const word=root.querySelector('[data-token="0"]');
  expect(word.style.left).toBe('10%');expect(word.style.top).toBe('20%');
  word.click();await vi.waitFor(()=>expect(word.getAttribute('aria-pressed')).toBe('true'));
  expect(root.querySelector('[data-pending-count]').textContent).toBe('1');
  const call=w.fetch.mock.calls.find(([,options])=>options?.method==='POST');
  expect(JSON.parse(call[1].body)).toEqual({page:1,token:'0',selected:true});
  expect(call[1].headers['X-CSRF-Token']).toBe('token');
  expect(w.fetch.mock.calls.some(([url])=>url.includes('/create'))).toBe(false);
});

it('restores saved selections and removes one without deleting cards',async()=>{
  picks=[pending];await init();const word=root.querySelector('[data-token="0"]');
  expect(word.getAttribute('aria-pressed')).toBe('true');
  root.querySelector('[aria-label="Remove городах"]').click();
  await vi.waitFor(()=>expect(root.querySelector('[data-pending-count]').textContent).toBe('0'));
  expect(word.getAttribute('aria-pressed')).toBe('false');
  expect(root.querySelector('[data-create-selected]').disabled).toBe(true);
});

it('does not pretend a failed save highlighted a word',async()=>{
  await init();w.fetch.mockResolvedValueOnce({ok:false,json:async()=>({error:'Save failed'})});
  const word=root.querySelector('[data-token="0"]');word.click();
  await vi.waitFor(()=>expect(root.querySelector('[data-selection-status]').textContent).toBe('Save failed'));
  expect(word.getAttribute('aria-pressed')).toBe('false');
  expect(word.disabled).toBe(false);
});

it('lets an OCR reading be corrected without authoring a card',async()=>{
  picks=[pending];await init();
  root.querySelector('[data-pending-list] input').value='го́родах';
  root.querySelector('[data-pending-list] details button').click();
  await vi.waitFor(()=>expect(root.querySelector('[data-pending-list] strong').textContent).toBe('го́родах'));
  expect(JSON.parse(w.fetch.mock.calls.at(-1)[1].body)).toEqual({action:'edit',id:'pick',surface:'го́родах'});
});

it('keeps box alignment when the source page is enlarged',async()=>{
  await init();root.querySelector('[data-word-zoom]').click();
  expect(root.querySelector('.lesson-word-sheet').classList.contains('is-enlarged')).toBe(true);
  expect(root.querySelector('[data-token="0"]').style.left).toBe('10%');
});

it('moves generated words out of pending while keeping their page highlight',async()=>{
  picks=[{...pending,status:'saved'}];await init();
  expect(root.querySelector('[data-pending-list]').children.length).toBe(0);
  expect(root.querySelector('[data-pending-count]').textContent).toBe('0');
  expect(root.querySelector('[data-pending-empty]').hidden).toBe(false);
  const word=root.querySelector('[data-token="0"]');
  expect(word.getAttribute('aria-pressed')).toBe('true');expect(word.disabled).toBe(true);
  expect(word.title).toContain('In your lesson cards');
});

it('shows the crop and suggestions before saving an uncertain reading',async()=>{
  page.words[0]={...page.words[0],surface:'тородах',needs_check:true,suggestions:[{surface:'городах'}]};
  await init();root.querySelector('[data-token="0"]').click();
  const dialog=root.querySelector('dialog');expect(dialog.open).toBe(true);
  expect(dialog.querySelector('img').getAttribute('src')).toBe('/select/1/crop/0');
  expect(w.fetch.mock.calls.some(([,options])=>options.method==='POST')).toBe(false);
  dialog.querySelector('[aria-label="Use городах"]').click();
  await vi.waitFor(()=>expect(root.querySelector('[data-pending-count]').textContent).toBe('1'));
  expect(JSON.parse(w.fetch.mock.calls.at(-1)[1].body)).toEqual({page:1,token:'0',selected:true,surface:'городах',confirmed:true});
  expect(root.querySelector('dialog')).toBeNull();
});

it('keeps an unsuccessful correction open without pretending it was saved',async()=>{
  page.words[0].needs_check=true;await init();root.querySelector('[data-token="0"]').click();
  w.fetch.mockResolvedValueOnce({ok:false,json:async()=>({error:'Connection failed'})});
  root.querySelector('dialog form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  await vi.waitFor(()=>expect(root.querySelector('dialog [role="status"]').textContent).toBe('Connection failed'));
  expect(root.querySelector('[data-pending-count]').textContent).toBe('0');
  expect(root.querySelector('dialog input').disabled).toBe(false);
});

function areaControls(){
  root.querySelector('.lesson-word-controls').insertAdjacentHTML('beforeend','<button data-select-area type="button">Select an area</button>');
  root.insertAdjacentHTML('beforeend','<div data-area-actions hidden><button data-read-area>Read</button><button data-cancel-area>Cancel</button></div>');
  const sheet=root.querySelector('.lesson-word-sheet');
  sheet.insertAdjacentHTML('beforeend','<div data-area-box hidden><span data-corner="se" role="button" tabindex="0"></span></div>');
  sheet.getBoundingClientRect=()=>({left:0,top:0,width:1000,height:500});
  sheet.setPointerCapture=vi.fn();sheet.hasPointerCapture=()=>true;sheet.releasePointerCapture=vi.fn();
  return sheet;
}

it('maps a drawn box to the page and asks for confirmation before adding it',async()=>{
  const sheet=areaControls();await init();root.querySelector('[data-select-area]').click();
  sheet.dispatchEvent(new w.MouseEvent('pointerdown',{bubbles:true,clientX:100,clientY:100,button:0}));
  sheet.dispatchEvent(new w.MouseEvent('pointermove',{bubbles:true,clientX:300,clientY:150,button:0}));
  sheet.dispatchEvent(new w.MouseEvent('pointerup',{bubbles:true,clientX:300,clientY:150,button:0}));
  w.fetch.mockResolvedValueOnce({ok:true,json:async()=>({...page.words[0],key:'area',needs_check:true})});
  root.querySelector('[data-read-area]').click();
  await vi.waitFor(()=>expect(root.querySelector('dialog')?.open).toBe(true));
  const call=w.fetch.mock.calls.find(([url])=>url==='/select/area');
  expect(JSON.parse(call[1].body).box.x).toBeCloseTo(.1);
  expect(JSON.parse(call[1].body).box.width).toBeCloseTo(.2);
  expect(JSON.parse(call[1].body).box.height).toBeCloseTo(.1);
  expect(root.querySelector('[data-pending-count]').textContent).toBe('0');
});

it('supports keyboard resizing and cancellation without losing pending words',async()=>{
  areaControls();picks=[pending];await init();root.querySelector('[data-select-area]').click();
  const handle=root.querySelector('[data-corner="se"]');
  handle.dispatchEvent(new w.KeyboardEvent('keydown',{bubbles:true,key:'ArrowRight'}));
  expect(parseFloat(root.querySelector('[data-area-box]').style.width)).toBeCloseTo(30.5);
  root.querySelector('[data-cancel-area]').click();
  expect(root.querySelector('[data-area-box]').hidden).toBe(true);
  expect(root.querySelector('[data-pending-count]').textContent).toBe('1');
});
