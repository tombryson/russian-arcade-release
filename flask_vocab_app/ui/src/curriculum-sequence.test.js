import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {afterEach, expect, it, vi} from 'vitest';
import {fireEvent, waitFor} from '@testing-library/preact';

const script = readFileSync('../static/js/curriculum_sequence.js','utf8');
const steps = [{id:'forms',label:'Word forms',label_ru:'Формы слов',availability:'available',work_state:'not_started'},{id:'speaking',label:'Speaking',label_ru:'Говорение',availability:'audio_unavailable',work_state:'not_started'},{id:'transfer',label:'New situation',label_ru:'Новая ситуация',availability:'available',work_state:'not_started'}];
const run={id:'r1',profile_id:'p1',revision:0,completed:false,completion_path:'guided',steps,next_action:{step_id:'forms',label:'Word forms'}};
const response = value => Promise.resolve({ok:true,json:async()=>value});
function setup(fetch, saved=null, teaching='', nextUnit=null, language='en') {
  delete document[Symbol.for('russian-arcade.curriculum-sequence')];
  document.head.innerHTML='<meta name="csrf-token" content="csrf"><meta name="learning-profile" content="p1"><meta name="learning-account" content="guest:1">';
  document.body.innerHTML=`<section data-curriculum-sequence data-profile-id="p1" data-language="${language}"><script data-sequence-data type="application/json"></script><button data-sequence-continue></button><button data-sequence-repeat hidden>Practise again</button><p data-sequence-status></p><details data-sequence-results hidden><summary>Recent assessed work</summary><div data-sequence-results-body></div></details><ol data-sequence-steps></ol><div data-sequence-error hidden></div></section>`;
  document.querySelector('script').textContent=JSON.stringify({id:'seq-v1',unit_id:'unit-v2',steps,run:saved,next_unit:nextUnit});
  document.body.insertAdjacentHTML('beforeend',teaching);
  const assign=vi.fn();
  const browser={location:{href:'https://example.com/demo/curriculum/units/unit-v2',hash:'',assign},history:{replaceState:vi.fn(),state:null},arcadeUrl: url=>url.startsWith('/demo/')?url:`/demo${url}`,addEventListener:vi.fn()};
  runInNewContext(script,{document,window:browser,Symbol,URL,fetch,crypto});
  return {assign,browser};
}
afterEach(()=>{document.body.innerHTML='';document.head.innerHTML='';vi.restoreAllMocks();});

it('shows truthful availability without allocating on page load, then starts within the demo workspace',async()=>{
  const fetch=vi.fn((url)=>response(url.endsWith('/runs')?run:{url:'/#practice/s1',run:{...run,revision:1}}));
  const {assign}=setup(fetch);
  expect(fetch).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain('Audio unavailable');
  expect(document.querySelector('[data-step-id="speaking"] button')).toBeNull();
  expect(document.getElementById('sequence-step-forms').dataset.stepId).toBe('forms');
  fireEvent.click(document.querySelector('[data-sequence-continue]'));
  await waitFor(()=>expect(assign).toHaveBeenCalledWith('/demo/#practice/s1'));
  expect(fetch.mock.calls[0][0]).toBe('/demo/api/v1/curriculum/units/unit-v2/runs');
  expect(fetch.mock.calls[0][1].headers).toMatchObject({'X-CSRF-Token':'csrf','X-Profile-ID':'p1','X-Account-Scope':'guest:1'});
});

it.each(['en','ru'])('offers the named next lesson and optional saved domain results in %s without allocating work',async language=>{
  const complete={...run,completed:true,next_action:null};
  const domains=['Grammar','Listening','Reading','Writing','Speaking'].map((label,index)=>({label,label_ru:`Навык ${index}`,latest:index===4?{level:'A1',scope_label:'A short location exchange',scope_label_ru:'Короткий разговор о месте',date:'2026-10-02',outcome:'demonstrated_in_task',condition:'unverified',support:['model_answer']}:null,pending:index===3?{state:'review_unavailable'}:null}));
  const fetch=vi.fn(url=>response(url.endsWith('/summary')?{domains}:complete));
  const {assign}=setup(fetch,complete,'',{url:'/curriculum/units/origins-and-destinations-v1',title:'Where from?',title_ru:'Откуда?'},language);
  await waitFor(()=>expect(document.querySelector('[data-sequence-continue]').disabled).toBe(false));
  expect(document.querySelector('[data-sequence-continue]').textContent).toContain(language==='ru'?'Откуда?':'Where from?');
  expect(document.querySelector('[data-sequence-repeat]').hidden).toBe(false);
  expect(document.querySelector('[data-sequence-results]').hidden).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(1);
  fireEvent.click(document.querySelector('[data-sequence-continue]'));
  expect(assign).toHaveBeenCalledWith('/demo/curriculum/units/origins-and-destinations-v1');expect(fetch).toHaveBeenCalledTimes(1);
  const details=document.querySelector('[data-sequence-results]');details.open=true;fireEvent(details,new Event('toggle'));
  await waitFor(()=>expect(details.querySelectorAll('dt')).toHaveLength(5));
  expect(details.textContent).toContain(language==='ru'?'Короткий разговор о месте':'A short location exchange');
  expect(details.textContent).toContain(language==='ru'?'С помощью':'With help');
  expect(details.textContent).toContain(language==='ru'?'Самостоятельность выполнения не проверялась.':'Independent conditions were not checked.');
  expect(details.textContent).toContain(language==='ru'?'Ответ сохранён; отзыв пока недоступен.':'Reply saved; feedback is unavailable.');
  expect(fetch.mock.calls.every(([,options])=>options.method==='GET')).toBe(true);
  expect(fetch.mock.calls[1][1].headers).toMatchObject({'X-Profile-ID':'p1','X-Account-Scope':'guest:1'});
});

it('switches the completion path explicitly before opening the early transfer challenge',async()=>{
  const fetch=vi.fn((url)=>response(url.endsWith('/runs')?run:url.endsWith('/navigation')?{run:{...run,revision:1,completion_path:'challenge'},url:'/curriculum/units/unit-v2?run=r1'}:{url:'/#practice/t1',run:{...run,revision:2,completion_path:'challenge'}}));
  const {assign}=setup(fetch);
  fireEvent.click(document.querySelector('[data-step-id="transfer"] button'));
  await waitFor(()=>expect(assign).toHaveBeenCalled());
  const navigation=fetch.mock.calls.find(([url])=>url.endsWith('/navigation'));
  expect(JSON.parse(navigation[1].body)).toMatchObject({completion_path:'challenge',step_id:'transfer',expected_revision:0});
  expect(JSON.parse(fetch.mock.calls.at(-1)[1].body).expected_revision).toBe(1);
});

it('retries an uncertain start with the identical request rather than creating another run',async()=>{
  let starts=0;
  const fetch=vi.fn((url)=>url.endsWith('/runs')?++starts===1?Promise.reject(new Error('Offline')):response(run):response({url:'/#practice/s1',run}));
  const {assign}=setup(fetch);
  fireEvent.click(document.querySelector('[data-sequence-continue]'));
  await waitFor(()=>expect(document.querySelector('[data-sequence-error] button')).toBeTruthy());
  fireEvent.click(document.querySelector('[data-sequence-error] button'));
  await waitFor(()=>expect(assign).toHaveBeenCalled());
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
});

it('plays teaching examples one at a time without allocating learner work and pauses when examples close',()=>{
  const pause=vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  const play=vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
  const fetch=vi.fn();
  setup(fetch,null,'<details><audio data-teaching-audio controls preload="none"></audio><audio data-teaching-audio controls preload="none"></audio></details>');
  const [first,second]=document.querySelectorAll('audio');
  expect(play).not.toHaveBeenCalled();
  fireEvent.play(first);
  expect(pause.mock.contexts).toEqual([second]);
  pause.mockClear();
  const details=first.closest('details');
  fireEvent(details,new Event('toggle'));
  expect(pause.mock.contexts).toEqual([first,second]);
  expect(fetch).not.toHaveBeenCalled();
});

it('shows a recoverable audio error while keeping the teaching text readable',()=>{
  setup(vi.fn(),null,'<dl><dt>Встретимся в парке.</dt><dd><audio data-teaching-audio controls preload="none"></audio><span data-teaching-audio-error hidden>Audio is unavailable. You can keep reading the examples.</span></dd></dl>');
  const audio=document.querySelector('audio'),status=document.querySelector('[data-teaching-audio-error]');
  fireEvent.error(audio);
  expect(status.hidden).toBe(false);
  expect(document.querySelector('dt').textContent).toBe('Встретимся в парке.');
  fireEvent.loadedData(audio);
  expect(status.hidden).toBe(true);
});
