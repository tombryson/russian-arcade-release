import { useEffect, useRef, useState } from 'preact/hooks';
import { api, endOnLeave } from './learning-api';
import { captionRows, LiveConnection, type Caption, type VoiceState } from './live-connection';
import type { Language } from './review-types';
import './styles/conversation.css';
import './styles/live-conversation.css';
import { russianTranscript } from './conversation-transcript';
import { SpeakingHistory } from './SpeakingHistory';
import { ActivityHeader } from './ActivityHeader';
import type { PracticeLevel } from './Progression';
import { StepThroughConversation } from './StepThroughConversation';

type Recording = {id:string;ordinal:number;state:string;audio_url:string;sample_count:number;sample_rate:number;error:string|null;retryable:boolean;
  transcript:{text:string}|null; assessment:{communication:string;uncertainty:string;corrections:{original:string;replacement:string;explanation:string}[]}|null};
type Scenario = {title:string;title_ru?:string;description:string;description_ru?:string;opening:string;seed?:string;
  scenario_id?:string;target_level?:PracticeLevel;category_title?:string;category_title_ru?:string;role?:string;role_ru?:string;icon?:string;sign?:string;
  goals:string[];goals_ru?:string[];goal_ids?:string[];menu?:Record<string,number>;
  reference?:{title:string;title_ru?:string;items:{label:string;label_ru?:string;value:string;value_ru?:string}[]}};
type LevelDetail = {title:string;title_ru:string;description:string;description_ru:string;topic_id:string};
type ScenarioChoice = {id:string;title:string;title_ru:string;description:string;description_ru:string;role:string;role_ru:string;icon:string;sign:string;variant_count:number;available?:boolean;levels?:PracticeLevel[];level_details?:Partial<Record<PracticeLevel,LevelDetail>>};
type Catalogue = {activity:{id:string;title:string;title_ru:string};scenarios:ScenarioChoice[]};
type Score = {score:number|null;reason:string;evidence:string[]};
type SpeakingReport = {basis:string;rubric_version:string;model:string;transcript:string;speech_status:'russian'|'mixed'|'no_russian'|'insufficient'|'unclear';
  grammar:Score;fluency:Score;goals:{id:string;status:'completed'|'not_yet'|'uncertain';evidence:string[]}[];
  summary:string;next_step:string;corrections:{original:string;replacement:string;explanation:string;category:string}[];uncertainty:string;
  criterion_details?:{label:string;label_ru:string;outcome:'satisfied'|'partial'|'not_satisfied'|'insufficient_evidence';feedback:string}[]};
type Review = {state:'queued'|'analysing'|'ready'|'failed';error:string|null;retryable:boolean;report:SpeakingReport|null};
type Saved = {id:string;scenario_id?:string;state:string;connected:boolean;needs_recovery?:boolean;finalized:boolean;created_at:number;error:string|null;captions:Caption[];recordings:Recording[];
  scenario?:Scenario;end_reason?:string|null;review?:Review|null};
type Options = {configured:boolean;notes_configured:boolean;max_seconds:number;sessions:{id:string;state:string;created_at:number}[];scenario?:Scenario};
const practiceLevels:readonly PracticeLevel[]=['A1','A2','B1','B2'];

export function LiveConversation({sessionId,language='en',initialScenarioId,initialLevel='A1'}:{sessionId?:string;language?:Language;initialScenarioId?:string;initialLevel?:PracticeLevel}) {
  const t = (en:string,ru:string) => language === 'ru' ? ru : en;
  const [practiceMode,setPracticeMode] = useState<'fluent'|'step'>('fluent');
  const [preparingStep,setPreparingStep] = useState(false);
  const [options,setOptions] = useState<Options>();
  const [catalogue,setCatalogue] = useState<Catalogue>();
  const [catalogueError,setCatalogueError] = useState('');
  const [catalogueRefresh,setCatalogueRefresh] = useState(0);
  const [level,setLevel]=useState<PracticeLevel>(initialLevel);
  const [selectedScenarioId,setSelectedScenarioId] = useState<string>();
  const initialScenarioOpened=useRef(false);
  const [saved,setSaved] = useState<Saved>();
  const [state,setState] = useState<VoiceState|'idle'|'review'>(sessionId ? 'review' : 'idle');
  const [error,setError] = useState('');
  const [muted,setMuted] = useState(false);
  const [captions,setCaptions] = useState<Caption[]>([]);
  const [showCaptions,setShowCaptions] = useState(true);
  const [playbackBlocked,setPlaybackBlocked] = useState(false);
  const [seconds,setSeconds] = useState(0);
  const [following,setFollowing] = useState(true);
  const [deleting,setDeleting] = useState(false);
  const [requestingReview,setRequestingReview] = useState(false);
  const [changingScenario,setChangingScenario] = useState(false);
  const [refresh,setRefresh] = useState(0);
  const call = useRef<LiveConnection>();
  const mounted = useRef(true);
  const viewGeneration = useRef(0);
  const starting = useRef(false);
  const startKey = useRef(crypto.randomUUID());
  const panel = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const focusNextView = useRef(false);
  const scenarioRequest = useRef(0);
  const rewardedReview = useRef<string>();
  const active = ['connecting','listening','ending'].includes(state);
  const isCurrentView = (generation:number) => mounted.current && generation===viewGeneration.current;

  useEffect(() => {
    mounted.current = true;
    const generation=viewGeneration.current;
    const abort = new AbortController();
    if (sessionId) void api<Saved>(`/api/v1/live-conversations/${sessionId}`,undefined,abort.signal).then(value => {
      if (!isCurrentView(generation) || abort.signal.aborted) return;
      setSaved(value); setCaptions(value.captions); setState('review');
    }).catch(e => { if (isCurrentView(generation) && !abort.signal.aborted) setError(e.message); });
    const leave = () => { viewGeneration.current++; call.current?.dispose(); };
    window.addEventListener('pagehide',leave);
    return () => { mounted.current=false; abort.abort(); leave(); window.removeEventListener('pagehide',leave); };
  },[]);

  useEffect(() => {
    if (state!=='idle' || selectedScenarioId || catalogue) return;
    const abort=new AbortController();
    setCatalogueError('');
    void api<Catalogue>('/api/v1/live-conversations/scenarios',undefined,abort.signal).then(value=>{
      if (!abort.signal.aborted) setCatalogue(value);
    }).catch(e=>{ if (!abort.signal.aborted) setCatalogueError(e.message); });
    return ()=>abort.abort();
  },[state,selectedScenarioId,catalogueRefresh]);

  useEffect(()=>{
    if(!initialScenarioId || !catalogue || sessionId || initialScenarioOpened.current)return;
    initialScenarioOpened.current=true;
    const scenario=catalogue.scenarios.find(item=>item.id===initialScenarioId && item.available!==false && item.variant_count>0 && (item.levels ?? ['A1']).includes(initialLevel));
    if(scenario)chooseScenario(scenario.id,initialLevel);
    else setError(t('This scenario is not available at that level. Choose another scenario.','Эта ситуация недоступна на выбранном уровне. Выберите другую.'));
  },[catalogue,initialScenarioId,initialLevel,sessionId]);

  useEffect(() => {
    if (!saved || !active) return;
    const generation=viewGeneration.current;
    let stopped = false;
    let busy = false;
    const heartbeat = setInterval(() => {
      if (busy || stopped || !isCurrentView(generation)) return;
      busy = true;
      void api<Saved>(`/api/v1/live-conversations/${saved.id}/heartbeat`,{}).then(value => {
        if (stopped || !isCurrentView(generation)) return;
        setSaved(value);
        if (['completed','interrupted','failed'].includes(value.state)) { call.current?.dispose(); setState('ended'); }
      }).catch(() => { if (!stopped && isCurrentView(generation)) setError(t('The app connection is unavailable. The call will end if it cannot reconnect.','Нет соединения с приложением. Разговор завершится, если связь не восстановится.')); })
        .finally(() => { busy=false; });
    },10000);
    return () => { stopped=true; clearInterval(heartbeat); };
  },[saved?.id,active]);

  useEffect(() => {
    if (state !== 'listening') return;
    const timer = setInterval(() => setSeconds(value => value+1),1000);
    return () => clearInterval(timer);
  },[state]);
  useEffect(() => { if (seconds >= (options?.max_seconds ?? 300)) call.current?.end(); },[seconds]);

  useEffect(() => {
    if (!saved || !['ended','review'].includes(state)) return;
    const generation=viewGeneration.current;
    let stopped = false;
    let timeout: ReturnType<typeof setTimeout>;
    let awaitingReview = 0;
    const read = async () => {
      try {
        const value = await api<Saved>(`/api/v1/live-conversations/${saved.id}`);
        if (stopped || !isCurrentView(generation)) return;
        setSaved(value);
        // Original provider fragments from the server replace, never concatenate
        // with, the copies received through the browser data channel.
        setCaptions(value.captions);
        const reviewPending = value.review && ['queued','analysing'].includes(value.review.state) && !value.review.retryable;
        // The close event can arrive before the server queues its final review.
        // A short, read-only grace period covers that race without evaluating
        // old conversations simply because someone opened their history.
        const reviewNotQueuedYet = value.scenario?.seed && !value.review && ++awaitingReview <= 4;
        if (value.connected || reviewPending || reviewNotQueuedYet || value.recordings.some(r => ['queued','capturing','analysing'].includes(r.state) && !r.retryable)) timeout=setTimeout(read,2500);
      } catch(e) { if (!stopped && isCurrentView(generation)) setError(e instanceof Error ? e.message : t('The saved conversation could not load.','Не удалось открыть разговор.')); }
    };
    void read();
    return () => { stopped=true; clearTimeout(timeout); };
  },[saved?.id,state,refresh]);

  useEffect(() => { if (following && panel.current) panel.current.scrollTop=panel.current.scrollHeight; },[captions,following,showCaptions]);
  useEffect(()=>{
    if (saved?.review?.state==='ready' && rewardedReview.current!==saved.id) {
      rewardedReview.current=saved.id;window.dispatchEvent(new Event('lingo:progression'));
    }
  },[saved?.id,saved?.review?.state]);

  async function start() {
    if (starting.current || !selectedScenarioId || !options?.scenario || changingScenario) return;
    const generation=viewGeneration.current;
    starting.current=true; setError(''); setState('connecting');
    try {
      const value = await api<Saved>('/api/v1/live-conversations',{submission_id:startKey.current,language,scenario_id:selectedScenarioId,scenario_seed:options.scenario.seed,target_level:level});
      if (!isCurrentView(generation)) {
        // Creation may finish after the learner leaves. Close the unused session
        // without requesting microphone access or connecting to the provider.
        endOnLeave(`/api/v1/live-conversations/${value.id}/finish`);
        return;
      }
      setSaved(value);
      history.replaceState(null,'',`#speaking/${value.id}`);
      const connection = new LiveConnection(value.id,{
        status:next => { if (isCurrentView(generation)) setState(next); },
        caption:fragment => { if (isCurrentView(generation)) setCaptions(previous => [...previous,fragment]); },
        error:message => { if (isCurrentView(generation)) setError(message); },
        playbackBlocked:() => { if (isCurrentView(generation)) setPlaybackBlocked(true); },
      },value.scenario?.opening);
      call.current=connection;
      await connection.start();
    } catch(e) {
      if (isCurrentView(generation)) {
        setError(e instanceof DOMException && ['NotAllowedError','PermissionDeniedError'].includes(e.name)
          ? t('Microphone access was declined. Allow it in your browser, then start a new conversation.','Доступ к микрофону отклонён. Разрешите его в браузере и начните новый разговор.')
          : e instanceof Error ? e.message : t('The call could not start.','Не удалось начать разговор.'));
        setState('ended');
      }
    } finally { if (isCurrentView(generation)) starting.current=false; }
  }

  async function retry(recording:Recording) {
    if (!saved) return;
    const generation=viewGeneration.current;
    setError('');
    try {
      const value=await api<Saved>(`/api/v1/live-conversations/${saved.id}/recordings/${recording.id}/retry`,{});
      if (isCurrentView(generation)) { setSaved(value); setState('ended'); setRefresh(v=>v+1); }
    } catch(e) { if (isCurrentView(generation)) setError(e instanceof Error ? e.message : 'Please retry.'); }
  }

  async function requestReview() {
    if (!saved || requestingReview) return;
    const generation=viewGeneration.current;
    setError(''); setRequestingReview(true);
    try {
      const value=await api<Saved>(`/api/v1/live-conversations/${saved.id}/review`,{});
      if (isCurrentView(generation)) { setSaved(value); setRefresh(v=>v+1); }
    } catch(e) { if (isCurrentView(generation)) setError(e instanceof Error ? e.message : t('The feedback could not start. Please try again.','Не удалось начать разбор. Попробуйте ещё раз.')); }
    finally { if (isCurrentView(generation)) setRequestingReview(false); }
  }

  async function finishSaved() {
    if (!saved) return;
    const generation=viewGeneration.current;
    try {
      const value=await api<Saved>(`/api/v1/live-conversations/${saved.id}/finish`,{});
      if (isCurrentView(generation)) { setSaved(value); setRefresh(v=>v+1); }
    } catch(e) { if (isCurrentView(generation)) setError(e instanceof Error ? e.message : 'Please retry.'); }
  }

  async function deleteSaved() {
    if (!saved || deleting) return;
    const generation=viewGeneration.current;
    setDeleting(true);
    try {
      await api(`/api/v1/live-conversations/${saved.id}/delete`,{});
      if (isCurrentView(generation)) newConversation();
    } catch(e) { if (isCurrentView(generation)) setError(e instanceof Error ? e.message : 'Please retry.'); }
    finally { if (isCurrentView(generation)) setDeleting(false); }
  }

  async function enablePlayback() {
    const generation=viewGeneration.current;
    try {
      await call.current?.play();
      if (isCurrentView(generation)) setPlaybackBlocked(false);
    } catch { if (isCurrentView(generation)) setError(t('Your browser could not play audio. Check its sound permissions.','Браузер не воспроизводит звук. Проверьте разрешения.')); }
  }

  async function refreshScenario(another=false,scenarioId=selectedScenarioId,targetLevel=level) {
    if (!scenarioId) return;
    const request=++scenarioRequest.current;
    setChangingScenario(true); setError('');
    const query=new URLSearchParams({scenario_id:scenarioId,level:targetLevel});
    if (another && options?.scenario?.seed) query.set('exclude_seed',options.scenario.seed);
    try {
      const value=await api<Options>(`/api/v1/live-conversations/options?${query}`);
      if (mounted.current && request===scenarioRequest.current) setOptions(value);
    } catch(e) {
      if (mounted.current && request===scenarioRequest.current) setError(e instanceof Error ? e.message : t('The next situation could not load. Please try again.','Не удалось загрузить следующую ситуацию. Попробуйте ещё раз.'));
    } finally { if (mounted.current && request===scenarioRequest.current) setChangingScenario(false); }
  }

  function chooseScenario(id:string,targetLevel:PracticeLevel) {
    focusNextView.current=true;
    window.scrollTo(0,0);
    setLevel(targetLevel); setSelectedScenarioId(id); setOptions(undefined); setPracticeMode('fluent'); startKey.current=crypto.randomUUID();
    void refreshScenario(false,id,targetLevel);
  }

  function newConversation(event?: Event) {
    viewGeneration.current++;
    starting.current=false;
    focusNextView.current=true;
    window.scrollTo(0,0);
    event?.preventDefault(); call.current?.dispose(); call.current=undefined;
    setSaved(undefined); setCaptions([]); setState('idle'); setError(''); setSeconds(0); setMuted(false); setPlaybackBlocked(false);
    setRequestingReview(false); setDeleting(false); setFollowing(true);
    scenarioRequest.current++; setChangingScenario(false); setSelectedScenarioId(undefined); setOptions(undefined);
    setPracticeMode('fluent'); setPreparingStep(false);
    startKey.current=crypto.randomUUID(); history.replaceState(null,'','#speaking');
  }

  const rows=captionRows(captions);
  const scenario=state==='idle' ? options?.scenario : saved?.scenario;
  const fluentReady=state==='idle' && practiceMode==='fluent' && !!options?.configured && !!selectedScenarioId && !!scenario && !changingScenario;
  const choice=catalogue?.scenarios.find(item=>item.id===selectedScenarioId);
  const showCatalogue=state==='idle' && !selectedScenarioId;
  const role=language==='ru' ? scenario?.role_ru ?? choice?.role_ru ?? 'Сотрудник кафе' : scenario?.role ?? choice?.role ?? 'Café worker';
  const category=language==='ru' ? scenario?.category_title_ru ?? choice?.title_ru ?? 'В кафе' : scenario?.category_title ?? choice?.title ?? 'A stop at the café';
  const goals=language==='ru' ? scenario?.goals_ru ?? scenario?.goals : scenario?.goals;
  const finished=saved && ['ended','review'].includes(state) && !saved.connected && !saved.needs_recovery;
  const compact=!!saved && ['ended','review'].includes(state);
  const naturalEnd=saved?.end_reason==='task_complete' || saved?.end_reason==='learner_finished';
  useEffect(() => {
    if (focusNextView.current && (showCatalogue || scenario)) {
      heading.current?.focus({preventScroll:true});
      focusNextView.current=false;
    }
  },[showCatalogue,scenario?.seed]);
  const captionPanel = <div class="live-caption-section">
      <div class="live-caption-heading"><label><input type="checkbox" checked={showCaptions} onChange={e => setShowCaptions(e.currentTarget.checked)} /> {t('Show conversation','Показать разговор')}</label>{!following && <button class="text-link" onClick={() => setFollowing(true)}>{t('Latest words ↓','Последние слова ↓')}</button>}</div>
      {showCaptions && <div class="live-captions" ref={panel} tabIndex={0} aria-label={t('Conversation captions','Текст разговора')} onScroll={e => { const el=e.currentTarget; setFollowing(el.scrollHeight-el.scrollTop-el.clientHeight<50); }}>
        {!rows.length && <p class="quiet">{t('Russian speech will appear here.','Здесь появится речь на русском.')}</p>}
        {rows.map(row => <div key={row.id} class={`live-caption ${row.role}`}><span>{row.role==='you' ? t('You','Вы') : role}</span><p lang="ru">{row.text}</p></div>)}
      </div>}
    </div>;
  const modeChoices = <fieldset class="speaking-mode-choices" disabled={!scenario || changingScenario || preparingStep} aria-describedby="speaking-mode-help">
    <legend class="sr-only">{t('Conversation mode','Режим разговора')}</legend>
    <div class="speaking-mode-options">
      <label class="speaking-mode-choice">
        <input type="radio" name="speaking-mode" value="fluent" checked={practiceMode==='fluent'} onChange={()=>setPracticeMode('fluent')} />
        <span>{t('Fluent conversation','Свободный разговор')}</span>
      </label>
      <label class="speaking-mode-choice">
        <input type="radio" name="speaking-mode" value="step" checked={practiceMode==='step'} onChange={()=>setPracticeMode('step')} />
        <span>{t('Step-through','Пошаговый разговор')}</span>
      </label>
    </div>
    <p id="speaking-mode-help">{practiceMode==='fluent'
      ? t('Speak naturally using your microphone.','Говорите свободно в микрофон.')
      : t('Pause after each line for reply choices and hints.','Пауза после каждой реплики: варианты ответа и подсказки.')}</p>
  </fieldset>;
  const scenarioRefreshLabel = changingScenario ? t('Finding a situation…','Выбираем ситуацию…') : options ? t('Another situation','Другая ситуация') : t('Try loading the situation again','Загрузить ситуацию ещё раз');
  const content = <>
    {showCatalogue ? <ActivityHeader title={t('Speaking','Разговорная практика')} description={t('Choose a scenario and practise speaking Russian.','Выберите ситуацию и практикуйте разговорный русский.')} headingRef={heading} headingTabIndex={-1} /> : <nav class="speaking-task-nav" aria-label={t('Speaking','Разговорная практика')}>
      {state==='idle' ? <button class="text-link" disabled={preparingStep} onClick={()=>newConversation()}>{t('← All scenarios','← Все ситуации')}</button>
        : <a class="text-link" href="#speaking" onClick={newConversation}>{t('← All scenarios','← Все ситуации')}</a>}
    </nav>}
    {showCatalogue ? <section class="speaking-catalogue" aria-label={t('Choose a scenario','Выберите ситуацию')}>
      {catalogue ? practiceLevels.map(band=>{
        const choices=catalogue.scenarios.filter(item=>item.available!==false && item.variant_count>0 && (item.levels ?? ['A1']).includes(band));
        if (!choices.length) return null;
        return <section class="speaking-level-group" key={band} aria-labelledby={`speaking-level-${band}`}>
          <h2 id={`speaking-level-${band}`}>{band}</h2>
          <ul class="speaking-scenario-grid">{choices.map(item=>{const detail=item.level_details?.[band] ?? item;return <li key={item.id}>
            <button class="speaking-scenario-card" onClick={()=>chooseScenario(item.id,band)} aria-labelledby={`speaking-scenario-${band}-${item.id}`}>
              <span class="speaking-scenario-icon" aria-hidden="true">{item.icon}</span>
              <span class="speaking-scenario-copy"><span class="speaking-scenario-title" id={`speaking-scenario-${band}-${item.id}`}>{language==='ru' ? detail.title_ru : detail.title}</span>
                <span class="speaking-scenario-description">{language==='ru' ? detail.description_ru : detail.description}</span>
                <span class="speaking-scenario-role">{language==='ru' ? item.role_ru : item.role}</span>
              </span><span class="speaking-scenario-arrow" aria-hidden="true">↗</span>
            </button>
          </li>;})}</ul>
        </section>;
      }) : catalogueError ? <div class="speaking-catalogue-error"><p class="error-note" role="alert">{catalogueError}</p><button class="live-mute" onClick={()=>setCatalogueRefresh(value=>value+1)}>{t('Try loading scenarios again','Загрузить ситуации ещё раз')}</button></div> : <p role="status">{t('Loading scenarios…','Загружаем ситуации…')}</p>}
      {practiceMode==='fluent' && <p class="quiet">{t('Speak in Russian, then get feedback on your grammar and fluency. The microphone stays off until you start.','Говорите по-русски и получайте обратную связь по грамматике и беглости речи. Микрофон включится, только когда вы начнёте разговор.')}</p>}
    </section> : sessionId && !saved && state==='review' ? <div class="live-scene">
      <h1 ref={heading} tabIndex={-1}>{t('Your conversation','Ваш разговор')}</h1>
      {!error && <p role="status">{t('Loading your conversation…','Загружаем ваш разговор…')}</p>}
    </div> : <>
    <div class={`live-stage${compact ? ' live-stage-finished' : ''}${active ? ' live-stage-active' : ''}`}>
      <div class="live-scene">
        <div class="live-brief-heading"><div>
          {!compact && <p class="kicker">{scenario?.target_level ? `${scenario.target_level} · ` : ''}{category}</p>}
          <h1 ref={heading} tabIndex={-1}>{scenario ? (language==='ru' ? scenario.title_ru ?? scenario.title : scenario.title) : state==='idle' ? category : t('Your conversation','Ваш разговор')}</h1>
        </div>{!compact && !active && <div class="live-cafe-sign" aria-hidden="true"><span>{scenario?.sign ?? choice?.sign ?? 'КАФЕ'}</span><span>{scenario?.icon ?? choice?.icon ?? '☕'}</span></div>}</div>
        <p>{scenario ? (language==='ru' ? scenario.description_ru ?? scenario.description : scenario.description) : choice ? language==='ru' ? choice.description_ru : choice.description : t('Practise speaking Russian at your own pace.','Практикуйте разговорный русский в своём темпе.')}</p>
        {goals && !compact && <ul class="live-task-goals" aria-label={t('Your task','Ваша задача')}>{goals.map(goal=><li key={goal}>{goal}</li>)}</ul>}
        {state === 'idle' && practiceMode==='fluent' && <p class="quiet">{t('Your conversation partner is an AI. You can pause, change your mind or ask them to repeat.','Ваш собеседник — ИИ. Можно подумать, передумать или попросить повторить.')}</p>}
        <div class="live-controls">
          {state==='idle' && modeChoices}
          {state==='idle' && practiceMode==='step' && scenario?.seed && !changingScenario && <StepThroughConversation key={`${selectedScenarioId}:${scenario.seed}:${level}`} embeddedSetup scenarioId={selectedScenarioId} scenarioSeed={scenario.seed} targetLevel={level} language={language} onPreparingChange={setPreparingStep} onReloadScenario={()=>void refreshScenario(true)} />}
          {state === 'idle' && <div class={`action-row${practiceMode==='step' ? ' speaking-step-secondary' : ''}`}>
            {practiceMode==='fluent' && <button class="cta" disabled={!fluentReady || starting.current} onClick={start}>{t('Start talking','Начать разговор')} <span aria-hidden="true">↗</span></button>}
            <button type="button" class="live-refresh" aria-label={scenarioRefreshLabel} title={scenarioRefreshLabel} aria-busy={changingScenario} disabled={changingScenario || preparingStep} onClick={()=>void refreshScenario(!!options)}>
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
                <path d="M16.023 9.348h4.992m0 0V4.356m0 4.992-3.181-3.182a8.25 8.25 0 0 0-13.803 3.7M7.977 14.652H2.985m0 0v4.992m0-4.992 3.181 3.182a8.25 8.25 0 0 0 13.803-3.7" />
              </svg>
            </button>
          </div>}
          {active && <>
            <p class="live-status" role="status"><span class={state==='listening' && !muted ? 'live-dot' : 'live-dot muted'} />{state==='connecting' ? t('Connecting…','Соединяем…') : state==='ending' ? t('Ending the call…','Завершаем разговор…') : muted ? t('Microphone muted','Микрофон выключен') : t('The conversation is live','Разговор начался')} <span>{Math.floor(seconds/60)}:{String(seconds%60).padStart(2,'0')}</span></p>
            <div class="action-row">
              {state==='listening' && <button class="live-mute" aria-pressed={muted} onClick={() => { call.current?.mute(!muted); setMuted(!muted); }}>{muted ? t('Turn on microphone','Включить микрофон') : t('Mute microphone','Выключить микрофон')}</button>}
              <button class="live-end" disabled={state==='ending'} onClick={() => call.current?.end()}>{t('End conversation','Завершить разговор')}</button>
            </div>
          </>}
          {['ended','review'].includes(state) && <div>
            <p class="live-status">{saved?.connected ? t('This conversation is still open in another tab.','Этот разговор открыт в другой вкладке.') : naturalEnd ? t('Conversation finished.','Разговор завершён.') : t('Your conversation is saved.','Разговор сохранён.')}</p>
            <div class="action-row">{!finished && <a class="cta" href="#speaking" onClick={newConversation}>{t('Try another conversation','Начать новый разговор')} ↗</a>}
              {(saved?.connected || saved?.needs_recovery) && <button class="live-end" onClick={finishSaved}>{saved.needs_recovery ? t('Recover saved audio','Восстановить запись') : t('End conversation','Завершить разговор')}</button>}</div>
          </div>}
          {playbackBlocked && active && <button class="cta" onClick={enablePlayback}>{t('Turn on sound','Включить звук')}</button>}
          {state==='idle' && practiceMode==='fluent' && options && !options.configured && <p role="status" class="quiet">{t('Fluent conversation is currently unavailable.','Свободный разговор сейчас недоступен.')}</p>}
          {fluentReady && options && <p class="quiet">{options.max_seconds <= 60
            ? t('Up to one minute in the demo. Your microphone audio is saved for speaking feedback.','В демоверсии — до одной минуты. Запись микрофона сохраняется для разбора речи.')
            : t('Up to five minutes. Your microphone audio is saved for speaking feedback.','До пяти минут. Запись микрофона сохраняется для разбора речи.')}</p>}
        </div>
        {active && captionPanel}
        {compact && scenario && <details class="live-task-details"><summary>{t('Task & reference','Задание и подсказки')}</summary>
          <div class="live-task-reference">
            {goals && <ul class="live-task-goals" aria-label={t('Your task','Ваша задача')}>{goals.map(goal=><li key={goal}>{goal}</li>)}</ul>}
            <ScenarioReference scenario={scenario} language={language} />
          </div>
        </details>}
      </div>
      {!compact && <ScenarioReference scenario={scenario} language={language} />}
    </div>
    </>}
    {error && <p class="error-note" role="alert">{error}</p>}
    {finished && <section class="live-feedback" aria-labelledby="speaking-feedback-heading">
      <p class="kicker">{t('AI practice feedback','Обратная связь от ИИ')}</p>
      <h2 id="speaking-feedback-heading">{t('How you got on','Как прошёл разговор')}</h2>
      {saved.review?.state==='ready' && saved.review.report
        ? <SpeakingFeedback report={saved.review.report} scenario={scenario} language={language} />
        : <>
          {saved.review && ['queued','analysing'].includes(saved.review.state) && !saved.review.retryable
            ? <p role="status">{t('Listening back to your conversation…','Прослушиваем ваш разговор…')}</p>
            : <>
              {saved.review?.error && <p class="quiet" role="status">{saved.review.error}</p>}
              {!saved.review && <p>{t('Get feedback on your grammar, fluency and the task.','Получите обратную связь по грамматике, беглости речи и заданию.')}</p>}
              <button class="live-mute" disabled={requestingReview || !saved.recordings.length} onClick={requestReview}>{requestingReview ? t('Starting feedback…','Начинаем разбор…') : saved.review ? t('Try feedback again','Повторить разбор') : t('Get speaking feedback','Получить обратную связь')}</button>
              {!saved.recordings.length && <p class="quiet">{t('There is no saved microphone audio to review.','Нет сохранённой записи микрофона для разбора.')}</p>}
            </>}
        </>}
      <div class="live-review-actions"><a class="cta" href="#speaking" onClick={newConversation}>{t('Try another conversation','Начать новый разговор')} ↗</a></div>
    </section>}
    {!active && rows.length>0 && captionPanel}
    {saved && saved.recordings.some(r => r.state !== 'capturing') && <details class="live-notes" open={!active && !saved.review}>
      <summary>{saved.review ? t('Original recordings','Исходные записи') : t('Recordings & language notes','Записи и разбор речи')}</summary>
      <p class="quiet">{saved.review ? t('Listen back to the original recording if anything in the feedback seems wrong.','Если что-то в разборе кажется неверным, прослушайте исходную запись.') : t('These notes use a separate transcription of your microphone audio. Listen to the recording if a suggestion looks wrong.','Для разбора используется отдельное распознавание записи микрофона. Если замечание кажется неверным, прослушайте запись.')}</p>
      {saved.recordings.filter(r => r.state!=='capturing').map(recording => <section class="live-recording" key={recording.id}>
        <h3>{t('Recording','Запись')} {recording.ordinal} <span>{Math.round(recording.sample_count/recording.sample_rate)} {t('sec','сек')}</span></h3>
        <audio controls preload="none" src={recording.audio_url} aria-label={`${t('Your recording','Ваша запись')} ${recording.ordinal}`} />
        {recording.transcript && <details><summary>{t('What the transcription heard','Распознанный текст')}</summary>{russianTranscript(recording.transcript.text) !== null ? <p lang="ru">{recording.transcript.text}</p> : <p class="quiet">{t('No Russian transcript to show.','Нет русского текста для показа.')}</p>}</details>}
        {!saved.review && recording.assessment && <><p>{recording.assessment.communication}</p>{recording.assessment.corrections.map((c,i) => <div class="conversation-correction" key={i}><span lang="ru">{c.original}</span> → <strong lang="ru">{c.replacement}</strong><p>{c.explanation}</p></div>)}{recording.assessment.uncertainty && <p class="quiet">{recording.assessment.uncertainty}</p>}</>}
        {!saved.review && ['queued','analysing'].includes(recording.state) && <p class="quiet">{t('Preparing language notes…','Готовим разбор речи…')}</p>}
        {!saved.review && recording.error && <p class="quiet">{recording.error}</p>}
        {!saved.review && recording.retryable && <button class="text-link" onClick={() => retry(recording)}>{scenario?.seed && !recording.assessment ? t('Retry transcription','Повторить распознавание') : t('Try language notes again','Повторить разбор речи')}</button>}
      </section>)}
    </details>}
    {saved && !active && !saved.connected && <details class="live-delete"><summary>{t('Delete this conversation','Удалить этот разговор')}</summary><p>{t('This removes its recordings, captions and language notes.','Записи, текст и разбор этого разговора будут удалены.')}</p><button class="live-end" disabled={deleting} onClick={deleteSaved}>{t('Delete conversation','Удалить разговор')}</button></details>}
    {state==='idle' && <>
      <SpeakingHistory language={language} />
      <details class="speaking-tools"><summary>{t('Developer tools','Инструменты разработчика')}</summary>
        <a class="text-link" href="#speaking/lab">{t('Speech lab','Проверка распознавания')} ↗</a>
      </details>
    </>}
  </>;
  return <section class={`page live-page${showCatalogue ? ' activity-entry' : ''}`}>
    {showCatalogue ? <div class="activity-entry-content">{content}</div> : content}
  </section>;
}

// Menu glosses are display help for these curated café items, not vocabulary
// translations written back into the learner's database.
const menuGlosses:Record<string,string>={чай:'Tea',кофе:'Coffee',какао:'Cocoa',сок:'Juice',булочка:'Bun',бутерброд:'Sandwich',пирог:'Pie',печенье:'Biscuits','яблочный пирог':'Apple pie'};
function ScenarioReference({scenario,language}:{scenario?:Scenario;language:Language}) {
  const t=(en:string,ru:string)=>language==='ru' ? ru : en;
  const reference=Array.isArray(scenario?.reference?.items) ? scenario.reference : undefined;
  const menu=Object.entries(scenario?.menu ?? {});
  const cafe=!scenario?.scenario_id || scenario.scenario_id==='cafe';
  const title=reference ? language==='ru' ? reference.title_ru ?? reference.title : reference.title : menu.length ? cafe ? t('On the menu','Меню') : t('Price list','Цены') : t('A little help','Небольшая подсказка');
  return <aside class="live-menu" aria-label={!reference && menu.length && cafe ? t('Café menu','Меню кафе') : title}><span class="kicker">{title}</span>
    {reference ? reference.items.map((item,index)=><div key={index}><span><strong>{language==='ru' ? item.label_ru ?? item.label : item.label}</strong></span><span>{language==='ru' ? item.value_ru ?? item.value : item.value}</span></div>) : menu.map(([word,price]) => <div key={word}><span><strong lang="ru">{word}</strong>{language==='en' && menuGlosses[word] && <small>{menuGlosses[word]}</small>}</span><span>{price} ₽</span></div>)}
    {!reference && !menu.length && <p>{t('You don’t need perfect Russian to make yourself understood.','Не обязательно говорить идеально, чтобы вас поняли.')}</p>}
    <p>{t('Need to hear it again?','Нужно услышать ещё раз?')}<br/><span lang="ru">«Повторите, пожалуйста.»</span></p>
  </aside>;
}

function SpeakingFeedback({report,scenario,language}:{report:SpeakingReport;scenario?:Scenario;language:Language}) {
  const t=(en:string,ru:string)=>language==='ru' ? ru : en;
  const goalLabels=language==='ru' ? scenario?.goals_ru ?? scenario?.goals : scenario?.goals;
  return <>
    <p class="live-feedback-summary">{report.summary}</p>
    <div class="live-score-grid">
      {([['grammar',t('Grammar','Грамматика')],['fluency',t('Fluency','Беглость речи')]] as const).map(([key,label])=>{
        const score=report[key];
        return <section class="live-score" key={key} aria-label={label}>
          <h3>{label}</h3>
          <p class={score.score===null ? 'live-score-empty' : 'live-score-number'}>{score.score===null ? (report.speech_status==='unclear' ? t('Not enough clear speech','Недостаточно разборчивой речи') : t('Not enough speech','Недостаточно речи')) : <><strong>{score.score}</strong><span> / 5</span></>}</p>
          <p>{score.reason}</p>
        </section>;
      })}
    </div>
    {report.goals.length>0 && <div class="live-goal-review"><h3>{t('Your task','Ваша задача')}</h3><ul>
      {report.goals.map((goal,goalIndex)=>{
        const index=scenario?.goal_ids?.indexOf(goal.id) ?? goalIndex;
        const label=index>=0 ? goalLabels?.[index] : undefined;
        return label ? <li key={goal.id}><span aria-hidden="true" class={`live-goal-mark ${goal.status}`}>{goal.status==='completed' ? '✓' : '·'}</span><span>{label}</span><small>{goal.status==='completed' ? t('Done','Готово') : goal.status==='uncertain' ? t('Not clear from the recording','По записи неясно') : t('Still to try','Ещё можно попробовать')}</small></li> : null;
      })}
    </ul></div>}
    {report.corrections.slice(0,2).map((correction,index)=><div class="conversation-correction" key={index}><span lang="ru">{correction.original}</span> → <strong lang="ru">{correction.replacement}</strong><p>{correction.explanation}</p></div>)}
    {report.next_step && <div class="live-next-step"><h3>{t('Try this next time','Попробуйте в следующий раз')}</h3><p>{report.next_step}</p></div>}
    {report.uncertainty && <p class="quiet">{report.uncertainty}</p>}
    {!!report.criterion_details?.length && <details class="live-review-evidence"><summary>{t('What this recording shows','Что показывает эта запись')}</summary>
      <p class="quiet">{t('This practice feedback may include help you received during the conversation.','Эта обратная связь может учитывать результат подсказок, полученных во время разговора.')}</p>
      {report.criterion_details.map((criterion,index)=><section key={index}>
        <h3>{language==='ru' ? criterion.label_ru : criterion.label}</h3>
        <p>{criterion.outcome==='satisfied' ? t('Shown in this recording','Есть в этой записи') : criterion.outcome==='partial' ? t('Partly shown','Показано частично') : criterion.outcome==='not_satisfied' ? t('Needs practice','Стоит потренировать') : t('Not enough evidence','Недостаточно материала')}</p>
        <p>{criterion.feedback}</p>
      </section>)}
    </details>}
    <details class="live-review-evidence"><summary>{t('What the review heard','Что услышала модель при разборе')}</summary>
      <p class="quiet">{t('This comes from a separate review of your recording. It may differ from the live captions.','Это результат отдельного прослушивания записи. Он может отличаться от текста во время разговора.')}</p>
      {russianTranscript(report.transcript)!==null ? <p lang="ru" class="live-review-transcript">{report.transcript}</p> : <p class="quiet">{t('No Russian transcript to show.','Нет русского текста для показа.')}</p>}
    </details>
  </>;
}
