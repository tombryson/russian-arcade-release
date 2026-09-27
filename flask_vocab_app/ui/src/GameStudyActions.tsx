import { useGameText } from "./GameLocale";
import { useEffect, useRef, useState } from 'preact/hooks';
import { api, ApiError } from './learning-api';
import type { GameWord } from './journey-games-api';
export function GameStudyActions({
  sessionId, words = []
}: {
  sessionId: string;
  words?: GameWord[];
}) {
  const t = useGameText();
  const choices = [...new Map(words.filter(word => word.card_key).map(word => [word.card_key, word])).values()];
  const [excluded, setExcluded] = useState<string[]>([]);
  const selected = choices.filter(word => !excluded.includes(word.card_key!));
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [blocked, setBlocked] = useState(false);
  const pending = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function open() {
    if (pending.current || (choices.length > 0 && !selected.length)) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api<{
        id: string;
      }>(`/api/v1/games/sessions/${encodeURIComponent(sessionId)}/flashcards`, choices.length ? {items: selected.map(word => word.card_key)} : {});
      if (!result || typeof result.id !== 'string' || !result.id) throw new Error(t("Your flashcards could not open. Please try again."));
      if (mounted.current) window.location.hash = `generate/${encodeURIComponent(result.id)}`;
    } catch (cause) {
      if (mounted.current) {
        setError(cause instanceof Error ? cause.message : t("Your flashcards could not open. Please try again."));
        setBlocked(cause instanceof ApiError && ['profile_changed', 'forbidden', 'profile_required', 'not_found'].includes(cause.code));
      }
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return <div class="journey-game-study"><p>{t("Keep these words fresh with flashcards, pictures and Russian audio.")}</p>
    {!!choices.length && <details class="journey-game-card-selection"><summary>{t("Choose words for flashcards")} · {selected.length}/{choices.length}</summary>
      <fieldset disabled={busy || blocked}><legend>{t("Keep the words you want to practise.")}</legend>
        {choices.map(word => <label key={word.card_key}>
          <input type="checkbox" checked={!excluded.includes(word.card_key!)} onChange={event => setExcluded(previous => event.currentTarget.checked ? previous.filter(key => key !== word.card_key) : [...previous, word.card_key!])} />
          <span><strong lang="ru">{word.form || word.lemma}</strong><span lang="ru">{word.sentence}</span></span>
        </label>)}
      </fieldset>
    </details>}
    <button class="text-link" disabled={busy || blocked || (choices.length > 0 && !selected.length)} onClick={() => void open()}>{busy ? t("Opening flashcards…") : t("Practise these words")} <span aria-hidden="true">→</span></button>
    {error && <p role="alert">{error}{blocked && <> <a href="/post/profiles">{t("Choose your profile")}</a></>}</p>}
  </div>;
}
