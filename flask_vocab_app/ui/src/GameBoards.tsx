import { useGameText } from "./GameLocale";
import { useState } from 'preact/hooks';
import { LessonVisual } from './LessonVisual';
import sceneActivityArtwork from './assets/scene-builder-activity-v1.webp';
import bagActivityArtwork from './assets/barsik-pack-bag-v1.webp';
import directionsActivityArtwork from './assets/barsik-directions-v1.webp';
import stampActivityArtwork from './assets/barsik-missing-stamp-v1.webp';
import radioActivityArtwork from './assets/barsik-radio-v1.webp';
import sortActivityArtwork from './assets/barsik-mailbox-sort-v1.webp';
import letterActivityArtwork from './assets/barsik-letter-back-v1.webp';
import detectiveActivityArtwork from './assets/barsik-detective-v1.webp';
import { AudioClue } from './GameAudio';
import type { GameRound, JourneyGameId } from './journey-games-api';
export const gamePresentation: Record<JourneyGameId, {
  instructions: string;
  check: string;
  help: string;
  finish: string;
  summary: string;
  correct: string;
}> = {
  'pack-bag': {
    instructions: 'Read or listen to the Russian. Choose the pictures to put in Barsik’s bag, then check what you packed.',
    check: 'Check the bag',
    help: 'Choose pictures to pack. Click a packed picture to put it back.',
    finish: 'Packed and ready.',
    summary: 'You used your Russian to help Barsik pack his bag.',
    correct: 'Just what Barsik needed.'
  },
  directions: {
    instructions: 'Explore a neighbourhood, ask the people you meet for directions and deliver a letter.',
    check: 'Check the route',
    help: 'You can undo a turn or start your route again before checking.',
    finish: 'You found the way.',
    summary: 'You followed the directions and helped Barsik on his way.',
    correct: 'That’s the way.'
  },
  'scene-builder': {
    instructions: 'Look at the scene and build the Russian sentence. Choose the words and endings that fit.',
    check: 'Check the sentence',
    help: 'Choose an answer in each row. You can change it before checking.',
    finish: 'Practice complete.',
    summary: 'You’ve practised how Russian describes places, actions and people.',
    correct: 'That fits the scene.'
  },
  pairs: {
    instructions: 'Choose a Russian postcard, then its matching picture. Pair all the cards before checking.',
    check: 'Check the pairs',
    help: 'Choose a Russian card, then its picture. You can change your pairs before checking.',
    finish: 'A little more familiar.',
    summary: 'You’ve practised recognising your Russian words in pictures.',
    correct: 'Those pairs belong together.'
  },
  'mailbox-sort': {
    instructions: 'Read each Russian message and put it in the mailbox with its English meaning.',
    check: 'Check the mail',
    help: 'Choose a message, then a mailbox. You can move it again before checking.',
    finish: 'The mail is sorted.',
    summary: 'You’ve practised understanding Russian messages in context.',
    correct: 'Every message has a place.'
  },
  'missing-stamp': {
    instructions: 'Read the English translation and complete the Russian postcard. Choose the word that fits the whole sentence.',
    check: 'Check the postcard',
    help: 'Use the full sentence and its translation to choose the missing word.',
    finish: 'Your postcards are complete.',
    summary: 'You’ve practised choosing Russian words in their sentences.',
    correct: 'The postcard makes sense.'
  },
  radio: {
    instructions: 'Listen to the message, then choose the picture it describes. You can replay it or reveal the Russian text if you need it.',
    check: 'Check what I heard',
    help: 'Listen first. Replaying is welcome; reading the message is available when you need it.',
    finish: 'Message received.',
    summary: 'You’ve practised understanding Russian in context.',
    correct: 'You caught the message.'
  },
  detective: {
    instructions: 'Read both clues, then choose the delivery card that fits them together. One clue on its own will not be enough.',
    check: 'Check the clues',
    help: 'Look at the picture and the route on each card. Both clues need to fit.',
    finish: 'Case closed.',
    summary: 'You’ve practised using two Russian clues together to find a delivery.',
    correct: 'Both clues fit.'
  },
  'letter-back': {
    instructions: 'Listen to the Russian message and rebuild it with the word tiles. The English translation helps you follow its meaning.',
    check: 'Send the reply',
    help: 'Put the tiles in the order you hear. Click a tile in your message to remove it.',
    finish: 'A reply for Barsik.',
    summary: 'You’ve practised hearing how Russian words fit together in a sentence.',
    correct: 'That reply does the job.'
  }
};
const activityArtwork: Record<Exclude<JourneyGameId, 'pairs'>, string> = {
  'pack-bag': bagActivityArtwork,
  directions: directionsActivityArtwork,
  'scene-builder': sceneActivityArtwork,
  'missing-stamp': stampActivityArtwork,
  radio: radioActivityArtwork,
  'mailbox-sort': sortActivityArtwork,
  'letter-back': letterActivityArtwork,
  detective: detectiveActivityArtwork,
};

export function GameArtwork({gameId}: {gameId: JourneyGameId}) {
  if (gameId !== 'pairs') {
    return <div class="first-steps-art game-artwork game-artwork-illustrated" aria-hidden="true"><img src={activityArtwork[gameId]} alt="" width="512" height="512" decoding="async" /></div>;
  }
  // Retired Postcard Pairs sessions keep their original illustration.
  return <div class="first-steps-art game-artwork" aria-hidden="true"><svg viewBox="0 0 140 140" fill="none"><circle cx="70" cy="70" r="61" fill="#f0dfb8"/><g stroke="#3e454d" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
    <g transform="rotate(-10 46 69)"><rect x="20" y="35" width="47" height="67" rx="5" fill="#fbf5e7"/><path d="M31 50h25M31 62h20M31 74h17"/></g>
    <g transform="rotate(9 96 74)"><rect x="71" y="43" width="47" height="67" rx="5" fill="#e4ae74"/><path d="M82 67h25v22H82z" fill="#fbf5e7"/><path d="M82 68l12 10 13-10"/></g>
  </g></svg></div>;
}
export function VocabularyPicture({
  visual = 'envelope',
  image_url,
  label
}: {
  visual?: string;
  image_url?: string;
  label?: string;
}) {
  return image_url ? <span class="game-vocabulary-picture"><img src={image_url} alt={label ?? ''} loading="eager" /></span> : <LessonVisual kind={visual} />;
}
type BoardProps = {
  round: GameRound;
  selected: string[];
  onChange: (answer: string[]) => void;
  disabled: boolean;
  expected?: string[];
};
const assignments = (values: string[]) => Object.fromEntries(values.map(value => value.split(':')));
function updateAssignment(selected: string[], left: string, right: string, exclusive = false) {
  const mapping = assignments(selected);
  for (const key of Object.keys(mapping)) if (key === left || exclusive && mapping[key] === right) delete mapping[key];
  mapping[left] = right;
  return Object.entries(mapping).map(([a, b]) => `${a}:${b}`).sort();
}
function MatchMark({
  correct
}: {
  correct: boolean;
}) {
  const t = useGameText();
  return <span class={`game-match-mark ${correct ? 'is-correct' : 'is-incorrect'}`} aria-label={correct ? t("Correct") : t("Try a different match")}>{correct ? '✓' : '×'}</span>;
}
export function PairsBoard({
  round,
  selected,
  onChange,
  disabled,
  expected
}: BoardProps) {
  const t = useGameText();
  const [active, setActive] = useState('');
  const left = round.left ?? [],
    right = round.right ?? [],
    paired = assignments(selected),
    answers = expected ? assignments(expected) : null;
  const current = left.some(item => item.id === active) ? active : left.find(item => !paired[item.id])?.id ?? left[0]?.id;
  function pair(id: string) {
    if (!current) return;
    const next = updateAssignment(selected, current, id, true);
    onChange(next);
    const newPairs = assignments(next);
    setActive(left.find(item => !newPairs[item.id])?.id ?? current);
  }
  return <div class="game-pairs-board"><div class="game-pair-column"><p class="journey-game-board-label">{t("Russian postcards")}{" "}<span>{selected.length} / {left.length}</span></p>{left.map((item, index) => {
        const rightItem = right.find(choice => choice.id === paired[item.id]),
          correct = answers?.[item.id] === paired[item.id];
        return <div class="game-pair-row" key={item.id}><button class={`game-russian-postcard${current === item.id && !disabled ? ' is-active' : ''}${rightItem ? ' is-paired' : ''}`} disabled={disabled} aria-pressed={current === item.id} onClick={() => setActive(item.id)}><span class="game-pair-number" aria-hidden="true">{index + 1}</span><span lang="ru">{item.text}</span>{answers && <MatchMark correct={correct} />}</button>{item.audio_key && <AudioClue text={item.text} audioKey={item.audio_key} hideText label={t("Listen: {0}", {
            "0": item.text
          })} />}</div>;
      })}</div>
    <div class="game-pair-column"><p class="journey-game-board-label">{t("Match a picture")}</p>{right.map(item => {
        const source = left.find(word => paired[word.id] === item.id),
          number = source ? left.indexOf(source) + 1 : null;
        return <button key={item.id} class={`game-picture-postcard${source ? ' is-paired' : ''}`} disabled={disabled || !current} onClick={() => pair(item.id)} aria-label={expected ? t("Picture of {0}", {
          "0": item.label
        }) : t("Match with {0}", {
          "0": item.label
        })}><VocabularyPicture visual={item.visual} image_url={item.image_url} />{number && <span class="game-pair-number" aria-label={t("Paired with postcard {0}", {
            "0": number
          })}>{number}</span>}</button>;
      })}</div>
    {answers && <div class="game-correct-pairs"><h3>{t("The matching postcards")}</h3><ul>{left.map(item => {
          const picture = right.find(choice => choice.id === answers[item.id]);
          return <li key={item.id}>{picture && <VocabularyPicture visual={picture.visual} image_url={picture.image_url} />}<span lang="ru">{item.text}</span></li>;
        })}</ul></div>}
  </div>;
}
export function MailSortBoard({
  round,
  selected,
  onChange,
  disabled,
  expected
}: BoardProps) {
  const t = useGameText();
  const [active, setActive] = useState('');
  const sentences = round.sentences ?? [],
    bins = round.bins ?? [],
    sorted = assignments(selected),
    answers = expected ? assignments(expected) : null;
  const current = sentences.some(item => item.id === active) ? active : sentences.find(item => !sorted[item.id])?.id ?? sentences[0]?.id;
  function deliver(binId: string) {
    if (!current) return;
    const next = updateAssignment(selected, current, binId);
    onChange(next);
    const assigned = assignments(next);
    setActive(sentences.find(item => !assigned[item.id])?.id ?? current);
  }
  return <div class="game-mail-board"><div class="game-mail-tray"><p class="journey-game-board-label">{t("Messages to sort")}{" "}<span>{selected.length} / {sentences.length}</span></p><div>{sentences.map((item, index) => <div class="game-mail-message-row" key={item.id}><button class={`game-mail-message${current === item.id && !disabled ? ' is-active' : ''}${sorted[item.id] ? ' is-sorted' : ''}`} disabled={disabled} aria-pressed={current === item.id} onClick={() => setActive(item.id)}><small>{String(index + 1).padStart(2, '0')}</small><span lang="ru">{item.text}</span>{answers && <MatchMark correct={answers[item.id] === sorted[item.id]} />}</button>{item.audio_key && <AudioClue text={item.text} audioKey={item.audio_key} hideText label={t("Listen: {0}", {
            "0": item.text
          })} />}</div>)}</div></div>
    <div class="game-mailboxes">{bins.map((bin, index) => {
        const contained = sentences.filter(item => sorted[item.id] === bin.id);
        return <div key={bin.id} class={`game-mailbox game-mailbox-${index}`}><button class="game-mailbox-post" disabled={disabled || !current} onClick={() => deliver(bin.id)} aria-label={t("Put the message in {0}", {
            "0": bin.label
          })}><span class="game-mail-slot" aria-hidden="true" /><strong>{bin.label}</strong>{bin.description && <small>{bin.description}</small>}</button><div class="game-mailbox-contents" aria-label={t("{0} messages", {
            "0": bin.label
          })}>{contained.length ? contained.map(item => <button key={item.id} disabled={disabled} class={answers ? answers[item.id] === bin.id ? 'is-correct' : 'is-incorrect' : ''} lang="ru" onClick={() => setActive(item.id)}>{item.text}</button>) : <span aria-hidden="true">—</span>}</div>{answers && <div class="game-mailbox-correct"><p>{t("Belongs here")}</p>{sentences.filter(item => answers[item.id] === bin.id).map(item => <p key={item.id} lang="ru">{item.text}</p>)}</div>}</div>;
      })}</div>
  </div>;
}
export function ClozeBoard({
  round,
  selected,
  onChange,
  disabled,
  expected
}: BoardProps) {
  const t = useGameText();
  const choices = round.choices ?? [],
    chosen = choices.find(item => item.id === (expected?.[0] ?? selected[0]));
  const parts = (round.sentence ?? '[[blank]]').split('[[blank]]');
  return <div class="game-cloze-board"><div class="game-cloze-postcard"><div class="game-postcard-address" aria-hidden="true"><VocabularyPicture visual={round.visual} image_url={round.image_url} /><span>Барсику</span></div><div class="game-cloze-message"><p class="journey-game-board-label">{round.objective === 'grammar' ? t("Word form") : t("Sentence meaning")}</p><p class="game-cloze-sentence" lang="ru">{parts.map((part, index) => <span key={index}>{index > 0 && <span class={`game-cloze-gap${expected ? ' is-revealed' : ''}`}>{chosen?.text ?? '…'}</span>}{part}</span>)}</p><p class="game-cloze-translation">{round.translation}</p></div></div><div class="game-word-tiles" aria-label={t("Words for the missing space")}>{choices.map(item => <button key={item.id} lang="ru" disabled={disabled} class={`${selected[0] === item.id ? 'is-selected ' : ''}${expected?.includes(item.id) ? 'is-correct' : ''}`} aria-pressed={selected[0] === item.id} onClick={() => onChange([item.id])}>{item.text}</button>)}</div></div>;
}
export function RadioBoard({
  round,
  selected,
  onChange,
  disabled,
  expected,
  onHeard,
  onTranscript
}: {
  round: GameRound;
  selected: string[];
  onChange: (answer: string[]) => void;
  disabled: boolean;
  expected?: string[];
  onHeard: (key: string) => Promise<void>;
  onTranscript: () => void;
}) {
  const t = useGameText();
  return <div class="game-radio-board"><div class="game-radio"><div class="game-radio-top"><span class="game-radio-name">{t("Post Office Radio")}</span><span class="game-radio-light" aria-hidden="true" /></div><div class="game-radio-tuner" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div><div class="game-radio-face"><div class="game-radio-grille" aria-hidden="true" /><div class="game-radio-listen">{round.clues.map((clue, index) => <div key={`${round.id}-${index}`}><p>{t("Message")}{" "}{round.clues.length > 1 ? index + 1 : ''}</p><AudioClue audioKey={clue.audio_key} text={clue.text} hideText label={round.clues.length > 1 ? t("Listen to message {0}", {
              "0": index + 1
            }) : t("Listen to the message")} disabled={disabled && !expected} onHeard={expected ? undefined : onHeard} /></div>)}</div></div></div>
    <div class="game-radio-response"><h3>{t("What did you hear?")}</h3><div class="game-radio-choices">{(round.choices ?? []).map(item => <button key={item.id} disabled={disabled} aria-label={item.label ?? item.text} aria-pressed={selected[0] === item.id} class={`${selected[0] === item.id ? 'is-selected ' : ''}${expected?.includes(item.id) ? 'is-correct' : ''}`} onClick={() => onChange([item.id])}>{item.visual || item.image_url ? <VocabularyPicture visual={item.visual} image_url={item.image_url} /> : <span lang="ru">{item.text}</span>}{expected?.includes(item.id) && <MatchMark correct />}</button>)}</div>
      {round.support?.transcript || expected ? <div class="game-radio-transcript"><p class="journey-game-board-label">{t("The message")}</p>{round.clues.map((clue, index) => <p key={index} lang="ru">{clue.text}</p>)}{!expected && <small>{t("You’re practising with the written message this time.")}</small>}</div> : <button class="text-link" disabled={disabled} onClick={onTranscript}>{t("Show the Russian text")}</button>}
    </div></div>;
}
const routeArrows: Record<string, string> = {
  straight: '↑',
  left: '←',
  right: '→'
};
export function DetectiveBoard({
  round,
  selected,
  onChange,
  disabled,
  expected
}: BoardProps) {
  const t = useGameText();
  return <div class="game-detective-board"><div class="game-detective-evidence"><span class="game-detective-pin" aria-hidden="true" /><p class="journey-game-board-label">{t("Two clues. One delivery.")}</p>{round.clues.map((clue, index) => <div class="game-evidence-note" key={index}><span class="game-evidence-number">{index + 1}</span><AudioClue text={clue.text} audioKey={clue.audio_key} /></div>)}</div>
    <div class="game-delivery-cards" aria-label={t("Possible deliveries")}>{(round.destinations ?? []).map((item, index) => <button key={item.id} disabled={disabled} aria-label={item.label} aria-pressed={selected[0] === item.id} class={`game-delivery-card${selected[0] === item.id ? ' is-selected' : ''}${expected?.includes(item.id) ? ' is-correct' : ''}`} onClick={() => onChange([item.id])}><span class="game-delivery-number">{String(index + 1).padStart(2, '0')}</span><VocabularyPicture visual={item.visual} image_url={item.image_url} /><span class="game-delivery-route" aria-hidden="true">{item.route.map((move, step) => <span key={step}>{routeArrows[move] ?? move}</span>)}</span>{expected?.includes(item.id) && <MatchMark correct />}</button>)}</div></div>;
}
export function LetterBackBoard({
  round,
  selected,
  onChange,
  disabled,
  expected,
  onHeard,
  onTranscript
}: BoardProps & {
  onHeard?: (key: string) => Promise<void>;
  onTranscript?: () => void;
}) {
  const t = useGameText();
  const tiles = round.tiles ?? [],
    message = t(round.audio_required ? 'message' : 'reply');
  return <div class="game-reply-board">{round.audio_required && <div class="game-reply-listening"><p class="journey-game-board-label">{t("Listen and rebuild the message")}</p>{round.clues.map((clue, index) => <AudioClue key={`${round.id}-${index}`} audioKey={clue.audio_key} text={clue.text} hideText label={round.clues.length > 1 ? t("Listen to part {0}", {
        "0": index + 1
      }) : t("Listen to the message")} disabled={disabled && !expected} onHeard={expected ? undefined : onHeard} />)}{round.translation && <p class="game-reply-translation">{round.translation}</p>}{round.support?.transcript || expected ? <div class="game-reply-transcript">{round.clues.map((clue, index) => <p key={index} lang="ru">{clue.text}</p>)}</div> : <button class="text-link" disabled={disabled} onClick={onTranscript}>{t("Show the Russian text")}</button>}</div>}<div class="game-reply-paper"><div class="game-reply-stamp" aria-hidden="true"><GameArtwork gameId="letter-back" /></div><p class="journey-game-board-label">{t("Your")}{" "}{message} <span>{selected.length} / {round.max_choices}</span></p><div class="game-reply-composition" aria-label={t("Your Russian {0}", {
        "0": message
      })}>{selected.length ? selected.map((id, index) => {
          const tile = tiles.find(item => item.id === id);
          return tile && <button key={`${id}-${index}`} lang="ru" disabled={disabled} aria-label={t("Remove {0} from your {1}", {
            "0": tile.text,
            "1": message
          })} onClick={() => onChange(selected.filter((_, position) => position !== index))}>{tile.text}</button>;
        }) : <p>{t("Choose a tile below to start your message.")}</p>}</div>{expected && <div class="game-reply-answer"><p>{round.audio_required ? t("The recorded message") : t("One reply that fits")}</p><p lang="ru">{expected.map(id => tiles.find(item => item.id === id)?.text).join(' ')}</p></div>}</div>
    <div class="game-word-tiles game-reply-tiles" aria-label={round.audio_required ? t("Word tiles") : t("Phrases for your reply")}>{tiles.map(item => <button key={item.id} lang="ru" disabled={disabled || selected.includes(item.id) || selected.length >= round.max_choices} onClick={() => onChange([...selected, item.id])}>{item.text}</button>)}</div>
  </div>;
}
