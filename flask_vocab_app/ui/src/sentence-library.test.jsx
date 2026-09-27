import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/preact';
import { readFileSync } from 'node:fs';

const source = readFileSync('../static/js/sentence_library.js', 'utf8');

beforeAll(() => { window.eval(source); });
afterEach(() => {
    window.dispatchEvent(new Event('pagehide'));
    document.body.innerHTML = '';
    vi.restoreAllMocks();
});

function recordingRow(number) {
    return `<tr data-sentence-id="${number}"><td lang="ru">Кот дома.</td><td lang="en">The cat is home.</td><td>
      <audio controls preload="none" aria-label="Play sentence ${number}"><source src="/audio/${number}.mp3" type="audio/mpeg"></audio>
      <button type="button" data-sentence-play data-play-label="Play sentence ${number}"
        data-pause-label="Pause sentence ${number}" data-error="Audio unavailable. Try again."
        aria-label="Play sentence ${number}" hidden>Play</button>
      <span class="sentence-store-audio-error" role="status" hidden></span>
    </td></tr>`;
}

function media(row) {
    const audio = row.querySelector('audio');
    const state = { paused: true, ended: false, error: null };
    for (const property of Object.keys(state)) {
        Object.defineProperty(audio, property, { configurable: true, get: () => state[property] });
    }
    const play = vi.spyOn(audio, 'play').mockImplementation(() => {
        state.paused = false;
        state.ended = false;
        audio.dispatchEvent(new Event('play'));
        audio.dispatchEvent(new Event('playing'));
        return Promise.resolve();
    });
    const pause = vi.spyOn(audio, 'pause').mockImplementation(() => {
        if (state.paused) return;
        state.paused = true;
        audio.dispatchEvent(new Event('pause'));
    });
    const load = vi.spyOn(audio, 'load').mockImplementation(() => {
        state.error = null;
        state.ended = false;
        state.paused = true;
        audio.currentTime = 0;
        audio.dispatchEvent(new Event('emptied'));
    });
    return {
        audio, play, pause, load, state,
        button: row.querySelector('[data-sentence-play]'),
        error: row.querySelector('[role="status"]'),
        end() {
            state.paused = true;
            state.ended = true;
            audio.dispatchEvent(new Event('ended'));
        },
        fail() {
            state.error = { code: 3, message: 'Decoding failed' };
            state.paused = true;
            audio.dispatchEvent(new Event('error'));
        },
    };
}

function swapEvent(name, target = document.getElementById('mainContent')) {
    document.body.dispatchEvent(new CustomEvent(`htmx:${name}`, { bubbles: true, detail: { target } }));
}

function page({ mount = true } = {}) {
    document.body.innerHTML = `<main id="mainContent" class="sentence-store">
      <details class="sentence-store-add" data-library-disclosure>
        <summary>Add sentence</summary><form>
          <textarea id="add-russian" name="sentence"></textarea>
          <textarea id="add-english" name="english"></textarea>
          <button type="button" data-library-close>Cancel</button>
        </form>
      </details>
      <form role="search"><input type="search" id="library-search" name="q">
        <details class="sentence-store-filters" data-library-disclosure>
          <summary>Filters</summary>
          <select id="library-topic" name="topic"><option value="">All topics</option><option value="family">Family</option></select>
          <select id="library-level" name="level"><option value="">All levels</option><option value="2">Level 2</option></select>
          <button type="submit">Apply</button>
        </details>
      </form>
      <table><tbody>${recordingRow(1)}${recordingRow(2)}
        <tr data-sentence-id="3"><td>No recording</td></tr>
      </tbody></table>
      <button id="outside" type="button">Outside</button>
    </main>`;
    const first = media(document.querySelector('[data-sentence-id="1"]'));
    const second = media(document.querySelector('[data-sentence-id="2"]'));
    if (mount) swapEvent('afterSwap');
    return { first, second, main: document.getElementById('mainContent') };
}

function expectStopped(item, number) {
    expect(item.button.hasAttribute('data-playing')).toBe(false);
    expect(item.button.getAttribute('aria-label')).toBe(`Play sentence ${number}`);
    expect(item.button.hasAttribute('aria-busy')).toBe(false);
}

describe('saved sentence audio', () => {
    it('progressively replaces the native player with an accessible custom control', () => {
        const { first, main } = page({ mount: false });
        expect(first.audio.controls).toBe(true);
        expect(first.audio.hidden).toBe(false);
        expect(first.button.hidden).toBe(true);

        swapEvent('afterSwap');

        expect(first.audio.controls).toBe(false);
        expect(first.audio.hidden).toBe(true);
        expect(first.audio.preload).toBe('none');
        expect(first.audio.querySelector('source').getAttribute('src')).toBe('/audio/1.mp3');
        expect(first.button.hidden).toBe(false);
        expectStopped(first, 1);
        expect(main.classList.contains('sentence-store-player-ready')).toBe(true);
        expect(first.play).not.toHaveBeenCalled();
    });

    it('allows only one sentence to play and resets the previous control', async () => {
        const { first, second } = page();
        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));
        expect(first.state.paused).toBe(false);
        expect(first.button.dataset.playing).toBe('true');
        expect(first.button.getAttribute('aria-label')).toBe('Pause sentence 1');

        fireEvent.click(second.button);

        expect(first.pause).toHaveBeenCalledOnce();
        expect(first.state.paused).toBe(true);
        expectStopped(first, 1);
        expect(second.play).toHaveBeenCalledOnce();
        expect(second.state.paused).toBe(false);
        expect(second.button.getAttribute('aria-label')).toBe('Pause sentence 2');
    });

    it('pauses and resumes at the current position, then replays an ended recording from the start', async () => {
        const { first } = page();
        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));
        first.audio.currentTime = 2;
        fireEvent.click(first.button);
        expect(first.pause).toHaveBeenCalledOnce();
        expectStopped(first, 1);

        fireEvent.click(first.button);
        expect(first.play).toHaveBeenCalledTimes(2);
        expect(first.audio.currentTime).toBe(2);
        first.audio.currentTime = 5;
        first.end();
        expectStopped(first, 1);

        fireEvent.click(first.button);
        expect(first.play).toHaveBeenCalledTimes(3);
        expect(first.audio.currentTime).toBe(0);
        expect(first.button.dataset.playing).toBe('true');
    });

    it('resets the control when playback is paused by the browser', () => {
        const { first } = page();
        fireEvent.click(first.button);
        first.audio.pause();
        expectStopped(first, 1);
        fireEvent.click(first.button);
        expect(first.play).toHaveBeenCalledTimes(2);
        expect(first.state.paused).toBe(false);
    });

    it('shows a failed play request and allows a successful retry', async () => {
        const { first } = page();
        first.play.mockRejectedValueOnce(new DOMException('Unsupported audio', 'NotSupportedError'));
        first.state.error = { code: 4 };
        fireEvent.click(first.button);

        await waitFor(() => expect(first.error.hidden).toBe(false));
        expect(first.error.textContent).toBe('Audio unavailable. Try again.');
        expectStopped(first, 1);
        expect(first.button.disabled).toBe(false);
        expect(first.load).toHaveBeenCalledOnce();

        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));
        expect(first.play).toHaveBeenCalledTimes(2);
        expect(first.error.hidden).toBe(true);
        expect(first.error.textContent).toBe('');
        expect(first.state.paused).toBe(false);
    });

    it('recovers from a media error that happens after playback has started', async () => {
        const { first } = page();
        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));
        first.fail();

        expectStopped(first, 1);
        expect(first.error.hidden).toBe(false);
        expect(first.error.textContent).toBe('Audio unavailable. Try again.');

        fireEvent.click(first.button);
        expect(first.load).toHaveBeenCalledOnce();
        expect(first.play).toHaveBeenCalledTimes(2);
        expect(first.error.hidden).toBe(true);
        expect(first.state.paused).toBe(false);
    });

    it('reports a failed source while play remains pending and reloads the recording on retry', async () => {
        const { first } = page();
        first.play.mockImplementationOnce(() => {
            first.state.paused = false;
            // A missing <source> can fail without rejecting the play() promise
            // or setting audio.error; its error event does not bubble.
            return new Promise(() => {});
        });
        fireEvent.click(first.button);
        expect(first.button.getAttribute('aria-busy')).toBe('true');
        expect(first.load).not.toHaveBeenCalled();

        first.audio.querySelector('source').dispatchEvent(new Event('error'));

        expect(first.audio.error).toBeNull();
        expect(first.pause).toHaveBeenCalledOnce();
        expect(first.state.paused).toBe(true);
        expectStopped(first, 1);
        expect(first.error.hidden).toBe(false);
        expect(first.error.textContent).toBe('Audio unavailable. Try again.');
        expect(first.button.disabled).toBe(false);

        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));

        expect(first.load).toHaveBeenCalledOnce();
        expect(first.play).toHaveBeenCalledTimes(2);
        expect(first.load.mock.invocationCallOrder[0]).toBeLessThan(first.play.mock.invocationCallOrder[1]);
        expect(first.state.paused).toBe(false);
        expect(first.button.dataset.playing).toBe('true');
        expect(first.error.hidden).toBe(true);
        expect(first.error.textContent).toBe('');
    });

    it('clears an earlier row error when another recording plays', async () => {
        const { first, second } = page();
        first.play.mockRejectedValueOnce(new Error('Offline'));
        fireEvent.click(first.button);
        await waitFor(() => expect(first.error.hidden).toBe(false));

        fireEvent.click(second.button);

        expect(first.error.hidden).toBe(true);
        expect(second.error.hidden).toBe(true);
        expect(second.play).toHaveBeenCalledOnce();
    });

    it('stops for main-content replacement and mounts new HTMX rows only once', async () => {
        const { first, main } = page();
        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));
        swapEvent('beforeSwap', main.querySelector('tbody'));
        expect(first.pause).not.toHaveBeenCalled();
        swapEvent('beforeSwap', main);
        expect(first.pause).toHaveBeenCalledOnce();
        expectStopped(first, 1);

        main.outerHTML = `<main id="mainContent" class="sentence-store"><table><tbody>${recordingRow(4)}</tbody></table></main>`;
        const next = media(document.querySelector('[data-sentence-id="4"]'));
        swapEvent('afterSwap');
        swapEvent('afterSwap');
        fireEvent.click(next.button);
        expect(first.button.isConnected).toBe(false);
        expect(next.play).toHaveBeenCalledOnce();
        expect(next.pause).not.toHaveBeenCalled();
        expect(next.button.hidden).toBe(false);
        expect(next.button.dataset.playing).toBe('true');
    });

    it('does not show an audio failure when navigation cancels a pending play', async () => {
        const { first, main } = page();
        let rejectPlay;
        first.play.mockImplementationOnce(() => {
            first.state.paused = false;
            return new Promise((resolve, reject) => { rejectPlay = reject; });
        });
        fireEvent.click(first.button);
        expect(first.button.getAttribute('aria-busy')).toBe('true');
        swapEvent('beforeSwap', main);
        rejectPlay(new DOMException('Playback interrupted', 'AbortError'));
        await Promise.resolve();

        expect(first.pause).toHaveBeenCalledOnce();
        expectStopped(first, 1);
        expect(first.error.hidden).toBe(true);
        expect(first.error.textContent).toBe('');
    });

    it('ignores an earlier failed play request after the same recording is paused and retried', async () => {
        const { first } = page();
        let rejectEarlierPlay;
        first.play.mockImplementationOnce(() => {
            first.state.paused = false;
            return new Promise((resolve, reject) => { rejectEarlierPlay = reject; });
        });
        fireEvent.click(first.button);
        fireEvent.click(first.button);
        fireEvent.click(first.button);
        await waitFor(() => expect(first.button.hasAttribute('aria-busy')).toBe(false));

        rejectEarlierPlay(new Error('Earlier playback failed'));
        await Promise.resolve();

        expect(first.play).toHaveBeenCalledTimes(2);
        expect(first.state.paused).toBe(false);
        expect(first.button.dataset.playing).toBe('true');
        expect(first.button.getAttribute('aria-label')).toBe('Pause sentence 1');
        expect(first.error.hidden).toBe(true);
    });

    it('keeps the resumed control active when a queued pause event arrives late', () => {
        const { first } = page();
        // Browsers queue media events: pause can arrive after a subsequent play().
        first.pause.mockImplementation(() => { first.state.paused = true; });
        fireEvent.click(first.button);
        fireEvent.click(first.button);
        fireEvent.click(first.button);
        first.audio.dispatchEvent(new Event('pause'));

        expect(first.state.paused).toBe(false);
        expect(first.button.dataset.playing).toBe('true');
        expect(first.button.getAttribute('aria-label')).toBe('Pause sentence 1');
    });

    it('stops audio when the browser leaves the page', () => {
        const { first } = page();
        fireEvent.click(first.button);
        window.dispatchEvent(new Event('pagehide'));
        expect(first.pause).toHaveBeenCalledOnce();
        expect(first.state.paused).toBe(true);
        expectStopped(first, 1);
    });
});

describe('saved sentence disclosures', () => {
    it('closes Add with Escape or Cancel, returns focus, and preserves both draft fields', () => {
        page();
        const add = document.querySelector('.sentence-store-add');
        const summary = add.querySelector('summary');
        const russian = document.getElementById('add-russian');
        const english = document.getElementById('add-english');
        fireEvent.click(summary);
        expect(add.open).toBe(true);
        fireEvent.input(russian, { target: { value: 'Моя семья дома.' } });
        fireEvent.input(english, { target: { value: 'My family is home.' } });
        russian.focus();
        const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
        russian.dispatchEvent(escape);

        expect(escape.defaultPrevented).toBe(true);
        expect(add.open).toBe(false);
        expect(document.activeElement).toBe(summary);
        fireEvent.click(summary);
        expect(russian.value).toBe('Моя семья дома.');
        expect(english.value).toBe('My family is home.');
        fireEvent.click(add.querySelector('[data-library-close]'));
        expect(add.open).toBe(false);
        expect(document.activeElement).toBe(summary);
        expect(russian.value).toBe('Моя семья дома.');
        expect(english.value).toBe('My family is home.');
    });

    it('preserves search and filter selections through Escape and outside dismissal', () => {
        page();
        const filters = document.querySelector('.sentence-store-filters');
        const summary = filters.querySelector('summary');
        const topic = document.getElementById('library-topic');
        const level = document.getElementById('library-level');
        const search = document.getElementById('library-search');
        fireEvent.input(search, { target: { value: 'семья' } });
        fireEvent.click(summary);
        fireEvent.change(topic, { target: { value: 'family' } });
        fireEvent.change(level, { target: { value: '2' } });
        fireEvent.click(topic);
        expect(filters.open).toBe(true);
        level.focus();
        fireEvent.keyDown(level, { key: 'Escape' });
        expect(filters.open).toBe(false);
        expect(document.activeElement).toBe(summary);

        fireEvent.click(summary);
        fireEvent.click(document.getElementById('outside'));
        expect(filters.open).toBe(false);
        fireEvent.click(summary);
        expect(topic.value).toBe('family');
        expect(level.value).toBe('2');
        expect(search.value).toBe('семья');
    });

    it('closes Add when Filters opens without losing the typed sentence', () => {
        page();
        const add = document.querySelector('.sentence-store-add');
        const filters = document.querySelector('.sentence-store-filters');
        const russian = document.getElementById('add-russian');
        fireEvent.click(add.querySelector('summary'));
        fireEvent.input(russian, { target: { value: 'Не потеряй меня.' } });
        fireEvent.click(russian);
        expect(add.open).toBe(true);

        fireEvent.click(filters.querySelector('summary'));

        expect(filters.open).toBe(true);
        expect(add.open).toBe(false);
        expect(russian.value).toBe('Не потеряй меня.');
    });
});
