import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/preact';
import { readFileSync } from 'node:fs';
const editorSource = readFileSync('../static/js/activity_editor.js', 'utf8');
const translationSource = readFileSync('../static/js/translation.js', 'utf8');
beforeAll(() => { window.eval(editorSource); window.eval(translationSource); });
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function workspace() {
    document.body.innerHTML = `<main id="mainContent"><section class="sentence-workspace" data-game-id="12"
        data-leave-message="Discard translation?" data-network-error="Try again." data-unsaved="Unsaved changes"
        data-checking="Checking translation…" data-saving="Saving…">
        <p lang="en">The cat is at home.</p>
        <form data-translation-editor action="/sentence/assess" method="post">
        <input name="sentence_id" type="hidden" value="12"><input name="revision" type="hidden" value="0">
        <textarea name="user_response" data-saved-value=""></textarea>
        <button type="submit">Check</button><button type="submit" formaction="/sentence/save">Save</button>
        <span class="sentence-draft-status"></span></form>
        <div id="sentence-action-status"></div><div id="sentence-feedback">Earlier feedback</div></section></main>`;
    const form = document.querySelector('form');
    const field = form.querySelector('textarea');
    field.value = 'Кот дома.';
    return { form, field, check: form.querySelector('button'), save: form.querySelectorAll('button')[1] };
}
function submit(form, submitter) {
    form.dispatchEvent(new SubmitEvent('submit', { bubbles:true, cancelable:true, submitter }));
}
function response(ok, data) {
    return { ok, headers:new Headers({'content-type':'application/json'}), json:async()=>data };
}
function prepareForm() {
    document.body.innerHTML = `<form data-translation-prepare action="/sentence/generate" method="post"
        data-pending="Preparing…" data-ready="Open prepared sentence" data-error="Try a saved sentence.">
        <select name="topic"><option value="home">Home</option><option value="school">School</option></select>
        <select name="difficulty"><option value="1">Beginner</option><option value="2">Elementary</option></select>
        <button type="submit">Create</button><p data-prepare-status></p></form>`;
    return document.querySelector('form');
}

describe('translation editor', () => {
    it('checks the Russian answer against a saved ID and refreshes progress without replacing writing', async () => {
        const { form, field, check } = workspace();
        const fetch = vi.fn().mockResolvedValue(response(true, { revision:1, message:'Checked and saved.', feedback:'<p>3/4 · Useful feedback</p>' }));
        vi.stubGlobal('fetch', fetch);
        const progress = vi.fn();
        document.body.addEventListener('activity:checked', progress, { once:true });
        submit(form, check);
        expect(document.getElementById('sentence-action-status').textContent).toBe('Checking translation…');
        await waitFor(() => expect(field.dataset.savedValue).toBe('Кот дома.'));
        const data = fetch.mock.calls[0][1].body;
        expect(data.get('sentence_id')).toBe('12');
        expect(data.get('user_response')).toBe('Кот дома.');
        expect(data.has('sentence')).toBe(false);
        expect(data.has('english')).toBe(false);
        expect(document.querySelector('textarea')).toBe(field);
        expect(progress).toHaveBeenCalledTimes(1);
    });

    it('saves drafts separately and protects later edits from a delayed save', async () => {
        const { form, field, save } = workspace();
        let resolve;
        const fetch = vi.fn().mockReturnValue(new Promise(done => { resolve = done; }));
        vi.stubGlobal('fetch', fetch);
        submit(form, save);
        fireEvent.input(field, {target:{value:'Кот спит дома.'}});
        resolve(response(true, { revision:1, message:'Saved.', feedback:'' }));
        await waitFor(() => expect(save.disabled).toBe(false));
        expect(fetch.mock.calls[0][0]).toBe('/sentence/save');
        expect(field.value).toBe('Кот спит дома.');
        expect(field.dataset.savedValue).toBe('Кот дома.');
        const confirm = vi.spyOn(window,'confirm').mockReturnValue(false);
        const request = new CustomEvent('htmx:beforeRequest',{bubbles:true,cancelable:true,detail:{target:document.getElementById('mainContent')}});
        document.body.dispatchEvent(request);
        expect(request.defaultPrevented).toBe(true);
        expect(confirm).toHaveBeenCalledWith('Discard translation?');
    });

    it('retains the answer and earlier feedback when checking fails', async () => {
        const { form, field, check } = workspace();
        vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(false,{error:'Check unavailable. Save your draft.'})));
        submit(form, check);
        await waitFor(() => expect(document.getElementById('sentence-action-status').textContent).toContain('Check unavailable'));
        expect(field.value).toBe('Кот дома.');
        expect(document.getElementById('sentence-feedback').textContent).toBe('Earlier feedback');
        expect(form.elements.revision.value).toBe('0');
    });
});

describe('translation preparation and optional audio', () => {
    it('preserves setup on failed generation without submitting twice', async () => {
        const form = prepareForm();
        let resolve;
        const fetch = vi.fn().mockReturnValue(new Promise(done=>{resolve=done;}));
        vi.stubGlobal('fetch',fetch);
        form.elements.topic.value='school';
        submit(form,form.querySelector('button'));
        submit(form,form.querySelector('button'));
        expect(fetch).toHaveBeenCalledTimes(1);
        resolve(response(false,{error:'Generation unavailable.'}));
        await waitFor(()=>expect(form.querySelector('button').disabled).toBe(false));
        expect(form.elements.topic.value).toBe('school');
        expect(form.querySelector('[data-prepare-status]').textContent).toBe('Generation unavailable.');
    });

    it('offers the prepared result without discarding settings changed during the request', async () => {
        const form = prepareForm();
        let resolve;
        vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(done=>{resolve=done;})));
        submit(form,form.querySelector('button'));
        form.elements.difficulty.value='2';
        resolve(response(true,{url:'/sentences/practice/12'}));
        await waitFor(()=>expect(form.querySelector('[data-prepare-status] a')).not.toBeNull());
        expect(form.querySelector('a').textContent).toBe('Open prepared sentence');
        expect(form.elements.difficulty.value).toBe('2');
    });

    it('loads audio independently and keeps feedback on audio failure', async () => {
        const { field } = workspace();
        document.getElementById('sentence-feedback').insertAdjacentHTML('beforeend',`<div class="translation-audio">
          <button data-translation-audio="/sentence/audio/12" data-pending="Preparing audio…" data-error="Audio unavailable.">Audio</button><span data-audio-status></span></div>`);
        const button=document.querySelector('[data-translation-audio]');
        const fetch=vi.fn().mockResolvedValue(response(false,{error:'Audio unavailable.'}));
        vi.stubGlobal('fetch',fetch);
        fireEvent.click(button);
        await waitFor(()=>expect(button.disabled).toBe(false));
        expect(document.querySelector('[data-audio-status]').textContent).toBe('Audio unavailable.');
        expect(document.getElementById('sentence-feedback').textContent).toContain('Earlier feedback');
        expect(field.value).toBe('Кот дома.');
        fetch.mockResolvedValue(response(true,{html:'<audio controls src="/static/media/test.mp3"></audio>'}));
        fireEvent.click(button);
        await waitFor(()=>expect(document.querySelector('audio')).not.toBeNull());
        expect(field.value).toBe('Кот дома.');
    });
});
