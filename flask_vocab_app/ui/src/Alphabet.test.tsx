import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/preact';
import {Alphabet} from './Alphabet';

const letterButtons = () => within(screen.getByRole('list', {name: 'Russian letters'})).getAllByRole('button');
const signButtons = () => within(screen.getByRole('list', {name: 'Silent signs'})).getAllByRole('button');
const voiceRadio = (name: 'Female' | 'Male') => screen.getByRole('radio', {name}) as HTMLInputElement;
const voicePreference = 'word-post-alphabet-voice';
async function click(element: HTMLElement) { await act(async () => { fireEvent.click(element); }); }
async function advance(milliseconds: number) { await act(async () => { vi.advanceTimersByTime(milliseconds); }); }
function enter(element: HTMLElement, pointerType = 'mouse') {
  const event = new Event('pointerenter');
  Object.defineProperty(event, 'pointerType', {value: pointerType});
  fireEvent(element, event);
}

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  vi.stubGlobal('fetch', vi.fn());
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Russian alphabet', () => {
  it('shows all 33 letters without loading audio or calling a provider, with a return to the lesson', () => {
    const {container} = render(<Alphabet returnHref="#first-delivery" returnLabel="Your first delivery"/>);
    const buttons = letterButtons();
    expect(screen.getByRole('heading', {level: 1, name: 'Russian alphabet'})).toBe(document.activeElement);
    expect(buttons).toHaveLength(31);
    expect(buttons[0].textContent).toBe('Аа');
    expect(buttons[30].textContent).toBe('Яя');
    expect(buttons.filter(button => button.getAttribute('aria-label')?.endsWith(', vowel'))).toHaveLength(10);
    expect(buttons.filter(button => button.getAttribute('aria-label')?.endsWith(', consonant'))).toHaveLength(21);
    expect(signButtons()).toHaveLength(2);
    expect(screen.getByRole('region', {name: 'Silent signs'})).toBeTruthy();
    expect(signButtons().map(button => button.getAttribute('aria-label'))).toEqual(['Explore Ъ ъ, hard sign', 'Explore Ь ь, soft sign']);
    expect(screen.getByText('No sound of their own.')).toBeTruthy();
    expect(buttons.filter(button => button.getAttribute('aria-label')?.startsWith('Listen to syllable '))).toHaveLength(12);
    expect(screen.getByText('Letter sound')).toBeTruthy();
    expect(screen.getByRole('link', {name: 'Your first delivery'}).getAttribute('href')).toBe('#first-delivery');
    expect(screen.getByText('Click a letter to hear a pronunciation example. Try the word too.')).toBeTruthy();
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByText(/hover/i)).toBeNull();
    expect(within(screen.getByRole('group', {name: 'Voice'})).getAllByRole('radio')).toHaveLength(2);
    expect(voiceRadio('Female').checked).toBe(true);
    expect(voiceRadio('Male').checked).toBe(false);
    expect(container.querySelector('audio')?.getAttribute('src')).toBeNull();
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    ['П', 'п', 'па', 'pe', 'а'],
    ['Б', 'б', 'ба', 'be', 'а'],
  ] as const)('labels the practice syllable for %s instead of presenting it as an isolated sound', async (upper, lower, syllable, id, vowel) => {
    const {container} = render(<Alphabet/>);
    await click(screen.getByRole('button', {name: `Listen to syllable ${syllable} for ${upper} ${lower}, consonant`}));
    const detail = screen.getByRole('complementary', {name: `About ${upper} ${lower}`});
    const caption = detail.querySelector('.alphabet-sound-caption')!;
    expect(caption.textContent).toContain(`Practice syllable: ${syllable}`);
    expect(caption.textContent).toContain(`${upper} followed by ${vowel}.`);
    expect(within(detail).queryByText('Letter sound')).toBeNull();
    expect(within(detail).queryByRole('button', {name: /sound:/})).toBeNull();
    expect(within(detail).getByRole('button', {name: `Stop syllable: ${syllable}`})).toBeTruthy();
    expect(within(detail).getByRole('button', {name: /Listen to letter name:/})).toBeTruthy();
    expect(container.querySelector('audio')?.getAttribute('src')).toBe(`/static/audio/alphabet-v1/sounds/female/${id}-sound.mp3?v=sounds-v9`);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['В', 'в', 've'], ['Н', 'н', 'en'], ['Ц', 'ц', 'tse'],
    ['Ф', 'ф', 'ef'], ['Ч', 'ч', 'che'], ['Щ', 'щ', 'shcha'],
    ['Ш', 'ш', 'sha'], ['Й', 'й', 'short-i'], ['Ж', 'ж', 'zhe'],
  ] as const)('plays isolated %s in both voices with the matching label', async (upper, lower, id) => {
    const {container} = render(<Alphabet/>);
    for (const label of ['Female', 'Male'] as const) {
      await click(voiceRadio(label));
      await click(screen.getByRole('button', {name: `Listen to ${upper} ${lower} sound, consonant`}));
      const detail = screen.getByRole('complementary', {name: `About ${upper} ${lower}`});
      expect(within(detail).getByRole('button', {name: `Stop sound: ${upper}`})).toBeTruthy();
      expect(detail.textContent).not.toContain('Practice syllable:');
      expect(container.querySelector('audio')?.getAttribute('src')).toBe(`/static/audio/alphabet-v1/sounds/${label.toLowerCase()}/${id}-sound.mp3?v=sounds-v9`);
    }
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
  });

  it('retains the word-initial vowel example without calling it a practice syllable', async () => {
    const {container} = render(<Alphabet/>);
    await click(screen.getByRole('button', {name: 'Listen to Е е sound, vowel'}));
    const detail = screen.getByRole('complementary', {name: 'About Е е'});
    expect(within(detail).getByText('Sound at the start of a word')).toBeTruthy();
    expect(within(detail).getByRole('button', {name: 'Stop sound: Е'})).toBeTruthy();
    expect(detail.textContent).not.toContain('Practice syllable:');
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/female/ye-sound.mp3?v=sounds-v9');
  });

  it('refreshes the corrected male Е for both sound and name without substituting Э', async () => {
    const {container} = render(<Alphabet/>);
    await click(screen.getByRole('radio', {name: 'Male', exact: true}));
    await click(screen.getByRole('button', {name: 'Listen to Е е sound, vowel'}));
    const audio = container.querySelector('audio')!;
    expect(audio.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/male/ye-sound.mp3?v=sounds-v9');
    await click(screen.getByRole('button', {name: 'Listen to letter name: е'}));
    expect(audio.getAttribute('src')).toBe('/static/audio/alphabet-v1/male/ye-name.mp3?v=ye-v2');
    await click(screen.getByRole('button', {name: 'Listen to Э э sound, vowel'}));
    expect(audio.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/male/e-sound.mp3?v=sounds-v9');
  });

  it('retries a failed syllable only on request and never substitutes its letter name', async () => {
    const attempted: (string | null)[] = [];
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(function (this: HTMLMediaElement) {
      attempted.push(this.getAttribute('src'));
      return Promise.reject(new Error('Syllable recording unavailable'));
    });
    const {container} = render(<Alphabet/>);
    await click(screen.getByRole('button', {name: 'Listen to syllable па for П п, consonant'}));
    expect(attempted).toEqual(['/static/audio/alphabet-v1/sounds/female/pe-sound.mp3?v=sounds-v9']);
    expect(container.querySelector('audio')?.getAttribute('src')).toBeNull();
    expect(screen.getByRole('status').textContent).toContain('Press a play button to try again.');
    enter(letterButtons()[1]);
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name: 'Listen to letter name: пэ'})).toBeTruthy();
    await click(screen.getByRole('button', {name: 'Listen to syllable: па'}));
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/female/pe-sound.mp3?v=sounds-v9');
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('status')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    ['Female', 'female', ''],
    ['Male', 'male', 'male/'],
  ] as const)('plays the %s practice syllable, letter name, and word only after an explicit click', async (label, voice, folder) => {
    const {container} = render(<Alphabet/>);
    const audio = container.querySelector('audio')!;
    await click(voiceRadio(label));
    expect(voiceRadio(label).checked).toBe(true);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(audio.getAttribute('src')).toBeNull();
    await click(screen.getByRole('button', {name: 'Listen to syllable ба for Б б, consonant'}));
    expect(audio.getAttribute('src')).toBe(`/static/audio/alphabet-v1/sounds/${voice}/be-sound.mp3?v=sounds-v9`);
    expect(screen.getByRole('button', {name: 'Stop syllable: ба'})).toBeTruthy();
    await click(screen.getByRole('button', {name: 'Listen to word: бана́н (banana)'}));
    expect(audio.getAttribute('src')).toBe(`/static/audio/alphabet-v1/${folder}be-word.mp3`);
    await click(screen.getByRole('button', {name: 'Listen to letter name: бэ'}));
    expect(audio.getAttribute('src')).toBe(`/static/audio/alphabet-v1/${folder}be-name.mp3`);
    await click(screen.getByRole('button', {name: 'Listen to syllable: ба'}));
    expect(audio.getAttribute('src')).toBe(`/static/audio/alphabet-v1/sounds/${voice}/be-sound.mp3?v=sounds-v9`);
    await click(screen.getByRole('button', {name: 'Stop syllable: ба'}));
    expect(audio.getAttribute('src')).toBeNull();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(4);
    expect(container.querySelectorAll('audio')).toHaveLength(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    ['Ъ', 'ъ', 'hard-sign', 'твёрдый знак', 'объе́кт', 'object'],
    ['Ь', 'ь', 'soft-sign', 'мя́гкий знак', 'дверь', 'door'],
  ] as const)('selects %s silently, stopping an active sound while keeping its name and example playable', async (upper, lower, id, name, example, meaning) => {
    const {container} = render(<Alphabet/>);
    const audio = container.querySelector('audio')!;
    await click(letterButtons()[0]);
    const pauses = vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length;
    const sign = screen.getByRole('button', {name: `Explore ${upper} ${lower}, ${id === 'hard-sign' ? 'hard' : 'soft'} sign`});
    await click(sign);
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(pauses + 1);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(audio.getAttribute('src')).toBeNull();
    expect(sign.getAttribute('aria-pressed')).toBe('true');
    const detail = screen.getByRole('complementary', {name: `About ${upper} ${lower}`});
    expect(within(detail).getByText('No sound of its own.')).toBeTruthy();
    expect(within(detail).queryByRole('button', {name: /(?:sound|syllable):/})).toBeNull();
    await click(voiceRadio('Male'));
    await click(sign);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(audio.getAttribute('src')).toBeNull();
    await click(screen.getByRole('button', {name: `Listen to letter name: ${name}`}));
    expect(audio.getAttribute('src')).toBe(`/static/audio/alphabet-v1/male/${id}-name.mp3`);
    await click(screen.getByRole('button', {name: `Listen to word: ${example} (${meaning})`}));
    expect(audio.getAttribute('src')).toBe(`/static/audio/alphabet-v1/male/${id}-word.mp3`);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole('status')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('remembers each voice choice across visits without automatically starting a clip', async () => {
    const first = render(<Alphabet/>);
    await click(voiceRadio('Male'));
    expect(localStorage.getItem(voicePreference)).toBe('male');
    first.unmount();
    const second = render(<Alphabet/>);
    expect(voiceRadio('Male').checked).toBe(true);
    expect(second.container.querySelector('audio')?.getAttribute('src')).toBeNull();
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    await click(screen.getByRole('button', {name: 'Listen to sound: А'}));
    expect(second.container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/male/a-sound.mp3?v=sounds-v9');
    await click(screen.getByRole('button', {name: 'Listen to letter name: а'}));
    expect(second.container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/male/a-name.mp3');
    await click(screen.getByRole('button', {name: 'Listen to word: арбу́з (watermelon)'}));
    expect(second.container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/male/a-word.mp3');
    await click(voiceRadio('Female'));
    expect(localStorage.getItem(voicePreference)).toBe('female');
    second.unmount();
    render(<Alphabet/>);
    expect(voiceRadio('Female').checked).toBe(true);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(3);
  });

  it.each(['unknown', 'MALE', ''])('defaults to female for an unsupported saved preference %j', preference => {
    localStorage.setItem(voicePreference, preference);
    const {container} = render(<Alphabet/>);
    expect(voiceRadio('Female').checked).toBe(true);
    expect(voiceRadio('Male').checked).toBe(false);
    expect(container.querySelector('audio')?.getAttribute('src')).toBeNull();
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('keeps both voices usable when reading and writing local storage fail', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Storage is disabled', 'SecurityError'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Storage is full', 'QuotaExceededError'); });
    const {container} = render(<Alphabet/>);
    expect(voiceRadio('Female').checked).toBe(true);
    await click(voiceRadio('Male'));
    expect(voiceRadio('Male').checked).toBe(true);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    await click(letterButtons()[0]);
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/male/a-sound.mp3?v=sounds-v9');
    await click(voiceRadio('Female'));
    expect(container.querySelector('audio')?.getAttribute('src')).toBeNull();
    await click(screen.getByRole('button', {name: 'Listen to word: арбу́з (watermelon)'}));
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/a-word.mp3');
    expect(screen.queryByRole('status')).toBeNull();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
  });

  it('silently stops a pending clip on voice change and ignores its late rejection', async () => {
    let rejectOld!: (reason: Error) => void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectOld = reject; }));
    const {container} = render(<Alphabet/>);
    const audio = container.querySelector('audio')!;
    await click(letterButtons()[1]);
    const pauses = vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length;
    await click(voiceRadio('Male'));
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(pauses + 1);
    expect(audio.getAttribute('src')).toBeNull();
    expect(screen.getByRole('button', {name: 'Listen to letter name: бэ'})).toBeTruthy();
    expect(letterButtons()[1].getAttribute('aria-pressed')).toBe('true');
    enter(letterButtons()[2]);
    fireEvent.mouseEnter(letterButtons()[3]);
    enter(letterButtons()[4], 'touch');
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('status')).toBeNull();
    await click(screen.getByRole('button', {name: 'Listen to syllable: ба'}));
    await act(async () => { rejectOld(new Error('Previous voice was interrupted')); });
    expect(audio.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/male/be-sound.mp3?v=sounds-v9');
    expect(screen.getByRole('button', {name: 'Stop syllable: ба'})).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not interrupt audio when the selected voice is clicked again', async () => {
    const {container} = render(<Alphabet/>);
    await click(letterButtons()[0]);
    const pauses = vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length;
    await click(voiceRadio('Female'));
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(pauses);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/female/a-sound.mp3?v=sounds-v9');
  });

  it('never plays or changes selection on mouse or pointer entry, before or after a click', async () => {
    const {container} = render(<Alphabet/>);
    const buttons = letterButtons();
    enter(buttons[1]);
    fireEvent.mouseEnter(buttons[2]);
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    await click(buttons[0]);
    enter(buttons[1]);
    fireEvent.mouseEnter(buttons[2]);
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/female/a-sound.mp3?v=sounds-v9');
    expect(buttons[0].getAttribute('aria-pressed')).toBe('true');
    fireEvent.ended(container.querySelector('audio')!);
    enter(buttons[3]);
    fireEvent.mouseEnter(buttons[4]);
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(container.querySelector('audio')?.getAttribute('src')).toBeNull();
    expect(buttons[0].getAttribute('aria-pressed')).toBe('true');
  });

  it('ignores a legacy enabled hover preference across visits and exposes no hover control', async () => {
    localStorage.setItem('word-post-alphabet-hover-sound', 'on');
    const first = render(<Alphabet/>);
    expect(screen.queryByRole('switch')).toBeNull();
    await click(letterButtons()[0]);
    enter(letterButtons()[1]);
    fireEvent.mouseEnter(letterButtons()[2]);
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    await click(letterButtons()[1]);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    first.unmount();
    render(<Alphabet/>);
    expect(screen.queryByRole('switch')).toBeNull();
    enter(letterButtons()[0]);
    await advance(1000);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
  });

  it('lets keyboard users navigate every letter without unexpected playback', async () => {
    render(<Alphabet/>);
    const buttons = letterButtons();
    buttons[0].focus();
    fireEvent.keyDown(buttons[0], {key: 'ArrowRight'});
    expect(document.activeElement).toBe(buttons[1]);
    expect(buttons[1].getAttribute('aria-pressed')).toBe('true');
    fireEvent.keyDown(buttons[1], {key: 'End'});
    expect(document.activeElement).toBe(buttons[30]);
    fireEvent.keyDown(buttons[30], {key: 'Home'});
    expect(document.activeElement).toBe(buttons[0]);
    fireEvent.keyDown(buttons[0], {key: 'ArrowDown'});
    expect(document.activeElement).toBe(buttons[7]);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    // Native buttons leave Enter/Space uncancelled; the browser activates them
    // with a click whose detail is zero (jsdom does not synthesize that click).
    for (const key of ['Enter', ' ']) {
      expect(fireEvent.keyDown(buttons[7], {key})).toBe(true);
      fireEvent.keyUp(buttons[7], {key});
      await act(async () => { fireEvent.click(buttons[7], {detail: 0}); });
    }
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('complementary', {name: 'About Ж ж'})).toBeTruthy();
    expect(buttons.filter(button => button.tabIndex === 0)).toHaveLength(1);
  });

  it('keeps both groups keyboard-accessible when a silent sign is selected', () => {
    render(<Alphabet/>);
    const letters = letterButtons();
    const signs = signButtons();
    expect(signs[0].tabIndex).toBe(0);
    signs[0].focus();
    fireEvent.keyDown(signs[0], {key: 'ArrowRight'});
    expect(document.activeElement).toBe(signs[1]);
    expect(signs[1].getAttribute('aria-pressed')).toBe('true');
    expect(letters[0].tabIndex).toBe(0);
    expect(signs.filter(button => button.tabIndex === 0)).toHaveLength(1);
    expect(screen.getByRole('complementary', {name: 'About Ь ь'})).toBeTruthy();
    expect(screen.getByText('Letter 30 / 33')).toBeTruthy();
    fireEvent.keyDown(signs[1], {key: 'Home'});
    expect(document.activeElement).toBe(signs[0]);
    letters[0].focus();
    fireEvent.keyDown(letters[0], {key: 'End'});
    expect(document.activeElement).toBe(letters[30]);
    expect(signs[0].tabIndex).toBe(0);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('plays the contextual word from its tile and reuses one player, stopping the previous clip', async () => {
    const {container} = render(<Alphabet/>);
    const audio = container.querySelector('audio')!;
    await click(letterButtons()[1]);
    const pauses = vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length;
    await click(screen.getByRole('button', {name: 'Listen to word: бана́н (banana)'}));
    expect(audio.getAttribute('src')).toBe('/static/audio/alphabet-v1/be-word.mp3');
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(pauses + 1);
    expect(container.querySelectorAll('audio')).toHaveLength(1);
    expect(vi.mocked(HTMLMediaElement.prototype.play).mock.contexts).toEqual([audio, audio]);
    await click(screen.getByRole('button', {name: 'Stop word: бана́н (banana)'}));
    expect(audio.getAttribute('src')).toBeNull();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps touch selection explicit and never starts synthetic hover audio', async () => {
    render(<Alphabet/>);
    await click(letterButtons()[0]);
    enter(letterButtons()[1], 'touch');
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    await click(letterButtons()[1]);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
  });

  it('offers a friendly manual retry after blocked playback without enabling hover', async () => {
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException('Playback blocked', 'NotAllowedError'));
    render(<Alphabet/>);
    await click(letterButtons()[0]);
    expect(screen.getByRole('status').textContent).toContain('Press a play button to try again.');
    enter(letterButtons()[1]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    await click(screen.getByRole('button', {name: 'Listen to sound: А'}));
    expect(screen.queryByRole('status')).toBeNull();
    enter(letterButtons()[1]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
  });

  it('ignores a superseded play rejection so the new letter stays selected and playable', async () => {
    let rejectOld!: (reason: Error) => void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectOld = reject; }));
    const {container} = render(<Alphabet/>);
    await click(letterButtons()[0]);
    await click(letterButtons()[1]);
    await act(async () => { rejectOld(new Error('Previous clip was interrupted')); });
    expect(screen.queryByRole('status')).toBeNull();
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/sounds/female/be-sound.mp3?v=sounds-v9');
    expect(screen.getByRole('button', {name: 'Stop syllable: ба'})).toBeTruthy();
  });

  it('cancels active audio when leaving the page without delayed playback', async () => {
    const {container, unmount} = render(<Alphabet/>);
    const audio = container.querySelector('audio')!;
    await click(letterButtons()[0]);
    enter(letterButtons()[1]);
    vi.mocked(HTMLMediaElement.prototype.pause).mockClear();
    unmount();
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(1);
    expect(audio.getAttribute('src')).toBeNull();
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  });
});
