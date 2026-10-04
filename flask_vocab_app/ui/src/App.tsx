import {GameLanguage} from './GameLocale';
import { appUrl } from './app-url';
import { useEffect, useRef, useState } from 'preact/hooks';
import { Sheet, ActivityLink } from './components';
import { WelcomeHero } from './WelcomeHero';
import { CoursePreparation } from './CoursePreparation';
import {courseHref,parseReleasedCourse} from './course-routes';
import { FirstDelivery } from './FirstDelivery';
import { FirstSteps } from './FirstSteps';
import { Alphabet } from './Alphabet';
import { JourneyGame, GameCatalogue } from './JourneyGames';
import { GameShop } from './GameShop';
import { api, type Household, type LearningHome, type Progress, type PracticeSession } from './learning-api';
import { Practice } from './Practice';
import { AssessmentPilot } from './AssessmentPilot';
import {UnitExchange} from './UnitExchange';
import { Flashcards, FlashcardsSetup } from './Flashcards';
import { GenerateCards } from './GenerateCards';
import { NativeReview } from './NativeReview';
import { Conversation } from './Conversation';
import { LiveConversation } from './LiveConversation';
import { Journey, ProgressionBadge, useProgression, type PracticeLevel } from './Progression';
import { CourseJourney } from './CourseJourney';
import { SkillProgress } from './SkillProgress';
import { UserSessionLink, type UserProfile, type AccountMode } from './UserSessionLink';
import {useOnboarding, type OnboardingState} from './Onboarding';
import { ActivitySidebar, type ActivityNavigation } from './ActivitySidebar';
import { AppearancePicker } from './AppearancePicker';
import { ActivitiesMenu } from './ActivitiesMenu';
import { ActivityHeader } from './ActivityHeader';
import type { Language } from './review-types';
import { StepThroughConversation } from './StepThroughConversation';
import sleepingBarsik from './assets/barsik-sleeping-v1.webp';
import './styles/lesson-player.css';

type Page = 'home' | 'activities' | 'alphabet' | 'words' | 'practice' | 'assessment' | 'first-delivery' | 'first-steps' | 'flashcards' | 'review' | 'generate' | 'conversation' | 'speech-lab' | 'speaking' | 'journey' | 'game' | 'games' | 'shop';
type Route = { alphabetFrom?:'first-delivery'|'first-steps'; unitExchangeId?:string; page: Page; gameId?:string; sessionId?: string; worldId?:string; chapterId?:string; courseReleaseId?:string; checkpointId?:string;coursePracticeId?:string;courseSectionId?:string; wordId?: number; lessonId?: string; firstStepsVersion?:string; topic?:string; scenarioId?:string; speakingLevel?:PracticeLevel; speakingMode?:'fluent'|'step'; canonicalHash?: string };
function route(): Route {
  const hash = window.location.hash.slice(1);
  if (hash === 'alphabet' || hash.startsWith('alphabet?')) {
    const from = new URLSearchParams(hash.split('?')[1]).get('from');
    return {page:'alphabet', alphabetFrom:from === 'first-delivery' || from === 'first-steps' ? from : undefined};
  }
  const unitExchange = /^unit-exchange\/([A-Za-z0-9_-]+)$/.exec(hash);
  if (unitExchange) return {page:'speaking',unitExchangeId:unitExchange[1]};
  const assessment = /^assessment(?:\/([A-Za-z0-9_-]+))?$/.exec(hash);
  if (assessment) return { page: 'assessment', sessionId: assessment[1] };
  const gameSession=/^games\/session\/([A-Za-z0-9_-]+)$/.exec(hash);
  if(gameSession)return {page:'game',sessionId:gameSession[1]};
  const game=/^games\/([a-z][a-z0-9-]{1,48})$/.exec(hash);
  if(game)return {page:'game',gameId:game[1]};
  const firstSteps=/^first-steps(?:\/([a-z-]+))?(?:\?(.*))?$/.exec(hash);
  if (firstSteps) return {page:'first-steps',lessonId:firstSteps[1],firstStepsVersion:new URLSearchParams(firstSteps[2]).get('version') ?? undefined};
  if (hash === 'journey/post-office') return {page:'first-steps',canonicalHash:'#first-steps'};
  const releasedCourse=parseReleasedCourse(hash);
  if(releasedCourse)return {page:'journey',...releasedCourse};
  const coursePractice=/^journey\/practice\/(?:start\/([a-z-]+)|([A-Za-z0-9_-]+))$/.exec(hash);
  if(coursePractice)return {page:'journey',courseSectionId:coursePractice[1],coursePracticeId:coursePractice[2]};
  const course=/^journey\/(chapter|checkpoint)\/([A-Za-z0-9_-]+)$/.exec(hash);
  if (course) return {page:'journey', ...(course[1]==='chapter' ? {chapterId:course[2]} : {checkpointId:course[2]})};
  const journey=/^journey(?:\/([A-Za-z0-9_-]+))?$/.exec(hash);
  if (journey) return {page:'journey',worldId:journey[1]};
  const conversation = /^(?:conversation|speaking\/recorded)\/([A-Za-z0-9_.:-]+)$/.exec(hash);
  if (conversation) return {page:'conversation',sessionId:conversation[1],canonicalHash:`#speaking/recorded/${conversation[1]}`};
  if (hash === 'speech-lab' || hash === 'speaking/lab') return {page:'speech-lab',canonicalHash:'#speaking/lab'};
  const step=/^speaking\/step(?:\/([A-Za-z0-9_-]+))?$/.exec(hash);
  if(step)return step[1] ? {page:'speaking',speakingMode:'step',sessionId:step[1]} : {page:'speaking',canonicalHash:'#speaking'};
  const scenario=/^speaking\/scenario\/([a-z-]+)(?:\?(.*))?$/.exec(hash);
  if(scenario){
    const level=new URLSearchParams(scenario[2] ?? '').get('level') ?? 'A1';
    const speakingLevel=(['A1','A2','B1','B2'] as const).find(item=>item===level);
    return speakingLevel ? {page:'speaking',scenarioId:scenario[1],speakingLevel} : {page:'speaking'};
  }
  const live = /^(?:live-conversation|speaking)(?:\/([A-Za-z0-9_.:-]+))?$/.exec(hash);
  if (live) return {page:'speaking',sessionId:live[1],canonicalHash:`#speaking${live[1] ? '/' + live[1] : ''}`};
  if (hash === 'conversation') return {page:'speaking',canonicalHash:'#speaking'};
  const generation = /^generate(?:\/([A-Za-z0-9_.:-]+))?(?:\?word_id=(\d+))?$/.exec(hash);
  if (generation) return { page:'generate', sessionId:generation[1], wordId:generation[2] ? Number(generation[2]) : undefined };
  const review = /^review\/([A-Za-z0-9_.:-]+)$/.exec(hash);
  if (review) return { page: 'review', sessionId: review[1] };
  if (hash === 'flashcards' || hash.startsWith('flashcards?')) {
    const params = new URLSearchParams(hash.split('?')[1]);
    const word = params.get('word_id'), lesson = params.get('lesson_id'), topic = params.get('topic');
    return { page:'flashcards', wordId:word && /^\d+$/.test(word) ? Number(word) : undefined, lessonId:lesson || undefined, topic:topic || undefined };
  }
  const session = /^practice\/([A-Za-z0-9_.:-]+)$/.exec(hash);
  if (session) return { page: 'practice', sessionId: session[1] };
  if (hash === 'first-delivery') return { page: 'first-delivery' };
  if (hash === 'shop') return { page: 'shop' };
  if (hash === 'games') return { page: 'games' };
  if (hash === 'activities' || hash === 'letter') return { page: 'activities' };
  if (hash === 'words' || hash === 'pocket') return { page: 'words' };
  return { page: 'home' };
}

const activities = [
  { title: 'Comprehension', description: 'Read or listen, then answer questions about the story.', href: '/comprehension', mark: 'Аа', detail: 'Reading & listening' },
  { title: 'Word Jumble', description: 'Use the given words to write a sentence of your own.', href: '/word_jumble', mark: 'Я…', detail: 'Creative word game' },
  { title: 'Translate a sentence', description: 'Translate an English sentence into Russian and get feedback.', href: '/sentences', mark: 'А↔A', detail: 'Translation' },
  { title: 'Writing', description: 'Write about a topic using the words in your task.', href: '/writing', mark: 'абв', detail: 'Longer practice' },
  { title: 'Lessons', description: 'Work through questions and exercises from your learning materials.', href: '/lessons', mark: 'Aa', detail: 'Guided exercises' },
  { title: 'Speaking', description: 'Choose a situation, speak Russian and get feedback on your grammar and fluency.', href: '#speaking', mark: '↔', detail: 'Speaking & listening' },
];
type State = { mode: 'loading' | 'legacy' | 'adult' | 'locked' | 'child' | 'personal' | 'error'; household?: Household; home?: LearningHome; progress?: Progress; error?: string };

export function App({ householdEnabled = false, nativeEnabled = true, language = 'en', csrfToken = '', navigation, navigationLayout = 'top', initialProfile, initialOnboarding, accountMode = 'local', signInAvailable = false, demoAvailable = false, sessionScope, defaultCourseRelease='a1-v1' }: { defaultCourseRelease?:string;householdEnabled?: boolean; nativeEnabled?: boolean; language?: Language; csrfToken?: string; navigation?: ActivityNavigation | null; navigationLayout?: 'top' | 'sidebar'; initialProfile?: UserProfile | null; initialOnboarding?: OnboardingState; accountMode?: AccountMode; signInAvailable?: boolean; demoAvailable?: boolean; sessionScope?: string }) {
  const [location, setLocation] = useState<Route>(route);
  const onboarding=useOnboarding(initialOnboarding);
  const [state, setState] = useState<State>({ mode: householdEnabled ? 'loading' : 'legacy' });
  const signedOut = !householdEnabled && initialProfile === null;
  const profile = householdEnabled ? state.household?.profile ?? null : initialProfile === undefined ? state.household?.profile ?? null : initialProfile;
  const progression=useProgression(!signedOut && (!householdEnabled || !!state.household?.profile),profile?.id);
  const [refresh, setRefresh] = useState(0);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState('');
  const pendingStart = useRef<{ profile_id: string; version_id: string; submission_id: string }>();
  const startAbort = useRef<AbortController>();
  const heading = useRef<HTMLHeadingElement>(null);
  const practiceHeading = useRef<HTMLHeadingElement>(null);
  const navigated = useRef(false);
  const workspace = useRef<HTMLDivElement>(null);
  const header = useRef<HTMLElement>(null);
  const activityWorkspace = Boolean(navigation && navigationLayout === 'sidebar');
  const lessonWorkspace = location.page === 'first-delivery' || location.page === 'first-steps' && !!location.lessonId;
  const learningWorkspace = lessonWorkspace || location.page === 'alphabet' || location.page === 'assessment' || location.page === 'practice' || location.page === 'speaking' || location.page === 'journey' && Boolean(location.chapterId || location.checkpointId || location.coursePracticeId || location.courseSectionId);
  const activeNavigationPage = ['flashcards','review','generate'].includes(location.page) ? 'native_flashcards'
    : ['conversation','speech-lab','speaking'].includes(location.page) ? 'speaking'
    : location.page === 'words' ? 'vocab'
    : ['home','first-delivery','first-steps'].includes(location.page) ? 'home'
    : ['game','games'].includes(location.page) ? 'games'
    : location.page === 'alphabet' ? 'alphabet' : location.page === 'activities' ? 'activities' : location.page === 'shop' ? 'shop' : '';

  useEffect(() => {
    if (location.canonicalHash && window.location.hash !== location.canonicalHash) {
      history.replaceState(history.state, '', location.canonicalHash);
    }
  }, [location]);
  useEffect(() => {
    if (!workspace.current) return;
    const sidebar = workspace.current.querySelector<HTMLElement>('.activity-sidebar');
    const brand = sidebar?.querySelector<HTMLElement>('.sidebar-brand-row');
    const toggle = sidebar?.querySelector<HTMLElement>('.activity-menu-toggle');
    const measure = () => {
      let pixels = header.current?.getBoundingClientRect().height ?? 0;
      if (activityWorkspace && sidebar && brand && toggle && getComputedStyle(toggle).display !== 'none') {
        // The expanded menu scrolls independently; only its compact shell
        // needs to clear focused headings and profile anchors.
        const style = getComputedStyle(sidebar);
        pixels = toggle.getBoundingClientRect().bottom - sidebar.getBoundingClientRect().top + (parseFloat(style.paddingBottom) || 0);
      }
      const height = `${Math.max(0, pixels)}px`;
      workspace.current?.style.setProperty('--activity-header-height', height);
      document.documentElement.style.setProperty('--skill-header-height', height);
    };
    measure();
    window.addEventListener('resize', measure);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    for (const element of [header.current, brand, toggle]) {
      if (element) observer?.observe(element);
    }
    return () => {
      window.removeEventListener('resize', measure);
      observer?.disconnect();
    };
  }, [activityWorkspace, learningWorkspace]);

  useEffect(() => {
    const navigate = () => {
      if (window.location.hash === '#main') return;
      navigated.current = true; setLocation(route());
    };
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  useEffect(() => {
    if (location.page === 'home' && window.location.hash === '#choose-practice') {
      practiceHeading.current?.focus();
    } else if (navigated.current) heading.current?.focus();
  }, [location, state.mode]);
  useEffect(() => {
    if (signedOut) { setState({mode:'legacy'}); return; }
    if (!householdEnabled && !['flashcards','review','generate','conversation','speech-lab','speaking','practice','assessment'].includes(location.page)) { setState({mode:'legacy'});return; }
    const controller = new AbortController();
    startAbort.current?.abort(); setStarting(false); setStartError(''); setState({ mode: 'loading' });
    void (async () => {
      try {
        const household = await api<Household>('/api/v1/household', undefined, controller.signal);
        if (household.adult) setState({ mode: 'adult', household });
        else if (!household.profile) setState({ mode: 'locked', household });
        else if (['flashcards','review','generate','conversation','speech-lab','speaking','practice','assessment'].includes(location.page)) {
          if (!controller.signal.aborted) setState({ mode: householdEnabled ? 'child' : 'personal', household, home: {profile:household.profile,content:[],sessions:[]} });
        } else {
          const [home, progress] = await Promise.all([
            api<LearningHome>('/api/v1/post', undefined, controller.signal),
            api<Progress>('/api/v1/word-pocket', undefined, controller.signal),
          ]);
          if (home.profile.id !== household.profile.id || progress.profile_id !== household.profile.id) throw new Error('The study profile changed. Please reload.');
          if (!controller.signal.aborted) setState({ mode: householdEnabled ? 'child' : 'personal', household, home, progress });
        }
      } catch (error) {
        if (!controller.signal.aborted) setState({ mode: 'error', error: error instanceof Error ? error.message : 'We could not open your activities.' });
      }
    })();
    return () => controller.abort();
  }, [householdEnabled, signedOut, refresh, location.page]);
  useEffect(() => {
    const onVisible = () => {
      // Personal generation settings are unsaved form state; keep them on tab return.
      if (!householdEnabled && location.page==='generate' && !location.sessionId) return;
      if (['conversation','speech-lab','speaking'].includes(location.page)) return;
      if (document.visibilityState === 'visible') setRefresh(value => value + 1);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => { document.removeEventListener('visibilitychange', onVisible); startAbort.current?.abort(); };
  }, [householdEnabled,location.page,location.sessionId]);

  async function start(versionId: string) {
    if (!state.home || starting) return;
    const profileId = state.home.profile.id;
    if (pendingStart.current?.version_id !== versionId || pendingStart.current.profile_id !== profileId) pendingStart.current = { profile_id: profileId, version_id: versionId, submission_id: crypto.randomUUID() };
    const controller = new AbortController(); startAbort.current = controller;
    setStarting(true); setStartError('');
    try {
      const saved = await api<PracticeSession>('/api/v1/learning-sessions', pendingStart.current, controller.signal);
      pendingStart.current = undefined; window.location.hash = `practice/${saved.id}`;
    } catch (error) { if (!controller.signal.aborted) setStartError(error instanceof Error ? error.message : 'Please try starting again.'); }
    finally { if (!controller.signal.aborted) setStarting(false); }
  }

  const legacy = state.mode === 'legacy' || state.mode === 'adult' || state.mode === 'personal';
  const wordsHref = householdEnabled && !legacy ? '#words' : '/vocab';
  const menuActivities = (navigation?.activities ?? [
    {page:'native_flashcards', href:'#flashcards', label:language === 'ru' ? 'Карточки' : 'Flashcards', boost:false},
    {page:'comprehension', href:'/comprehension', label:language === 'ru' ? 'Понимание текста' : 'Comprehension', boost:false},
    {page:'speaking', href:'#speaking', label:language === 'ru' ? 'Разговорная практика' : 'Speaking', boost:false},
    {page:'writing', href:'/writing', label:language === 'ru' ? 'Письменная практика' : 'Writing', boost:false},
    {page:'lessons', href:'/lessons', label:language === 'ru' ? 'Уроки' : 'Lessons', boost:false},
    {page:'word_jumble', href:'/word_jumble', label:language === 'ru' ? 'Слова вперемешку' : 'Word Jumble', boost:false},
    {page:'sentences', href:'/sentences', label:language === 'ru' ? 'Перевести предложение' : 'Translate a sentence', boost:false},
    {page:'alphabet', href:'#alphabet', label:language === 'ru' ? 'Алфавит' : 'Alphabet', boost:false},
  ]).filter(item => nativeEnabled || item.page !== 'native_flashcards');
  const profileControl = <UserSessionLink profile={profile} language={language} household={householdEnabled} accountMode={accountMode} signInAvailable={signInAvailable} demoAvailable={demoAvailable} sessionScope={sessionScope} />;
  const appearanceControl = <AppearancePicker language={language} navigationLayout={navigationLayout} csrfToken={csrfToken} />;
  const coinBalance = onboarding.state.coins_introduced && <ProgressionBadge progression={progression} language={language} introductory={signedOut || householdEnabled && !profile} />;
  const languageControl = <details class="post-language"><summary aria-label={language === 'ru' ? 'Язык интерфейса' : 'Interface language'}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 5h12M9 3v2M12 5c-1 5-4 8-8 10M5 8c1 3 4 6 7 7M13 21l4.5-11L22 21M15 17h5"/></svg></summary><form method="post" action="/ui-language"><input type="hidden" name="csrf_token" value={csrfToken} /><input type="hidden" name="next" value={appUrl(`/${window.location.hash}`)} /><button name="lang" value="en" lang="en" aria-current={language === 'en' ? 'true' : undefined}>English</button><button name="lang" value="ru" lang="ru" aria-current={language === 'ru' ? 'true' : undefined}>Русский</button></form></details>;
  const skillProgress = onboarding.state.progress_introduced && <SkillProgress progression={progression} language={language} introductory={signedOut || householdEnabled && !profile} profileHref="/#journey" />;
  const ready = state.home?.content.filter(item => item.kind === 'activity') ?? [];
  const nativeReady = nativeEnabled && state.home?.content.some(item => item.kind === 'deck');
  const resumable = state.home?.sessions.find(item => item.status === 'active' && item.content_status === 'published');
  const nextChapter=progression.data?.course?.chapters.find(chapter=>chapter.id===progression.data?.course?.current_chapter_id);
  const courseJourney=(progression.data?.course?.release_id ?? (signedOut ? defaultCourseRelease : undefined))==='a1-journey-v2';
  const tutorialNext = {
    href: '#first-steps/bag?version=first-steps-v2', label: 'Next lesson: Name what you see',
    description: 'Next, help Barsik check his bag before he sets off.',
  };

  function availableActivities() {
    const cards = nativeEnabled && <ActivityLink title="Flashcards" description="Generate cards from your vocabulary and study them here." href="#flashcards" mark="Я ↻" detail="Spaced practice" />;
    if (legacy) return <div class="activity-list">{cards}{activities.map(activity => <ActivityLink key={activity.href} {...activity} {...(language === 'ru' && activity.href === '#speaking' ? {title:'Разговорная практика',description:'Выберите ситуацию, поговорите по-русски и получите разбор грамматики и беглости речи.',detail:'Говорение и аудирование'} : {})} />)}</div>;
    if (state.mode === 'locked') return <Sheet><h2>Who’s learning?</h2><p>A grown-up can choose a learner and open their saved activities.</p><a class="text-link" href="/post/household">Choose a learner</a></Sheet>;
    return <>
      {cards}
      {resumable && <ActivityLink title={`Continue: ${resumable.title}`} description="Pick up where you left off. Your answers are saved." href={`#practice/${resumable.id}`} mark="→" detail="In progress" />}
      {ready.length ? <div class="practice-list">{ready.map(item => <div class="practice-row" key={item.version_id}><div><h3>{item.title}</h3><p>Choose an answer, check it and save your practice.</p></div>
        <button class="cta" disabled={starting} onClick={() => void start(item.version_id)}>{starting ? 'Opening…' : 'Start practice'}<span class="sr-only">: {item.title}</span></button></div>)}</div>
        : !resumable && !nativeReady && <Sheet><h2>Choose your first activity together.</h2><p>A grown-up needs to approve some learning material before you start.</p><a class="text-link" href="/post/household">Ask a grown-up to help</a></Sheet>}
      {startError && <p role="alert" class="error-note">{startError} You can try Start practice again.</p>}
      <p class="quiet section-note">More reading and sentence games are being adapted for learner profiles. Grown-ups can open them in the existing workspace.</p>
    </>;
  }

  return <GameLanguage.Provider value={language}><div ref={workspace} class={`navigation-layout-${navigationLayout}${activityWorkspace ? ' activity-workspace' : ''}${lessonWorkspace ? ' lesson-workspace' : ''}${learningWorkspace ? ' learning-workspace' : ''}${location.page === 'speaking' ? ' speaking-workspace' : ''}`}>
    <a class="skip-link" href="#main">Skip to content</a>
    {!activityWorkspace && <header ref={header} class="top"><a class="brand" href="#home" aria-label="Russian Arcade home"><span class="mark" lang="ru" aria-hidden="true">Я</span><span><span class="brand-name">Russian Arcade</span><span class="origin">Learn and practise Russian</span></span></a>
      <nav class="nav" aria-label={language === 'ru' ? 'Главное меню' : 'Main navigation'}>
        <a href="#home" aria-current={['home','first-delivery','first-steps'].includes(location.page) ? 'page' : undefined}>{language === 'ru' ? 'Главная' : 'Home'}</a>
        <ActivitiesMenu items={menuActivities} language={language} active={['activities','practice','review','flashcards','generate','conversation','speech-lab','speaking','game','games','alphabet'].includes(location.page)} activePage={activeNavigationPage} />
        <a href={wordsHref} aria-current={location.page === 'words' ? 'page' : undefined}>{language === 'ru' ? 'Мои слова' : 'My words'}</a>
      </nav>
      {coinBalance}
      {languageControl}
      {appearanceControl}
      {profileControl}
      {skillProgress}
    </header>}
    <div class={activityWorkspace ? 'activity-layout' : undefined}>
    {activityWorkspace && navigation && <ActivitySidebar navigation={navigation} activePage={activeNavigationPage} language={language} profileControl={profileControl} coinBalance={coinBalance} languageControl={languageControl} appearanceControl={appearanceControl} skillProgress={skillProgress} wordsHref={wordsHref} showSavedSentences={!householdEnabled || state.mode === 'adult'} />}
    <div class={activityWorkspace ? 'activity-workspace-content' : undefined}>
    <main id="main" class={location.page==='game'?'game-workspace':undefined} tabIndex={-1}>
      {householdEnabled && state.home && location.page !== 'home' && <div class="learner-bar"><span>{language === 'ru' ? 'Учится' : 'Learning as'} {state.home.profile.display_name}</span><a href="/post/household">{language === 'ru' ? 'Сменить ученика' : 'Change learner'}</a></div>}
      {signedOut && !['home','activities','alphabet','words','first-delivery','first-steps','game','games','shop'].includes(location.page) ? <section class="page"><p class="kicker">Russian Arcade</p><h1 ref={heading} tabIndex={-1}>{language === 'ru' ? 'Кто занимается?' : 'Who’s learning?'}</h1><p>{language === 'ru' ? 'Выберите профиль, чтобы сохранить занятия и продолжить с того же места.' : 'Choose your profile to save your practice and pick up where you left off.'}</p><a class="cta" href="/post/profiles">{language === 'ru' ? 'Выбрать профиль' : 'Choose your profile'}</a></section>
        : state.mode === 'loading' ? <section class="page"><h1 ref={heading} tabIndex={-1}>Opening your activities…</h1><p role="status">Checking your saved learning.</p></section>
        : state.mode === 'error' ? <section class="page"><h1 ref={heading} tabIndex={-1}>Your activities could not open.</h1><p role="alert">{state.error}</p><div class="action-row"><button class="cta" onClick={() => setRefresh(value => value + 1)}>Try again</button>{householdEnabled ? <a href="/post/household">Choose a learner</a> : <a href="#activities">Back to activities</a>}</div></section>
        : location.page === 'game' ? <JourneyGame key={`${profile?.id ?? state.mode}:${location.sessionId ?? location.gameId}`} gameId={location.gameId} sessionId={location.sessionId} profileHref={householdEnabled ? '/post/household' : '/post/profiles'}/>
        : location.page === 'alphabet' ? <Alphabet returnHref={location.alphabetFrom ? `#${location.alphabetFrom}` : '#activities'} returnLabel={location.alphabetFrom === 'first-delivery' ? 'Back to your first words' : location.alphabetFrom === 'first-steps' ? 'First steps' : 'Activities'} />
        : location.page === 'first-steps' ? <FirstSteps key={`${profile?.id ?? state.mode}:${location.firstStepsVersion ?? ''}:${location.lessonId ?? 'overview'}`} lessonId={location.lessonId} version={location.firstStepsVersion} journeyHref={courseHref(progression.data?.course?.release_id ?? defaultCourseRelease,'home')} profileHref={householdEnabled ? '/post/household' : '/post/profiles'} />
        : location.page === 'shop' ? <GameShop key={profile?.id ?? state.mode} profileHref={householdEnabled ? '/post/household' : '/post/profiles'} />
        : location.page === 'games' ? <section class="page activity-entry games-page"><div class="activity-entry-content"><ActivityHeader title={language === 'ru' ? 'Игры' : 'Games'} description={language === 'ru' ? 'Выберите игру. Новые игры можно открыть в магазине.' : 'Choose a game to play. Unlock more in the shop.'} headingRef={heading} headingTabIndex={-1} actions={<a class="text-link" href="#shop">{language === 'ru' ? 'Магазин' : 'Shop'} <span aria-hidden="true">→</span></a>} /><GameCatalogue key={profile?.id ?? state.mode} context="games" /></div></section>
        : location.page === 'first-delivery' ? <><FirstDelivery key={state.home?.profile.id ?? state.mode} next={tutorialNext} courseJourney={courseJourney} onIntroduce={onboarding.introduce} profileHref={householdEnabled ? "/post/household" : "/post/profiles"} />{onboarding.error && <div class="page onboarding-save-note" role="status"><p>{language==='ru' ? 'Не удалось сохранить знакомство с приложением.' : 'Your introduction could not be saved.'} {onboarding.error}</p><button class="text-link" onClick={()=>void onboarding.retry()}>{language==='ru' ? 'Попробовать ещё раз' : 'Try saving again'}</button></div>}</>
        : location.page === 'journey' && location.worldId && !onboarding.state.coins_introduced ? <section class="page"><h1>Your first delivery</h1><p>Meet Barsik and see how your practice helps his journey.</p><a class="cta" href="#first-delivery">Let’s begin</a></section>
        : location.page === 'journey' && (location.coursePracticeId || location.courseSectionId) ? <CoursePreparation key={`${profile?.id ?? state.mode}:${location.courseReleaseId ?? ''}:${location.coursePracticeId ?? location.courseSectionId}`} releaseId={location.courseReleaseId} practiceId={location.coursePracticeId} sectionId={location.courseSectionId} language={language} progression={progression}/>
        : location.page === 'journey' ? location.worldId ? <Journey key={`${profile?.id ?? state.mode}:${location.worldId}`} worldId={location.worldId} language={language} progression={progression} /> : <CourseJourney key={`${profile?.id ?? state.mode}:${location.courseReleaseId ?? ''}:${location.chapterId ?? location.checkpointId ?? 'overview'}`} releaseId={location.courseReleaseId} chapterId={location.chapterId} attemptId={location.checkpointId} language={language} progression={progression} />
        : location.page === 'speaking' ? location.unitExchangeId ? <UnitExchange key={`${profile?.id}:${location.unitExchangeId}`} id={location.unitExchangeId} profileId={profile?.id} language={language} /> : location.speakingMode==='step' && location.sessionId
          ? <StepThroughConversation key={`${state.home?.profile.id}:${location.sessionId}`} sessionId={location.sessionId} language={language} />
          : <LiveConversation key={`${state.home?.profile.id}:${location.sessionId ?? location.scenarioId ?? 'new'}:${location.speakingLevel ?? 'A1'}`} sessionId={location.sessionId} initialScenarioId={location.scenarioId} initialLevel={location.speakingLevel} language={language} />
        : ['conversation','speech-lab'].includes(location.page) ? <Conversation key={`${state.home?.profile.id}:${location.sessionId ?? location.page}`} sessionId={location.sessionId} lab={location.page==='speech-lab'} language={language} />
        : location.page === 'generate' && nativeEnabled ? state.mode === 'personal' || state.mode === 'adult' ? <GenerateCards key={location.sessionId ?? `new:${location.wordId ?? ''}`} batchId={location.sessionId} wordId={location.wordId} language={language} /> : <FlashcardsSetup adult={false} language={language} />
        : ['flashcards','review'].includes(location.page) && !nativeEnabled ? <section class="page"><h1>Flashcard practice is paused.</h1><p>Your saved cards and reviews are kept. Enable native flashcards in the app configuration to continue.</p><a class="text-link" href="#activities">Back to activities</a></section>
        : ['flashcards','review'].includes(location.page) && nativeEnabled ? ['child','personal'].includes(state.mode) && state.home
          ? location.page === 'review' && location.sessionId ? <NativeReview key={`${state.home.profile.id}:${location.sessionId}`} profileId={state.home.profile.id} sessionId={location.sessionId} language={language} personal={!householdEnabled} /> : <Flashcards key={`${state.home.profile.id}:${location.wordId ?? "all"}:${location.lessonId ?? "all"}:${location.topic ?? ''}`} wordId={location.wordId} lessonId={location.lessonId} topic={location.topic} profileId={state.home.profile.id} language={language} personal={!householdEnabled} />
          : <FlashcardsSetup adult={state.mode === 'adult'} language={language} />
        : location.page === 'assessment' && profile ? <AssessmentPilot key={`${profile.id}:${location.sessionId ?? 'overview'}`} sessionId={location.sessionId} profileId={profile.id} language={language} />
        : location.page === 'practice' ? (state.mode === 'child' || state.mode === 'personal') && state.home && location.sessionId ? <Practice language={language} key={`${state.home.profile.id}:${location.sessionId}`} sessionId={location.sessionId} profileId={state.home.profile.id} onFinish={() => { window.location.hash = 'activities'; setRefresh(value => value + 1); }} />
          : <section class="page"><h1 ref={heading} tabIndex={-1}>Choose a profile to continue.</h1><p>Open the profile that started this practice.</p><a class="text-link" href="/post/profiles">Choose a profile</a></section>
        : location.page === 'home' ? <>
          <WelcomeHero key={profile?.id ?? state.mode} courseJourney={courseJourney} headingRef={heading} profileKey={profile?.id} nextDestination={nextChapter ? {title:language==='ru' ? nextChapter.title_ru : nextChapter.title,href:nextChapter.active_attempt_id ? `#journey/checkpoint/${nextChapter.active_attempt_id}` : courseHref(progression.data?.course?.release_id,nextChapter.id)} : undefined} />
          <section class="home-section" aria-labelledby="choose-practice">
            <div>
            <div class="section-heading"><div><h2 id="choose-practice" ref={practiceHeading} tabIndex={-1}>Choose what to practise</h2>{legacy && <p>Read a story, try a game or spend some time with your words.</p>}</div></div>
            {state.home && <div class="practice-learner"><span>{language === 'ru' ? 'Учится' : 'Learning as'} {state.home.profile.display_name}</span><a href="/post/household">{language === 'ru' ? 'Сменить ученика' : 'Change learner'}</a></div>}
            {legacy ? <><div class="home-choices">
              <ActivityLink {...activities[0]} detail={undefined} />
              {nativeEnabled ? <ActivityLink title="Flashcards" description="Generate cards from your vocabulary and study them here." href="#flashcards" mark="Я ↻" /> : <ActivityLink {...activities[1]} detail={undefined} />}
              <ActivityLink title="My words" description="Find a word, explore its meaning or add something new to learn." href="/vocab" mark="Слова" />
            </div><a class="text-link more-activities" href="#activities">All activities <span aria-hidden="true">↗</span></a></> : availableActivities()}
            </div>
            <figure class="home-rest">
              <img src={sleepingBarsik} width="1536" height="1024" loading="lazy" decoding="async" alt={language === 'ru' ? 'Барсик свернулся клубочком и спит рядом со своей почтовой сумкой.' : 'Barsik curled up asleep beside his postbag.'} />
            </figure>
          </section>
        </> : location.page === 'activities' ? <section class="page"><p class="kicker">Learn by doing</p><h1 ref={heading} tabIndex={-1}>Choose an activity.</h1><p class="intro">{legacy ? "Read, write and put your Russian into practice." : "Choose something to practise."}</p>{availableActivities()}
          <ActivityLink title="Russian alphabet" description="Explore the letters and hear them in words." href="#alphabet" mark="Аа" />
          <GameCatalogue key={profile?.id ?? state.mode} context="activities"/>
          {legacy && <aside class="development-note"><h2>Anki Link</h2><p>Prefer to study in Anki? Its existing card generator is available as an optional tool.</p><a class="text-link" href="/tools/anki/">Open existing Anki card tools <span aria-hidden="true">↗</span></a></aside>}
        </section> : <section class="page"><p class="kicker">Your vocabulary</p><h1 ref={heading} tabIndex={-1}>My words</h1>
          {legacy ? <><p class="intro">Find a word, explore its forms or add something new to learn.</p><div class="action-row"><a class="cta" href="/vocab">Open vocabulary library <span aria-hidden="true">↗</span></a><a class="text-link" href="/sentences/saved">{language === 'ru' ? 'Разговорник' : 'Phrasebook'}</a></div><Sheet><h2>Words can come from anywhere.</h2><p>Add them in the app or capture them in Google Drive. Your existing library keeps them together.</p></Sheet></>
            : state.mode === 'locked' ? <Sheet><h2>Choose a learner to see their words.</h2><a class="text-link" href="/post/household">Choose a learner</a></Sheet>
              : <><p>Words linked to your recent practice appear here. A correct answer means you practised a word; remembering it takes revisiting.</p>{state.progress?.evidence.length ? <ul class="word-list">{Array.from(new Map(state.progress.evidence.map(item => [item.word_id, item])).values()).map(item => <li key={item.word_id}><strong lang="ru">{item.lemma}</strong><span>Practised in an activity</span></li>)}</ul> : <Sheet><h2>No word practice saved yet.</h2><p>Start an approved activity with linked vocabulary to see your words here.</p><a class="text-link" href="#activities">Choose an activity</a></Sheet>}
                <p class="quiet section-note">This list shows vocabulary from your recent saved activity answers.</p></>}
        </section>}
    </main>
    <footer class="bottom"><span>Russian Arcade - Tom Bryson 2026</span></footer>
    </div>
    </div>
  </div></GameLanguage.Provider>;
}
