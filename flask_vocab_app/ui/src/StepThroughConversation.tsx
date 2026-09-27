import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { api, ApiError } from './learning-api';
import { ActivityHeader } from './ActivityHeader';
import type { Language } from './review-types';
import type { PracticeLevel } from './Progression';
import { playStepAudio, primeStepAudio, stopStepAudio } from './step-audio-player';
import './styles/step-through-conversation.css';

type Localized = {en:string;ru:string};
type Line = {russian:string;english:string};
type Scenario = {title:string;title_ru?:string;description?:string;description_ru?:string;role?:string;role_ru?:string;seed:string};
type Step = {
  id:string;ordinal:number;npc:Line;intent:Localized;options:{id:string;russian:string}[];
  hint:Localized|null;answered:boolean;
  feedback:{option_id:string;correct:boolean;explanation:Localized;english:string}|null;
  npc_audio_url:string|null;reply_audio_url:string|null;npc_audio_error?:string|null;
};
export type StepConversation = {
  id:string;state:'preparing'|'active'|'completed'|'failed';scenario:Scenario;target_level:PracticeLevel;
  language:Language;created_at:number;error:string|null;retryable:boolean;turn_count:number;completed_turns:number;
  current_turn:Step|null;transcript:{id:string;ordinal:number;npc:Line;reply:Line}[];ending?:Line;
  ending_audio_url?:string|null;ending_audio_error?:string|null;
  audio_configured?:boolean;reward?:{amount:number;basis:string}|null;
};
type Options = {configured:boolean;audio_configured:boolean;scenario:Scenario|null;sessions:{id:string;state:string;created_at:number;title:string;title_ru?:string;target_level:PracticeLevel}[]};
type AudioKind = 'npc'|'reply'|'ending';
type Command = {kind:'start'|'answer'|'hint'|'next'|'retry'|AudioKind;url:string;body:Record<string,unknown>};
type Props = {sessionId?:string;scenarioId?:string;scenarioSeed?:string;targetLevel?:PracticeLevel;language?:Language;onBack?:()=>void;embeddedSetup?:boolean;onPreparingChange?:(busy:boolean)=>void;onReloadScenario?:()=>void};
const endpoint='/api/v1/step-conversations';

export function StepThroughConversation({sessionId,scenarioId,scenarioSeed,targetLevel='A1',language='en',onBack,embeddedSetup=false,onPreparingChange,onReloadScenario}:Props) {
  const t=(en:string,ru:string)=>language==='ru' ? ru : en;
  const local=(value:Localized)=>language==='ru' ? value.ru : value.en;
  const [options,setOptions]=useState<Options>();
  const [saved,setSaved]=useState<StepConversation>();
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState<Command['kind']|null>(null);
  const [selected,setSelected]=useState('');
  const [error,setError]=useState('');
  const [retryCommand,setRetryCommand]=useState<Command|null>(null);
  const [needsReload,setNeedsReload]=useState(false);
  const [accountChanged,setAccountChanged]=useState(false);
  const [audioNotice,setAudioNotice]=useState('');
  const [playing,setPlaying]=useState<AudioKind|null>(null);
  const preparingCallback=useRef(onPreparingChange);
  preparingCallback.current=onPreparingChange;
  const playbackRequest=useRef(0);
  const controller=useRef<AbortController>();
  const generation=useRef(0);
  const inFlight=useRef(false);
  const currentTurn=useRef<string>();
  const startKey=useRef(crypto.randomUUID());
  const focusTarget=useRef<'turn'|'feedback'|null>(null);
  const prompt=useRef<HTMLParagraphElement>(null);
  const feedback=useRef<HTMLDivElement>(null);
  const heading=useRef<HTMLHeadingElement>(null);
  const playNext=useRef<AudioKind|null>(null);
  const automaticAudio=useRef<string>();
  const automaticAdvance=useRef<string>();
  const lastState=useRef<StepConversation['state']>();
  const endingPending=useRef(false);
  const turn=saved?.current_turn;
  const accepted=!!turn?.answered && !!turn.feedback?.correct;
  const blockingRetry=retryCommand && !['npc','reply','ending'].includes(retryCommand.kind);
  const disabled=loading || !!busy || !!blockingRetry || needsReload || accountChanged;
  const embedded=embeddedSetup && !sessionId;
  const preparing=busy==='start' || retryCommand?.kind==='start';

  useLayoutEffect(()=>{onPreparingChange?.(preparing);},[preparing,onPreparingChange]);
  useEffect(()=>()=>preparingCallback.current?.(false),[]);

  function accept(value:StepConversation,restore=false) {
    if (restore) {automaticAdvance.current=undefined;automaticAudio.current=undefined;}
    if (!restore && lastState.current==='active' && value.state==='completed') endingPending.current=true;
    lastState.current=value.state;
    if (restore || currentTurn.current!==value.current_turn?.id) {
      setSelected(value.current_turn?.feedback?.option_id ?? '');
      setAudioNotice('');
      playbackRequest.current++;setPlaying(null);
      stopStepAudio();playNext.current=null;
    }
    currentTurn.current=value.current_turn?.id;
    setSaved(value);
  }

  function report(reason:unknown) {
    const blocked=reason instanceof ApiError && ['account_changed','profile_changed'].includes(reason.code);
    setAccountChanged(blocked);
    setError(reason instanceof Error ? reason.message : t('The conversation could not be loaded. Please try again.','Не удалось загрузить разговор. Попробуйте ещё раз.'));
    return blocked;
  }

  async function load(id:string|null|undefined=sessionId ?? saved?.id) {
    if (inFlight.current) return;
    const version=generation.current;
    inFlight.current=true;setLoading(true);setError('');setRetryCommand(null);
    try {
      if (id) {
        const value=await api<StepConversation>(`${endpoint}/${encodeURIComponent(id)}`,undefined,controller.current?.signal);
        if (version===generation.current) accept(value,true);
      } else {
        const query=new URLSearchParams({scenario_id:scenarioId ?? 'cafe',level:targetLevel});
        const value=await api<Options>(`${endpoint}/options?${query}`,undefined,controller.current?.signal);
        if (version===generation.current) setOptions(value);
      }
      if (version===generation.current) {setNeedsReload(false);setAccountChanged(false);}
    } catch(reason) {if (version===generation.current && !controller.current?.signal.aborted) report(reason);}
    finally {if (version===generation.current) {inFlight.current=false;setLoading(false);}}
  }

  useEffect(()=>{
    controller.current=new AbortController();generation.current++;inFlight.current=false;
    currentTurn.current=undefined;startKey.current=crypto.randomUUID();
    automaticAudio.current=undefined;automaticAdvance.current=undefined;lastState.current=undefined;endingPending.current=false;playNext.current=null;
    setSaved(undefined);setOptions(undefined);setSelected('');setBusy(null);setNeedsReload(false);setAccountChanged(false);
    playbackRequest.current++;setPlaying(null);
    void load(sessionId ?? null);
    return ()=>{generation.current++;playbackRequest.current++;controller.current?.abort();stopStepAudio();};
  },[sessionId,scenarioId,scenarioSeed,targetLevel]);

  useEffect(()=>{
    if (saved?.state!=='preparing' || saved.retryable || error) return;
    const abort=new AbortController();const version=generation.current;
    const timer=setTimeout(()=>{
      void api<StepConversation>(`${endpoint}/${encodeURIComponent(saved.id)}`,undefined,abort.signal)
        .then(value=>{if (!abort.signal.aborted && version===generation.current) accept(value);})
        .catch(reason=>{if (!abort.signal.aborted && version===generation.current) report(reason);});
    },1500);
    return ()=>{clearTimeout(timer);abort.abort();};
  },[saved,error]);

  useLayoutEffect(()=>{
    if (focusTarget.current==='feedback') feedback.current?.focus({preventScroll:true});
    if (focusTarget.current==='turn') (saved?.state==='completed' ? heading.current : prompt.current)?.focus({preventScroll:true});
    focusTarget.current=null;
  },[saved]);

  function audioUrl(kind:AudioKind) {
    return kind==='ending' ? saved?.ending_audio_url : kind==='npc' ? turn?.npc_audio_url : turn?.reply_audio_url;
  }

  async function play(kind:AudioKind) {
    const version=generation.current;
    const request=++playbackRequest.current;
    const url=audioUrl(kind);
    if (!url) return;
    setAudioNotice('');setPlaying(kind);
    const finished=()=>{if(version===generation.current && request===playbackRequest.current) setPlaying(null);};
    try {await playStepAudio(url,{onEnded:finished,onError:()=>{
      if(version===generation.current && request===playbackRequest.current) {
        setPlaying(null);setAudioNotice(t('Audio could not play. Try again.','Не удалось воспроизвести аудио. Попробуйте ещё раз.'));
      }
    }});}
    catch(reason) {
      if (version!==generation.current || request!==playbackRequest.current) return;
      setPlaying(null);
      setAudioNotice(reason instanceof DOMException && reason.name==='NotAllowedError'
        ? t('Audio is ready. Select Listen to play it.','Аудио готово. Нажмите «Послушать».')
        : t('Audio could not play. Try again.','Не удалось воспроизвести аудио. Попробуйте ещё раз.'));
    }
  }

  useEffect(()=>{
    const kind=playNext.current;
    if (kind && audioUrl(kind)) {
      playNext.current=null;
      if (kind!=='reply') automaticAudio.current=`${saved!.id}:${kind==='npc' ? turn!.id : 'ending'}`;
      void play(kind);
    }
  },[turn?.npc_audio_url,turn?.reply_audio_url,saved?.ending_audio_url]);

  // Each character line plays once. Hints, feedback and polling must not restart it.
  useEffect(()=>{
    if (embedded || disabled || error || !saved) return;
    const kind=saved.state==='active' && turn && !accepted ? 'npc'
      : saved.state==='completed' && endingPending.current ? 'ending' : null;
    if (!kind) return;
    const key=`${saved.id}:${kind==='npc' ? turn!.id : 'ending'}`;
    if (automaticAudio.current===key) return;
    automaticAudio.current=key;
    if (audioUrl(kind)) void play(kind);
    else if (saved.audio_configured && !(kind==='npc' ? turn?.npc_audio_error : saved.ending_audio_error)) command(kind);
  },[saved,loading,busy,error,accountChanged,needsReload,embedded]);

  // Checking a correct reply is the learner's turn; the character responds next.
  useEffect(()=>{
    if (embedded || disabled || error || !saved || saved.state!=='active' || !turn || !accepted) return;
    const key=`${saved.id}:${turn.id}`;
    if (automaticAdvance.current===key) return;
    automaticAdvance.current=key;
    command('next');
  },[saved,loading,busy,error,accountChanged,needsReload,embedded]);

  async function run(command:Command) {
    if (inFlight.current || accountChanged) return;
    const version=generation.current;
    inFlight.current=true;setBusy(command.kind);setError('');setRetryCommand(null);
    try {
      const value=await api<StepConversation>(command.url,command.body,controller.current?.signal);
      if (version!==generation.current || controller.current?.signal.aborted) return;
      focusTarget.current=command.kind==='answer' ? 'feedback' : ['next','start','retry'].includes(command.kind) ? 'turn' : null;
      accept(value);setNeedsReload(false);
      if (['npc','reply','ending'].includes(command.kind)) playNext.current=command.kind as AudioKind;
      if (command.kind==='start') window.location.hash=`speaking/step/${encodeURIComponent(value.id)}`;
    } catch(reason) {
      if (version!==generation.current || controller.current?.signal.aborted) return;
      const blocked=report(reason);
      const stale=reason instanceof ApiError && ['stale_turn','conflict','answer_required'].includes(reason.code);
      const rejectedStart=command.kind==='start' && reason instanceof ApiError && ['invalid_input','not_found','unavailable'].includes(reason.code);
      // A rejected preview created no session. Unlock the scenario controls;
      // only uncertain failures must retain the exact start request for retry.
      if (rejectedStart) setOptions(undefined);
      else if (blocked || stale) setNeedsReload(true);
      else setRetryCommand(command);
    } finally {if (version===generation.current) {inFlight.current=false;setBusy(null);}}
  }

  function command(kind:Command['kind'],body:Record<string,unknown>={}) {
    if (!saved || disabled) return;
    const path=['npc','reply','ending'].includes(kind) ? 'audio' : kind;
    if (kind==='answer' || kind==='next') {playbackRequest.current++;stopStepAudio();setPlaying(null);}
    void run({kind,url:`${endpoint}/${encodeURIComponent(saved.id)}/${path}`,body:{...body,...(kind==='retry' ? {} : {turn_id:kind==='ending' ? 'ending' : turn?.id}),...(path==='audio' ? {kind} : {})}});
  }
  function listen(kind:AudioKind) {
    if (playing===kind) {
      playbackRequest.current++;
      stopStepAudio();
      setPlaying(null);return;
    }
    if (disabled) return;
    primeStepAudio();
    if (audioUrl(kind)) void play(kind);
    else command(kind);
  }
  const scenario=saved?.scenario ?? options?.scenario;
  const title=saved?.state==='completed' ? t('Conversation complete','Разговор завершён')
    : scenario ? (language==='ru' ? scenario.title_ru || scenario.title : scenario.title) : t('Step-through conversation','Пошаговый разговор');
  const role=scenario ? (language==='ru' ? scenario.role_ru || scenario.role : scenario.role) : undefined;
  const previous=(saved?.transcript ?? []).filter(line=>saved?.state==='completed' || line.id!==turn?.id);
  const showFeedback=turn?.feedback && (accepted || selected===turn.feedback.option_id);
  const audio=(kind:AudioKind)=>saved?.audio_configured===false && !audioUrl(kind) ? null : <div class="step-audio">
    <button type="button" class="step-text-button" disabled={disabled && playing!==kind} onClick={()=>listen(kind)} aria-label={playing===kind
      ? kind!=='reply' ? t('Pause the other speaker','Приостановить запись собеседника') : t('Pause your reply','Приостановить запись своего ответа')
      : kind!=='reply' ? t('Listen to the other speaker','Послушать собеседника') : t('Listen to your reply','Послушать свой ответ')}>
      <span aria-hidden="true">{playing===kind ? 'Ⅱ' : '▷'}</span> {busy===kind ? t('Preparing audio…','Готовим аудио…') : playing===kind ? t('Pause','Пауза') : t('Listen','Послушать')}
    </button>
  </div>;

  const startSeed=embedded ? scenarioSeed : scenarioSeed ?? options?.scenario?.seed;
  const messages=<>
    {error && <div class="step-error" role="alert"><p>{error}</p><div class="step-actions">
      {accountChanged ? <button type="button" class="step-text-button" onClick={()=>window.location.reload()}>{t('Reload page','Обновить страницу')}</button>
        : <>{retryCommand && <button type="button" class="step-text-button" disabled={!!busy || loading} onClick={()=>void run(retryCommand)}>{t('Try again','Попробовать ещё раз')}</button>}
          {retryCommand?.kind!=='start' && <button type="button" class="step-text-button" disabled={!!busy || loading} onClick={()=>{if (embedded && !options && onReloadScenario) onReloadScenario();else void load();}}>{saved || sessionId ? t('Reload conversation','Обновить разговор') : t('Reload scenario','Обновить ситуацию')}</button>}</>}
    </div></div>}
    {loading && <p role="status">{t('Opening your conversation…','Открываем разговор…')}</p>}
  </>;
  const setupContent=<>
    {!loading && !saved && options && <div class="step-preview">
      {!embedded && <p>{language==='ru' ? scenario?.description_ru || scenario?.description : scenario?.description}</p>}
      <p class="step-muted">{t('Listen, choose a reply and check it. The conversation continues when your reply fits. You can say it aloud; recording is not needed.','Слушайте, выбирайте ответ и проверяйте его. Когда ответ подходит, разговор продолжается. Можно произносить реплики вслух — запись не нужна.')}</p>
      {options.configured && options.scenario && startSeed ? <button type="button" class="cta" disabled={disabled} onClick={()=>{primeStepAudio();void run({kind:'start',url:endpoint,body:{submission_id:startKey.current,scenario_id:scenarioId ?? 'cafe',scenario_seed:startSeed,target_level:targetLevel,language}});}}>
        {busy==='start' ? t('Preparing your conversation…','Готовим разговор…') : t('Start step-through','Начать пошаговый разговор')}
      </button> : <p role="status" class="step-muted">{options.configured ? t('No conversation is available for this level yet.','Для этого уровня пока нет подходящего разговора.') : t('Step-through conversations are not available right now.','Пошаговые разговоры сейчас недоступны.')}</p>}
      {!embedded && !!options.sessions?.length && <details class="step-history"><summary>{t('Previous conversations','Предыдущие разговоры')}</summary><ul class="step-history-links">
        {options.sessions.map(item=><li key={item.id}><a href={`#speaking/step/${encodeURIComponent(item.id)}`}>{language==='ru' ? item.title_ru || item.title : item.title} <span>{item.target_level} · {item.state==='completed' ? t('Complete','Завершён') : t('Continue','Продолжить')}</span></a></li>)}
      </ul></details>}
    </div>}
    {!loading && saved?.state==='preparing' && !saved.retryable && <p role="status">{t('Preparing your conversation…','Готовим разговор…')}</p>}
    {!loading && saved && (saved.state==='failed' || saved.state==='preparing' && saved.retryable) && <div class="step-error"><p role="alert">{saved.error || t('The conversation could not be prepared.','Не удалось подготовить разговор.')}</p>
      {saved.retryable && <button type="button" class="cta" disabled={disabled} onClick={()=>command('retry')}>{busy==='retry' ? t('Preparing…','Готовим…') : t('Try preparing again','Попробовать снова')}</button>}
    </div>}
  </>;
  if (embedded) return <div class="step-embedded-setup">{messages}{setupContent}
    {!loading && (saved?.state==='active' || saved?.state==='completed') && <p role="status">{t('Opening your conversation…','Открываем разговор…')}</p>}
  </div>;

  return <section class="page activity-entry step-conversation-page"><div class="activity-entry-content">
    <div class="step-meta"><nav class="step-back" aria-label={t('Speaking','Разговорная практика')}>
      {onBack ? <button class="step-text-button" type="button" onClick={onBack}>← {t('Speaking','Разговорная практика')}</button>
        : <a class="text-link" href="#speaking/step">← {t('Speaking','Разговорная практика')}</a>}
    </nav>
    <p class="step-mode">{t('Step-through','По шагам')} · {saved?.target_level ?? targetLevel}</p></div>
    <div class="step-session-heading">
      <ActivityHeader title={title} headingRef={heading} headingTabIndex={-1}/>
      {!loading && saved?.state==='active' && turn && <div class="step-progress"><span>{t(`Step ${turn.ordinal} of ${saved.turn_count}`,`Шаг ${turn.ordinal} из ${saved.turn_count}`)}</span><progress value={saved.completed_turns} max={saved.turn_count} aria-label={t('Conversation progress','Прогресс разговора')}/></div>}
    </div>
    {messages}{setupContent}
    {!loading && saved?.state==='active' && turn && <div class="step-turn">
      <div class="step-npc">
        <div class="step-npc-toolbar"><span class="step-speaker">{role || t('Other speaker','Собеседник')}</span>{audio('npc')}</div>
        <p ref={prompt} tabIndex={-1} lang="ru">{turn.npc.russian}</p>
        {(audioNotice || turn.npc_audio_error) && <div class="step-audio-notice" role="status">{audioNotice || turn.npc_audio_error}</div>}
      </div>
      {!accepted && <form class="step-response" onSubmit={event=>{event.preventDefault();if (selected && !disabled) command('answer',{submission_id:crypto.randomUUID(),option_id:selected});}}>
        <fieldset disabled={disabled} class="step-choices"><legend><span class="step-turn-label" aria-hidden="true">{t('Your turn','Ваша очередь')}</span><span class="step-task">{local(turn.intent)}</span></legend>
          {turn.options.map(option=><label key={option.id} class={`step-choice${selected===option.id ? ' is-selected' : ''}`}><input type="radio" name={`reply-${turn.id}`} value={option.id} checked={selected===option.id} onChange={()=>{setSelected(option.id);setError('');}}/><span lang="ru">{option.russian}</span></label>)}
        </fieldset>
        {turn.hint && <div class="step-hint"><p>{local(turn.hint)}</p></div>}
        {showFeedback && <div class="step-feedback" role="status" ref={feedback} tabIndex={-1}><strong>{t('Try another reply.','Попробуйте другой ответ.')}</strong><p>{local(turn.feedback!.explanation)}</p></div>}
        <div class="step-reply-actions">
          {!turn.hint && <button type="button" class="step-text-button" disabled={disabled} onClick={()=>command('hint')}>{busy==='hint' ? t('Opening hint…','Открываем подсказку…') : t('Show a hint','Показать подсказку')}</button>}
          <button type="submit" class="cta step-check" disabled={!selected || disabled}>{busy==='answer' ? t('Checking…','Проверяем…') : t('Check reply','Проверить ответ')}<span aria-hidden="true">→</span></button>
        </div>
      </form>}
      {accepted && <div class="step-feedback is-accepted" role="status" ref={feedback} tabIndex={-1}>
        <span class="step-speaker">{t('Your reply','Ваш ответ')}</span><p class="step-accepted-russian" lang="ru">{turn.options.find(option=>option.id===turn.feedback!.option_id)?.russian}</p><p class="step-translation" lang="en">{turn.feedback!.english}</p>
        <p>{local(turn.feedback!.explanation)}</p>{audio('reply')}
        {busy==='next' && <p>{t('Waiting for the next reply…','Ждём следующую реплику…')}</p>}
      </div>}
    </div>}
    {!loading && saved?.state==='completed' && <div class="step-complete">
      {saved.ending && <><p class="step-ending" lang="ru">{saved.ending.russian}</p><p class="step-translation" lang="en">{saved.ending.english}</p></>}
      {saved.ending && audio('ending')}
      {(audioNotice || saved.ending_audio_error) && <p class="step-muted" role="status">{audioNotice || saved.ending_audio_error}</p>}
      <p>{t(`You worked through ${saved.completed_turns} replies. Your conversation is saved.`,'Вы разобрали все реплики. Разговор сохранён.')}</p>
      {saved.reward && saved.reward.amount>0 && <p class="step-reward">{t(`Lingocoins earned: ${saved.reward.amount}`,`Получено лингокоинов: ${saved.reward.amount}`)}</p>}
      <a class="cta" href="#speaking/step">{t('Choose another conversation','Выбрать другой разговор')}</a>
    </div>}
    {!loading && !!previous.length && <details class="step-history"><summary>{saved?.state==='completed' ? t('Review conversation','Посмотреть разговор') : t('Conversation so far','Предыдущие реплики')}</summary><ol>
      {previous.map(line=><li key={line.id}><p lang="ru"><span class="step-speaker">{role || t('Other speaker','Собеседник')}</span>{line.npc.russian}</p><p lang="ru"><span class="step-speaker">{t('You','Вы')}</span>{line.reply.russian}</p><p class="step-translation" lang="en">{line.reply.english}</p></li>)}
    </ol></details>}
  </div></section>;
}
