/* Writing aids never prevent saving, checking or continuing an answer. */
(() => {
    let timer = null;
    const count = () => {
        const form = document.querySelector('[data-writing-editor]');
        if (!form) return;
        const words = form.elements.user_response.value.match(/[\p{L}\p{N}]+(?:[-’'][\p{L}\p{N}]+)*/gu) || [];
        const output = form.querySelector('[data-writing-count] span');
        if (output) output.textContent = String(words.length);
    };
    const stop = () => { if (timer?.interval) clearInterval(timer.interval); if (timer) timer.interval = null; };
    const display = () => {
        if (!timer) return;
        const seconds = Math.max(0, Math.ceil(timer.remaining / 1000));
        timer.root.querySelector('output').textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
        timer.root.querySelector('[data-timer-toggle]').textContent = timer.running ? timer.root.dataset.pause : timer.root.dataset.start;
        timer.root.querySelector('select').disabled = timer.running;
    };
    const init = () => {
        count();
        const root = document.querySelector('[data-writing-timer]');
        if (root === timer?.root) return;
        stop();
        timer = root ? { root, remaining: Number(root.querySelector('select').value) * 60000, running:false, interval:null } : null;
        display();
    };
    const reset = () => {
        if (!timer) return;
        stop();
        timer.running = false;
        timer.remaining = Number(timer.root.querySelector('select').value) * 60000;
        timer.root.querySelector('[data-timer-status]').textContent = '';
        display();
    };
    document.addEventListener('input', event => { if (event.target.matches('[data-writing-editor] textarea')) count(); });
    document.addEventListener('change', event => { if (event.target.matches('[data-writing-timer] select')) { init(); reset(); } });
    document.addEventListener('click', event => {
        if (!event.target.closest('[data-timer-toggle], [data-timer-reset]')) return;
        init();
        if (event.target.closest('[data-timer-reset]')) { reset(); return; }
        if (timer.running) {
            timer.remaining = Math.max(0,timer.deadline-Date.now());
            stop(); timer.running = false; display(); return;
        }
        if (timer.remaining <= 0) reset();
        timer.running = true;
        timer.deadline = Date.now()+timer.remaining;
        timer.interval = setInterval(() => {
            if (!timer.root.isConnected) { stop(); timer = null; return; }
            timer.remaining = Math.max(0,timer.deadline-Date.now());
            if (timer.remaining <= 0) {
                stop(); timer.running = false;
                timer.root.querySelector('[data-timer-status]').textContent = timer.root.dataset.finished;
            }
            display();
        },250);
        display();
    });
    document.addEventListener('DOMContentLoaded',init);
    document.addEventListener('htmx:afterSwap',init);
    document.addEventListener('htmx:historyRestore',init);
    document.addEventListener('htmx:beforeHistorySave',reset);
    if (document.readyState !== 'loading') init();
})();
