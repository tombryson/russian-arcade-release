import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/preact';
import { readFileSync } from 'node:fs';
const source = readFileSync('../static/js/activity_editor.js', 'utf8');

beforeAll(() => { window.eval(source); });
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function page(value = '') {
    document.body.innerHTML = `<main id="mainContent"><section class="sentence-workspace" data-game-id="example"
      data-leave-message="Discard changes?" data-network-error="Try again." data-unsaved="Unsaved changes"
      data-checking="Checking…" data-saving="Saving…">
      <button data-insert-word="кот">кот</button>
      <form data-sentence-editor action="/word_jumble/mark/example" method="post">
      <input type="hidden" name="revision" value="0">
      <textarea name="user_response" maxlength="1000" data-saved-value=""></textarea>
      <button type="submit">Check</button><button type="submit" formaction="/word_jumble/save/example">Save</button>
      <span class="sentence-draft-status"></span></form>
      <div id="sentence-action-status"></div><div id="sentence-feedback">Earlier feedback</div>
      <details><summary>Saved practice</summary></details></section></main>`;
    const form = document.querySelector('form');
    form.querySelector('textarea').value = value;
    return { form, field: form.querySelector('textarea'), check: form.querySelector('button'), save: form.querySelectorAll('button')[1] };
}
function submit(form, submitter) {
    form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true, submitter }));
}
function reply(ok = true, data = {}) {
    return { ok, headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ok ? { revision: 1, message: 'Saved.', feedback: '<p>Checked sentence</p>', ...data } : data };
}
function navigation() {
    const event = new CustomEvent('htmx:beforeRequest', { bubbles: true, cancelable: true,
        detail: { target: document.getElementById('mainContent') } });
    document.body.dispatchEvent(event);
    return event;
}

describe('sentence editor', () => {
    it('acknowledges word preparation, prevents duplicates and recovers after Back navigation', () => {
        document.body.innerHTML = `<form data-jumble-setup data-preparing="Choosing your words…">
          <button type="submit">Start</button><p role="status" data-preparation-status></p></form>`;
        const form = document.querySelector('form');
        const first = new SubmitEvent('submit', { bubbles: true, cancelable: true });
        form.dispatchEvent(first);
        expect(first.defaultPrevented).toBe(false); // Preserve normal browser navigation.
        expect(form.getAttribute('aria-busy')).toBe('true');
        expect(form.querySelector('button').disabled).toBe(true);
        expect(form.querySelector('[role="status"]').textContent).toBe('Choosing your words…');
        const duplicate = new SubmitEvent('submit', { bubbles: true, cancelable: true });
        form.dispatchEvent(duplicate);
        expect(duplicate.defaultPrevented).toBe(true);
        window.dispatchEvent(new Event('pageshow'));
        expect(form.querySelector('button').disabled).toBe(false);
        expect(form.hasAttribute('aria-busy')).toBe(false);
        expect(form.querySelector('[role="status"]').textContent).toBe('');
    });

    it('inserts a tile at the caret, adds spaces, and keeps existing writing', () => {
        const { field } = page('Мой дома.');
        field.setSelectionRange(4, 4);
        fireEvent.click(document.querySelector('[data-insert-word]'));
        expect(field.value).toBe('Мой кот дома.');
        expect(document.activeElement).toBe(field);
        expect(document.querySelector('.sentence-draft-status').textContent).toBe('Unsaved changes');
    });

    it('saves separately without replacing the textarea or losing its focus', async () => {
        const { form, field, save } = page('Семья дома.');
        const fetch = vi.fn().mockResolvedValue(reply());
        vi.stubGlobal('fetch', fetch);
        field.focus();
        submit(form, save);
        await waitFor(() => expect(field.dataset.savedValue).toBe('Семья дома.'));
        expect(fetch.mock.calls[0][0]).toBe('/word_jumble/save/example');
        expect(fetch.mock.calls[0][1].body.get('user_response')).toBe('Семья дома.');
        expect(document.activeElement).toBe(field);
        expect(document.querySelector('textarea')).toBe(field);
        expect(form.elements.revision.value).toBe('1');
        const confirm = vi.spyOn(window, 'confirm');
        expect(navigation().defaultPrevented).toBe(false);
        expect(confirm).not.toHaveBeenCalled();
    });

    it('keeps later edits unsaved when an earlier check returns', async () => {
        const { form, field, check, save } = page('Первый ответ.');
        let resolve;
        const fetch = vi.fn().mockReturnValue(new Promise(done => { resolve = done; }));
        vi.stubGlobal('fetch', fetch);
        submit(form, check);
        expect(check.disabled).toBe(true);
        expect(save.disabled).toBe(true);
        fireEvent.input(field, { target: { value: 'Более новый ответ.' } });
        submit(form, save);
        expect(fetch).toHaveBeenCalledTimes(1);
        resolve(reply());
        await waitFor(() => expect(check.disabled).toBe(false));
        expect(field.value).toBe('Более новый ответ.');
        expect(field.dataset.savedValue).toBe('Первый ответ.');
        expect(form.elements.revision.value).toBe('1');
        expect(document.querySelector('.sentence-draft-status').textContent).toBe('Unsaved changes');
    });

    it('retains both the draft and previous feedback on provider or connection failure', async () => {
        const { form, field, check } = page('Мой ответ.');
        const fetch = vi.fn().mockResolvedValue(reply(false, { error: 'Check unavailable. Save your draft.' }));
        vi.stubGlobal('fetch', fetch);
        submit(form, check);
        await waitFor(() => expect(document.getElementById('sentence-action-status').textContent).toContain('Check unavailable'));
        expect(field.value).toBe('Мой ответ.');
        expect(field.dataset.savedValue).toBe('');
        expect(document.getElementById('sentence-feedback').textContent).toBe('Earlier feedback');
        fetch.mockRejectedValue(new Error('offline'));
        submit(form, check);
        await waitFor(() => expect(document.getElementById('sentence-action-status').textContent).toBe('Try again.'));
        expect(field.value).toBe('Мой ответ.');
        expect(check.disabled).toBe(false);
    });

    it('allows library disclosure and protects unsaved writing from navigation', () => {
        const { field } = page('Не потеряй меня.');
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        document.querySelector('details').open = true;
        expect(field.value).toBe('Не потеряй меня.');
        expect(confirm).not.toHaveBeenCalled();
        expect(navigation().defaultPrevented).toBe(true);
        expect(confirm).toHaveBeenCalledWith('Discard changes?');
        const unload = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(unload);
        expect(unload.defaultPrevented).toBe(true);
    });

    it('preserves dirty writing in HTMX history independently from the last saved value', () => {
        const { field } = page('Изменённый ответ.');
        field.dataset.savedValue = 'Сохранённый ответ.';
        document.body.dispatchEvent(new CustomEvent('htmx:beforeHistorySave', { bubbles: true }));
        const clone = field.cloneNode(true);
        expect(clone.textContent).toBe('Изменённый ответ.');
        expect(clone.dataset.savedValue).toBe('Сохранённый ответ.');
    });

    it('refreshes only the current library entry after saving', async () => {
        const { form, save } = page('Кот дома.');
        document.getElementById('mainContent').insertAdjacentHTML('beforeend', `
          <a data-practice-id="example"><span data-practice-state>Ready to try</span><span data-practice-date>Yesterday</span></a>
          <a data-practice-id="other"><span data-practice-state>Ready to try</span><span data-practice-date>Yesterday</span></a>`);
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(true, { state: 'Draft saved', display_date: '9 Sep 2026' })));
        submit(form, save);
        await waitFor(() => expect(document.querySelector('[data-practice-id="example"]').textContent).toBe('Draft saved →9 Sep 2026'));
        expect(document.querySelector('[data-practice-id="other"]').textContent).toBe('Ready to tryYesterday');
        expect(document.querySelector('.sentence-draft-status').textContent).toBe('');
        expect(document.getElementById('sentence-action-status').textContent).toBe('Saved.');
    });

    it('opens activity entry pages at the top without scrolling to the heading', () => {
        document.body.innerHTML = `<main id="mainContent" class="activity-entry">
            <header><h1 id="sentence-page-title" tabindex="-1">Word Jumble</h1></header>
        </main>`;
        const heading = document.querySelector('h1');
        const focus = vi.spyOn(heading, 'focus');
        heading.scrollIntoView = vi.fn();
        const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
        document.body.dispatchEvent(new CustomEvent('htmx:afterSwap', { bubbles: true,
            detail: { target: document.getElementById('mainContent') } }));
        expect(document.activeElement).toBe(heading);
        expect(focus).toHaveBeenCalledWith({ preventScroll: true });
        expect(heading.scrollIntoView).not.toHaveBeenCalled();
        expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'instant' });

        scrollTo.mockClear();
        document.body.dispatchEvent(new CustomEvent('htmx:afterSwap', { bubbles: true,
            detail: { target: document.querySelector('header') } }));
        expect(scrollTo).not.toHaveBeenCalled();
    });

    it('focuses and reveals the heading after a saved practice opens', () => {
        page();
        const heading = document.createElement('h1');
        heading.id = 'sentence-page-title';
        heading.tabIndex = -1;
        heading.scrollIntoView = vi.fn();
        document.getElementById('mainContent').prepend(heading);
        document.body.dispatchEvent(new CustomEvent('htmx:afterSwap', { bubbles: true,
            detail: { target: document.getElementById('mainContent') } }));
        expect(document.activeElement).toBe(heading);
        expect(heading.scrollIntoView).toHaveBeenCalledWith({ block: 'start' });
    });
});
