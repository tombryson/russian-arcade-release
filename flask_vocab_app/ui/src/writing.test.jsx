import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/preact';
import { readFileSync } from 'node:fs';
beforeAll(() => {
    for (const name of ['activity_editor.js','writing_tools.js','translation.js']) window.eval(readFileSync('../static/js/'+name,'utf8'));
});
afterEach(() => {
    document.body.dispatchEvent(new CustomEvent('htmx:beforeHistorySave',{bubbles:true}));
    document.body.innerHTML='';
    document.body.dispatchEvent(new CustomEvent('htmx:afterSwap',{bubbles:true,detail:{}}));
    vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals();
});
function setup(text='Мой город красивый.') {
    document.body.innerHTML=`<main id="mainContent"><h1 id="sentence-page-title" tabindex="-1">My town</h1><section class="sentence-workspace" data-game-id="1" data-leave-message="Discard writing?" data-network-error="Try again." data-unsaved="Unsaved" data-checking="Reading…" data-saving="Saving…">
    <button data-insert-word="парк">парк</button><form data-writing-editor action="/writing/assess" method="post"><input name="exercise_id" value="1"><input name="revision" value="0">
    <div data-writing-count>Words: <span>0</span></div><textarea name="user_response" maxlength="20000" data-saved-value=""></textarea><button type="submit">Check</button><button type="submit" formaction="/writing/save">Save</button><span class="sentence-draft-status"></span></form>
    <details data-writing-timer data-start="Start" data-pause="Pause" data-finished="Time’s up. Keep writing if you like."><summary>Optional focus timer</summary><select><option value="5">5</option><option value="10" selected>10</option></select><output>10:00</output><button data-timer-toggle>Start</button><button data-timer-reset>Reset</button><p data-timer-status></p></details>
    <div id="sentence-action-status"></div><div id="sentence-feedback">Previous feedback</div></section></main>`;
    const form=document.querySelector('form');
    form.elements.user_response.value=text;
    document.body.dispatchEvent(new CustomEvent('htmx:afterSwap',{bubbles:true,detail:{}}));
    return {form,field:form.elements.user_response,check:form.querySelector('button'),save:form.querySelectorAll('button')[1]};
}
function submit(form,submitter) {form.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter}));}
function result(ok,data) {return {ok,headers:new Headers({'content-type':'application/json'}),json:async()=>data};}

describe('writing editor and aids',()=>{
    it('counts Russian writing and inserts a word at the caret',()=>{
        const {field}=setup('Привет, мир! Где-то дома.');
        expect(document.querySelector('[data-writing-count] span').textContent).toBe('4');
        field.setSelectionRange(field.value.length,field.value.length);
        fireEvent.click(document.querySelector('[data-insert-word]'));
        expect(field.value).toBe('Привет, мир! Где-то дома. парк');
        expect(document.querySelector('[data-writing-count] span').textContent).toBe('5');
        expect(document.querySelector('.sentence-draft-status').textContent).toBe('Unsaved');
    });
    it('saves the task ID and exact draft without replacing the editor or later edits',async()=>{
        const {form,field,save}=setup('  «Мой город»\nЕсть парк.');
        let resolve; const fetch=vi.fn().mockReturnValue(new Promise(done=>{resolve=done;})); vi.stubGlobal('fetch',fetch);
        submit(form,save); fireEvent.input(field,{target:{value:'Новая строка.'}});
        resolve(result(true,{revision:1,message:'Saved.',feedback:''}));
        await waitFor(()=>expect(save.disabled).toBe(false));
        expect(fetch.mock.calls[0][0]).toBe('/writing/save');
        expect(fetch.mock.calls[0][1].body.get('exercise_id')).toBe('1');
        expect(fetch.mock.calls[0][1].body.get('user_response')).toBe('  «Мой город»\nЕсть парк.');
        expect(field.value).toBe('Новая строка.');
        expect(field.dataset.savedValue).toBe('  «Мой город»\nЕсть парк.');
        expect(document.querySelector('textarea')).toBe(field);
        const confirm=vi.spyOn(window,'confirm').mockReturnValue(false);
        const nav=new CustomEvent('htmx:beforeRequest',{bubbles:true,cancelable:true,detail:{target:document.getElementById('mainContent')}});
        document.body.dispatchEvent(nav);
        expect(nav.defaultPrevented).toBe(true);expect(confirm).toHaveBeenCalledWith('Discard writing?');
    });
    it('keeps writing and past feedback when a check fails',async()=>{
        const {form,field,check}=setup();
        vi.stubGlobal('fetch',vi.fn().mockResolvedValue(result(false,{error:'Check unavailable. Save a draft.'})));
        submit(form,check);
        await waitFor(()=>expect(check.disabled).toBe(false));
        expect(field.value).toBe('Мой город красивый.');
        expect(document.getElementById('sentence-feedback').textContent).toBe('Previous feedback');
        expect(form.elements.revision.value).toBe('0');
    });
    it('starts only on request, pauses accurately and never locks the editor at expiry',()=>{
        vi.useFakeTimers(); const {field,check,save}=setup();
        const toggle=document.querySelector('[data-timer-toggle]');
        vi.advanceTimersByTime(60000);expect(document.querySelector('output').textContent).toBe('10:00');
        fireEvent.click(toggle);vi.advanceTimersByTime(61000);fireEvent.click(toggle);
        expect(document.querySelector('output').textContent).toBe('8:59');
        vi.advanceTimersByTime(60000);expect(document.querySelector('output').textContent).toBe('8:59');
        fireEvent.click(toggle);vi.advanceTimersByTime(539000);
        expect(document.querySelector('[data-timer-status]').textContent).toContain('Time’s up');
        expect(field.disabled).toBe(false);expect(check.disabled).toBe(false);expect(save.disabled).toBe(false);
        fireEvent.click(document.querySelector('[data-timer-reset]'));
        expect(document.querySelector('output').textContent).toBe('10:00');
    });
    it('resets the timer and preserves a draft when storing navigation history',()=>{
        vi.useFakeTimers(); const {field}=setup('Черновик.');
        fireEvent.click(document.querySelector('[data-timer-toggle]'));vi.advanceTimersByTime(10000);
        document.body.dispatchEvent(new CustomEvent('htmx:beforeHistorySave',{bubbles:true}));
        expect(field.textContent).toBe('Черновик.');
        expect(document.querySelector('output').textContent).toBe('10:00');
        expect(document.querySelector('[data-timer-toggle]').textContent).toBe('Start');
        expect(vi.getTimerCount()).toBe(0);
    });
    it('retains writing setup on failure and offers a prepared task after settings change',async()=>{
        document.body.innerHTML=`<form data-writing-prepare action="/writing/generate" data-ready="Open task" data-pending="Preparing…" data-error="Try again."><select name="target_words"><option value="30">30</option><option value="100">100</option></select><button type="submit">Create</button><p data-prepare-status></p></form>`;
        const form=document.querySelector('form');let resolve;
        const fetch=vi.fn().mockReturnValue(new Promise(done=>{resolve=done;}));vi.stubGlobal('fetch',fetch);
        submit(form,form.querySelector('button'));form.elements.target_words.value='100';
        resolve(result(true,{url:'/writing/load/9'}));
        await waitFor(()=>expect(form.querySelector('a')).not.toBeNull());
        expect(form.querySelector('a').getAttribute('href')).toBe('/writing/load/9');
        expect(form.elements.target_words.value).toBe('100');
        fetch.mockResolvedValue(result(false,{error:'Preparation unavailable.'}));
        submit(form,form.querySelector('button'));
        await waitFor(()=>expect(form.querySelector('[data-prepare-status]').textContent).toBe('Preparation unavailable.'));
        expect(form.elements.target_words.value).toBe('100');
    });
});
