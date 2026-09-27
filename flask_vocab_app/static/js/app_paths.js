/* Keep activity requests inside the workspace that rendered this document. */
(() => {
    'use strict';
    const configured = document.querySelector('meta[name="app-base-path"]')?.content || '';
    const base = /^\/(?:[A-Za-z0-9_-]+\/?)+$/.test(configured) ? configured.replace(/\/$/, '') : '';
    const mounted = path => path === base || path.startsWith(base + '/');
    const shared = path => (path.startsWith('/static/') && !/^\/static\/(?:media|uploads)(?:\/|$)/.test(path)) || path.startsWith('/post/assets/') ||
        /^\/trial\/(?:sign-in|callback|connect|sign-out)(?:\/|$)/.test(path);

    window.arcadeUrl = value => {
        if (!base || typeof value !== 'string' || !value || value.startsWith('//')) return value;
        // Hash routes, relative imports, external links and blob recordings keep
        // their original meaning. Only same-origin absolute paths are mounted.
        const absolute = /^[A-Za-z][A-Za-z0-9+.-]*:/.test(value);
        if (!absolute && !value.startsWith('/')) return value;
        let url;
        try { url = new URL(value, window.location.href); } catch (_) { return value; }
        if (url.origin !== window.location.origin || mounted(url.pathname) || shared(url.pathname)) return value;
        url.pathname = base + url.pathname;
        return absolute ? url.href : url.pathname + url.search + url.hash;
    };
    window.arcadePath = value => {
        if (!base || typeof value !== 'string') return value;
        if (value === base) return '/';
        return value.startsWith(base + '/') ? value.slice(base.length) : value;
    };

    if (!base) return;
    // A Request carries its body, method, signal and credentials. Retain those
    // when changing its URL; explicit fetch options still take precedence.
    if (window.fetch) {
        const originalFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {
            const isRequest = typeof Request !== 'undefined' && input instanceof Request;
            const original = isRequest ? input.url : String(input);
            const target = window.arcadeUrl(original);
            if (target === original) return originalFetch(input, init);
            if (!isRequest) return originalFetch(target, init);
            const options = {
                method: input.method, headers: input.headers,
                body: input.method === 'GET' || input.method === 'HEAD' ? undefined : input.body,
                mode: input.mode, credentials: input.credentials, cache: input.cache,
                redirect: input.redirect, referrer: input.referrer, referrerPolicy: input.referrerPolicy,
                integrity: input.integrity, keepalive: input.keepalive, signal: input.signal,
                ...('duplex' in input ? { duplex: input.duplex } : {}),
            };
            // Reconstructing a keepalive body from its exposed stream is
            // forbidden by Fetch; preserve its bytes for unload requests.
            if (input.keepalive && input.body) {
                return input.arrayBuffer().then(body => originalFetch(new Request(target, { ...options, body }), init));
            }
            return originalFetch(new Request(target, options), init);
        };
    }
    // HTMX may construct a request from a dynamically rendered activity form.
    document.addEventListener('htmx:configRequest', event => {
        event.detail.path = window.arcadeUrl(event.detail.path);
    });
})();
