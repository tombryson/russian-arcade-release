import {afterEach, beforeAll, expect, it, vi} from 'vitest';
import {fireEvent, waitFor} from '@testing-library/preact';
import {readFileSync} from 'node:fs';
beforeAll(() => window.eval(readFileSync('../static/js/comprehension_listening.js', 'utf8')));
afterEach(() => {document.body.innerHTML=''; document.head.innerHTML=''; vi.unstubAllGlobals();});
function setup() {
  document.head.innerHTML='<meta name="learning-profile" content="me"><meta name="learning-account" content="local"><meta name="csrf-token" content="token">';
  document.body.innerHTML=`<article data-listening-task="one" data-listened="false" data-transcript-visible="false">
    <h2 id="reading-story-title">Listening practice</h2><audio data-comprehension-audio></audio>
    <button data-show-transcript>Show transcript</button><button data-retry-listened hidden>Retry</button><p data-listening-status></p>
    <div data-comprehension-transcript hidden><div id="story-container" data-story-id="7" data-task-id="one"></div></div>
    <form id="question-form" data-listened="false" data-transcript-visible="false"><input name="task_id" value="one"><input name="task_revision" value="0"><fieldset data-listening-answers disabled><textarea>My draft</textarea></fieldset></form></article>`;
  document.dispatchEvent(new CustomEvent('htmx:afterSwap'));
  return {article:document.querySelector('article'), fields:document.querySelector('fieldset'), audio:document.querySelector('audio'), transcript:document.querySelector('[data-show-transcript]')};
}
const response=(extra={}) => ({ok:true,json:async()=>({task_id:'one',revision:0,listened:true,transcript_visible:false,...extra})});
it('keeps text hidden and enables answers after saved playback',async()=>{
  const v=setup(); const fetch=vi.fn().mockResolvedValue(response()); vi.stubGlobal('fetch',fetch);
  expect(v.fields.disabled).toBe(true); fireEvent(v.audio,new Event('ended'));
  await waitFor(()=>expect(v.fields.disabled).toBe(false));
  expect(document.querySelector('[data-comprehension-transcript]').hidden).toBe(true);
  expect(JSON.parse(fetch.mock.calls[0][1].body).operation).toBe('listened');
  expect(fetch.mock.calls[0][1].headers['X-CSRFToken']).toBe('token');
});
it('reveals plain transcript text only after the receipt saves',async()=>{
  const v=setup(); const fetch=vi.fn().mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce(response({transcript_visible:true,text:'Кот <script>bad</script>',words:[],title:'Кот',title_en:'A cat',capture_key:'key'})); vi.stubGlobal('fetch',fetch);
  fireEvent.click(v.transcript); await waitFor(()=>expect(v.transcript.disabled).toBe(false));
  expect(v.fields.disabled).toBe(true); expect(document.querySelector('[data-comprehension-transcript]').hidden).toBe(true);
  fireEvent.click(v.transcript); await waitFor(()=>expect(v.fields.disabled).toBe(false));
  expect(document.querySelector('#story-container').textContent).toBe('Кот <script>bad</script>');
  expect(document.querySelector('#story-container script')).toBeNull();
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
});
it('retries playback with the same receipt key and preserves the draft',async()=>{
  const v=setup(); const fetch=vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(response()); vi.stubGlobal('fetch',fetch);
  fireEvent(v.audio,new Event('ended')); const retry=document.querySelector('[data-retry-listened]');
  await waitFor(()=>expect(retry.hidden).toBe(false)); expect(v.fields.disabled).toBe(true);
  fireEvent.click(retry); await waitFor(()=>expect(v.fields.disabled).toBe(false));
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
  expect(document.querySelector('textarea').value).toBe('My draft');
});
it.each(['revision','profile','account','detached'])('ignores delayed transcript after %s changes',async kind=>{
  const v=setup(); let resolve; vi.stubGlobal('fetch',vi.fn(()=>new Promise(done=>{resolve=done;})));
  fireEvent.click(v.transcript);
  if(kind==='revision') document.querySelector('[name="task_revision"]').value='1';
  if(kind==='profile') document.querySelector('[name="learning-profile"]').content='other';
  if(kind==='account') document.querySelector('[name="learning-account"]').content='other';
  if(kind==='detached') v.article.remove();
  resolve(response({transcript_visible:true,text:'SECRET',words:[],title:'Кот'}));
  await new Promise(done=>setTimeout(done,0)); expect(v.article.textContent).not.toContain('SECRET');
});
it('follows the task issued by More questions',async()=>{
  const v=setup(); const fetch=vi.fn().mockResolvedValue(response({task_id:'two'})); vi.stubGlobal('fetch',fetch);
  document.querySelector('[name="task_id"]').value='two';
  v.article.dispatchEvent(new CustomEvent('htmx:afterSwap',{bubbles:true})); fireEvent(v.audio,new Event('ended'));
  await waitFor(()=>expect(v.fields.disabled).toBe(false));
  expect(fetch.mock.calls[0][0]).toBe('/comprehension/tasks/two/support');
  expect(document.querySelector('#story-container').dataset.taskId).toBe('two');
  expect(document.querySelector('[data-comprehension-transcript]').hidden).toBe(true);
});
