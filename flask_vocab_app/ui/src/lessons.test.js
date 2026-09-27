import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const script = readFileSync('../static/js/lessons.js', 'utf8');
let dom, w, form;
beforeEach(() => {
  dom = new JSDOM(`<html lang="en"><body><main class="lesson-page">
    <form action="/check" data-lesson-editor data-save-url="/draft">
      <input name="draft_revision" value="0"><input name="submission_key" value="original-key">
      <textarea name="answer" data-saved=""></textarea>
      <button type="submit">Check</button><button type="button" data-lesson-save>Save</button>
      <span data-draft-status></span><span data-check-status></span>
    </form><form action="/bookmark" data-lesson-bookmark><span role="status"></span></form>
    </main></body></html>`, {url:'http://localhost/lessons', runScripts:'outside-only'});
  w = dom.window;
  w.fetch = vi.fn();
  w.eval(script);
  form = w.document.querySelector('[data-lesson-editor]');
});
afterEach(() => dom.window.close());
const result = (body, ok = true) => ({ok, json:async () => body});
const clickSave = () => form.querySelector('[data-lesson-save]').click();
const submit = target => target.dispatchEvent(new w.Event('submit', {bubbles:true, cancelable:true}));

it('serializes saves so a newer draft uses the returned revision', async () => {
  let finishFirst;
  w.fetch.mockImplementationOnce(() => new Promise(resolve => { finishFirst = resolve; }))
    .mockResolvedValueOnce(result({revision:2}));
  form.elements.answer.value = 'Первый ответ';
  clickSave();
  await vi.waitFor(() => expect(w.fetch).toHaveBeenCalledTimes(1));
  form.elements.answer.value = 'Новый ответ';
  clickSave();
  expect(w.fetch).toHaveBeenCalledTimes(1);
  finishFirst(result({revision:1}));
  await vi.waitFor(() => expect(form.elements.draft_revision.value).toBe('2'));
  const [url, options] = w.fetch.mock.calls[1];
  expect(url).toBe('/draft');
  expect(options.body.get('draft_revision')).toBe('1');
  expect(options.body.get('answer')).toBe('Новый ответ');
  expect(form.elements.answer.dataset.saved).toBe('Новый ответ');
});

it('does not send an answer for checking when saving it conflicts', async () => {
  w.fetch.mockResolvedValue(result({error:'A newer draft was saved elsewhere.'}, false));
  form.elements.answer.value = 'Мой ответ';
  submit(form);
  await vi.waitFor(() => expect(form.querySelector('[data-check-status]').textContent).toContain('newer draft'));
  expect(w.fetch).toHaveBeenCalledTimes(1);
  expect(w.fetch.mock.calls[0][0]).toBe('/draft');
  expect(form.elements.answer.value).toBe('Мой ответ');
  expect(form.elements.answer.readOnly).toBe(false);
});

it('saves before grading and retains the draft after a provider failure', async () => {
  w.fetch.mockResolvedValueOnce(result({revision:1}))
    .mockResolvedValueOnce(result({error:'Checking is temporarily unavailable.'}, false));
  form.elements.answer.value = 'Мой ответ';
  submit(form);
  await vi.waitFor(() => expect(form.querySelector('[data-check-status]').textContent).toContain('unavailable'));
  expect(w.fetch.mock.calls.map(call => call[0])).toEqual(['/draft', 'http://localhost/check']);
  expect(w.fetch.mock.calls[1][1].body.get('draft_revision')).toBe('1');
  expect(form.elements.answer.dataset.saved).toBe('Мой ответ');
  expect(form.querySelector('button').disabled).toBe(false);
});

it('reports a failed bookmark without claiming the place was saved', async () => {
  w.fetch.mockResolvedValue(result({error:'Connection failed.'}, false));
  const bookmark = w.document.querySelector('[data-lesson-bookmark]');
  submit(bookmark);
  await vi.waitFor(() => expect(bookmark.querySelector('[role=status]').textContent).toBe('Connection failed.'));
});


it('retains a lesson card preparation failure and allows a deliberate retry',async()=>{
  const cardForm=w.document.createElement('form');
  cardForm.action='/prepare-cards';cardForm.dataset.lessonCardsPrepare='';
  cardForm.innerHTML='<input name="csrf_token" value="token"><p data-card-status></p><button>Continue</button>';
  w.document.body.append(cardForm);
  w.fetch.mockResolvedValue(result({state:'failed',error:'Choose pages with complete sentences.'}));
  submit(cardForm);
  await vi.waitFor(()=>expect(cardForm.querySelector('[data-card-status]').textContent).toContain('complete sentences'));
  expect(cardForm.querySelector('button').disabled).toBe(false);
  expect(w.fetch).toHaveBeenCalledTimes(1);
  expect(w.fetch.mock.calls[0][1].body.get('csrf_token')).toBe('token');
});

it('keeps the viewport and page zoom through a lesson pagination swap',()=>{
  const target=w.document.createElement('div');
  target.innerHTML='<form data-lesson-page-nav></form><div class="lesson-word-scroll"><div class="lesson-word-sheet is-enlarged"></div></div>';
  w.document.body.append(target);
  target.querySelector('.lesson-word-scroll').scrollLeft=120;
  Object.defineProperty(w,'scrollY',{value:420,configurable:true});
  w.scrollTo=vi.fn();
  const xhr={},requestConfig={elt:target.querySelector('form')};
  w.document.dispatchEvent(new w.CustomEvent('htmx:beforeSwap',{detail:{xhr,target,requestConfig,shouldSwap:true}}));
  target.innerHTML='<button data-word-zoom>Enlarge page</button><div class="lesson-word-scroll"><div class="lesson-word-sheet"></div></div>';
  w.document.dispatchEvent(new w.CustomEvent('htmx:afterSwap',{detail:{xhr,target}}));
  expect(w.scrollTo).toHaveBeenCalledWith({left:0,top:420,behavior:'instant'});
  expect(target.querySelector('.lesson-word-sheet').classList.contains('is-enlarged')).toBe(true);
  expect(target.querySelector('.lesson-word-scroll').scrollLeft).toBe(120);
  expect(target.querySelector('[data-word-zoom]').textContent).toBe('Fit page');
  expect(target.style.minHeight).toBe('');
});

it('does not restore lesson pagination scroll on an unrelated or failed swap',()=>{
  w.scrollTo=vi.fn();const target=w.document.querySelector('main'),xhr={};
  w.document.dispatchEvent(new w.CustomEvent('htmx:beforeSwap',{detail:{xhr,target,shouldSwap:false,requestConfig:{elt:form}}}));
  w.document.dispatchEvent(new w.CustomEvent('htmx:afterSwap',{detail:{xhr,target}}));
  expect(w.scrollTo).not.toHaveBeenCalled();
});
