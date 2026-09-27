import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class TestAudio extends EventTarget {
  src = '';
  preload = '';
  play = vi.fn<() => Promise<void>>().mockResolvedValue();
  pause = vi.fn();
  load = vi.fn();
  removeAttribute = vi.fn((name: string) => { if (name === 'src') this.src = ''; });
}

describe('Step-through audio player', () => {
  let media: TestAudio;
  let createAudio: ReturnType<typeof vi.fn>;
  let audio: typeof import('./step-audio-player');
  const handlers = () => ({ onEnded: vi.fn(), onError: vi.fn() });

  beforeEach(async () => {
    vi.resetModules();
    media = new TestAudio();
    createAudio = vi.fn(function () { return media; });
    vi.stubGlobal('Audio', createAudio);
    class TestURL extends URL {
      static createObjectURL = vi.fn(() => 'blob:step-silence');
      static revokeObjectURL = vi.fn();
    }
    vi.stubGlobal('URL', TestURL);
    audio = await import('./step-audio-player');
  });

  afterEach(() => {
    audio.stopStepAudio();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('primes on the Start gesture and reuses that element for the conversation', async () => {
    expect(createAudio).not.toHaveBeenCalled();
    audio.primeStepAudio();
    expect(media.play).toHaveBeenCalledTimes(1);
    expect(media.src).toBe('blob:step-silence');
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.objectContaining({ type: 'audio/wav' }));

    const npc = handlers();
    await audio.playStepAudio('/npc.mp3', npc);
    expect(createAudio).toHaveBeenCalledTimes(1);
    expect(media.src).toBe('/npc.mp3');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:step-silence');
    media.dispatchEvent(new Event('ended'));
    expect(npc.onEnded).toHaveBeenCalledTimes(1);

    await audio.playStepAudio('/learner.mp3', handlers());
    expect(createAudio).toHaveBeenCalledTimes(1);
  });

  it('releases the priming URL when the silent clip ends', () => {
    audio.primeStepAudio();
    media.dispatchEvent(new Event('ended'));
    audio.stopStepAudio();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  });

  it('does not replace a playing line or repeat priming after successful playback', async () => {
    await audio.playStepAudio('/npc.mp3', handlers());
    audio.primeStepAudio();
    expect(media.src).toBe('/npc.mp3');
    expect(media.play).toHaveBeenCalledTimes(1);
    media.dispatchEvent(new Event('ended'));
    audio.stopStepAudio();
    audio.primeStepAudio();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('ignores a pending play rejection after leaving the conversation', async () => {
    let rejectPlay!: (reason: Error) => void;
    media.play.mockImplementationOnce(() => new Promise((_, reject) => { rejectPlay = reject; }));
    const npc = handlers();
    const pending = audio.playStepAudio('/npc.mp3', npc);
    audio.stopStepAudio();
    rejectPlay(new DOMException('Interrupted by load', 'AbortError'));

    await expect(pending).resolves.toBeUndefined();
    media.dispatchEvent(new Event('ended'));
    media.dispatchEvent(new Event('error'));
    expect(npc.onEnded).not.toHaveBeenCalled();
    expect(npc.onError).not.toHaveBeenCalled();
    expect(media.src).toBe('');
    expect(media.pause).toHaveBeenCalled();
  });

  it('does not let a previous line finish or fail the current line', async () => {
    const listeners = vi.spyOn(media, 'addEventListener');
    const previous = handlers();
    await audio.playStepAudio('/previous.mp3', previous);
    const previousListeners = listeners.mock.calls.map(([, listener]) => listener as EventListener);
    const current = handlers();
    await audio.playStepAudio('/current.mp3', current);

    for (const listener of previousListeners) listener(new Event('ended'));
    expect(previous.onEnded).not.toHaveBeenCalled();
    expect(previous.onError).not.toHaveBeenCalled();
    expect(current.onEnded).not.toHaveBeenCalled();
    media.dispatchEvent(new Event('ended'));
    media.dispatchEvent(new Event('ended'));
    expect(current.onEnded).toHaveBeenCalledTimes(1);
  });

  it('reports a blocked current clip once so the UI can offer replay', async () => {
    const blocked = new DOMException('Playback requires interaction', 'NotAllowedError');
    media.play.mockRejectedValueOnce(blocked);
    const npc = handlers();
    await expect(audio.playStepAudio('/npc.mp3', npc)).rejects.toBe(blocked);
    media.dispatchEvent(new Event('error'));
    expect(npc.onError).toHaveBeenCalledTimes(1);
    expect(npc.onEnded).not.toHaveBeenCalled();
  });

  it('ignores an old pending rejection after the next clip starts', async () => {
    let rejectPlay!: (reason: Error) => void;
    media.play.mockImplementationOnce(() => new Promise((_, reject) => { rejectPlay = reject; }));
    const previous = handlers();
    const pending = audio.playStepAudio('/previous.mp3', previous);
    const current = handlers();
    await audio.playStepAudio('/current.mp3', current);
    rejectPlay(new DOMException('New source selected', 'AbortError'));
    await expect(pending).resolves.toBeUndefined();
    expect(previous.onError).not.toHaveBeenCalled();
    media.dispatchEvent(new Event('ended'));
    expect(current.onEnded).toHaveBeenCalledTimes(1);
  });
});
