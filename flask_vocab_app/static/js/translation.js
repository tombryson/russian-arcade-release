/* Preparation and optional audio are separate from saving/checking the editor. */
(() => {
    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!form.matches('[data-translation-prepare], [data-writing-prepare]') || !window.fetch) return;
        event.preventDefault();
        if (form.dataset.busy === 'true') return;
        const status = form.querySelector('[data-prepare-status]');
        const button = form.querySelector('button[type="submit"]');
        const data = new FormData(form);
        const fingerprint = JSON.stringify([...data]);
        form.dataset.busy = 'true';
        button.disabled = true;
        status.textContent = form.dataset.pending;
        try {
            const response = await fetch(form.action, { method: 'POST', body: data, headers: { Accept: 'application/json' } });
            const result = await response.json();
            if (!form.isConnected) return;
            if (!response.ok) {
                status.textContent = result.error || form.dataset.error;
                return;
            }
            const prefix = form.matches('[data-writing-prepare]') ? '/writing/load/' : '/sentences/';
            if (typeof result.url !== 'string' || !result.url.startsWith(prefix)) throw new Error('Invalid destination');
            // Do not discard changes typed while a sentence was being prepared.
            if (fingerprint !== JSON.stringify([...new FormData(form)])) {
                const link = document.createElement('a');
                link.href = result.url;
                link.textContent = form.dataset.ready;
                status.replaceChildren(link);
            } else {
                window.location.assign(result.url);
            }
        } catch (_) {
            if (form.isConnected) status.textContent = form.dataset.error;
        } finally {
            delete form.dataset.busy;
            button.disabled = false;
        }
    });
    document.addEventListener('click', async event => {
        const button = event.target.closest('[data-translation-audio]');
        if (!button || button.disabled) return;
        const container = button.closest('.translation-audio');
        const status = container.querySelector('[data-audio-status]');
        button.disabled = true;
        status.textContent = button.dataset.pending;
        try {
            const response = await fetch(button.dataset.translationAudio, { method: 'POST', headers: { Accept: 'application/json' } });
            const result = await response.json();
            if (!container.isConnected) return;
            if (!response.ok || typeof result.html !== 'string') {
                status.textContent = result.error || button.dataset.error;
                return;
            }
            container.innerHTML = result.html;
        } catch (_) {
            if (container.isConnected) status.textContent = button.dataset.error;
        } finally {
            button.disabled = false;
        }
    });
})();
