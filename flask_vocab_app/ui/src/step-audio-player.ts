type PlaybackHandlers = {
  onEnded(): void;
  onError(): void;
};

// Keep the element outside the route component. The Start gesture can authorise
// it before the request completes, and the conversation reuses that element.
let player: HTMLAudioElement | undefined;
let generation = 0;
let releasePlayback: (() => void) | undefined;
let playbackAuthorised = false;
let priming = false;

function getPlayer(): HTMLAudioElement {
  if (!player) {
    player = new Audio();
    player.preload = 'auto';
  }
  return player;
}

export function stopStepAudio(): void {
  generation += 1;
  releasePlayback?.();
  releasePlayback = undefined;
  if (player) {
    player.pause();
    player.removeAttribute('src');
    // Abort pending loading/play requests and queued events for the old source.
    player.load();
  }
}

async function startPlayback(
  url: string,
  handlers: PlaybackHandlers,
  releaseSource?: () => void,
): Promise<void> {
  stopStepAudio();
  const audio = getPlayer();
  const current = ++generation;
  let finished = false;

  const release = () => {
    audio.removeEventListener('ended', ended);
    audio.removeEventListener('error', failed);
    releaseSource?.();
  };
  const finish = (callback: () => void) => {
    if (current !== generation || finished) return;
    finished = true;
    release();
    releasePlayback = undefined;
    callback();
  };
  const ended = () => finish(handlers.onEnded);
  const failed = () => finish(handlers.onError);

  audio.src = url;
  audio.load();
  audio.addEventListener('ended', ended);
  audio.addEventListener('error', failed);
  releasePlayback = release;

  try {
    await audio.play();
    if (current === generation) playbackAuthorised = true;
  } catch (error) {
    // A route change or the next line may cancel a pending play promise.
    if (current !== generation || finished) return;
    failed();
    throw error;
  }
}

export function playStepAudio(url: string, handlers: PlaybackHandlers): Promise<void> {
  return startPlayback(url, handlers);
}

function silentWav(): Blob {
  // Twenty milliseconds of 16-bit mono silence at 8 kHz.
  const samples = 160;
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  text(0, 'RIFF');
  view.setUint32(4, buffer.byteLength - 8, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples * 2, true);
  return new Blob([buffer], { type: 'audio/wav' });
}

export function primeStepAudio(): void {
  if (playbackAuthorised || priming || releasePlayback) return;
  const url = URL.createObjectURL(silentWav());
  priming = true;
  // This calls play synchronously within the Start click. Browser policy can
  // still reject it; the actual line's failure handler offers a replay action.
  void startPlayback(url, {
    onEnded() {},
    onError() {},
  }, () => URL.revokeObjectURL(url)).catch(() => {}).finally(() => { priming = false; });
}
