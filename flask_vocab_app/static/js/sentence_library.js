/* Compact playback controls for the saved sentence library. */
(() => {
    const mounted = new WeakSet();
    let active = null;

    function reset(item) {
        item.button.removeAttribute('data-playing');
        item.button.setAttribute('aria-label', item.button.dataset.playLabel);
        item.button.removeAttribute('aria-busy');
        if (active === item) active = null;
    }

    function stop() {
        if (!active) return;
        const item = active;
        active = null;
        item.request += 1;
        item.audio.pause();
        reset(item);
    }

    function mount() {
        const library = document.querySelector('.sentence-store');
        if (!library) return;
        library.querySelectorAll('[data-sentence-play]').forEach(button => {
            if (mounted.has(button)) return;
            mounted.add(button);
            const row = button.closest('[data-sentence-id]');
            const audio = row.querySelector('audio');
            const error = row.querySelector('.sentence-store-audio-error');
            const item = { button, audio, request: 0, failed: false };
            function showError() {
                if (active !== item || !button.isConnected) return;
                item.failed = true;
                stop();
                error.textContent = button.dataset.error;
                error.hidden = false;
            }
            audio.hidden = true;
            audio.controls = false;
            button.hidden = false;
            audio.addEventListener('pause', () => { if (audio.paused) reset(item); });
            audio.addEventListener('ended', () => reset(item));
            audio.addEventListener('error', showError);
            // A failed <source> may leave play() pending rather than reject it.
            audio.querySelectorAll('source').forEach(source => source.addEventListener('error', showError));
            button.addEventListener('click', async () => {
                if (active === item) {
                    stop();
                    return;
                }
                stop();
                error.hidden = true;
                error.textContent = '';
                // A previous failed recording should not leave a message over the next row.
                library.querySelectorAll('.sentence-store-audio-error').forEach(message => { message.hidden = true; });
                active = item;
                const request = ++item.request;
                button.dataset.playing = 'true';
                button.setAttribute('aria-label', button.dataset.pauseLabel);
                button.setAttribute('aria-busy', 'true');
                try {
                    if (item.failed || audio.error) { audio.load(); item.failed = false; }
                    if (audio.ended) audio.currentTime = 0;
                    await audio.play();
                    if (request === item.request) button.removeAttribute('aria-busy');
                } catch (failure) {
                    // Cancelling a pending play by pausing or navigating is intentional.
                    if (request !== item.request || failure?.name === 'AbortError') return;
                    showError();
                }
            });
        });
        library.classList.add('sentence-store-player-ready');
    }

    function close(disclosure, focus = false) {
        disclosure.open = false;
        if (focus) disclosure.querySelector('summary').focus({ preventScroll: true });
    }

    document.addEventListener('click', event => {
        const cancel = event.target.closest('[data-library-close]');
        if (cancel) close(cancel.closest('[data-library-disclosure]'), true);
        document.querySelectorAll('[data-library-disclosure][open]').forEach(disclosure => {
            if (!disclosure.contains(event.target)) close(disclosure);
        });
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        const disclosure = document.activeElement?.closest('[data-library-disclosure][open]');
        if (disclosure) { close(disclosure, true); event.preventDefault(); }
    });
    document.addEventListener('htmx:beforeSwap', event => {
        if (event.detail.target?.id === 'mainContent') stop();
    });
    document.addEventListener('htmx:afterSwap', mount);
    window.addEventListener('pagehide', stop);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
    else mount();
})();
