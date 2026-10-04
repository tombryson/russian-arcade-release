import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/preact';
import {Alphabet} from './Alphabet';

const letterButtons = () => within(screen.getByRole('list', {name: 'Russian letters'})).getAllByRole('button');
async function click(element: HTMLElement) { await act(async () => { fireEvent.click(element); }); }
async function advance(milliseconds: number) { await act(async () => { vi.advanceTimersByTime(milliseconds); }); }
function enter(element: HTMLElement, pointerType = 'mouse') {
  const event = new Event('pointerenter');
  Object.defineProperty(event, 'pointerType', {value: pointerType});
  fireEvent(element, event);
}
function leave(element: HTMLElement) { fireEvent(element, new Event('pointerleave')); }

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
    expect(buttons).toHaveLength(33);
    expect(buttons[0].textContent).toBe('Аа');
    expect(buttons[32].textContent).toBe('Яя');
    expect(buttons.filter(button => button.getAttribute('aria-label')?.endsWith(', vowel'))).toHaveLength(10);
    expect(buttons.filter(button => button.getAttribute('aria-label')?.endsWith(', consonant'))).toHaveLength(21);
    expect(buttons.filter(button => button.getAttribute('aria-label')?.endsWith(', sign'))).toHaveLength(2);
    expect(screen.getByRole('link', {name: 'Your first delivery'}).getAttribute('href')).toBe('#first-delivery');
    expect(screen.getByText('Select a letter to listen. Then hover to hear others.')).toBeTruthy();
    expect(container.querySelector('audio')?.getAttribute('src')).toBeNull();
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('unlocks hover with an explicit play, debounces movement, and cancels a passing hover', async () => {
    const {container} = render(<Alphabet/>);
    const buttons = letterButtons();
    enter(buttons[1]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    await click(buttons[0]);
    enter(buttons[1]);
    await advance(90);
    leave(buttons[1]);
    enter(buttons[2]);
    await advance(170);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    await advance(20);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/ve-name.mp3');
    expect(buttons[2].getAttribute('aria-pressed')).toBe('true');
    enter(buttons[3]);
    leave(buttons[3]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
  });

  it('honours the hover preference across visits while keeping manual playback available', async () => {
    const first = render(<Alphabet/>);
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
    await click(screen.getByRole('switch'));
    await click(letterButtons()[0]);
    enter(letterButtons()[1]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    await click(letterButtons()[1]);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    first.unmount();
    render(<Alphabet/>);
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('lets keyboard users navigate every letter without unexpected playback', async () => {
    render(<Alphabet/>);
    const buttons = letterButtons();
    buttons[0].focus();
    fireEvent.keyDown(buttons[0], {key: 'ArrowRight'});
    expect(document.activeElement).toBe(buttons[1]);
    expect(buttons[1].getAttribute('aria-pressed')).toBe('true');
    fireEvent.keyDown(buttons[1], {key: 'End'});
    expect(document.activeElement).toBe(buttons[32]);
    fireEvent.keyDown(buttons[32], {key: 'Home'});
    expect(document.activeElement).toBe(buttons[0]);
    fireEvent.keyDown(buttons[0], {key: 'ArrowDown'});
    expect(document.activeElement).toBe(buttons[7]);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    await click(buttons[7]);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('complementary', {name: 'About Ж ж'})).toBeTruthy();
    expect(buttons.filter(button => button.tabIndex === 0)).toHaveLength(1);
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

  it('offers a friendly manual retry after blocked playback and suspends hover until it succeeds', async () => {
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException('Playback blocked', 'NotAllowedError'));
    render(<Alphabet/>);
    await click(letterButtons()[0]);
    expect(screen.getByRole('status').textContent).toContain('Press a play button to try again.');
    enter(letterButtons()[1]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    await click(screen.getByRole('button', {name: 'Listen to letter name: а'}));
    expect(screen.queryByRole('status')).toBeNull();
    enter(letterButtons()[1]);
    await advance(250);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(3);
  });

  it('ignores a superseded play rejection so the new letter stays selected and playable', async () => {
    let rejectOld!: (reason: Error) => void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectOld = reject; }));
    const {container} = render(<Alphabet/>);
    await click(letterButtons()[0]);
    await click(letterButtons()[1]);
    await act(async () => { rejectOld(new Error('Previous clip was interrupted')); });
    expect(screen.queryByRole('status')).toBeNull();
    expect(container.querySelector('audio')?.getAttribute('src')).toBe('/static/audio/alphabet-v1/be-name.mp3');
    expect(screen.getByRole('button', {name: 'Stop letter name: бэ'})).toBeTruthy();
  });

  it('cancels active audio and queued hover when leaving the page', async () => {
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
