import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {fireEvent} from '@testing-library/preact';

const script=readFileSync('../static/js/sequence_drafts.js','utf8');
const result=(body,status=200)=>({ok:status<400,status,json:async()=>body});
const tick=async()=>{for(let count=0;count<15;count++)await Promise.resolve();};
function setup(fetch,kind='writing',sequence=true){
  delete document[Symbol.for('russian-arcade.sequence-drafts')];
  document.head.innerHTML='<meta name="csrf-token" content="csrf"><meta name="learning-profile" content="p1"><meta name="learning-account" content="guest:1">';
  document.body.innerHTML=`<section class="writing-workspace reading-workspace"><a href="/demo/curriculum/units/unit?run=r1">Back to lesson</a><form ${sequence?`data-sequence-draft="${kind}"`:''} data-draft-language="en" data-draft-revision="0">
    <input name="exercise_id" value="w1"><input name="revision" value="0"><input name="task_id" value="r1"><input name="task_revision" value="0">
    ${kind==='writing'?'<textarea name="user_response" data-saved-value=""></textarea>':'<textarea name="answers[]"></textarea><textarea name="answers[]"></textarea>'}
    <button type="submit">Check</button><button type="submit" formaction="/demo/writing/save">Save</button><p class="sentence-draft-status" data-sequence-draft-status></p></form>
    <form data-writing-model-answer><button type="submit">Show example</button></form></section>`;
  const assign=vi.fn(),reload=vi.fn();
  const browser={location:{href:'https://example.com/demo/writing/load/1',assign,reload},confirm:vi.fn(()=>true),arcadeUrl:url=>url.startsWith('/')&&!url.startsWith('/demo/')?`/demo${url}`:url};
  runInNewContext(script,{document,window:browser,Symbol,WeakMap,URL,Element,Event,SubmitEvent,FormData,crypto,fetch,setTimeout:(...args)=>setTimeout(...args),clearTimeout:(id)=>clearTimeout(id)});
  const form=document.querySelector('form');
  return{form,field:form.querySelector('textarea'),fields:[...form.querySelectorAll('textarea')],status:form.querySelector('p'),assign,reload,check:form.querySelector('button'),save:form.querySelectorAll('button')[1]};
}
beforeEach(()=>vi.useFakeTimers());
afterEach(()=>{document.body.innerHTML='';document.head.innerHTML='';vi.clearAllTimers();vi.useRealTimers();vi.restoreAllMocks();});

it('autosaves only lesson editors after 800ms and acknowledges the exact saved text',async()=>{
  const fetch=vi.fn().mockResolvedValue(result({revision:1}));
  let ui=setup(fetch,'writing',false);fireEvent.input(ui.field,{target:{value:'Unrelated'}});
  await vi.advanceTimersByTimeAsync(900);expect(fetch).not.toHaveBeenCalled();
  let resolve;fetch.mockReturnValue(new Promise(done=>{resolve=done;}));
  ui=setup(fetch);expect(fetch).not.toHaveBeenCalled();
  fireEvent.input(ui.field,{target:{value:'  Я в школе.\n'}});
  await vi.advanceTimersByTimeAsync(799);expect(fetch).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);expect(ui.status.textContent).toBe('Saving…');
  expect(fetch.mock.calls[0][0]).toBe('/demo/writing/save');
  expect(fetch.mock.calls[0][1].body.get('user_response')).toBe('  Я в школе.\n');
  expect(fetch.mock.calls[0][1].headers).toMatchObject({'X-CSRF-Token':'csrf','X-Profile-ID':'p1','X-Account-Scope':'guest:1'});
  resolve(result({revision:1}));await tick();expect(ui.status.textContent).toBe('Saved');expect(ui.field.dataset.savedValue).toBe(ui.field.value);
});

it('serializes later edits without overwriting them and uses the acknowledged revision',async()=>{
  let resolve;const fetch=vi.fn().mockReturnValueOnce(new Promise(done=>{resolve=done;})).mockResolvedValue(result({revision:2}));
  const {field,form,status}=setup(fetch);
  fireEvent.input(field,{target:{value:'First'}});await vi.advanceTimersByTimeAsync(800);
  fireEvent.input(field,{target:{value:'Second'}});await vi.advanceTimersByTimeAsync(800);expect(fetch).toHaveBeenCalledTimes(1);
  resolve(result({revision:1}));await tick();
  expect(fetch).toHaveBeenCalledTimes(2);expect(fetch.mock.calls[1][1].body.get('revision')).toBe('1');
  expect(fetch.mock.calls[1][1].body.get('user_response')).toBe('Second');expect(field.value).toBe('Second');
  expect(form.elements.revision.value).toBe('2');expect(status.textContent).toBe('Saved');
});

it('uses the dedicated Reading draft API and resets its revision after a completed check',async()=>{
  const fetch=vi.fn().mockResolvedValue(result({revision:0,draft_revision:1}));
  const {fields,form,check}=setup(fetch,'reading');
  fireEvent.input(fields[0],{target:{value:'Она в школе.'}});await vi.advanceTimersByTimeAsync(800);
  expect(fetch.mock.calls[0][0]).toBe('/demo/api/v1/comprehension/tasks/r1/draft');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({expected_revision:0,expected_draft_revision:0,response:{answers:['Она в школе.','']}});
  const checked=vi.fn(event=>event.preventDefault());form.addEventListener('submit',checked);
  form.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:check}));await tick();expect(checked).toHaveBeenCalledTimes(1);
  form.elements.task_revision.value='1';form.dispatchEvent(new CustomEvent('htmx:afterRequest',{bubbles:true,detail:{elt:form,successful:true}}));
  fetch.mockResolvedValue(result({revision:1,draft_revision:1}));
  fireEvent.input(fields[1],{target:{value:'В парк.'}});await vi.advanceTimersByTimeAsync(800);
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({expected_revision:1,expected_draft_revision:0,response:{answers:['Она в школе.','В парк.']}});
  expect(fetch.mock.calls.every(([url])=>url.endsWith('/draft'))).toBe(true);
});

it('flushes before checking or revealing an example and prevents duplicate check dispatches',async()=>{
  let resolve;const fetch=vi.fn().mockReturnValue(new Promise(done=>{resolve=done;}));
  const {form,field,check}=setup(fetch);const checked=vi.fn(event=>event.preventDefault());form.addEventListener('submit',checked);
  fireEvent.input(field,{target:{value:'Draft'}});
  const submit=()=>form.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:check}));submit();submit();
  expect(checked).not.toHaveBeenCalled();resolve(result({revision:1}));await tick();expect(checked).toHaveBeenCalledTimes(1);
  form.dispatchEvent(new Event('sequence:editor-settled'));
  fetch.mockResolvedValue(result({revision:2}));fireEvent.input(field,{target:{value:'Later draft'}});
  const help=document.querySelector('[data-writing-model-answer]'),revealed=vi.fn(event=>event.preventDefault());help.addEventListener('submit',revealed);
  help.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:help.querySelector('button')}));
  expect(revealed).not.toHaveBeenCalled();await tick();expect(revealed).toHaveBeenCalledTimes(1);expect(form.elements.revision.value).toBe('2');
});

it('keeps a failed navigation draft, retries the same command, and only then returns to its lesson',async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(result({revision:1}));
  const {field,assign}=setup(fetch);fireEvent.input(field,{target:{value:'Keep me'}});
  fireEvent.click(document.querySelector('a'));await tick();
  expect(assign).not.toHaveBeenCalled();expect(field.value).toBe('Keep me');
  expect(document.body.textContent).toContain('Leave without saving');
  fireEvent.click([...document.querySelectorAll('button')].find(button=>button.textContent==='Retry save'));await tick();
  expect(fetch.mock.calls[1][1].body).toBe(fetch.mock.calls[0][1].body);
  expect(assign).toHaveBeenCalledWith('http://localhost:3000/demo/curriculum/units/unit?run=r1');
});

it('preserves conflicting text and requires explicit discard before failed-save navigation',async()=>{
  const fetch=vi.fn().mockResolvedValue(result({error:{code:'stale_revision',message:'Changed'}},409));
  const {field,assign}=setup(fetch);fireEvent.input(field,{target:{value:'My text'}});
  fireEvent.click(document.querySelector('a'));await tick();
  expect(field.value).toBe('My text');expect(document.querySelector('textarea[readonly]').value).toBe('My text');
  expect(document.body.textContent).not.toContain('Retry save');expect(assign).not.toHaveBeenCalled();
  fireEvent.click([...document.querySelectorAll('button')].find(button=>button.textContent==='Leave without saving'));
  expect(assign).toHaveBeenCalledTimes(1);expect(fetch).toHaveBeenCalledTimes(1);
});

it('keeps new text local while the original reply awaits feedback',async()=>{
  const fetch=vi.fn();const {form,field}=setup(fetch);form.dataset.reviewPending='true';
  fireEvent.input(field,{target:{value:'A later edit'}});await vi.advanceTimersByTimeAsync(800);
  expect(fetch).not.toHaveBeenCalled();expect(field.value).toBe('A later edit');
  expect(document.body.textContent).toContain('Finish its feedback before editing');
  expect(document.querySelector('textarea[readonly]').value).toBe('A later edit');
});

it('blocks another Check after the original is saved even when its text has not changed',async()=>{
  const fetch=vi.fn();const {form,check}=setup(fetch);const submit=vi.fn(event=>event.preventDefault());form.addEventListener('submit',submit);
  form.dataset.reviewPending='true';form.dispatchEvent(new Event('sequence:editor-settled'));
  expect(check.disabled).toBe(true);
  form.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:check}));await tick();
  expect(submit).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();
});

it('adopts the Reading pending-review response and preserves the explicit saved-reply retry',async()=>{
  const fetch=vi.fn();const {form,check}=setup(fetch,'reading');
  form.closest('.reading-workspace').insertAdjacentHTML('beforeend','<div data-reading-review-pending><form action="/comprehension/review/original" method="post"><button type="submit">Retry feedback on saved reply</button></form></div>');
  form.dispatchEvent(new CustomEvent('htmx:afterRequest',{bubbles:true,detail:{elt:form,successful:false}}));
  expect(form.dataset.reviewPending).toBe('true');expect(check.disabled).toBe(true);
  const retry=document.querySelector('[data-reading-review-pending] form');const sent=vi.fn(event=>event.preventDefault());retry.addEventListener('submit',sent);
  retry.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:retry.querySelector('button')}));await tick();
  expect(sent).toHaveBeenCalledTimes(1);expect(fetch).not.toHaveBeenCalled();
});
