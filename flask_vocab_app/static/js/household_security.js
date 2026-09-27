/* Temporary CSRF adapter for the legacy forms, HTMX and fetch clients. */
(() => {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    const profile = document.querySelector('meta[name="learning-profile"]')?.content;
    const scope = document.querySelector('meta[name="learning-account"]')?.content;
    if (!token) return;
    const local = value => new URL(value, window.location.href).origin === window.location.origin;
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
        const url = input instanceof Request ? input.url : String(input);
        if (!local(url)) return originalFetch(input, init);
        const headers = new Headers(init.headers ?? (input instanceof Request ? input.headers : undefined));
        headers.set('X-CSRF-Token', token);
        if (profile) headers.set('X-Profile-ID', profile);
        const method = (init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
        const sessionProbe = method === 'GET' && new URL(url, window.location.href).pathname === '/api/v1/user-session';
        // The account watcher needs the current identity to reload stale tabs.
        // Activity requests stay bound to the account that opened this document.
        if (scope && !sessionProbe) headers.set('X-Account-Scope', scope);
        return originalFetch(input, { ...init, headers });
    };
    document.addEventListener('htmx:configRequest', event => {
        if (local(event.detail.path)) {
            event.detail.headers['X-CSRF-Token'] = token;
            if (profile) event.detail.headers['X-Profile-ID'] = profile;
            if (scope) event.detail.headers['X-Account-Scope'] = scope;
        }
    });
    const submissions = new WeakMap();
    function needsToken(form, submitter) {
        const method = submitter?.hasAttribute('formmethod') ? submitter.getAttribute('formmethod') : form.method;
        const action = submitter?.hasAttribute('formaction') ? submitter.getAttribute('formaction') : form.action;
        return method.toLowerCase() === 'post' && local(action);
    }
    document.addEventListener('submit', event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const submission = { includeToken: needsToken(form, event.submitter) };
        submissions.set(form, submission);
        // formdata has no submitter. Retain its overrides through the browser's
        // submission task, then let subsequent FormData calls use the form defaults.
        setTimeout(() => { if (submissions.get(form) === submission) submissions.delete(form); }, 0);
        const fields = Array.from(form.elements).filter(field =>
            field instanceof HTMLInputElement && field.type === 'hidden' && field.name === 'csrf_token');
        if (!submission.includeToken) {
            fields.forEach(field => field.remove());
            return;
        }
        let hidden = fields.shift();
        fields.forEach(field => field.remove());
        if (!hidden) {
            hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'csrf_token';
            form.append(hidden);
        }
        hidden.value = token;
    }, true);
    document.addEventListener('formdata', event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const includeToken = submissions.get(form)?.includeToken ?? needsToken(form);
        if (includeToken) event.formData.set('csrf_token', token);
        else event.formData.delete('csrf_token');
    }, true);
})();
