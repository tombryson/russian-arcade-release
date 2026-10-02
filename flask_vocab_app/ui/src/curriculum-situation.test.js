import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {afterEach, expect, it, vi} from 'vitest';
import {fireEvent} from '@testing-library/preact';

const script = readFileSync('../static/js/curriculum_situation.js', 'utf8');
const pending = {id:'situation1',unit_id:'location-destination-v1',mode:'listening',state:'pending',stage:'text',retryable:false,error:null,url:null};
const response = value => Promise.resolve({ok:true,json:async()=>value});
const settle = async () => { for (let index=0; index<8; index++) await Promise.resolve(); };
function setup(fetch, state=pending, language='en') {
  document.head.innerHTML='<meta name="csrf-token" content="csrf"><meta name="learning-profile" content="p1"><meta name="learning-account" content="guest:1">';
  document.body.innerHTML=`<section data-situation-preparation data-language="${language}"><script data-situation-state type="application/json"></script><p data-situation-status></p><span data-situation-spinner hidden></span><button data-situation-retry hidden>Retry</button></section>`;
  document.querySelector('script').textContent=JSON.stringify(state);
  const timers=[], events={}, replace=vi.fn();
  const browser={location:{replace},arcadeUrl:path=>path.startsWith('/demo/')?path:'/demo'+path,
    setTimeout:vi.fn((callback,delay)=>{timers.push({callback,delay});return timers.length;}),
    addEventListener:vi.fn((type,callback)=>{events[type]=callback;})};
  runInNewContext(script,{document,window:browser,fetch});
  return {replace,events,browser,timers,root:document.querySelector('section'),
    status:document.querySelector('[data-situation-status]'),spinner:document.querySelector('[data-situation-spinner]'),
    retry:document.querySelector('[data-situation-retry]'),
    tick:async()=>{expect(timers.length).toBeGreaterThan(0);timers.shift().callback();await settle();}};
}
afterEach(()=>{document.body.innerHTML='';document.head.innerHTML='';vi.restoreAllMocks();});

it('shows preparation immediately and claims once before polling with account and profile headers', async()=>{
  let resolve;
  const fetch=vi.fn().mockImplementationOnce(()=>new Promise(done=>{resolve=done;}))
    .mockImplementation(()=>response({...pending,state:'running'}));
  const ui=setup(fetch);
  expect(ui.root.getAttribute('aria-busy')).toBe('true');
  expect(ui.spinner.hidden).toBe(false);
  expect(ui.status.textContent).toBe('Preparing a new situation…');
  expect(ui.retry.hidden).toBe(true);
  expect(ui.retry.disabled).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0]).toEqual(['/demo/api/v1/curriculum/situations/situation1/prepare',expect.objectContaining({
    method:'POST',credentials:'same-origin',cache:'no-store',body:JSON.stringify({retry:false}),
    headers:{'Content-Type':'application/json','X-CSRF-Token':'csrf','X-Profile-ID':'p1','X-Account-Scope':'guest:1'},
  })]);
  resolve(await response({...pending,state:'running'}));
  await settle();
  expect(ui.timers[0].delay).toBe(2000);
  await ui.tick();
  expect(fetch.mock.calls.map(([,options])=>options.method)).toEqual(['POST','GET']);
  expect(fetch.mock.calls[1][0]).toBe('/demo/api/v1/curriculum/situations/situation1');
});

it('prepares the pending audio stage and opens the saved player within the demo workspace',async()=>{
  const fetch=vi.fn().mockImplementationOnce(()=>response({...pending,stage:'audio'}))
    .mockImplementationOnce(()=>response({...pending,state:'ready',stage:'ready',url:'/#practice/lesson1'}));
  const ui=setup(fetch);
  await settle();
  expect(ui.status.textContent).toBe('Recording your message…');
  expect(ui.timers[0].delay).toBe(0);
  expect(ui.replace).not.toHaveBeenCalled();
  await ui.tick();
  expect(fetch.mock.calls.map(([,options])=>options.method)).toEqual(['POST','POST']);
  expect(ui.replace).toHaveBeenCalledOnce();
  expect(ui.replace).toHaveBeenCalledWith('/demo/#practice/lesson1');
  expect(ui.timers).toHaveLength(0);
});

it('offers an explicit retry for failed audio while preserving the same job',async()=>{
  const failed={...pending,stage:'audio',state:'failed',retryable:true,error:'preparation_failed'};
  const fetch=vi.fn(()=>response({...failed,retryable:false}));
  const ui=setup(fetch,failed);
  expect(fetch).not.toHaveBeenCalled();
  expect(ui.spinner.hidden).toBe(true);
  expect(ui.root.getAttribute('aria-busy')).toBe('false');
  expect(ui.retry.hidden).toBe(false);
  expect(ui.status.textContent).toBe('The recording could not be prepared. Try again with the same activity.');
  fireEvent.click(ui.retry);
  await settle();
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0][0]).toBe('/demo/api/v1/curriculum/situations/situation1/prepare');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({retry:true});
  expect(ui.retry.hidden).toBe(true);
  expect(ui.timers).toHaveLength(0);
});

it('shows progress immediately while an explicit retry request is still pending',async()=>{
  let resolve;
  const fetch=vi.fn(()=>new Promise(done=>{resolve=done;}));
  const ui=setup(fetch,{...pending,stage:'audio',state:'failed',retryable:true,error:'preparation_failed'});
  fireEvent.click(ui.retry);
  expect(ui.root.getAttribute('aria-busy')).toBe('true');
  expect(ui.spinner.hidden).toBe(false);
  expect(ui.retry.hidden).toBe(true);
  expect(ui.retry.disabled).toBe(true);
  expect(ui.status.textContent).toBe('Recording your message…');
  expect(fetch).toHaveBeenCalledOnce();
  resolve(await response({...pending,state:'failed',retryable:true}));
  await settle();
});

it('reads status after an uncertain POST instead of repeating the paid request',async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new Error('Connection lost'))
    .mockImplementationOnce(()=>response({...pending,state:'running'}))
    .mockImplementationOnce(()=>response({...pending,state:'failed',retryable:true,error:'preparation_interrupted'}));
  const ui=setup(fetch);
  await settle();
  expect(ui.status.textContent).toContain('Reconnecting');
  await ui.tick();
  await ui.tick();
  expect(fetch.mock.calls.map(([,options])=>options.method)).toEqual(['POST','GET','GET']);
  expect(ui.retry.hidden).toBe(false);
  expect(ui.timers).toHaveLength(0);
});

it('stops on an ownership or session error without retrying',async()=>{
  const fetch=vi.fn(async()=>({ok:false,json:async()=>({error:{message:'Reopen this lesson in your account.'}})}));
  const ui=setup(fetch);
  await settle();
  expect(ui.status.textContent).toBe('Reopen this lesson in your account.');
  expect(ui.spinner.hidden).toBe(true);
  expect(ui.root.getAttribute('aria-busy')).toBe('false');
  expect(ui.timers).toHaveLength(0);
  expect(ui.replace).not.toHaveBeenCalled();
});

it('uses a truthful allowance message and does not retry it automatically',async()=>{
  const ui=setup(vi.fn(),{...pending,state:'failed',error:'allowance_unavailable',retryable:true},'ru');
  expect(ui.status.textContent).toContain('Лимит ИИ недоступен.');
  expect(ui.status.textContent).toContain('Задание сохранено.');
  expect(ui.timers).toHaveLength(0);
});

it('stops queued polling when the page is hidden',async()=>{
  const fetch=vi.fn(()=>response({...pending,state:'running'}));
  const ui=setup(fetch);
  await settle();
  ui.events.pagehide();
  await ui.tick();
  expect(fetch).toHaveBeenCalledOnce();
  expect(ui.timers).toHaveLength(0);
});

it('ignores an in-flight ready response after leaving the page',async()=>{
  let resolve;
  const fetch=vi.fn(()=>new Promise(done=>{resolve=done;}));
  const ui=setup(fetch);
  ui.events.pagehide();
  resolve(await response({...pending,state:'ready',url:'/#practice/lesson1'}));
  await settle();
  expect(ui.replace).not.toHaveBeenCalled();
  expect(ui.timers).toHaveLength(0);
});
