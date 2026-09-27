/* A transcript is disclosed only after its support receipt has been saved. */
(() => {
    const mounted = new WeakSet();
    const ru = () => document.documentElement.lang === 'ru';
    const text = (en, russian) => ru() ? russian : en;
    const requestKey = () => crypto.randomUUID().replaceAll('-', '');
    function mount() {
        document.querySelectorAll('[data-listening-task]').forEach(article => {
            if (mounted.has(article)) return;
            mounted.add(article);
            const taskId = () => article.querySelector('[name="task_id"]')?.value;
            const profile = document.querySelector('meta[name="learning-profile"]')?.content;
            const account = document.querySelector('meta[name="learning-account"]')?.content;
            const status = article.querySelector('[data-listening-status]');
            const transcript = article.querySelector('[data-show-transcript]');
            const retry = article.querySelector('[data-retry-listened]');
            const audio = article.querySelector('[data-comprehension-audio]');
            let pending = false;
            const keys = new Map();
            const revision = () => article.querySelector('[name="task_revision"]')?.value;
            function refresh() {
                const id = taskId();
                if (id && id !== article.dataset.listeningTask) {
                    article.dataset.listeningTask = id;
                    const form = article.querySelector('#question-form');
                    article.dataset.listened = form.dataset.listened;
                    // Keep hidden transcripts hidden until their disclosure response arrives.
                    article.dataset.transcriptVisible = form.dataset.transcriptVisible;
                    const container = article.querySelector('#story-container');
                    if (container) container.dataset.taskId = id;
                    if (audio) audio.src = `/comprehension/tasks/${id}/audio`;
                    document.dispatchEvent(new CustomEvent('arcade:comprehension-transcript'));
                }
                const fields = article.querySelector('[data-listening-answers]');
                if (fields) fields.disabled = pending || !(article.dataset.listened === 'true' || article.dataset.transcriptVisible === 'true');
                transcript.disabled = pending;
                retry.disabled = pending;
            }
            async function record(operation) {
                if (pending || !article.isConnected) return;
                const version = revision();
                const id = taskId();
                const identity = `${id}:${version}:${operation}`;
                if (!keys.has(identity)) keys.set(identity, requestKey());
                pending = true;
                refresh();
                status.textContent = text('Saving…', 'Сохраняем…');
                const current = () => article.isConnected && taskId() === id && revision() === version &&
                    document.querySelector('meta[name="learning-profile"]')?.content === profile &&
                    document.querySelector('meta[name="learning-account"]')?.content === account;
                try {
                    const response = await fetch(`/comprehension/tasks/${id}/support`, {
                        method: 'POST', headers: {'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''},
                        body: JSON.stringify({operation, task_revision: Number(version), request_key: keys.get(identity)}),
                    });
                    const data = await response.json();
                    if (!current()) return;
                    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : text('Please try again.', 'Попробуйте ещё раз.'));
                    if (data.task_id !== id || data.revision !== Number(version)) throw new Error(text('This story has changed. Reload it to continue.', 'Текст изменился. Обновите страницу.'));
                    article.dataset.listened = String(data.listened);
                    article.dataset.transcriptVisible = String(data.transcript_visible);
                    if (operation === 'transcript') {
                        const panel = article.querySelector('[data-comprehension-transcript]');
                        const container = panel.querySelector('#story-container');
                        const paragraph = document.createElement('p');
                        paragraph.lang = 'ru';
                        paragraph.textContent = data.text;
                        container.replaceChildren(paragraph);
                        container.dataset.words = JSON.stringify(data.words);
                        container.dataset.storyKey = data.capture_key;
                        panel.hidden = false;
                        transcript.hidden = true;
                        const title = article.querySelector('#reading-story-title');
                        title.textContent = ru() ? data.title : (data.title_en || data.title);
                        title.lang = ru() || !data.title_en ? 'ru' : 'en';
                        document.dispatchEvent(new CustomEvent('arcade:comprehension-transcript'));
                    }
                    retry.hidden = true;
                    status.textContent = operation === 'transcript'
                        ? text('Transcript shown. You can answer with the text available.', 'Текст открыт. Можно отвечать с его помощью.')
                        : text('You can answer now, or listen again.', 'Теперь можно ответить или послушать ещё раз.');
                } catch (error) {
                    if (!current()) return;
                    status.textContent = error instanceof TypeError ? text('Could not save playback. Try again.', 'Не удалось сохранить прослушивание. Попробуйте ещё раз.') : error.message;
                    if (operation === 'listened') retry.hidden = false;
                } finally {
                    pending = false;
                    if (article.isConnected) refresh();
                }
            }
            audio?.addEventListener('ended', () => {
                if (article.dataset.listened !== 'true') record('listened');
            });
            audio?.addEventListener('error', () => {
                status.textContent = text('The recording could not play. Try again, or show the transcript.', 'Не удалось воспроизвести запись. Попробуйте ещё раз или откройте текст.');
            });
            transcript.addEventListener('click', () => record('transcript'));
            retry.addEventListener('click', () => record('listened'));
            article.addEventListener('htmx:afterSwap', refresh);
            refresh();
        });
    }
    document.addEventListener('DOMContentLoaded', mount);
    document.addEventListener('htmx:afterSwap', mount);
    if (document.readyState !== 'loading') mount();
})();
