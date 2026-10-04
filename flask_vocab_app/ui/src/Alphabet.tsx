import {useEffect, useRef, useState} from 'preact/hooks';
import type {JSX} from 'preact';
import {appUrl} from './app-url';
import alphabetData from './alphabet-data.json';
import './styles/alphabet.css';

type Letter = {
  id: string; upper: string; lower: string; name: string; nameAudio: string;
  example: string; exampleMeaning: string; exampleAudio: string;
  kind: 'vowel' | 'consonant' | 'sign'; note: string;
};
type Clip = 'name' | 'word';
const letters = alphabetData as Letter[];
const labels = {vowel: 'Vowel', consonant: 'Consonant', sign: 'Sign'};
const preferenceKey = 'word-post-alphabet-hover-sound';
const hoverDelay = 180;

function initialHoverSound() {
  try { return localStorage.getItem(preferenceKey) !== 'off'; }
  catch { return true; }
}

function Speaker({playing = false}: {playing?: boolean}) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    {playing ? <><path d="M9 5v14M15 5v14"/></> : <><path d="m11 5-5 4H3v6h3l5 4z"/><path d="M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/></>}
  </svg>;
}

function ExampleWord({letter}: {letter: Letter}) {
  const parts = letter.example.split(new RegExp(`([${letter.upper}${letter.lower}]\u0301?)`, 'g'));
  return <>{parts.map((part, index) => part[0]?.toLocaleLowerCase('ru') === letter.lower
    ? <mark key={index}>{part}</mark> : <span key={index}>{part}</span>)}</>;
}

export function Alphabet({returnHref = '#activities', returnLabel = 'Activities'}: {returnHref?: string; returnLabel?: string}) {
  const [selectedId, setSelectedId] = useState(letters[0].id);
  const [hoverSound, setHoverSound] = useState(initialHoverSound);
  const [activated, setActivated] = useState(false);
  const [playing, setPlaying] = useState('');
  const [error, setError] = useState('');
  const player = useRef<HTMLAudioElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const grid = useRef<HTMLOListElement>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>();
  const audioActivated = useRef(false);
  const attempt = useRef(0);
  const active = useRef<{key: string; source: 'manual' | 'hover'}>();
  const mounted = useRef(true);
  const selected = letters.find(letter => letter.id === selectedId) ?? letters[0];
  const position = letters.indexOf(selected);

  function cancelHover() {
    if (hoverTimer.current !== undefined) clearTimeout(hoverTimer.current);
    hoverTimer.current = undefined;
  }

  function stopAudio(audio: HTMLAudioElement | null = player.current) {
    attempt.current += 1;
    active.current = undefined;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    if (mounted.current) setPlaying('');
  }

  useEffect(() => {
    mounted.current = true;
    heading.current?.focus({preventScroll: true});
    const audio = player.current;
    return () => { mounted.current = false; cancelHover(); stopAudio(audio); };
  }, []);

  async function play(letter: Letter, clip: Clip, source: 'manual' | 'hover' = 'manual') {
    cancelHover();
    stopAudio();
    setSelectedId(letter.id);
    setError('');
    const audio = player.current;
    if (!audio) return;
    const current = attempt.current;
    const key = `${letter.id}:${clip}`;
    active.current = {key, source};
    setPlaying(key);
    const fail = () => {
      if (!mounted.current || attempt.current !== current) return;
      stopAudio();
      audioActivated.current = false;
      setActivated(false);
      setError('Audio couldn’t play. Press a play button to try again.');
    };
    audio.onended = () => { if (attempt.current === current) stopAudio(); };
    audio.onerror = fail;
    audio.src = appUrl(clip === 'name' ? letter.nameAudio : letter.exampleAudio);
    try {
      await audio.play();
      if (!mounted.current || attempt.current !== current) return;
      audioActivated.current = true;
      setActivated(true);
    } catch { fail(); }
  }

  function playOrStop(clip: Clip) {
    cancelHover();
    if (active.current?.key === `${selected.id}:${clip}`) stopAudio();
    else void play(selected, clip);
  }

  function hover(letter: Letter, event: JSX.TargetedPointerEvent<HTMLButtonElement>) {
    cancelHover();
    if (event.pointerType !== 'mouse' || !hoverSound || !audioActivated.current) return;
    hoverTimer.current = setTimeout(() => { void play(letter, 'name', 'hover'); }, hoverDelay);
  }

  function toggleHoverSound() {
    const enabled = !hoverSound;
    setHoverSound(enabled);
    cancelHover();
    if (!enabled && active.current?.source === 'hover') stopAudio();
    try { localStorage.setItem(preferenceKey, enabled ? 'on' : 'off'); }
    catch { /* The preference still works when browser storage is unavailable. */ }
  }

  function move(event: JSX.TargetedKeyboardEvent<HTMLButtonElement>, index: number) {
    const columns = Number(grid.current && getComputedStyle(grid.current).getPropertyValue('--alphabet-columns')) || 7;
    const next = event.key === 'ArrowRight' ? index + 1 : event.key === 'ArrowLeft' ? index - 1
      : event.key === 'ArrowDown' ? index + columns : event.key === 'ArrowUp' ? index - columns
      : event.key === 'Home' ? 0 : event.key === 'End' ? letters.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    const destination = Math.max(0, Math.min(letters.length - 1, next));
    cancelHover();
    stopAudio();
    setSelectedId(letters[destination].id);
    grid.current?.querySelectorAll<HTMLButtonElement>('button')[destination]?.focus();
  }

  const namePlaying = playing === `${selected.id}:name`;
  const wordPlaying = playing === `${selected.id}:word`;
  return <section class="page alphabet-page" aria-labelledby="alphabet-heading">
    <a class="text-link alphabet-back" href={returnHref}><span aria-hidden="true">← </span>{returnLabel}</a>
    <header class="alphabet-header">
      <div><p class="kicker">Letters & sounds</p><div class="alphabet-title-line"><h1 ref={heading} tabIndex={-1} id="alphabet-heading">Russian alphabet</h1><span>33 letters</span></div></div>
      <button type="button" class="alphabet-hover-switch" role="switch" aria-checked={hoverSound} onClick={toggleHoverSound}>
        <span class="alphabet-switch-track" aria-hidden="true"><span/></span>Hover sound <span class="alphabet-switch-value">{hoverSound ? 'On' : 'Off'}</span>
      </button>
    </header>
    <div class="alphabet-toolbar">
      <p class="alphabet-instruction">{!activated && hoverSound ? 'Select a letter to listen. Then hover to hear others.'
        : hoverSound ? 'Hover to hear a letter. Select its word to hear it in context.' : 'Select a letter or its word to listen.'}</p>
      <ul class="alphabet-legend" aria-label="Letter types">{(['vowel', 'consonant', 'sign'] as const).map(kind =>
        <li class={`alphabet-kind-${kind}`} key={kind}><span aria-hidden="true"/>{labels[kind]}s</li>)}</ul>
    </div>
    <div class="alphabet-layout">
      <div class="alphabet-grid-wrap">
        <p id="alphabet-keyboard-help" class="alphabet-sr-only">Use the arrow keys to choose a letter, then press Enter or Space to listen.</p>
        <ol ref={grid} class="alphabet-grid" aria-label="Russian letters" aria-describedby="alphabet-keyboard-help">
          {letters.map((letter, index) => <li key={letter.id}>
            <button type="button" class={`alphabet-letter alphabet-kind-${letter.kind}${selected.id === letter.id ? ' is-selected' : ''}${playing === `${letter.id}:name` ? ' is-playing' : ''}`}
              aria-label={`Listen to ${letter.upper} ${letter.lower} (${letter.name}), ${labels[letter.kind].toLowerCase()}`}
              aria-pressed={selected.id === letter.id} aria-controls="alphabet-detail" tabIndex={selected.id === letter.id ? 0 : -1}
              onClick={() => void play(letter, 'name')} onPointerEnter={event => hover(letter, event)} onPointerLeave={cancelHover}
              onKeyDown={event => move(event, index)}>
              <span class="alphabet-letter-pair" lang="ru"><span>{letter.upper}</span><span>{letter.lower}</span></span>
              <span class="alphabet-letter-indicator" aria-hidden="true">{playing === `${letter.id}:name` ? '♪' : ''}</span>
            </button>
          </li>)}
        </ol>
        <p class="alphabet-grid-caption">10 vowels · 21 consonants · 2 signs</p>
      </div>
      <aside id="alphabet-detail" class={`alphabet-detail alphabet-kind-${selected.kind}`} aria-label={`About ${selected.upper} ${selected.lower}`}>
        <div class="alphabet-detail-meta"><span>Letter {String(position + 1).padStart(2, '0')} / 33</span><span class="alphabet-kind-label">{labels[selected.kind]}</span></div>
        <h2 class="alphabet-detail-pair" lang="ru"><span>{selected.upper}</span><span>{selected.lower}</span></h2>
        <button type="button" class="alphabet-name-play" onClick={() => playOrStop('name')} aria-label={`${namePlaying ? 'Stop' : 'Listen to'} letter name: ${selected.name}`}>
          <span><span class="alphabet-detail-label">Letter name</span><strong lang="ru">{selected.name}</strong></span><span class="alphabet-play-icon"><Speaker playing={namePlaying}/></span>
        </button>
        <button type="button" class={`alphabet-example${wordPlaying ? ' is-playing' : ''}`} onClick={() => playOrStop('word')} aria-label={`${wordPlaying ? 'Stop' : 'Listen to'} word: ${selected.example} (${selected.exampleMeaning})`}>
          <span class="alphabet-detail-label">In a word</span><span class="alphabet-example-row"><strong lang="ru"><ExampleWord letter={selected}/></strong><span class="alphabet-play-icon"><Speaker playing={wordPlaying}/></span></span>
          <span class="alphabet-example-meaning">{selected.exampleMeaning}</span>
        </button>
        <p class="alphabet-note">{selected.note}</p>
      </aside>
    </div>
    {error && <p class="alphabet-error" role="status">{error}</p>}
    <audio ref={player} preload="none" hidden aria-hidden="true"/>
  </section>;
}
