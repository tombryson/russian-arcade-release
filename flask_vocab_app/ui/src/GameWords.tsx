import { useGameText } from "./GameLocale";
import { useEffect, useRef, useState } from 'preact/hooks';
import { addGameWord, getGameWord, type GameWord, type GameWordLookup } from './journey-games-api';

/** Words are looked up only after the learner selects one, and saved explicitly. */
export function GameWords({
  sessionId,
  text,
  words
}: {
  sessionId: string;
  text?: string;
  words?: GameWord[];
}) {
  const t = useGameText();
  const [selected, setSelected] = useState(''),
    [entry, setEntry] = useState<GameWordLookup>(),
    [lemma, setLemma] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [knownWords, setKnownWords] = useState<Set<string>>(new Set());
  function acceptWord(next: GameWordLookup) {
    setEntry(next);
    if (next.in_vocabulary) setKnownWords(previous => new Set([...previous, next.word.toLocaleLowerCase('ru')]));
  }
  const choice = entry?.choices?.find(item => `${item.lemma}|${item.pos ?? ''}` === lemma),
    resolved = choice ?? entry;
  const abort = useRef<AbortController>(),
    mounted = useRef(true),
    saving = useRef(false);
  useEffect(() => () => {
    mounted.current = false;
    abort.current?.abort();
  }, []);
  async function lookup(word: string) {
    if (saving.current) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setSelected(word);
    setEntry(undefined);
    setLemma('');
    setBusy(true);
    setError('');
    try {
      const next = await getGameWord(sessionId, word, controller.signal);
      if (!controller.signal.aborted) {
        acceptWord(next);
        setLemma(next.choices?.length ? '' : next.lemma ?? '');
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : t("This word could not load."));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function add() {
    if (!entry || !lemma || saving.current) return;
    saving.current = true;
    setBusy(true);
    setError('');
    try {
      const next = await addGameWord(sessionId, selected, choice?.lemma ?? lemma, choice?.pos ?? entry.pos ?? undefined);
      if (mounted.current) acceptWord(next);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : t("This word could not be saved."));
    } finally {
      saving.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const split = text?.split(/([\p{Script=Cyrillic}][\p{Script=Cyrillic}\p{M}’-]*)/u);
  return <div class="game-words">
    {text ? <><p class="game-word-reading-note">{t("Select a word to explore it or add it to your vocabulary.")}</p><p class="game-word-text" lang="ru">{split?.map((part, index) => /[\p{Script=Cyrillic}]/u.test(part) ? <button key={index} class="game-text-word" disabled={saving.current} aria-pressed={selected === part} onClick={() => void lookup(part)}>{part}</button> : part)}</p></> : words?.length ? <><h3>{t("Words from this activity")}</h3><p>{t("Keep a word you’d like to practise again.")}</p><div class="game-word-chips">{Array.from(new Map(words.map(word => [word.form, word])).values()).map(word => <button key={word.form} disabled={saving.current} aria-pressed={selected === word.form} onClick={() => void lookup(word.form)}><span lang="ru">{word.form}</span>{word.in_vocabulary === false && !knownWords.has(word.form.toLocaleLowerCase('ru')) && <small>{t("New")}</small>}</button>)}</div></> : null}
    {selected && <aside class="game-word-detail" aria-label={t("Word: {0}", {
      "0": selected
    })}>
      <div class="game-word-detail-head"><h3 lang="ru">{entry?.lemma || selected}</h3><button class="text-link" disabled={busy} onClick={() => {
          setSelected('');
          setEntry(undefined);
          setError('');
        }}>{t("Close")}</button></div>
      {busy && !entry && <p role="status">{t("Looking up")}{" "}{selected}…</p>}
      {entry && <>{entry.lemma && entry.lemma !== selected && <p class="quiet">{t("Form in this activity:")}{" "}<span lang="ru">{selected}</span>{entry.pos ? ` · ${entry.pos}` : ''}</p>}{entry.meaning && <p>{entry.meaning}</p>}{entry.message && <p>{entry.message}</p>}{entry.context && <blockquote lang="ru">{entry.context}</blockquote>}{entry.translation && <p>{entry.translation}</p>}
        {!!entry.choices?.length && <fieldset disabled={busy} class="game-word-meanings"><legend>{t("Which word is used here?")}</legend>{entry.choices.map((choice, index) => <label key={`${choice.lemma}-${index}`}><input type="radio" name={`word-meaning-${sessionId}`} value={`${choice.lemma}|${choice.pos ?? ''}`} checked={lemma === `${choice.lemma}|${choice.pos ?? ''}`} onChange={() => setLemma(`${choice.lemma}|${choice.pos ?? ''}`)} />{choice.label}</label>)}</fieldset>}
        <div class="action-row">{resolved?.in_vocabulary ? <p class="game-word-added" role="status">{entry.added ? t("Added to your vocabulary.") : t("Already in your vocabulary.")}</p> : resolved?.can_add && <button class="cta" disabled={busy || !lemma} onClick={() => void add()}>{busy ? t("Saving…") : t("Add to my words")} <span aria-hidden="true">+</span></button>}{resolved?.dictionary_url && <a class="text-link" href={resolved.dictionary_url} target="_blank" rel="noreferrer">{t("Open dictionary")}{" "}<span aria-hidden="true">↗</span></a>}</div>
      </>}
      {error && <div role="alert"><p>{error}</p><button class="text-link" disabled={busy} onClick={() => entry ? void add() : void lookup(selected)}>{t("Try again")}</button></div>}
    </aside>}
  </div>;
}
