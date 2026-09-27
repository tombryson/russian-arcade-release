import { useGameText } from "./GameLocale";
import { useContext } from 'preact/hooks';
import { GameMedia } from './GameLocale';
import { useEffect, useRef, useState } from 'preact/hooks';
import { getGameAudio, prepareGameAudio } from './journey-games-api';
let playingClue: {
  audio: HTMLAudioElement;
  stop: () => void;
} | null = null;
type AudioClueProps = {
  text?: string;
  audioKey: string;
  label?: string;
  onHeard?: (key: string) => Promise<void>;
  disabled?: boolean;
  hideText?: boolean;
};
export function AudioClue(props: AudioClueProps) {
  const enabled = useContext(GameMedia);
  if (!enabled) return props.hideText ? null : <div class="journey-game-clue"><p lang="ru">{props.text}</p></div>;
  return <AudioCluePlayer key={props.audioKey} {...props} />;
}
function AudioCluePlayer({
  text,
  audioKey,
  label,
  onHeard,
  disabled = false,
  hideText = false
}: AudioClueProps) {
  const t = useGameText();
  const [status, setStatus] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle');
  const [error, setError] = useState('');
  const audio = useRef<HTMLAudioElement | null>(null),
    mounted = useRef(true),
    pending = useRef(false),
    url = useRef(''),
    abort = useRef(new AbortController());
  useEffect(() => () => {
    mounted.current = false;
    abort.current.abort();
    audio.current?.pause();
    if (playingClue?.audio === audio.current) playingClue = null;
    audio.current = null;
  }, []);
  async function play() {
    if (pending.current) return;
    if (status === 'playing') {
      audio.current?.pause();
      setStatus('idle');
      return;
    }
    pending.current = true;
    setStatus('loading');
    setError('');
    try {
      if (!url.current) {
        let prepared = await prepareGameAudio(audioKey);
        if (!mounted.current) return;
        for (let attempt = 0; prepared.status === 'pending' && attempt < 10; attempt++) {
          await new Promise(resolve => setTimeout(resolve, 900));
          if (!mounted.current) return;
          prepared = await getGameAudio(audioKey, abort.current.signal);
        }
        url.current = prepared.url ?? '';
        if (!url.current) throw new Error(prepared.message || t("The recording is not ready yet. Try listening again."));
      }
      if (!audio.current) {
        audio.current = new Audio(url.current);
        audio.current.onended = () => {
          if (mounted.current) setStatus('idle');
        };
        audio.current.onerror = () => {
          if (mounted.current) {
            setStatus('error');
            setError(t("The recording could not play. Try listening again."));
          }
          url.current = '';
          audio.current = null;
        };
      }
      if (playingClue?.audio !== audio.current) playingClue?.stop();
      playingClue = {
        audio: audio.current,
        stop: () => {
          audio.current?.pause();
          if (mounted.current) setStatus('idle');
        }
      };
      audio.current.currentTime = 0;
      await audio.current.play();
      if (mounted.current) {
        setStatus('playing');
        await onHeard?.(audioKey);
      }
    } catch (cause) {
      if (mounted.current) {
        setStatus('error');
        setError(cause instanceof Error ? cause.message : t("The recording could not play."));
      }
    } finally {
      pending.current = false;
    }
  }
  return <div class="journey-game-clue"><div class="journey-game-clue-row">{!hideText && text && <p lang="ru">{text}</p>}<button class="journey-game-audio" disabled={disabled || status === 'loading'} onClick={() => void play()} aria-label={status === 'playing' ? text && !hideText ? t("Stop recording: {0}", {
        "0": text
      }) : t("Stop recording") : label ?? (text ? t("Listen: {0}", {
        "0": text
      }) : t("Listen to the message"))} title={status === 'playing' ? t("Stop recording") : t("Listen in Russian")}>{status === 'loading' ? <span class="journey-game-audio-loading" aria-hidden="true">…</span> : status === 'playing' ? <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6v12M16 6v12" /></svg> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 9h4l5-4v14l-5-4H3zM16 8a6 6 0 0 1 0 8M19 5a10 10 0 0 1 0 14" /></svg>}</button></div>{error && <p class="journey-game-audio-error" role="status">{error}</p>}</div>;
}
