import { useGameText } from "./GameLocale";
import { useEffect, useRef, useState } from 'preact/hooks';
import { ApiError } from './learning-api';
import { getGame, prepareGame, type GameState } from './journey-games-api';
export function GamePreparation({
  initial,
  onReady,
  onBlocked
}: {
  initial: GameState;
  onReady: (state: GameState) => void;
  onBlocked: (error: unknown) => void;
}) {
  const t = useGameText();
  const [state, setState] = useState(initial),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0),
    [working, setWorking] = useState(false);
  const callbacks = useRef({
    onReady,
    onBlocked
  });
  callbacks.current = {
    onReady,
    onBlocked
  };
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    if (revision === 0 && initial.preparation?.status === 'failed') return () => controller.abort();
    async function run() {
      setWorking(true);
      setError('');
      try {
        let next = initial.preparation?.status === 'ready' && revision === 0 ? await getGame(initial.id, controller.signal) : await prepareGame(initial.id, revision > 0, controller.signal);
        while (!controller.signal.aborted) {
          if (next.profile_id !== initial.profile_id) throw new ApiError(t("Your profile changed. Reopen this page before continuing."), 'profile_changed');
          if (next.phase !== 'preparing') {
            callbacks.current.onReady(next);
            return;
          }
          setState(next);
          if (!['pending', 'running'].includes(next.preparation?.status ?? '')) return;
          await new Promise<void>(resolve => {
            const stop = () => {
              clearTimeout(timer);
              controller.signal.removeEventListener('abort', stop);
              resolve();
            };
            timer = setTimeout(stop, 900);
            controller.signal.addEventListener('abort', stop, {
              once: true
            });
          });
          if (controller.signal.aborted) return;
          next = await prepareGame(initial.id, false, controller.signal);
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          if (cause instanceof ApiError && ['profile_changed', 'locked', 'not_found', 'unauthorized', 'csrf_failed'].includes(cause.code)) callbacks.current.onBlocked(cause);else setError(cause instanceof Error ? cause.message : t("Preparation paused. You can retry from here."));
        }
      } finally {
        if (!controller.signal.aborted) setWorking(false);
      }
    }
    void run();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [initial.id, revision]);
  const radio = state.game_id === 'radio', delivery=state.game_id==='directions',
    progress = state.preparation,
    failed = progress?.status === 'failed' || !!error;
  return <div class="game-preparation"><p class="kicker">{t("Getting your game ready")}</p><h2>{failed ? t("Preparation paused.") : delivery ? t("Preparing your delivery.") : radio ? t("Tuning in…") : t("Getting ready to play.")}</h2><p>{t(error || progress?.error || progress?.message || (radio ? "Writing and recording today’s programme." : "Preparing the words and material for this game."))}</p><progress aria-label={t("Game preparation")} value={progress?.ready ?? 0} max={Math.max(1, progress?.total ?? 1)} />{!!progress?.total && <p class="quiet">{progress.ready}{" "}{t("of")}{" "}{progress.total}{" "}{t("ready")}</p>}{failed && !working && <button class="cta" onClick={() => setRevision(value => value + 1)}>{t("Retry preparation")}{" "}<span aria-hidden="true">→</span></button>}{working && <p class="quiet" role="status">{radio ? t("The programme is being saved so you can replay it later.") : t("Your progress is saved as the game is prepared.")}</p>}</div>;
}
