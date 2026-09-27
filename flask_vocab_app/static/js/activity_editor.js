/* Progressive enhancement: the editor stays mounted while drafts/checks are saved. */
(() => {
    // A short library may need a generated top-up. Keep ordinary form navigation,
    // but acknowledge the wait and prevent duplicate clicks while it runs.
    document.addEventListener('submit', event => {
        const form = event.target;
        if (!form.matches('[data-jumble-setup]')) return;
        if (form.dataset.busy === 'true') { event.preventDefault(); return; }
        form.dataset.busy = 'true';
        form.setAttribute('aria-busy', 'true');
        form.querySelector('button[type="submit"]').disabled = true;
        form.querySelector('[data-preparation-status]').textContent = form.dataset.preparing;
    });
    window.addEventListener('pageshow', () => {
        document.querySelectorAll('[data-jumble-setup]').forEach(form => {
            delete form.dataset.busy;
            form.removeAttribute('aria-busy');
            form.querySelector('button[type="submit"]').disabled = false;
            form.querySelector('[data-preparation-status]').textContent = '';
        });
    });
    const editorSelector = '[data-sentence-editor], [data-translation-editor], [data-writing-editor]';
    const editor = () => document.querySelector(editorSelector);
    const input = form => form?.querySelector('textarea[name="user_response"]');
    const dirty = form => !!input(form) && input(form).value !== input(form).dataset.savedValue;
    const workspace = form => form.closest('.sentence-workspace');
    const updateDraftStatus = form => {
        if (!form) return;
        const status = form.querySelector('.sentence-draft-status');
        if (dirty(form)) status.textContent = workspace(form).dataset.unsaved;
        else status.textContent = '';
    };

    document.addEventListener('input', event => {
        const form = event.target.closest(editorSelector);
        if (form) {
            updateDraftStatus(form);
            if (form.dataset.busy !== 'true') workspace(form).querySelector('#sentence-action-status').textContent = '';
        }
    });
    document.addEventListener('click', event => {
        const tile = event.target.closest('[data-insert-word]');
        if (!tile) return;
        const form = tile.closest('.sentence-workspace').querySelector(editorSelector);
        const field = input(form);
        const before = field.value.slice(0, field.selectionStart);
        const after = field.value.slice(field.selectionEnd);
        const word = tile.dataset.insertWord;
        const insertion = (before && !/[\s«“("']$/.test(before) ? ' ' : '') + word +
            (after && !/^[\s.,!?;:»”)"]/.test(after) ? ' ' : '');
        if (before.length + insertion.length + after.length > field.maxLength) return;
        field.setRangeText(insertion, field.selectionStart, field.selectionEnd, 'end');
        field.focus();
        field.dispatchEvent(new Event('input', { bubbles: true }));
    });
    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!form.matches(editorSelector) || !window.fetch) return;
        event.preventDefault();
        if (form.dataset.busy === 'true') return;
        const root = workspace(form);
        const status = root.querySelector('#sentence-action-status');
        const url = event.submitter?.getAttribute('formaction') || form.action;
        const checking = new URL(url, window.location.href).pathname.match(/\/(mark|assess)(\/|$)/);
        const submitted = input(form).value;
        const body = new FormData(form);
        const buttons = [...form.querySelectorAll('button[type="submit"]')];
        form.dataset.busy = 'true';
        form.setAttribute('aria-busy', 'true');
        buttons.forEach(button => { button.disabled = true; });
        status.textContent = checking ? root.dataset.checking : root.dataset.saving;
        status.classList.remove('sentence-error');
        try {
            const response = await fetch(url, { method: 'POST', body, headers: { Accept: 'application/json' } });
            if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Unexpected response');
            const result = await response.json();
            if (!form.isConnected) return;
            if (!response.ok) {
                status.textContent = result.error || root.dataset.networkError;
                status.classList.add('sentence-error');
                return;
            }
            if (!Number.isInteger(result.revision) || typeof result.feedback !== 'string') throw new Error('Invalid response');
            form.elements.revision.value = result.revision;
            input(form).dataset.savedValue = submitted;
            root.querySelector('#sentence-feedback').innerHTML = result.feedback;
            document.querySelectorAll('[data-practice-id]').forEach(link => {
                if (link.dataset.practiceId !== root.dataset.gameId) return;
                link.querySelector('[data-practice-state]').textContent = result.state + ' →';
                link.querySelector('[data-practice-date]').textContent = result.display_date;
            });
            status.textContent = result.message;
            if (checking && form.matches('[data-translation-editor]')) document.body.dispatchEvent(new Event('activity:checked'));
            updateDraftStatus(form); // Edits made during the request remain unsaved.
        } catch (_) {
            if (!form.isConnected) return;
            status.textContent = root.dataset.networkError;
            status.classList.add('sentence-error');
        } finally {
            delete form.dataset.busy;
            form.removeAttribute('aria-busy');
            buttons.forEach(button => { button.disabled = false; });
        }
    });
    window.addEventListener('beforeunload', event => {
        if (!dirty(editor())) return;
        event.preventDefault();
        event.returnValue = '';
    });
    document.addEventListener('htmx:beforeRequest', event => {
        const form = editor();
        if (!dirty(form) || !['mainContent', 'jumble-content', 'writing-content'].includes(event.detail.target?.id)) return;
        if (!window.confirm(workspace(form).dataset.leaveMessage)) event.preventDefault();
    });
    document.addEventListener('htmx:afterSwap', event => {
        if (event.detail.target?.id !== 'mainContent') return;
        const main = document.getElementById('mainContent');
        if (main?.classList.contains('activity-entry')) {
            main.querySelector('h1')?.focus({ preventScroll: true });
            // Entry navigation starts at the page top, including its header spacing.
            window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
            return;
        }
        const heading = document.getElementById('sentence-page-title');
        if (!heading) return;
        heading.focus({ preventScroll: true });
        heading.scrollIntoView({ block: 'start' });
    });
    document.addEventListener('htmx:beforeHistorySave', () => {
        const form = editor();
        if (!form) return;
        // HTMX serializes DOM attributes; preserve the current writing separately
        // from data-saved-value so Back navigation cannot silently mark it saved.
        input(form).textContent = input(form).value;
        delete form.dataset.busy;
        form.removeAttribute('aria-busy');
        form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = false; });
    });
})();
