import {useEffect, useRef, useState} from 'preact/hooks';
import type {JSX} from 'preact';
import {appUrl} from './app-url';
import alphabetData from './alphabet-data.json';
import './styles/alphabet.css';

type Voice = 'female' | 'male';
type Letter = {
  id: string; upper: string; lower: string; name: string; nameAudio: Record<Voice, string>;
  example: string; exampleMeaning: string; exampleAudio: Record<Voice, string>;
  soundIpa: string | null; soundAudio: Record<Voice, string> | null;
  kind: 'vowel' | 'consonant' | 'sign'; note: string;
};
type Clip = 'sound' | 'name' | 'word';
const letters = alphabetData as Letter[];
const labels = {vowel: 'Vowel', consonant: 'Consonant', sign: 'Sign'};
const voicePreference = 'word-post-alphabet-voice';
function initialVoice(): Voice {
  try { return localStorage.getItem(voicePreference) === 'male' ? 'male' : 'female'; }
  catch { return 'female'; }
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
  const [voice, setVoice] = useState<Voice>(initialVoice);
  const [selectedId, setSelectedId] = useState(letters[0].id);
  const [playing, setPlaying] = useState('');
  const [error, setError] = useState('');
  const player = useRef<HTMLAudioElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const grid = useRef<HTMLOListElement>(null);
  const attempt = useRef(0);
  const active = useRef<string>();
  const mounted = useRef(true);
  const selected = letters.find(letter => letter.id === selectedId) ?? letters[0];
  const position = letters.indexOf(selected);

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
    return () => { mounted.current = false; stopAudio(audio); };
  }, []);

  async function play(letter: Letter, clip: Clip) {
    stopAudio();
    setSelectedId(letter.id);
    setError('');
    const recordings = clip === 'sound' ? letter.soundAudio : clip === 'name' ? letter.nameAudio : letter.exampleAudio;
    if (!recordings) return;
    const audio = player.current;
    if (!audio) return;
    const current = attempt.current;
    const key = `${letter.id}:${clip}`;
    active.current = key;
    setPlaying(key);
    const fail = () => {
      if (!mounted.current || attempt.current !== current) return;
      stopAudio();
      setError('Audio couldn’t play. Press a play button to try again.');
    };
    audio.onended = () => { if (attempt.current === current) stopAudio(); };
    audio.onerror = fail;
    // A new version prevents browsers replaying the previous looped sound files.
    audio.src = appUrl(recordings[voice]) + (clip === 'sound' ? '?v=single-v3' : '');
    try {
      await audio.play();
    } catch { fail(); }
  }

  function playOrStop(clip: Clip) {
    if (active.current === `${selected.id}:${clip}`) stopAudio();
    else void play(selected, clip);
  }

  function chooseVoice(next: Voice) {
    if (next === voice) return;
    stopAudio();
    setError('');
    setVoice(next);
    try { localStorage.setItem(voicePreference, next); } catch { /* Playback also works without storage. */ }
  }

  function move(event: JSX.TargetedKeyboardEvent<HTMLButtonElement>, index: number) {
    const columns = Number(grid.current && getComputedStyle(grid.current).getPropertyValue('--alphabet-columns')) || 7;
    const next = event.key === 'ArrowRight' ? index + 1 : event.key === 'ArrowLeft' ? index - 1
      : event.key === 'ArrowDown' ? index + columns : event.key === 'ArrowUp' ? index - columns
      : event.key === 'Home' ? 0 : event.key === 'End' ? letters.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    const destination = Math.max(0, Math.min(letters.length - 1, next));
    stopAudio();
    setSelectedId(letters[destination].id);
    grid.current?.querySelectorAll<HTMLButtonElement>('button')[destination]?.focus();
  }

  const namePlaying = playing === `${selected.id}:name`;
  const soundPlaying = playing === `${selected.id}:sound`;
  const wordPlaying = playing === `${selected.id}:word`;
  return <section class="page alphabet-page" aria-labelledby="alphabet-heading">
    <a class="text-link alphabet-back" href={returnHref}><span aria-hidden="true">← </span>{returnLabel}</a>
    <header class="alphabet-header">
      <div><p class="kicker">Letters & sounds</p><div class="alphabet-title-line"><h1 ref={heading} tabIndex={-1} id="alphabet-heading">Russian alphabet</h1><span>33 letters</span></div></div>
      <fieldset class="alphabet-voice"><legend>Voice</legend>
        {(['female', 'male'] as const).map(option => <label key={option} class={voice === option ? 'is-selected' : ''}>
          <input type="radio" name="alphabet-voice" value={option} checked={voice === option} onChange={() => chooseVoice(option)}/>
          <span>{option === 'female' ? 'Female' : 'Male'}</span>
        </label>)}
      </fieldset>
    </header>
    <div class="alphabet-toolbar">
      <p class="alphabet-instruction">Click a letter to hear its sound. Try the example word too.</p>
      <ul class="alphabet-legend" aria-label="Letter types">{(['vowel', 'consonant', 'sign'] as const).map(kind =>
        <li class={`alphabet-kind-${kind}`} key={kind}><span aria-hidden="true"/>{labels[kind]}s</li>)}</ul>
    </div>
    <div class="alphabet-layout">
      <div class="alphabet-grid-wrap">
        <p id="alphabet-keyboard-help" class="alphabet-sr-only">Use the arrow keys to choose a letter, then press Enter or Space to listen.</p>
        <ol ref={grid} class="alphabet-grid" aria-label="Russian letters" aria-describedby="alphabet-keyboard-help">
          {letters.map((letter, index) => <li key={letter.id}>
            <button type="button" class={`alphabet-letter alphabet-kind-${letter.kind}${selected.id === letter.id ? ' is-selected' : ''}${playing === `${letter.id}:sound` ? ' is-playing' : ''}`}
              aria-label={letter.soundAudio ? `Listen to ${letter.upper} ${letter.lower} sound, ${labels[letter.kind].toLowerCase()}` : `Explore ${letter.upper} ${letter.lower}, sign`}
              aria-pressed={selected.id === letter.id} aria-controls="alphabet-detail" tabIndex={selected.id === letter.id ? 0 : -1}
              onClick={() => void play(letter, 'sound')}
              onKeyDown={event => move(event, index)}>
              <span class="alphabet-letter-pair" lang="ru"><span>{letter.upper}</span><span>{letter.lower}</span></span>
              <span class="alphabet-letter-indicator" aria-hidden="true">{playing === `${letter.id}:sound` ? '♪' : ''}</span>
            </button>
          </li>)}
        </ol>
        <p class="alphabet-grid-caption">10 vowels · 21 consonants · 2 signs</p>
      </div>
      <aside id="alphabet-detail" class={`alphabet-detail alphabet-kind-${selected.kind}`} aria-label={`About ${selected.upper} ${selected.lower}`}>
        <div class="alphabet-detail-meta"><span>Letter {String(position + 1).padStart(2, '0')} / 33</span><span class="alphabet-kind-label">{labels[selected.kind]}</span></div>
        <h2 class="alphabet-detail-pair" lang="ru">{selected.soundAudio
          ? <button type="button" class="alphabet-sound-play" onClick={() => playOrStop('sound')} aria-label={`${soundPlaying ? 'Stop' : 'Listen to'} sound: ${selected.upper}`}>
            <span>{selected.upper}</span><span>{selected.lower}</span><span class="alphabet-play-icon"><Speaker playing={soundPlaying}/></span>
          </button>
          : <><span>{selected.upper}</span><span>{selected.lower}</span></>}</h2>
        <p class="alphabet-sound-caption">{!selected.soundAudio ? 'No sound of its own.' : 'ЕЁЮЯ'.includes(selected.upper) ? 'Sound at the start of a word' : 'Letter sound'}</p>
        <button type="button" class={`alphabet-example${wordPlaying ? ' is-playing' : ''}`} onClick={() => playOrStop('word')} aria-label={`${wordPlaying ? 'Stop' : 'Listen to'} word: ${selected.example} (${selected.exampleMeaning})`}>
          <span class="alphabet-detail-label">In a word</span><span class="alphabet-example-row"><strong lang="ru"><ExampleWord letter={selected}/></strong><span class="alphabet-play-icon"><Speaker playing={wordPlaying}/></span></span>
          <span class="alphabet-example-meaning">{selected.exampleMeaning}</span>
        </button>
        <p class="alphabet-note">{selected.note}</p>
        <button type="button" class="alphabet-name-play" onClick={() => playOrStop('name')} aria-label={`${namePlaying ? 'Stop' : 'Listen to'} letter name: ${selected.name}`}>
          <span>Letter name: <strong lang="ru">{selected.name}</strong></span><Speaker playing={namePlaying}/>
        </button>
      </aside>
    </div>
    {error && <p class="alphabet-error" role="status">{error}</p>}
    <audio ref={player} preload="none" hidden aria-hidden="true"/>
  </section>;
}
