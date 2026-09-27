import { useGameText } from "./GameLocale";
import { useEffect, useRef, useState } from 'preact/hooks';
import { GameWords } from './GameWords';
import { getGameAudio, prepareGameAudio, type GameBroadcast, type GameRound } from './journey-games-api';

/** A complete programme stays mounted while the learner answers its questions. */
export function RadioBroadcast({
  sessionId,
  broadcast,
  busy,
  onHeard,
  onTranscript,
  compact = false
}: {
  compact?: boolean;
  sessionId: string;
  broadcast: GameBroadcast;
  busy: boolean;
  onHeard: () => Promise<void>;
  onTranscript: () => void;
}) {
  const t = useGameText();
  const [url, setUrl] = useState(''),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0),
    [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement>(null),
    pendingReceipt = useRef(false);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setUrl('');
    setError('');
    setPlaying(false);
    async function load() {
      try {
        let result = await getGameAudio(broadcast.audio_key, abort.signal);
        if (result.status !== 'ready' && !abort.signal.aborted) result = await prepareGameAudio(broadcast.audio_key);
        for (let attempt = 0; result.status === 'pending' && attempt < 10 && !abort.signal.aborted; attempt++) {
          await new Promise<void>(resolve => {
            const stop = () => {
              clearTimeout(timer);
              abort.signal.removeEventListener('abort', stop);
              resolve();
            };
            timer = setTimeout(stop, 900);
            abort.signal.addEventListener('abort', stop, {
              once: true
            });
          });
          if (abort.signal.aborted) return;
          result = await getGameAudio(broadcast.audio_key, abort.signal);
        }
        if (abort.signal.aborted) return;
        if (!result.url || result.status !== 'ready') throw new Error(result.message || t("The programme could not load. Try loading it again."));
        setUrl(result.url);
      } catch (cause) {
        if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : t("The programme could not load."));
      }
    }
    void load();
    return () => {
      abort.abort();
      clearTimeout(timer);
      audio.current?.pause();
    };
  }, [broadcast.audio_key, revision]);
  async function heard() {
    setPlaying(false);
    if (broadcast.listened || pendingReceipt.current) return;
    pendingReceipt.current = true;
    try {
      await onHeard();
    } finally {
      pendingReceipt.current = false;
    }
  }
  return <section class={`radio-programme${compact ? ' is-compact' : ''}`} aria-label={t("Radio programme")}>
    <div class={`game-radio radio-programme-player${playing ? ' is-playing' : ''}`}>
      <div class="game-radio-top"><span class="game-radio-name">{t("Post Office Radio")}</span><span class="radio-on-air"><span class="game-radio-light" aria-hidden="true" />{playing ? t("On air") : t("Ready to tune in")}</span></div>
      <div class="game-radio-tuner" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
      <div class="radio-programme-face"><div class="game-radio-grille" aria-hidden="true" /><div class="radio-programme-controls"><p class="radio-programme-label">{t("Today’s programme")}</p><h2>{broadcast.title}</h2>
        {url ? <audio ref={audio} controls preload="metadata" src={url} aria-label={t("Listen to the radio programme")} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => void heard()} onError={() => {
            setError(t("The recording could not play. Try loading it again."));
            setPlaying(false);
          }} /> : !error && <p role="status">{t("Loading the programme…")}</p>}
        {error && <div class="radio-player-error" role="alert"><p>{error}</p><button class="text-link" onClick={() => setRevision(value => value + 1)}>{t("Reload recording")}</button></div>}
        <p class="radio-player-note">{t("Listen at your own pace. You can pause, rewind or listen again.")}</p>
      </div></div>
    </div>
    {broadcast.script ? <details class="radio-programme-transcript" open={broadcast.transcript}><summary>{t("Programme transcript")}</summary><GameWords sessionId={sessionId} text={broadcast.script} /></details> : <button class="text-link radio-transcript-toggle" disabled={busy} onClick={onTranscript}>{t("Show transcript")}</button>}
  </section>;
}
export function RadioQuestions({
  round,
  selected,
  onChange,
  disabled,
  expected
}: {
  round: GameRound;
  selected: string[];
  onChange: (answer: string[]) => void;
  disabled: boolean;
  expected?: string[];
}) {
  const t = useGameText();
  return <div class="radio-question-options" role="group" aria-label={t("Answer choices")}>{round.choices?.map((choice, index) => {
      const chosen = selected[0] === choice.id,
        correct = expected?.includes(choice.id),
        incorrect = !!expected && chosen && !correct;
      return <button key={choice.id} class={`radio-question-choice${chosen ? ' is-selected' : ''}${correct ? ' is-correct' : ''}${incorrect ? ' is-incorrect' : ''}`} aria-pressed={chosen} disabled={disabled} onClick={() => onChange([choice.id])}><span class="radio-choice-letter" aria-hidden="true">{String.fromCharCode(65 + index)}</span><span lang="ru">{choice.text}</span>{correct && <span class="radio-choice-result" aria-label={t("Correct answer")}>✓</span>}{incorrect && <span class="radio-choice-result" aria-label={t("Your answer")}>×</span>}</button>;
    })}</div>;
}
