import { useGameText } from "./GameLocale";
import { GameMedia, useGameLanguage } from './GameLocale';
import { useEffect, useRef, useState } from 'preact/hooks';
import { ApiError } from './learning-api';
import { AudioClue } from './GameAudio';
import { ClozeBoard, DetectiveBoard, GameArtwork, gamePresentation, LetterBackBoard, MailSortBoard, PairsBoard, RadioBoard, VocabularyPicture } from './GameBoards';
import { GamePreparation } from './GamePreparation';
import { RadioBroadcast, RadioQuestions } from './RadioBroadcast';
import { GameWords } from './GameWords';
import { GameWordSource } from './GameWordSource';
import { GameStudyActions } from './GameStudyActions';
import { DeliveryOptions, generatedDelivery, orderedDeliveries } from './DeliveryOptions';
import {SceneBuilder, SceneBuilderOptions} from './SceneBuilder';
import { DeliveryGame } from './DeliveryGame';
import { getGame, getGames, saveGame, startGame, type GameAction, type GameBoard, type GameCatalogueState, type GameObject, type GameOptions, type GameRound, type GameState, type GameSummary, type Heading, type JourneyGameId, type MapPosition } from './journey-games-api';
import './styles/journey-games.css';
const arrows: Record<string, string> = {
  left: '↶',
  straight: '↑',
  right: '↷'
};
const moveNames: Record<string, string> = {
  left: 'Turn left',
  straight: 'Go straight',
  right: 'Turn right'
};
const headingNames: Record<Heading, string> = {
  north: 'up',
  east: 'right',
  south: 'down',
  west: 'left'
};
const directions: Heading[] = ['north', 'east', 'south', 'west'];
const blockedCodes = ['profile_changed', 'locked', 'profile_required', 'learner_required', 'csrf_failed', 'unauthorized', 'not_found'];
function GameError({
  message,
  blocked = false,
  retry,
  busy = false
}: {
  message: string;
  blocked?: boolean;
  retry: () => void;
  busy?: boolean;
}) {
  const t = useGameText();
  return <div class="journey-game-error" role="alert"><p>{message}</p>{blocked ? <a class="text-link" href="/#activities">{t("Reopen activities")}</a> : <button class="text-link" disabled={busy} onClick={retry}>{t("Try again")}</button>}</div>;
}
function useCatalogue() {
  const t = useGameText();
  const [state, setState] = useState<GameCatalogueState>();
  const [error, setError] = useState(''),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setError('');
    void getGames(abort.signal).then(value => {
      if (!abort.signal.aborted) setState(value);
    }).catch(cause => {
      if (!abort.signal.aborted) {
        setState(undefined);
        setError(cause instanceof Error ? cause.message : t("Your games could not load."));
      }
    });
    return () => abort.abort();
  }, [revision]);
  return {
    state,
    error,
    retry: () => setRevision(value => value + 1)
  };
}
function GameShopLink() {
  const t = useGameText();
  return <div class="journey-game-lock"><p>{t("Unlock this game in the shop with Lingocoins.")}</p><a class="text-link" href="#shop">{t("Visit the shop")} <span aria-hidden="true">→</span></a></div>;
}
function GameCard({
  game, browseLocked = false
}: {
  game: GameSummary;
  browseLocked?: boolean;
}) {
  const t = useGameText();
  const playable = (game.unlocked || !!game.active_session_id) && game.availability !== 'local-only';
  const shopLink = browseLocked && !playable && game.availability !== 'local-only';
  const Title = browseLocked ? 'h2' : 'h3';
  const cardClass = `journey-game-card game-${game.id}${game.unlocked || game.active_session_id ? '' : ' is-locked'}`;
  const content = <>
    <div class="journey-game-card-art" aria-hidden="true"><GameArtwork gameId={game.id} /></div>
    <div class="journey-game-card-copy"><p class="kicker">{game.availability === 'local-only' ? t("Local installation") : game.active_session_id ? t("Continue playing") : game.availability === 'sample' ? t("Sample game") : !game.unlocked ? t("In the shop") : game.new ? t("New game unlocked") : t("Play again")}</p><Title>{t(game.title)}</Title><p>{t(game.description)}</p>
      {game.availability === 'local-only' ? <p class="quiet">{t("Available in your own installation.")}</p> : !browseLocked && !game.unlocked && !game.active_session_id && <GameShopLink/>}
    </div>
    {(playable || shopLink) && <span class="journey-game-card-arrow" aria-hidden="true">→</span>}
  </>;
  return playable
    ? <a class={cardClass} aria-label={t(game.title)} href={game.active_session_id ? `#games/session/${game.active_session_id}` : `#games/${game.id}`}>{content}</a>
    : shopLink ? <a class={cardClass} aria-label={`${t(game.title)} — ${t("In the shop")}`} href="#shop">{content}</a>
    : <article class={cardClass}>{content}</article>;
}
export function GameCatalogue({
  context = 'activities'
}: {
  context?: 'activities' | 'journey' | 'games';
}) {
  const t = useGameText();
  const {
    state,
    error,
    retry
  } = useCatalogue();
  const unlocked = state?.games.filter(game => game.unlocked || game.active_session_id) ?? [],
    upcoming = state?.games.filter(game => !game.unlocked && !game.active_session_id) ?? [];
  return <section class="journey-games-catalogue" aria-label={t("Games to discover")}>
    {context !== 'games' && <div class="journey-games-section-head"><p class="kicker">{t("Explore and practise")}</p><h2>{context === 'journey' ? t("Games along the way") : t("Games to discover")}</h2><p>{t(state?.public_demo ? "Build on words you know, meet new ones and try a different way to practise." : "Use your Lingocoins to choose new games from the shop.")}</p></div>}
    {state ? <>
      {context === 'games' ? <div class="journey-game-grid">{[...unlocked, ...upcoming].map(game => <GameCard key={game.id} game={game} browseLocked />)}</div> : <>
        {unlocked.length > 0 && <div class="journey-game-grid">{unlocked.map(game => <GameCard key={game.id} game={game} />)}</div>}
        {upcoming.length > 0 && !state.public_demo && <a class="journey-games-shop-link" href="#shop"><span><strong>{t("Visit the shop")}</strong><span>{t("Choose your next game. Unlock it once and keep playing.")}</span></span><span aria-hidden="true">→</span></a>}
        {state.public_demo && upcoming.length > 0 && <details class="journey-games-upcoming"><summary>{t("More games")}</summary><ul>{upcoming.map(game => <li key={game.id}><GameArtwork gameId={game.id}/><div><strong>{t(game.title)}</strong><p>{t("Available in your own installation.")}</p></div></li>)}</ul></details>}
      </>}
    </> : !error && <p role="status">{t("Opening your games…")}</p>}
    {error && <GameError message={error} retry={retry} />}
  </section>;
}
function ObjectArt({
  object
}: {
  object: GameObject;
}) {
  return <VocabularyPicture visual={object.visual === 'letter' ? 'envelope' : object.visual} image_url={object.image_url} />;
}
function BagBoard({
  round,
  selected,
  onChange,
  disabled,
  expected
}: {
  round: GameRound;
  selected: string[];
  onChange: (items: string[]) => void;
  disabled: boolean;
  expected?: string[];
}) {
  const t = useGameText();
  const objects = round.objects ?? [];
  function toggle(id: string) {
    if (selected.includes(id)) onChange(selected.filter(item => item !== id));else if (selected.length < round.max_choices) onChange([...selected, id]);
  }
  return <div class="journey-bag-board"><div class="journey-bag-shelf"><p class="journey-game-board-label">{expected ? t("What Barsik needed") : t("Picture cards")}</p><div class="journey-bag-objects">{objects.map(object => {
          const packed = selected.includes(object.id),
            needed = expected?.includes(object.id),
            wrong = !!expected && packed && !needed;
          return <button key={object.id} class={`journey-bag-object${expected ? ' is-feedback' : packed ? ' is-packed' : ''}${needed ? ' is-needed' : wrong ? ' is-unneeded' : ''}`} aria-label={expected ? needed ? t("Needed in the bag: {0}", {
            "0": object.label
          }) : wrong ? t("Not needed: {0}", {
            "0": object.label
          }) : object.label : `${packed ? t("Remove") : t("Pack")} ${object.label}`} aria-pressed={packed} disabled={disabled || !packed && selected.length >= round.max_choices} onClick={() => toggle(object.id)}><ObjectArt object={object} /><span class="journey-bag-select" aria-hidden="true">{expected ? needed ? '✓' : wrong ? '×' : '' : packed ? '✓' : '+'}</span></button>;
        })}</div></div>
    <div class="journey-bag-parcel"><p class="journey-game-board-label">{t("Barsik’s bag")}{" "}<span>{selected.length} / {round.max_choices}</span></p><div class="journey-bag-handle" aria-hidden="true" /><div class="journey-bag-pocket" aria-label={t("Packed items")}>{selected.length ? selected.map(id => {
          const object = objects.find(item => item.id === id);
          return object && <button key={id} aria-label={t("Take {0} out of the bag", {
            "0": object.label
          })} disabled={disabled} onClick={() => toggle(id)}><ObjectArt object={object} />{expected && <span class={`journey-bag-result ${expected.includes(id) ? 'is-correct' : 'is-incorrect'}`} aria-label={expected.includes(id) ? t("Correct item") : t("Different item needed")}>{expected.includes(id) ? '✓' : '×'}</span>}</button>;
        }) : <p>{t("Choose a picture")}<br />{t("to put it in the bag.")}</p>}</div><span class="journey-bag-buckle" aria-hidden="true" /></div>
  </div>;
}
export function traceRoute(board: GameBoard, moves: string[]): MapPosition[] {
  const path: MapPosition[] = [{
    ...board.start
  }];
  for (const move of moves) {
    const previous = path[path.length - 1],
      turn = move === 'left' ? -1 : move === 'right' ? 1 : 0;
    const heading = directions[(directions.indexOf(previous.heading) + turn + 4) % 4];
    const x = previous.x + (heading === 'east' ? 1 : heading === 'west' ? -1 : 0),
      y = previous.y + (heading === 'south' ? 1 : heading === 'north' ? -1 : 0);
    path.push({
      x,
      y,
      heading
    });
  }
  return path;
}
function MapBoard({
  board,
  selected,
  onChange,
  disabled,
  limit,
  expected
}: {
  board: GameBoard;
  selected: string[];
  onChange: (moves: string[]) => void;
  disabled: boolean;
  limit: number;
  expected?: string[];
}) {
  const t = useGameText();
  const path = traceRoute(board, selected),
    current = path[path.length - 1],
    expectedPath = expected ? traceRoute(board, expected) : null;
  const point = (p: MapPosition | {
    x: number;
    y: number;
  }) => `${30 + p.x * 60},${30 + p.y * 60}`;
  const canMove = (move: string) => {
    const destination = traceRoute(board, [...selected, move]).at(-1)!;
    return destination.x >= 0 && destination.x < board.width && destination.y >= 0 && destination.y < board.height;
  };
  const angle = directions.indexOf(current.heading) * 90,
    width = board.width * 60,
    height = board.height * 60;
  const streets = [...Array.from({
    length: board.height
  }, (_, i) => `M30 ${30 + i * 60}H${width - 30}`), ...Array.from({
    length: board.width
  }, (_, i) => `M${30 + i * 60} 30V${height - 30}`)];
  return <div class="journey-map-board"><div class="journey-map-frame"><svg viewBox={`0 0 ${width} ${height}`} class="journey-street-map" role="img" aria-label={t("Street map. Barsik is at column {0}, row {1}, facing {2}. {3} of {4} moves planned.", {
        "0": current.x + 1,
        "1": current.y + 1,
        "2": t(headingNames[current.heading]),
        "3": selected.length,
        "4": limit
      })}>
    <rect width={width} height={height} rx="20" fill="#e5e6c9" />
    {Array.from({
          length: board.height - 1
        }, (_, y) => Array.from({
          length: board.width - 1
        }, (_, x) => <g key={`${x}-${y}`} transform={`translate(${44 + x * 60} ${44 + y * 60})`}><rect width="32" height="32" rx="7" fill={(x + y) % 3 === 0 ? '#b9c8a2' : '#e7c499'} />{(x + y) % 3 === 0 ? <><circle cx="13" cy="12" r="8" fill="#779b77" /><circle cx="21" cy="23" r="6" fill="#779b77" /></> : <><path d="M7 12l9-6 9 6v14H7z" fill={(x + y) % 2 === 0 ? '#c27858' : '#8a9f9e'} /><path d="M6 12l10-7 10 7" fill="none" stroke="#5d6662" stroke-width="2" /><rect x="14" y="19" width="4" height="7" fill="#f7e9ce" /></>}</g>))}
    {streets.map((street, index) => <g key={index}><path d={street} fill="none" stroke="#faf5e7" stroke-width="18" stroke-linecap="round" /><path d={street} fill="none" stroke="#dfd8be" stroke-width="1.5" stroke-dasharray="2 7" /></g>)}
    {board.landmarks.map((item, index) => <g key={index} transform={`translate(${30 + item.x * 60} ${30 + item.y * 60})`}><title>{item.label ?? (item.visual === 'post-office' ? t("Post office") : t("Market"))}</title><rect x="-23" y="-23" width="46" height="46" rx="5" fill="#fffaeb" stroke="#b9b28b" stroke-width="2" /><>{item.image_url ? <image href={item.image_url} x="-20" y="-20" width="40" height="40" preserveAspectRatio="xMidYMid slice" /> : <><path d="M-16 0L0-14 16 0V16H-16Z" fill={item.visual === 'post-office' ? '#b15e44' : '#51876c'} /><text x="0" y="11" text-anchor="middle" fill="#fffdf3" font-size="18">{item.visual === 'post-office' ? '✉' : 'М'}</text></>}</></g>)}
    {expectedPath && <polyline points={expectedPath.map(point).join(' ')} fill="none" stroke="#51876c" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity=".65" stroke-dasharray="3 10" />}
    <circle cx={30 + board.start.x * 60} cy={30 + board.start.y * 60} r="8" fill="#fffdf3" stroke="#4f625d" stroke-width="2" />
    {path.length > 1 && <polyline points={path.map(point).join(' ')} fill="none" stroke="#b15e44" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" />}
    {path.slice(1, -1).map((position, index) => <circle key={index} cx={30 + position.x * 60} cy={30 + position.y * 60} r="4" fill="#b15e44" />)}
    <g class="journey-map-barsik" transform={`translate(${30 + current.x * 60} ${30 + current.y * 60})`}><circle r="17" fill="#fcf5df" stroke="#b15e44" stroke-width="2" /><path d="M-5 -23l5-6 5 6" fill="none" stroke="#32494a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" transform={`rotate(${angle})`} /><image href="/static/images/barsik-running-v1.webp" x="-20" y="-15" width="40" height="30" transform={current.heading === 'west' ? 'scale(-1 1)' : undefined} /></g>
    {expectedPath && <g transform={`translate(${point(expectedPath.at(-1)!)})`}><circle r="23" fill="none" stroke="#51876c" stroke-width="3" /><g transform="translate(16 -18)"><circle r="8" fill="#51876c" /><path d="M-4 0l3 3 5-6" fill="none" stroke="#fffdf3" stroke-width="2" /></g></g>}
  </svg><p class="journey-map-facing">{t("Barsik is facing")}{" "}<strong>{t(headingNames[current.heading])}</strong>{t(". Each arrow moves him one street.")}</p></div>
    <div class="journey-map-controls"><p class="journey-game-board-label">{t("Plan the route")}{" "}<span>{selected.length} / {limit}</span></p><div class="journey-map-route" aria-label={t("Your planned route")}>{selected.length ? selected.map((move, index) => <span key={index} aria-label={`${index + 1}. ${moveNames[move]}`}>{arrows[move]}</span>) : <p>{t("Your moves will appear here.")}</p>}</div><div class="journey-map-arrows">{['left', 'straight', 'right'].map(move => <button key={move} aria-label={t(moveNames[move])} title={t(moveNames[move])} disabled={disabled || selected.length >= limit || !canMove(move)} onClick={() => onChange([...selected, move])}><span aria-hidden="true">{arrows[move]}</span><small>{move === 'straight' ? t("Straight") : move === 'left' ? t("Left") : t("Right")}</small></button>)}</div><div class="journey-map-edit"><button class="text-link" disabled={disabled || !selected.length} onClick={() => onChange(selected.slice(0, -1))}>{t("Undo")}</button><button class="text-link" disabled={disabled || !selected.length} onClick={() => onChange([])}>{t("Start over")}</button></div><p class="journey-map-tip">{t("Left and right follow the way Barsik is facing.")}</p>{expectedPath && <p class="journey-map-legend"><span aria-hidden="true" />{t("The dotted green line shows the route in the instructions.")}</p>}</div>
  </div>;
}
export function JourneyGame({
  gameId,
  sessionId,
  profileHref = '/post/profiles'
}: {
  gameId?: string;
  sessionId?: string;
  profileHref?: string;
}) {
  const t = useGameText();
  const [catalogue, setCatalogue] = useState<GameCatalogueState>(),
    [state, setState] = useState<GameState>();
  const [options, setOptions] = useState<GameOptions>({
    source: 'vocabulary',
    rounds: 5
  });
  const [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [blocked, setBlocked] = useState(false);
  const mounted = useRef(true),
    pending = useRef(false),
    requestId = useRef(''),
    heading = useRef<HTMLHeadingElement>(null),
    last = useRef<{
      action: 'load' | 'start' | GameAction;
      body?: unknown;
    }>({
      action: 'load'
    }),
    owner = useRef<string | null | undefined>(undefined);
  const entry = catalogue?.games.find(game => game.id === gameId),
    round = state?.round;
  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    heading.current?.focus({
      preventScroll: true
    });
  }, [state?.phase, state?.round_index]);
  useEffect(() => {
    if (state?.game_id === 'scene-builder' && ['play', 'practice'].includes(state.phase)) {
      window.scrollTo({top: 0, behavior: 'instant'});
    }
  }, [state?.round?.id, state?.phase]);
  function accept(next: GameState, preserveDraft = false) {
    if (!mounted.current) return;
    if (owner.current !== undefined && owner.current !== next.profile_id) throw new ApiError(t("Your profile changed. Reopen this page before continuing."), 'profile_changed');
    owner.current = next.profile_id;
    setState(next);
    if (!preserveDraft) setSelected(next.result?.answer ?? []);
  }
  function report(cause: unknown) {
    if (!mounted.current) return;
    const inaccessible = cause instanceof ApiError && blockedCodes.includes(cause.code);
    setBlocked(inaccessible);
    if (inaccessible) {
      setState(undefined);
      setCatalogue(undefined);
      setSelected([]);
    }
    setError(cause instanceof Error ? cause.message : t("Your game could not be saved."));
  }
  async function load() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    setBlocked(false);
    last.current = {
      action: 'load'
    };
    try {
      if (sessionId) accept(await getGame(sessionId));else {
        const next = await getGames();
        if (mounted.current) {
          setCatalogue(next);
          owner.current = next.profile_id;
          if (!next.games.some(game => game.id === gameId)) {
            if (gameId === 'pairs') {
              window.location.hash = 'games/scene-builder';
              return;
            }
            throw new ApiError(t("This game could not be found."), 'not_found');
          }
        }
      }
    } catch (cause) {
      report(cause);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function start() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    last.current = {
      action: 'start'
    };
    if (!requestId.current) requestId.current = crypto.randomUUID();
    try {
      const startOptions=gameId==='scene-builder'?{grammar_focus:options.grammar_focus??'location',rounds:options.rounds,...(['motion','mixed'].includes(options.grammar_focus??'location')?{motion_level:options.motion_level??'A1'}:{})}:gameId==='directions'&&catalogue?.deliveries?.length?{...options,delivery_id:generatedDelivery(catalogue.deliveries)?.mission_id??options.delivery_id??orderedDeliveries(catalogue.deliveries)[0].mission_id}:options;
      const exploreNewTown=gameId==='directions'&&'delivery_id' in startOptions&&startOptions.delivery_id==='town-procedural'&&startOptions.delivery_new_town===true;
      const next = await startGame(gameId!, requestId.current, startOptions, !!entry?.active_session_id||exploreNewTown);
      accept(next);
      if (mounted.current) window.location.hash = `games/session/${next.id}`;
    } catch (cause) {
      report(cause);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function save(action: GameAction, body: unknown = {}) {
    if (pending.current || !state) return;
    pending.current = true;
    setBusy(true);
    setError('');
    last.current = {
      action,
      body
    };
    try {
      let next: GameState;
      try {
        next = await saveGame(state.id, action, body);
      } catch (cause) {
        if (cause instanceof ApiError && ['answer_already_saved', 'wrong_round', 'practice_finished', 'practice_checked'].includes(cause.code)) next = await getGame(state.id);else throw cause;
      }
      accept(next, ['hint', 'listen', 'transcript', 'practice_hint', 'practice_transcript'].includes(action) && next.round?.id === round?.id && ['play', 'practice'].includes(next.phase));
      if (mounted.current && ['continue', 'practice_continue'].includes(action) && next.phase === 'ready') {
        last.current = {
          action: 'complete',
          body: {}
        };
        next = await saveGame(next.id, 'complete');
        accept(next);
      }
    } catch (cause) {
      report(cause);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  function retry() {
    const request = last.current;
    if (request.action === 'load') void load();else if (request.action === 'start') void start();else void save(request.action, request.body);
  }
  const title = state?.title ?? entry?.title ?? t("A game with Barsik");
  const currentGame = (state?.game_id ?? entry?.id ?? gameId ?? 'pack-bag') as JourneyGameId;
  const language = useGameLanguage();
  const basePresentation = Object.fromEntries(Object.entries(gamePresentation[currentGame] ?? gamePresentation['pack-bag']).map(([key, value]) => [key, t(value)])) as typeof gamePresentation['pack-bag'];
  const vocabularyReply = currentGame === 'letter-back' && (round?.audio_required || ['vocabulary', 'lesson'].includes(state?.source?.kind ?? ''));
  const broadcast = state?.broadcast,
    radioProgramme = currentGame === 'radio' && (!state || !!broadcast);
  const presentation = radioProgramme ? {
    ...basePresentation,
    instructions: t("Tune in to a short Russian radio programme, then answer four questions about what you heard."),
    check: t("Check answer"),
    help: t("Choose the answer that matches the programme."),
    correct: t("That’s right."),
    finish: t("Thanks for listening."),
    summary: t("You’ve listened to a Russian programme and checked what you understood.")
  } : vocabularyReply ? {
    ...basePresentation,
    check: t("Check the message"),
    correct: t("That’s the message."),
    finish: t("Message complete.")
  } : basePresentation;
  const practising = !!state?.practice;
  const answerUncertain = !!error && ['answer', 'practice_answer'].includes(last.current.action);
  const interactionBlocked = busy || answerUncertain || !['play', 'practice'].includes(state?.phase ?? '');
  const expected = ['feedback', 'practice_feedback'].includes(state?.phase ?? '') ? state?.result?.expected_answer : undefined;
  const radioSupported = !!round && (round.support?.transcript || round.clues.every(clue => round.support?.listened_audio_keys.includes(clue.audio_key)));
  const needsListening = !broadcast && (currentGame === 'radio' || !!round?.audio_required);
  const completeDraft = !!round && selected.length > 0 && (currentGame !== 'scene-builder' || selected.length === round.scene_builder?.slots.length && selected.every(Boolean)) && (!['pairs', 'mailbox-sort', 'letter-back'].includes(currentGame) || selected.length === round.max_choices) && (!needsListening || radioSupported);
  const boardProps = round ? {
    round,
    selected,
    onChange: setSelected,
    disabled: interactionBlocked,
    expected
  } : null;
  function boardContent() {
    if (!round || !boardProps) return null;
    switch (currentGame) {
      case 'pack-bag':
        return <BagBoard {...boardProps} />;
      case 'directions':
        return round.board && <MapBoard board={round.board} selected={selected} onChange={setSelected} disabled={interactionBlocked} limit={round.max_choices} expected={expected} />;
      case 'scene-builder':
        return <SceneBuilder key={round.id} {...boardProps} slotResults={state?.result?.slot_results} />;
      case 'pairs':
        return <PairsBoard key={round.id} {...boardProps} />;
      case 'mailbox-sort':
        return <MailSortBoard key={round.id} {...boardProps} />;
      case 'missing-stamp':
        return <ClozeBoard {...boardProps} />;
      case 'radio':
        return broadcast ? <RadioQuestions {...boardProps} /> : <RadioBoard key={round.id} {...boardProps} onHeard={key => practising ? Promise.resolve() : save('listen', {
          round_id: round.id,
          audio_key: key
        })} onTranscript={() => void save(practising ? 'practice_transcript' : 'transcript', {
          round_id: round.id
        })} />;
      case 'detective':
        return <DetectiveBoard key={round.id} {...boardProps} />;
      case 'letter-back':
        return <LetterBackBoard key={round.id} {...boardProps} onHeard={key => practising ? Promise.resolve() : save('listen', {
          round_id: round.id,
          audio_key: key
        })} onTranscript={() => void save(practising ? 'practice_transcript' : 'transcript', {
          round_id: round.id
        })} />;
    }
  }
  const vocabularySource = state?.source?.kind === 'vocabulary' || state?.source?.href === '#words';
  const emptySource = !radioProgramme && !['directions','scene-builder'].includes(currentGame) && options.source === 'lesson' && !!catalogue?.sources && (catalogue.sources.lessons.find(item => item.id === options.lesson_id)?.count ?? 0) === 0;
  const playing = !!state && ['play', 'feedback', 'listening', 'practice', 'practice_feedback'].includes(state.phase);
  if (state?.delivery) return <DeliveryGame key={state.id} state={state} onState={accept} />;
  return <GameMedia.Provider value={!(state?.sample || catalogue?.public_demo)}><section class={`page journey-game game-player-${currentGame}${playing ? ' is-playing' : ''}`}>
    {state?.game_id==='directions'&&state.phase!=='preparing'&&<p class="delivery-upgrade">{t('This is a saved route from the earlier game.')} <a class="text-link" href="#games/directions">{t('Start a neighbourhood delivery')} →</a></p>}
    <div class="lesson-head"><a class="text-link" href="#activities">{t("All activities")}</a>{state?.source && !['route', 'sample', 'grammar'].includes(state.source.kind ?? '') && <a class="text-link" href={state.source.href}>{vocabularySource ? t("Back to vocabulary") : t("Back to the lesson")}</a>}</div>
    {!playing && <p class="kicker">{state?.phase === 'completed' ? t("Game complete") : t("Play with Barsik")}</p>}
    <header class="journey-game-heading"><h1 ref={heading} tabIndex={-1}>{t(title)}</h1>
      {playing && round && <div class="journey-game-round-head"><p class="journey-game-round-count">{practising ? t("Review") : broadcast ? t("Question") : t("Round")} {(state.practice?.index ?? state.round_index) + 1}{" "}{t("of")}{" "}{state.practice?.total ?? state.total_rounds}{currentGame==='scene-builder'&&round.scene_builder?.level&&<span class="scene-round-level" aria-label={`${language==='ru'?'Уровень':'Level'} ${round.scene_builder.level}`}>{round.scene_builder.level}</span>}</p><div class="journey-game-round-dots" aria-hidden="true">{Array.from({
              length: state.total_rounds
            }, (_, index) => <span key={index} class={index <= state.round_index ? 'is-current' : ''} />)}</div></div>}
    </header>
    {!state && entry && <div class="journey-game-intro"><div class="journey-game-intro-art" aria-hidden="true"><GameArtwork gameId={currentGame} /></div><div>{!(currentGame==='directions'&&generatedDelivery(catalogue?.deliveries??[]))&&<p class="intro">{currentGame==='directions'&&catalogue?.deliveries?.length?(language==='ru'?'Следуй указаниям, разговаривай с жителями и выполняй задания в городе.':'Follow directions, speak to neighbours and complete tasks around town.'):presentation.instructions}</p>}{entry.active_session_id && <a class="cta game-continue-saved" href={`#games/session/${entry.active_session_id}`}>{t("Continue saved game")}{" "}<span aria-hidden="true">→</span></a>}{entry.unlocked&&currentGame==='directions'&&!!catalogue?.deliveries?.length&&<DeliveryOptions choices={catalogue.deliveries} options={options} disabled={busy} onChange={value=>{setOptions(value);requestId.current='';setError('');}}/>}{entry.unlocked&&currentGame==='scene-builder' && <SceneBuilderOptions options={options} disabled={busy} onChange={value=>{setOptions(value);requestId.current='';setError('');}}/>}{entry.unlocked && entry.availability !== 'sample' && !['directions','scene-builder'].includes(currentGame) && <GameWordSource broadcast={radioProgramme} sources={catalogue?.sources} options={options} disabled={busy} onChange={value => {
            setOptions(value);
            requestId.current = '';
            setError('');
          }} />}{entry.unlocked&&!(currentGame==='directions'&&generatedDelivery(catalogue?.deliveries??[]))&&<p class="quiet">{entry.availability === 'sample' ? t("An authored sample. Full vocabulary practice is available in your own installation.") : currentGame === 'directions' ? (language==='ru'?'Выбери задание и способ практики.':'Choose a task and how you want to practise.') : radioProgramme ? t("About a minute · 4 questions") : t("{0} rounds.", {
              "0": options.rounds
            })}</p>}{entry.unlocked && emptySource && <p class="game-source-empty">{options.source === 'vocabulary' ? <>{t("Add words to")}{" "}<a href="#words">{t("your vocabulary")}</a>{" "}{t("to build this game.")}</> : t("This lesson has no saved words yet. Choose another word source.")}</p>}{entry.availability === 'local-only' ? <p>{t("This game is available in your own installation. Choose a sample from Activities to play here.")}</p> : entry.unlocked ? <button class="cta" disabled={busy || emptySource} onClick={() => void start()}>{busy ? t("Opening your game…") : entry.active_session_id ? radioProgramme ? t("Make another programme") : t("Start a new game") : radioProgramme ? t("Tune in") : t("Let’s play")} <span aria-hidden="true">→</span></button> : <GameShopLink/>}</div></div>}
    {broadcast && state?.phase !== 'preparing' && <RadioBroadcast compact={state?.phase !== 'listening'} sessionId={state!.id} broadcast={broadcast} busy={busy} onHeard={() => practising ? Promise.resolve() : save('listen', {
        round_id: 'broadcast',
        audio_key: broadcast.audio_key
      })} onTranscript={() => void save(practising ? 'practice_transcript' : 'transcript', {
        round_id: practising ? round!.id : 'broadcast'
      })} />}
    {state?.phase === 'listening' && broadcast ? <div class="radio-start-questions"><p>{broadcast.listened ? t("Ready to see what you caught?") : broadcast.transcript ? t("Read or listen, then try the questions.") : t("Listen to the programme first. The questions come next.")}</p><button class="cta" disabled={busy || !broadcast.listened && !broadcast.transcript} onClick={() => void save('quiz')}>{busy ? t("Opening questions…") : t("Answer the questions")} <span aria-hidden="true">→</span></button></div> : state?.phase === 'preparing' ? sessionId ? <GamePreparation key={state.id} initial={state} onReady={accept} onBlocked={report} /> : <p role="status">{t("Opening your saved game…")}</p> : state?.phase === 'completed' ? <div class="journey-game-completed">
      <div class="journey-game-completed-art" aria-hidden="true"><GameArtwork gameId={currentGame} /><span>✓</span></div><h2>{presentation.finish}</h2><p>{presentation.summary}</p>{state.summary && <p class="radio-quiz-score"><strong>{state.summary.correct_rounds} / {state.summary.total_rounds}</strong>{" "}{t("correct on the first try.")}</p>}{!!state.summary?.missed_rounds && <button class="cta" disabled={busy} onClick={() => void save('review')}>{t("Practise missed items")}{" "}<span aria-hidden="true">→</span></button>}
      {!state.profile_id ? <p class="quiet">{t("Your practice is saved on this device.")}{" "}<a href={profileHref}>{t("Create a profile to keep it.")}</a></p> : state.reward && state.reward.amount > 0 ? <p class="journey-game-reward"><strong>{state.reward.awarded_now ? '+' : ''}{state.reward.amount}{" "}{t("Lingocoins")}</strong> · {state.reward.awarded_now ? t("Added to your balance") : t("Already saved")}</p> : <p class="quiet">{state.reward?.reason === 'already_rewarded' ? t("You’ve already earned coins for this game today. You can keep playing.") : state.reward?.reason === 'daily_cap' ? t("Your game is saved. You’ve earned today’s activity coins, and you can keep playing.") : t("Your practice is saved. No extra coins were added this time.")}</p>}
      <div class="action-row"><a class="cta" href={state.source.kind==='grammar'?'#activities':state.source.href}>{['route', 'sample', 'grammar'].includes(state.source.kind ?? '') ? t("All activities") : vocabularySource ? t("Back to vocabulary") : state.source.kind === 'lesson' ? t("Back to the lesson") : t("Back to First steps")} <span aria-hidden="true">→</span></a><a class="text-link" href={`#games/${state.game_id === 'pairs' ? 'scene-builder' : state.game_id}`}>{state.game_id === 'pairs' ? t("Try Describe the scene") : t("Play again")}</a><a class="text-link" href="#activities">{t("Choose another activity")}</a></div>
      {!!state.words?.length && <GameWords sessionId={state.id} words={state.words} />}
      {state.profile_id && state.study_available && <GameStudyActions sessionId={state.id} words={state.words} />}
    </div> : state && round ? <>
      {practising && <div class="game-practice-notice"><p>{t("This is practice. Your first result is saved.")}</p><button class="text-link" disabled={busy} onClick={() => void save('practice_exit')}>{t("Close review")}</button></div>}
      <div class="journey-game-instruction">{currentGame!=='scene-builder'&&<h2 lang={broadcast ? 'ru' : undefined}>{t(round.prompt)}</h2>}
        {!['radio', 'detective'].includes(currentGame) && !round.audio_required && <div class="journey-game-clues">{round.clues.map((clue, index) => <AudioClue key={`${round.id}-${index}-${clue.audio_key}`} text={clue.text} audioKey={clue.audio_key} />)}</div>}
        {round.hint ? <p class="journey-game-hint" role="status">{language==='ru'&&round.hint_ru?round.hint_ru:t(round.hint)}</p> : ['play', 'practice'].includes(state.phase) && !needsListening && <button class="text-link" disabled={busy || answerUncertain} onClick={() => void save(practising ? 'practice_hint' : 'hint', {
            round_id: round.id
          })}>{t("Show a hint")}</button>}
      </div>
      <div class="journey-game-stage">{boardContent()}</div>
      {['feedback', 'practice_feedback'].includes(state.phase) && state.result ? <div class={`journey-game-feedback ${state.result.correct ? 'is-correct' : ''}`} role="status"><div><h2>{state.result.correct ? presentation.correct : t("Let’s take another look.")}</h2>{currentGame !== 'scene-builder' && <p>{state.result.feedback}</p>}{currentGame==='scene-builder' && language==='en' && state.result.translation && <p>{state.result.translation}</p>}{state.result.explanation && <p>{language === 'ru' ? state.result.explanation_ru : state.result.explanation}</p>}{state.result.answer_audio && state.result.answer_audio.length > 0 && <div class="game-answer-recordings"><p class="journey-game-board-label">{t(currentGame === "scene-builder" ? "Listen to the sentence" : "Listen to the complete message")}</p>{state.result.answer_audio.map((clue, index) => <AudioClue key={`${round.id}-answer-${index}`} text={clue.text} audioKey={clue.audio_key} hideText label={state.result!.answer_audio!.length > 1 ? t("Listen to phrase {0}", {
                "0": index + 1
              }) : t(currentGame === "scene-builder" ? "Listen to the sentence" : "Listen to the complete message")} />)}</div>}</div><div class="game-feedback-actions">{state.phase === 'feedback' && !state.result.correct && <button class="cta" disabled={busy} onClick={() => void save('retry', {
              round_id: round.id
            })}>{t("Try again")}</button>}<button class="cta" disabled={busy} onClick={() => void save(practising ? 'practice_continue' : 'continue', {
              round_id: round.id
            })}>{busy ? t("Saving…") : practising ? t("Continue") : state.round_index + 1 === state.total_rounds ? broadcast ? t("Finish programme") : t("Finish game") : broadcast ? t("Next question") : t("Next round")} <span aria-hidden="true">→</span></button></div></div> : <div class="journey-game-submit"><p>{presentation.help}{needsListening && !radioSupported && <>{" "}{t("Listen or reveal the text before checking.")}</>}</p><button class="cta" disabled={busy || answerUncertain || !completeDraft} onClick={() => void save(practising ? 'practice_answer' : 'answer', {
            round_id: round.id,
            answer: selected,
            ...(practising ? {
              request_id: crypto.randomUUID()
            } : {})
          })}>{busy ? t("Saving…") : presentation.check} <span aria-hidden="true">→</span></button>{practising && <button class="text-link" disabled={busy} onClick={() => void save('practice_continue', {
            round_id: round.id
          })}>{t("Skip this item")}</button>}</div>}
    </> : state?.phase === 'ready' ? <div class="journey-game-completed"><p>{t("You’ve played all")}{" "}{state.total_rounds}{" "}{t("rounds.")}</p><button class="cta" disabled={busy} onClick={() => void save('complete')}>{busy ? t("Saving…") : broadcast ? t("Finish programme") : t("Finish game")}</button></div> : !entry && !error && <p class="journey-game-loading" role="status">{t("Opening your game…")}</p>}
    {error && <GameError message={t(error)} blocked={blocked} retry={retry} busy={busy} />}
  </section></GameMedia.Provider>;
}
