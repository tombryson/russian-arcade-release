import {useEffect,useRef,useState} from 'preact/hooks';
import {api,ApiError} from './learning-api';
import {courseHref,coursePracticeHref,courseEndpoint} from './course-routes';
import type {Language} from './review-types';
import type {ProgressionState} from './Progression';
import './styles/course-journey.css';
import type {TargetCoverage} from './CoursePreparation';

type CourseLink={label:string;label_ru:string;href:string};
type SavedCourseAttempt={id:string;title:string;title_ru:string;status?:string};
type VocabularyChoice={lemma:string;pos:string;label?:string};
type VocabularyResult={needs_choice?:boolean;choices?:VocabularyChoice[];word_id?:number;status?:string;href?:string;flashcards_href?:string;enrichment_pending?:boolean};
export type CourseTopic={id:string;title:string;title_ru:string;completed:boolean;successful_tasks:number;required_tasks:number;links:{activity:string;label:string;label_ru:string;href:string}[]};
type ReferenceGroup={id:string;title:string;title_ru:string;items:{label:string;label_ru:string;ru:string;en:string}[]};
export type CourseChapter={objectives?:{en:string;ru:string}[];preparation?:{topic_id:string;title:string;title_ru:string;explanation:string;explanation_ru:string;examples:{ru:string;en:string}[];groups?:ReferenceGroup[]}[];id:string;number:number;title:string;title_ru:string;intro:string;intro_ru:string;status:'locked'|'practice'|'ready'|'passed';progress:number;topics:CourseTopic[];activity_count:number;required_activity_count:number;last_attempt_id:string|null;active_attempt_id?:string|null;target_coverage?:TargetCoverage;practice_href?:string};
export type CourseData={is_current_release?:boolean;current_release_id?:string;version:string|number;release_id?:string;chapter_count?:number;completed_milestones?:number;profile_id:string;band:string;unlocked_levels:string[];current_chapter_id:string|null;progress:number;completed:boolean;chapters:CourseChapter[];release_upgrade?:{release_id:string;title:string;title_ru:string;retained_access:string[];active_attempts:SavedCourseAttempt[];retained_milestones:number;starting_chapter:string;starting_chapter_title?:string;starting_chapter_title_ru?:string};previous_courses?:{release_id:string;title:string;title_ru:string;attempts:SavedCourseAttempt[]}[]};
export type CourseAttempt={draft_answers?:Record<string,string>;draft_revision?:number;sender?:string;sender_ru?:string;letter_purpose?:string;letter_purpose_ru?:string;consequence?:string;consequence_ru?:string;achieved?:boolean;writing_available?:boolean;flashcards_available?:boolean;vocabulary?:{word:string;context:string}[];release_id?:string;band?:string;chapter_count?:number;glossary?:{ru:string;en:string}[];id:string;chapter_id:string;chapter_number:number;title:string;title_ru:string;letter:string;letter_title:string;letter_title_ru:string;listening:{audio_url:string;transcript?:string};questions:{id:string;prompt:string;prompt_ru:string;choices:{id:string;text:string}[];kind:'reading'|'listening'|'language'|'response';hint?:string;hint_ru?:string}[];status:'active'|'passed'|'retry';support_used:boolean;listened:boolean;result?:{score:number;total:number;passed:boolean;essential_passed?:boolean;component_results?:{kind:string;score:number;total:number;required:number;passed:boolean}[];next_practice?:CourseLink[];vocabulary?:{word:string;context:string}[];writing_available?:boolean;feedback:{question_id:string;correct:boolean;answer:string;selected_answer?:string;explanation:string;explanation_ru:string}[]};course:CourseData};
type Submission={answers:Record<string,string>;submission_id:string};
type Draft={answers:Record<string,string>;pending?:Submission;revision?:number};
const storagePrefix='word-post:checkpoint:';
const chapterArtwork:Record<string,string>={
  home:'barsik-leaving-home-v1.webp',
  postoffice:'barsik-post-office-v1.webp',
  market:'barsik-market-v1.webp',
  leavingtown:'barsik-leaving-town-v1.webp',
};
function ChapterArtwork({releaseId,chapterId}:{releaseId?:string;chapterId:string}) {
  const image=releaseId==='a1-journey-v2' ? chapterArtwork[chapterId] : undefined;
  if(!image) return null;
  return <img class="course-milestone-art" src={`/static/images/${image}`} alt="" width="64" height="64" />;
}
const clamp=(value:number)=>Number.isFinite(value) ? Math.max(0,Math.min(1,value)) : 0;
const draftKey=(profile:string,attempt:string)=>`${storagePrefix}${encodeURIComponent(profile)}:${encodeURIComponent(attempt)}`;
function readDraft(profile:string,attempt:string):Draft {
  try {const saved=JSON.parse(sessionStorage.getItem(draftKey(profile,attempt)) || '{}');return {answers:saved.answers || {},pending:saved.pending,revision:saved.revision};} catch {return {answers:{}};}
}
function writeDraft(profile:string,attempt:string,value?:Draft) {
  try {if (value) sessionStorage.setItem(draftKey(profile,attempt),JSON.stringify(value));else sessionStorage.removeItem(draftKey(profile,attempt));} catch { /* Storage may be disabled; the current page still works. */ }
}
function clearOtherProfiles(profile:string) {
  try {for (let index=sessionStorage.length-1;index>=0;index--) {const key=sessionStorage.key(index);if (key?.startsWith(storagePrefix) && !key.startsWith(`${storagePrefix}${encodeURIComponent(profile)}:`)) sessionStorage.removeItem(key);}} catch { /* Storage is optional. */ }
}

export function CourseJourney({chapterId,attemptId,releaseId,language='en',progression}:{releaseId?:string;chapterId?:string;attemptId?:string;language?:Language;progression:ProgressionState}) {
  const t=(en:string,ru:string)=>language==='ru' ? ru : en;
  const profile=progression.data?.profile_id;
  const selectedRelease=releaseId ?? (attemptId ? undefined : progression.data?.course?.release_id);
  const identity=`${profile ?? ''}:${selectedRelease ?? ''}:${chapterId ?? ''}:${attemptId ?? ''}`;
  const currentIdentity=useRef(identity);currentIdentity.current=identity;
  const loadedIdentity=useRef('');
  const [course,setCourse]=useState<CourseData>();
  const [attempt,setAttempt]=useState<CourseAttempt>();
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const currentAnswers=useRef(answers);currentAnswers.current=answers;
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState('');
  const [revision,setRevision]=useState(0);
  const [letterOpen,setLetterOpen]=useState(false);
  const [questionGroup,setQuestionGroup]=useState('reading');
  const [upgradeOpen,setUpgradeOpen]=useState(false);
  const [selectedWord,setSelectedWord]=useState('');
  const [wordCaptureOpen,setWordCaptureOpen]=useState(false);
  const wordCapture=useRef<HTMLDetailsElement>(null);
  const [vocabularyResults,setVocabularyResults]=useState<Record<string,VocabularyResult>>({});
  const upgradeRequest=useRef<{release:string;request_id:string}>();
  const vocabularyRequests=useRef<Record<string,string>>({});
  const vocabularyChoices=useRef<Record<string,VocabularyChoice>>({});
  const writingRequest=useRef<string>();
  const pending=useRef<Submission>();
  const draftRevision=useRef(0);
  const draftLastSaved=useRef('{}');
  const draftSaving=useRef(false);
  const [draftConflict,setDraftConflict]=useState<{answers:Record<string,string>;revision:number}>();
  const [draftNote,setDraftNote]=useState('');
  const [draftTick,setDraftTick]=useState(0);
  const startRequest=useRef<{chapter:string;release?:string;challenge:boolean;request_id:string}>();
  const inFlight=useRef(false);
  const listeningReceiptPending=useRef(false);
  const recording=useRef<HTMLAudioElement>(null);
  const [audioFailed,setAudioFailed]=useState(false);
  const [recordingCompleted,setRecordingCompleted]=useState(false);
  const resultSummary=useRef<HTMLElement>(null);
  const focusResultOnSave=useRef(false);
  useEffect(()=>{
    currentIdentity.current=identity;
    setAudioFailed(false);setRecordingCompleted(false);
    const abort=new AbortController();draftRevision.current=0;draftLastSaved.current='{}';draftSaving.current=false;setDraftConflict(undefined);setDraftNote('');setLetterOpen(false);setQuestionGroup('reading');setUpgradeOpen(false);setVocabularyResults({});setSelectedWord('');setWordCaptureOpen(false);upgradeRequest.current=undefined;vocabularyRequests.current={};vocabularyChoices.current={};writingRequest.current=undefined;setLoading(true);setCourse(undefined);setAttempt(undefined);setAnswers({});setError('');setBusy('');pending.current=undefined;startRequest.current=undefined;inFlight.current=false;listeningReceiptPending.current=false;focusResultOnSave.current=false;
    if (profile) clearOtherProfiles(profile);
    const load=attemptId ? api<CourseAttempt>(`/api/v1/course/checkpoints/${encodeURIComponent(attemptId)}`,undefined,abort.signal) : api<CourseData>(courseEndpoint(releaseId),undefined,abort.signal);
    void load.then(value=>{
      if (abort.signal.aborted || currentIdentity.current!==identity) return;
      const loaded='course' in value ? value.course : value;
      if (profile && loaded.profile_id!==profile) throw new ApiError(t('The learner changed. Reload your journey.','Профиль изменился. Загрузите путешествие заново.'),'profile_changed');
      clearOtherProfiles(loaded.profile_id);loadedIdentity.current=identity;setCourse(loaded);
      if ('course' in value) {
        setAttempt(value);setLetterOpen(value.status!=='active' || Object.keys(value.draft_answers ?? {}).length>0 || Object.keys(readDraft(loaded.profile_id,value.id).answers).length>0);
        if (value.status==='active') {
          const draft=readDraft(loaded.profile_id,value.id);
          const savedAnswers=Object.keys(draft.answers).length || draft.pending ? draft.answers : value.draft_answers ?? {};
          const remoteRevision=value.draft_revision ?? 0;
          setAnswers(savedAnswers);setQuestionGroup(['reading','listening','language','response'].find(kind=>value.questions.some(question=>question.kind===kind && !savedAnswers[question.id])) ?? 'response');pending.current=draft.pending;draftRevision.current=remoteRevision;draftLastSaved.current=JSON.stringify(value.draft_answers ?? {});
          if(!draft.pending && Object.keys(draft.answers).length && (draft.revision ?? 0)<remoteRevision && JSON.stringify(draft.answers)!==draftLastSaved.current) setDraftConflict({answers:value.draft_answers ?? {},revision:remoteRevision});
        }
        else {setAnswers(Object.fromEntries((value.result?.feedback ?? []).filter(item=>item.selected_answer).map(item=>[item.question_id,item.selected_answer!])));writeDraft(loaded.profile_id,value.id);}
      }
    }).catch(e=>{if (!abort.signal.aborted && currentIdentity.current===identity) setError(e instanceof Error ? e.message : t('Your journey could not load.','Не удалось загрузить путешествие.'));})
      .finally(()=>{if (!abort.signal.aborted && currentIdentity.current===identity) setLoading(false);});
    return ()=>{abort.abort();if(currentIdentity.current===identity)currentIdentity.current='';};
  },[identity,revision]);
  const visibleCourse=loadedIdentity.current===identity && course && (!profile || course.profile_id===profile) ? course : undefined;
  const visibleAttempt=visibleCourse && attempt?.id===attemptId ? attempt : undefined;
  useEffect(()=>{
    if (!focusResultOnSave.current || !visibleAttempt?.result || !resultSummary.current) return;
    focusResultOnSave.current=false;
    resultSummary.current.focus({preventScroll:true});
    resultSummary.current.scrollIntoView?.({block:'start'});
  },[visibleAttempt?.id,visibleAttempt?.status]);
  useEffect(()=>{
    if(!visibleAttempt || visibleAttempt.status!=='active' || visibleAttempt.draft_revision===undefined || pending.current || draftConflict || draftSaving.current) return;
    const encoded=JSON.stringify(answers);
    if(encoded===draftLastSaved.current)return;
    const actor=identity;
    const timer=setTimeout(()=>{
      draftSaving.current=true;let saved=false;
      void api<CourseAttempt>(`/api/v1/course/checkpoints/${encodeURIComponent(visibleAttempt.id)}/draft`,{answers,revision:draftRevision.current}).then(value=>{
        if(currentIdentity.current!==actor)return;
        if(value.course.profile_id!==visibleCourse?.profile_id)throw new ApiError(t('The learner changed. Reload your journey.','Профиль изменился. Загрузите путешествие заново.'),'profile_changed');
        draftRevision.current=value.draft_revision ?? draftRevision.current;draftLastSaved.current=encoded;setDraftNote('');saved=true;if(!pending.current)writeDraft(value.course.profile_id,value.id,{answers:currentAnswers.current,revision:draftRevision.current});
      }).catch(async reason=>{
        if(currentIdentity.current!==actor)return;
        if(reason instanceof ApiError && ['profile_changed','locked','unauthorized','profile_required'].includes(reason.code)){showFailure(reason);return;}
        if(reason instanceof ApiError && ['draft_conflict','conflict','checkpoint_completed'].includes(reason.code)) {
          try {
            const latest=await api<CourseAttempt>(`/api/v1/course/checkpoints/${encodeURIComponent(visibleAttempt.id)}`);
            if(currentIdentity.current!==actor)return;
            if(latest.course.profile_id!==visibleCourse?.profile_id)throw new ApiError(t('The learner changed. Reload your journey.','Профиль изменился. Загрузите путешествие заново.'),'profile_changed');
            if(latest.status!=='active'){setAnswers(Object.fromEntries((latest.result?.feedback ?? []).filter(item=>item.selected_answer).map(item=>[item.question_id,item.selected_answer!])));pending.current=undefined;writeDraft(latest.course.profile_id,latest.id);accept(latest);progression.refresh();return;}
            setDraftConflict({answers:latest.draft_answers ?? {},revision:latest.draft_revision ?? 0});
          }catch(error){if(currentIdentity.current===actor){if(error instanceof ApiError && ['profile_changed','locked','unauthorized'].includes(error.code))showFailure(error);else setDraftNote(failure(error));}}
        } else setDraftNote(t('Answers are kept in this tab. Saving to your account will retry with your next change.','Ответы сохранены в этой вкладке. Повторим сохранение при следующем изменении.'));
      }).finally(()=>{if(currentIdentity.current===actor){draftSaving.current=false;if(saved)setDraftTick(value=>value+1);}});
    },450);
    return()=>clearTimeout(timer);
  },[answers,visibleAttempt?.id,visibleAttempt?.status,draftConflict,draftTick]);
  function resolveDraft(keepLocal:boolean) {
    if(!draftConflict || !visibleAttempt || !visibleCourse)return;
    draftRevision.current=draftConflict.revision;
    draftLastSaved.current=JSON.stringify(draftConflict.answers);
    const selected=keepLocal?{...answers}:draftConflict.answers;
    setAnswers(selected);writeDraft(visibleCourse.profile_id,visibleAttempt.id,{answers:selected,revision:draftRevision.current});setDraftConflict(undefined);
  }
  const offeredVocabulary=visibleAttempt?.vocabulary ?? visibleAttempt?.result?.vocabulary ?? [];
  const captureItem=offeredVocabulary.find(item=>item.word===selectedWord) ?? offeredVocabulary[0];
  const captureSaved=captureItem ? vocabularyResults[captureItem.word] : undefined;
  const receivedLetter=visibleAttempt?.release_id==='a1-journey-v2';
  const groupKinds=['reading','listening','language','response'].filter(kind=>visibleAttempt?.questions.some(question=>question.kind===kind));
  const groupTitle=(kind:string)=>({reading:t('Read the letter','Прочитайте письмо'),listening:t('Listen to the update','Послушайте сообщение'),language:t('Choose the form','Выберите форму'),response:t('Reply to the letter','Ответьте на письмо')}[kind] ?? kind);
  const componentTitle=(kind:string)=>({reading:t('Reading','Чтение'),listening:t('Listening','Аудирование'),language:t('Forms in context','Формы в контексте'),response:t('Reply','Ответ')}[kind] ?? kind);
  const groupedQuestions=receivedLetter && visibleAttempt?.status==='active';
  const shownQuestions=visibleAttempt?.questions.filter(question=>!groupedQuestions || question.kind===questionGroup) ?? [];
  const currentGroupIndex=groupKinds.indexOf(questionGroup);
  const earlierAttempt=!!(visibleAttempt?.release_id && visibleCourse?.release_id && visibleAttempt.release_id!==visibleCourse.release_id);
  const chapter=earlierAttempt ? undefined : visibleCourse?.chapters.find(item=>item.id===(chapterId ?? visibleAttempt?.chapter_id ?? visibleCourse.current_chapter_id));
  const failure=(e:unknown)=>e instanceof Error ? e.message : t('This could not be saved. Please try again.','Не удалось сохранить. Попробуйте ещё раз.');
  function showFailure(e:unknown) {
    if (e instanceof ApiError && ['locked','profile_changed','profile_required','adult_required','unauthorized'].includes(e.code)) {
      if (visibleCourse && visibleAttempt) writeDraft(visibleCourse.profile_id,visibleAttempt.id);
      setCourse(undefined);setAttempt(undefined);setAnswers({});pending.current=undefined;
    }
    setError(failure(e));
  }
  function accept(value:CourseAttempt) {
    if (value.course.profile_id!==visibleCourse?.profile_id) throw new ApiError(t('The learner changed. Reload your journey.','Профиль изменился. Загрузите путешествие заново.'),'profile_changed');
    setAttempt(value);setCourse(value.course);
  }
  async function hydrateReceipt(value:CourseAttempt,immutableReceipt=false) {
    if (value.course.profile_id!==visibleCourse?.profile_id) throw new ApiError(t('The learner changed. Reload your journey.','Профиль изменился. Загрузите путешествие заново.'),'profile_changed');
    // Saved command receipts are immutable, including ones written before
    // releases existed. Read today's routing without rewriting that receipt.
    // Both the receipt and an open page can name an old release. Start and
    // answer commands therefore always read the canonical saved assessment.
    if (immutableReceipt || !value.release_id || !value.course.release_id || value.course.release_id!==visibleCourse.release_id) {
      return api<CourseAttempt>(`/api/v1/course/checkpoints/${encodeURIComponent(value.id)}`);
    }
    return value;
  }
  async function start(selected:CourseChapter,challenge=false) {
    if (inFlight.current || !visibleCourse || visibleCourse.is_current_release===false) return;
    const owner=identity;inFlight.current=true;setBusy('start');setError('');
    if (startRequest.current?.chapter!==selected.id || startRequest.current.challenge!==challenge || startRequest.current.release!==visibleCourse.release_id) startRequest.current={chapter:selected.id,release:visibleCourse.release_id,challenge,request_id:crypto.randomUUID()};
    try {
      let value=await api<CourseAttempt>(`/api/v1/course/chapters/${encodeURIComponent(selected.id)}/checkpoint`,{request_id:startRequest.current.request_id,...(visibleCourse.release_id ? {release_id:visibleCourse.release_id} : {}),...(challenge ? {challenge:true} : {})});
      if (currentIdentity.current!==owner) return;
      value=await hydrateReceipt(value,true);
      if (currentIdentity.current!==owner) return;
      accept(value);progression.refresh();window.location.hash=`journey/checkpoint/${encodeURIComponent(value.id)}`;
    } catch(e) {if (currentIdentity.current===owner) showFailure(e);}
    finally {if (currentIdentity.current===owner) {inFlight.current=false;setBusy('');}}
  }
  async function checkpointAction(action:'answer'|'support'|'listened',body:unknown) {
    if (!visibleAttempt || inFlight.current || !visibleCourse) return;
    const owner=identity;inFlight.current=true;setBusy(action);setError('');
    if (action==='listened') listeningReceiptPending.current=false;
    try {
      let value=await api<CourseAttempt>(`/api/v1/course/checkpoints/${encodeURIComponent(visibleAttempt.id)}/${action}`,body);
      if (currentIdentity.current!==owner) return;
      value=await hydrateReceipt(value,action==='answer');
      if (currentIdentity.current!==owner) return;
      if (action==='answer' && visibleAttempt.status==='active' && value.status!=='active') focusResultOnSave.current=true;
      accept(value);
      if (value.status!=='active') {pending.current=undefined;writeDraft(value.course.profile_id,value.id);progression.refresh();}
    } catch(e) {if (currentIdentity.current===owner) showFailure(e);}
    finally {if (currentIdentity.current===owner) {inFlight.current=false;setBusy('');if (action!=='listened' && listeningReceiptPending.current) void checkpointAction('listened',{});}}
  }
  async function retryAudio() {
    const player=recording.current;
    if (!player) return;
    const owner=identity;setAudioFailed(false);
    try {player.load();await player.play();}
    catch {if(currentIdentity.current===owner && recording.current===player) setAudioFailed(true);}
  }
  async function switchRelease() {
    const upgrade=visibleCourse?.release_upgrade;
    if (!visibleCourse || !upgrade || inFlight.current) return;
    const owner=identity;inFlight.current=true;setBusy('switch');setError('');
    if (upgradeRequest.current?.release!==upgrade.release_id) upgradeRequest.current={release:upgrade.release_id,request_id:crypto.randomUUID()};
    try {
      const value=await api<CourseData>(`/api/v1/course/releases/${encodeURIComponent(upgrade.release_id)}/switch`,{request_id:upgradeRequest.current.request_id,from_release_id:visibleCourse.release_id});
      if(currentIdentity.current!==owner) return;
      if(value.profile_id!==visibleCourse.profile_id) throw new ApiError(t('The learner changed. Reload your journey.','Профиль изменился. Загрузите путешествие заново.'),'profile_changed');
      setCourse(value);setUpgradeOpen(false);upgradeRequest.current=undefined;progression.refresh();
    } catch(e) {if(currentIdentity.current===owner) showFailure(e);}
    finally {if(currentIdentity.current===owner){inFlight.current=false;setBusy('');}}
  }
  async function saveVocabulary(word:string,choice?:VocabularyChoice) {
    if(!visibleAttempt || visibleAttempt.status==='active' || inFlight.current) return;
    const owner=identity;inFlight.current=true;setBusy(`word:${word}`);setError('');
    if(choice)vocabularyChoices.current[word]=choice;
    choice ??= vocabularyChoices.current[word];
    const key=`${word}:${choice?.lemma ?? ''}:${choice?.pos ?? ''}`;
    vocabularyRequests.current[key] ??= crypto.randomUUID();
    try {
      const value=await api<VocabularyResult>(`/api/v1/course/checkpoints/${encodeURIComponent(visibleAttempt.id)}/vocabulary`,{word,request_id:vocabularyRequests.current[key],...(choice?{lemma:choice.lemma,pos:choice.pos}:{})});
      if(currentIdentity.current===owner) {setVocabularyResults(current=>({...current,[word]:value}));delete vocabularyRequests.current[key];}
    } catch(e) {if(currentIdentity.current===owner) showFailure(e);}
    finally {if(currentIdentity.current===owner){inFlight.current=false;setBusy('');}}
  }
  async function startWriting() {
    if(!visibleAttempt || visibleAttempt.status==='active' || inFlight.current) return;
    const owner=identity;inFlight.current=true;setBusy('writing');setError('');writingRequest.current ??= crypto.randomUUID();
    try {
      const value=await api<{href:string}>(`/api/v1/course/checkpoints/${encodeURIComponent(visibleAttempt.id)}/writing`,{request_id:writingRequest.current});
      if(currentIdentity.current===owner && value.href.startsWith('/writing/')) window.location.assign(value.href);
    } catch(e) {if(currentIdentity.current===owner) showFailure(e);}
    finally {if(currentIdentity.current===owner){inFlight.current=false;setBusy('');}}
  }
  async function createCards() {
    if(!visibleAttempt || visibleAttempt.status==='active' || inFlight.current) return;
    const owner=identity;inFlight.current=true;setBusy('cards');setError('');
    try {
      const value=await api<{id:string}>(`/api/v1/course/checkpoints/${encodeURIComponent(visibleAttempt.id)}/flashcards`,{});
      if(currentIdentity.current===owner) window.location.hash=`generate/${encodeURIComponent(value.id)}`;
    } catch(e) {if(currentIdentity.current===owner) showFailure(e);}
    finally {if(currentIdentity.current===owner){inFlight.current=false;setBusy('');}}
  }
  function selectWord(word:string) {
    setSelectedWord(word);setWordCaptureOpen(true);
    requestAnimationFrame(()=>wordCapture.current?.scrollIntoView({block:'nearest'}));
  }
  function choose(question:string,choice:string) {
    if (!visibleAttempt || !visibleCourse || pending.current || visibleAttempt.status!=='active') return;
    const next={...answers,[question]:choice};setAnswers(next);writeDraft(visibleCourse.profile_id,visibleAttempt.id,{answers:next,revision:draftRevision.current});
  }
  function submit() {
    if (!visibleAttempt || !visibleCourse || inFlight.current || draftConflict) return;
    if (!pending.current) pending.current={answers:{...answers},submission_id:crypto.randomUUID()};
    writeDraft(visibleCourse.profile_id,visibleAttempt.id,{answers,pending:pending.current,revision:draftRevision.current});
    void checkpointAction('answer',pending.current);
  }
  const stateText=(status:CourseChapter['status'])=>status==='passed' ? t('Passed','Пройдено') : status==='ready' ? t('Checkpoint ready','Можно пройти проверку') : status==='locked' ? t('Coming next','Впереди') : t('In practice','Практика');
  const position=(number:number,total=visibleCourse?.chapter_count ?? visibleCourse?.chapters.length ?? 4)=>t(`Milestone ${number} of ${total}`,`Этап ${number} из ${total}`);
  const milestoneCount=visibleCourse?.completed_milestones ?? visibleCourse?.chapters.filter(item=>item.status==='passed').length ?? 0;
  function topicList(selected:CourseChapter) {
    const targeted=visibleCourse?.release_id==='a1-journey-v2';
    return <ul class="course-topics">{selected.topics.map(topic=><li key={topic.id}>
      <div class="course-topic-heading"><h3>{t(topic.title,topic.title_ru)}</h3><span class="quiet" hidden={targeted}>{topic.completed ? t('✓ Practised','✓ Практика завершена') : t(`${topic.successful_tasks}/${topic.required_tasks} successful tasks`,`${topic.successful_tasks}/${topic.required_tasks} успешных заданий`)}</span></div>
      <div class="course-practice-links">{topic.links.map(link=><a key={`${topic.id}:${link.activity}`} href={link.href}>{t(link.label,link.label_ru)} →</a>)}</div>
      {selected.preparation?.filter(item=>item.topic_id===topic.id).map(item=><details class="course-preparation" key={item.topic_id} open={!targeted}>
        <summary>{t('Notes and examples','Пояснения и примеры')}</summary>
        {item.groups?.length ? <div class="course-reference-groups">{item.groups.map(group=><section class="course-reference-group" key={group.id}>
          <h4>{t(group.title,group.title_ru)}</h4>
          <dl>{group.items.map(example=><div key={`${example.label}:${example.ru}`}>
            <dt>{t(example.label,example.label_ru)}</dt>
            <dd><span lang="ru">{example.ru}</span><span lang="en">{example.en}</span></dd>
          </div>)}</dl>
        </section>)}</div> : <dl>{item.examples.map(example=><div key={example.ru}><dt lang="ru">{example.ru}</dt><dd lang="en">{example.en}</dd></div>)}</dl>}
      </details>)}
    </li>)}</ul>;
  }
  function chapterAction(selected:CourseChapter) {
    if (selected.status==='locked') return <p class="quiet">{t('Pass the previous milestone to continue. You can practise any time.','Пройдите предыдущий этап. Практика доступна в любое время.')}</p>;
    if (selected.status==='passed') return <>{selected.last_attempt_id && <a class="text-link" href={`#journey/checkpoint/${encodeURIComponent(selected.last_attempt_id)}`}>{t('View checkpoint result','Посмотреть результат проверки')} →</a>}</>;
    if(visibleCourse?.is_current_release===false)return <div class="course-checkpoint-entry">{selected.active_attempt_id && <a class="cta" href={`#journey/checkpoint/${encodeURIComponent(selected.active_attempt_id)}`}>{t('Continue saved checkpoint','Продолжить сохранённую проверку')} →</a>}<a class="text-link" href="#journey">{t('Return to your current journey','Вернуться к текущему путешествию')}</a></div>;
    return <div class="course-checkpoint-entry">
      {selected.status==='ready' ? <button class="cta" disabled={!!busy} onClick={()=>void start(selected)}>{busy==='start' ? t('Opening…','Открываем…') : t('Start checkpoint','Начать проверку')} →</button> : <button class="text-link" disabled={!!busy} onClick={()=>void start(selected,true)}>{busy==='start' ? t('Opening…','Открываем…') : t('Test out of this milestone','Пройти этап без подготовки')} →</button>}
      {selected.last_attempt_id && <a class="text-link" href={`#journey/checkpoint/${encodeURIComponent(selected.last_attempt_id)}`}>{t('Open saved checkpoint','Открыть сохранённую проверку')}</a>}
    </div>;
  }
  return <section class={`page course-page${attemptId ? ' is-checkpoint' : chapterId ? ' is-milestone' : ''}`}>
    <nav class="course-navigation" aria-label={t('Journey navigation','Навигация по путешествию')}><a class="text-link" href={attemptId ? (earlierAttempt ? '#journey' : courseHref(visibleAttempt?.release_id ?? releaseId,visibleAttempt?.chapter_id)) : chapterId ? courseHref(visibleCourse?.release_id ?? releaseId) : '#activities'}>← {attemptId ? (earlierAttempt ? t('Your journey','Ваше путешествие') : t('Milestone practice','Практика этапа')) : chapterId ? t('Your journey','Ваше путешествие') : t('All activities','Все занятия')}</a><a class="text-link" href="/curriculum">{t('Curriculum','Учебная программа')}</a></nav>
    {loading && <p role="status">{t('Opening your journey…','Открываем ваше путешествие…')}</p>}
    {error && <div class="course-error"><p class="error-note" role="alert">{error}</p>{!visibleCourse && <button class="live-mute" onClick={()=>setRevision(value=>value+1)}>{t('Try again','Попробовать ещё раз')}</button>}</div>}
    {!loading && visibleCourse && (attemptId ? visibleAttempt && <>
      <header class="course-heading"><p class="kicker">{visibleAttempt.band ?? visibleCourse.band} · {position(visibleAttempt.chapter_number,visibleAttempt.chapter_count)} · {receivedLetter ? t('A letter for Barsik','Письмо Барсику') : t('Checkpoint','Проверка')}</p><h1>{t(visibleAttempt.title,visibleAttempt.title_ru)}</h1>{visibleAttempt.letter_purpose ? <p>{t(visibleAttempt.letter_purpose,visibleAttempt.letter_purpose_ru ?? visibleAttempt.letter_purpose)}</p> : <p class="quiet">{t('Read the message, listen to the short recording, then answer.','Прочитайте сообщение, послушайте короткую запись и ответьте.')}</p>}</header>
      {earlierAttempt && <p class="quiet course-edition-note">{t('This saved assessment belongs to an earlier course. Your current journey is kept separately.','Эта сохранённая проверка относится к прежнему курсу. Прогресс текущего путешествия хранится отдельно.')}</p>}
      <div class="course-checkpoint-layout">
        <article id="course-letter" class={`course-letter${receivedLetter && !letterOpen ? ' is-sealed' : ''}`} aria-label={t(visibleAttempt.letter_title,visibleAttempt.letter_title_ru)}>
          <div class="course-letter-mark" aria-hidden="true"><span>✉</span><img src="/static/images/barsik-running-v1.webp" alt="" width="74" height="55" /></div>
          {visibleAttempt.sender && <p class="course-sender">{t('From','От')} <strong>{t(visibleAttempt.sender,visibleAttempt.sender_ru ?? visibleAttempt.sender)}</strong><span>{t('To Barsik','Барсику')}</span></p>}
          <p class="kicker">{t(visibleAttempt.letter_title,visibleAttempt.letter_title_ru)}</p>
          {receivedLetter && !letterOpen ? <button class="cta" onClick={()=>setLetterOpen(true)}>{t('Read the letter','Прочитать письмо')} →</button> : <>
            <div class="course-letter-text" lang="ru">{visibleAttempt.status!=='active' && offeredVocabulary.length ? visibleAttempt.letter.split(/([А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*)/).map((part,index)=>offeredVocabulary.some(item=>item.word===part) ? <button type="button" class="course-letter-word" key={index} onClick={()=>selectWord(part)} aria-label={t(`Keep ${part}`,`Сохранить ${part}`)}>{part}</button> : part) : visibleAttempt.letter}</div>
            {!!visibleAttempt.glossary?.length && <details class="course-glossary"><summary>{t('Useful words','Полезные слова')}</summary><dl>{visibleAttempt.glossary.map(word=><div key={word.ru}><dt lang="ru">{word.ru}</dt><dd>{word.en}</dd></div>)}</dl></details>}
            {receivedLetter && visibleAttempt.status==='active' && <a class="course-mobile-letter text-link" href="#course-question-groups" onClick={event=>{event.preventDefault();document.getElementById('course-question-groups')?.scrollIntoView({block:'start'});}}>{t('Answer the questions','Ответить на вопросы')} ↓</a>}
          </>}
          <p class="course-letter-signoff" aria-hidden="true">ПОЧТА · {visibleAttempt.chapter_number.toString().padStart(2,'0')}</p>
        </article>
        {(!receivedLetter || letterOpen) && <form class="course-questions" onSubmit={event=>{event.preventDefault();submit();}}>
          {draftConflict && <div class="course-draft-conflict" role="alert"><p>{t('These answers changed in another tab or device. Choose which draft to keep.','Ответы изменились в другой вкладке или на другом устройстве. Выберите, какие сохранить.')}</p><button type="button" class="live-mute" onClick={()=>resolveDraft(false)}>{t('Use saved answers','Использовать сохранённые ответы')}</button><button type="button" class="live-mute" onClick={()=>resolveDraft(true)}>{t('Keep these answers','Оставить эти ответы')}</button></div>}
          {draftNote && <p class="quiet" role="status">{draftNote}</p>}
          {groupedQuestions && <nav id="course-question-groups" class="course-question-groups" aria-label={t('Assessment sections','Разделы проверки')}>
            {groupKinds.map(kind=><button key={kind} type="button" aria-current={questionGroup===kind?'step':undefined} onClick={()=>setQuestionGroup(kind)}>{groupTitle(kind)} <span>{visibleAttempt.questions.filter(question=>question.kind===kind && answers[question.id]).length}/{visibleAttempt.questions.filter(question=>question.kind===kind).length}</span></button>)}
          </nav>}
          {receivedLetter && <a class="course-mobile-letter text-link" href="#course-letter" onClick={event=>{event.preventDefault();document.getElementById('course-letter')?.scrollIntoView({block:'start'});}}>{t('Refer to the letter','Вернуться к письму')} ↑</a>}
          {shownQuestions.map(question=>{
            const index=visibleAttempt.questions.findIndex(item=>item.id===question.id);
            const correction=visibleAttempt.result?.feedback.find(item=>item.question_id===question.id);
            const showAudio=question.kind==='listening' && visibleAttempt.questions.find(item=>item.kind==='listening')?.id===question.id;
            return <div class="course-question" key={question.id}>
              {showAudio && <section class="course-listening" aria-label={t('Listening recording','Аудиозапись')}><h2>{t('Listen to the message','Послушайте сообщение')}</h2><audio ref={recording} aria-label={t('Checkpoint recording','Запись для проверки')} controls preload="none" src={visibleAttempt.listening.audio_url} onError={()=>{if(currentIdentity.current===identity) setAudioFailed(true);}} onPlaying={()=>{if(currentIdentity.current===identity) setAudioFailed(false);}} onEnded={()=>{if (currentIdentity.current===identity && !visibleAttempt.listened && visibleAttempt.status==='active') {setRecordingCompleted(true);listeningReceiptPending.current=true;void checkpointAction('listened',{});}}} />
                {audioFailed && <div role="status"><p>{t('The recording couldn’t play. Try again, or read the transcript for a practice attempt.','Не удалось воспроизвести запись. Попробуйте снова или откройте текст для тренировочной попытки.')}</p><button type="button" class="text-button" onClick={()=>void retryAudio()}>{t('Retry audio','Повторить воспроизведение')}</button></div>}
                <p class="quiet">{visibleAttempt.listening.transcript ? t('Transcript support is on. You can finish this as practice.','Вы открыли текст записи. Можно завершить тренировочную попытку.') : visibleAttempt.listened ? t('✓ Recording heard. You can replay it.','✓ Запись прослушана. Можно включить её снова.') : recordingCompleted ? busy ? t('Saving listening progress…','Сохраняем прослушивание…') : t('You’ve heard the recording. Retry saving to continue.','Вы прослушали запись. Повторите сохранение, чтобы продолжить.') : !audioFailed ? t('Listen to the full recording before submitting.','Послушайте запись до конца перед отправкой.') : null}</p>
                {recordingCompleted && !visibleAttempt.listened && visibleAttempt.status==='active' && !visibleAttempt.listening.transcript && <button type="button" class="text-button" disabled={!!busy || !!pending.current} onClick={()=>void checkpointAction('listened',{})}>{t('Retry saving listening','Повторить сохранение прослушивания')}</button>}
                {visibleAttempt.listening.transcript ? <p class="course-support" lang="ru">{visibleAttempt.listening.transcript}</p> : <button type="button" class="text-button" disabled={!!busy || !!pending.current || visibleAttempt.status!=='active'} onClick={()=>void checkpointAction('support',{kind:'transcript'})}>{t('Read transcript · practice only','Читать текст записи · с поддержкой')}</button>}
              </section>}
              <fieldset disabled={!!busy || !!pending.current || visibleAttempt.status!=='active'}><legend><span>{index+1}.</span> {t(question.prompt,question.prompt_ru)}</legend><div class="course-choices">{question.choices.map(choice=><label class={`course-choice${answers[question.id]===choice.id ? ' is-selected' : ''}`} key={choice.id}><input type="radio" name={`course-${visibleAttempt.id}-${question.id}`} value={choice.id} checked={answers[question.id]===choice.id} onChange={()=>choose(question.id,choice.id)} /><span lang="ru">{choice.text}</span></label>)}</div></fieldset>
              {visibleAttempt.status==='active' && (question.hint ? <p class="course-support">{t(question.hint,question.hint_ru || question.hint)}</p> : <button class="text-button" type="button" disabled={!!busy || !!pending.current} onClick={()=>void checkpointAction('support',{kind:'hint',question_id:question.id})}>{t('Get a hint · practice only','Подсказка · с поддержкой')}</button>)}
              {correction && <div class={`course-correction${correction.correct ? ' is-correct' : ''}`}><strong>{correction.correct ? t('✓ Correct','✓ Верно') : t('Try this answer:','Верный ответ:')} {!correction.correct && <span lang="ru">{question.choices.find(choice=>choice.id===correction.answer)?.text}</span>}</strong><p>{t(correction.explanation,correction.explanation_ru)}</p></div>}
            </div>;
          })}
          {groupedQuestions && <div class="course-group-actions">{currentGroupIndex>0 && <button type="button" class="text-button" onClick={()=>setQuestionGroup(groupKinds[currentGroupIndex-1])}>← {groupTitle(groupKinds[currentGroupIndex-1])}</button>}{currentGroupIndex<groupKinds.length-1 && <button type="button" class="cta" onClick={()=>setQuestionGroup(groupKinds[currentGroupIndex+1])}>{groupTitle(groupKinds[currentGroupIndex+1])} →</button>}</div>}
          {visibleAttempt.status==='active' ? <div class="course-submit"><p class="quiet">{visibleAttempt.support_used ? t('Support used: this is a practice attempt. Try a fresh checkpoint without support to pass.','Вы использовали поддержку: это тренировочная попытка. Чтобы пройти главу, повторите проверку без подсказок.') : t('Hints and the transcript are always available. Using either makes this a practice attempt.','Подсказки и текст записи доступны всегда. С ними попытка становится тренировочной.')}</p><button class="cta" type="submit" hidden={groupedQuestions && currentGroupIndex<groupKinds.length-1} disabled={!!busy || !!draftConflict || !(visibleAttempt.listened || visibleAttempt.listening.transcript) || !visibleAttempt.questions.every(question=>answers[question.id])}>{busy==='answer' ? t('Saving answers…','Сохраняем ответы…') : pending.current ? t('Retry saving answers','Повторить сохранение ответов') : t('Check my answers','Проверить ответы')}</button>{pending.current && !busy && <p class="quiet">{t('Your selected answers are held while saving is retried.','Ваши ответы сохранены для повторной отправки.')}</p>}</div> : visibleAttempt.result && <section class="course-result" ref={resultSummary} tabIndex={-1} aria-label={t('Checkpoint result','Результат проверки')} aria-live="polite"><p class="kicker">{visibleAttempt.result.score}/{visibleAttempt.result.total} {t('correct','верно')}</p><h2>{visibleAttempt.result.passed ? receivedLetter && visibleAttempt.chapter_number===visibleAttempt.chapter_count ? t(`${visibleAttempt.band ?? 'A1'} course complete`,`Курс ${visibleAttempt.band ?? 'A1'} пройден`) : t('Milestone passed','Этап пройден') : t('A little more practice','Ещё немного практики')}</h2><p>{visibleAttempt.result.passed ? t('Your progress is saved. You’re ready for the next part of the journey.','Прогресс сохранён. Можно продолжать путешествие.') : visibleAttempt.support_used ? t('Good practice with support. To pass, try a fresh version without hints or the transcript.','Вы потренировались с поддержкой. Чтобы пройти главу, попробуйте новый вариант без подсказок и текста записи.') : visibleAttempt.result.essential_passed===false ? t('One key detail needs another look. Review the corrections and try again.','Ещё одна важная деталь требует внимания. Посмотрите исправления и попробуйте снова.') : t('Review the corrections above, practise the topics, and try a different message.','Посмотрите исправления, потренируйте темы и попробуйте другое сообщение.')}</p>{receivedLetter && !earlierAttempt && visibleAttempt.result.passed && <p class="course-permanent-progress">{t(`${visibleAttempt.band ?? visibleCourse.band} · ${milestoneCount} of ${visibleCourse.chapter_count ?? visibleCourse.chapters.length} milestones complete`,`${visibleAttempt.band ?? visibleCourse.band} · Пройдено этапов: ${milestoneCount} из ${visibleCourse.chapter_count ?? visibleCourse.chapters.length}`)}</p>}
          {visibleAttempt.consequence && visibleAttempt.result.passed && <p class="course-consequence">{t(visibleAttempt.consequence,visibleAttempt.consequence_ru ?? visibleAttempt.consequence)}</p>}
          {!!visibleAttempt.result.component_results?.length && <ul class="course-result-components">{visibleAttempt.result.component_results.map(component=><li key={component.kind}><span>{componentTitle(component.kind)}</span><strong>{component.score}/{component.total}</strong>{!component.passed && <span>{t(`Needs ${component.required}`,`Нужно ${component.required}`)}</span>}</li>)}</ul>}
          {!!visibleAttempt.result.next_practice?.length && <div class="course-next-practice"><h3>{t('What to practise next','Что повторить')}</h3>{visibleAttempt.result.next_practice.map(link=><a key={link.href} href={link.href}>{t(link.label,link.label_ru)} →</a>)}</div>}
          <div class="course-result-actions">{visibleAttempt.result.passed ? <a class="cta" href={visibleCourse.completed ? '/curriculum#level-A2' : '#journey'}>{visibleCourse.completed ? t('Explore A2 practice','Перейти к практике A2') : t('Continue the journey','Продолжить путешествие')} →</a> : chapter && <button type="button" class="cta" disabled={!!busy} onClick={()=>void start(chapter,chapter.status==='practice')}>{busy==='start' ? t('Opening…','Открываем…') : t('Try a different checkpoint','Попробовать другую проверку')} →</button>}{!earlierAttempt && <a class="text-link" href={courseHref(visibleAttempt.release_id ?? visibleCourse.release_id,visibleAttempt.chapter_id)}>{t('Practise this milestone','Практика этого этапа')}</a>}</div>
          {(visibleAttempt.writing_available || visibleAttempt.result.writing_available) && <button type="button" class="text-button" disabled={!!busy} onClick={()=>void startWriting()}>{busy==='writing' ? t('Opening writing…','Открываем задание…') : t('Write your own reply','Написать свой ответ')} →</button>}
          {visibleAttempt.flashcards_available && <button type="button" class="text-button" disabled={!!busy} onClick={()=>void createCards()}>{busy==='cards' ? t('Preparing cards…','Готовим карточки…') : t('Create flashcards from this letter','Создать карточки по письму')} →</button>}
          {!!offeredVocabulary.length && captureItem && <details ref={wordCapture} class="course-word-capture" open={wordCaptureOpen} onToggle={event=>setWordCaptureOpen(event.currentTarget.open)}><summary>{t('Keep words from this letter','Сохранить слова из письма')}</summary>
            <label class="course-word-picker">{t('Word','Слово')}<select value={captureItem.word} onChange={event=>setSelectedWord(event.currentTarget.value)}>{offeredVocabulary.map(item=><option key={item.word} value={item.word}>{item.word}</option>)}</select></label>
            <p class="course-capture-context" lang="ru">{captureItem.context.split(/(?<=[.!?])\s+/).find(sentence=>sentence.includes(captureItem.word)) ?? captureItem.context}</p>
            {captureSaved?.word_id ? <p>{captureSaved.href ? <a href={captureSaved.href}>{t('Saved in My words','Сохранено в «Мои слова»')}</a> : t('Saved in My words','Сохранено в «Мои слова»')}{captureSaved.flashcards_href && <> · <a href={captureSaved.flashcards_href}>{t('Create cards','Создать карточки')}</a></>}{captureSaved.enrichment_pending && <small>{t('Word saved. Details could not be prepared.','Слово сохранено. Не удалось подготовить сведения.')} <button type="button" class="text-button" disabled={!!busy} onClick={()=>void saveVocabulary(captureItem.word)}>{busy===`word:${captureItem.word}` ? t('Retrying…','Повторяем…') : t('Retry details','Повторить подготовку')}</button></small>}</p> : captureSaved?.needs_choice ? <fieldset><legend>{t('Which word is used here?','Какое слово здесь используется?')}</legend>{captureSaved.choices?.map(choice=><button type="button" class="live-mute" key={`${choice.lemma}:${choice.pos}`} disabled={!!busy} onClick={()=>void saveVocabulary(captureItem.word,choice)}>{choice.label ?? `${choice.lemma} · ${choice.pos}`}</button>)}</fieldset> : <button type="button" class="text-button" disabled={!!busy} onClick={()=>void saveVocabulary(captureItem.word)}>{busy===`word:${captureItem.word}` ? t('Saving…','Сохраняем…') : t('Add word','Добавить слово')}</button>}
          </details>}
          </section>}
        </form>}
      </div>
    </> : chapterId ? chapter?.status==='locked' ? <section class="course-locked-destination" aria-label={t(`Milestone ${chapter.number}, locked`,`Этап ${chapter.number}, пока недоступен`)}><h1>{chapter.number}</h1>{chapterAction(chapter)}</section> : chapter ? <>
      <header class="course-heading course-milestone-header">
        <div class="course-milestone-title-row">
          <div class="course-milestone-heading">
            <ChapterArtwork releaseId={visibleCourse.release_id} chapterId={chapter.id} />
            <div><p class="kicker">{visibleCourse.band} · {position(chapter.number)}</p><h1>{t(chapter.title,chapter.title_ru)}</h1></div>
          </div>
          <div class="course-milestone-progress">
            <span>{stateText(chapter.status)}</span>
            <div class="course-chapter-progress"><progress max={1} value={clamp(chapter.progress)} aria-label={t('Checkpoint preparation','Подготовка к проверке')} /><span>{Math.round(clamp(chapter.progress)*100)}%</span></div>
          </div>
        </div>
        <p>{t(chapter.intro,chapter.intro_ru)}</p>
      </header>
      <div class="course-milestone-actions">
        {visibleCourse.is_current_release!==false && visibleCourse.release_id==='a1-journey-v2' && <a class={chapter.status==='ready' ? 'text-link' : 'cta'} href={chapter.practice_href ?? coursePracticeHref(visibleCourse.release_id,chapter.id)}>{t('Practise these skills','Практика по теме')} →</a>}
        {chapterAction(chapter)}
      </div>
      <h2 class="course-section-title">{visibleCourse.release_id==='a1-journey-v2' ? t('More practice by topic','Дополнительная практика по темам') : t('Practise the milestone','Практика этапа')}</h2>
      {topicList(chapter)}
      {chapter.target_coverage && <details class="course-target-coverage"><summary>{t(`Focused practice · ${chapter.target_coverage.prepared_count}/${chapter.target_coverage.required_count}`,`Практика по навыкам · ${chapter.target_coverage.prepared_count}/${chapter.target_coverage.required_count}`)}</summary><ul>{chapter.target_coverage.targets.filter(target=>target.required).map(target=><li key={target.id}><span>{t(target.title,target.title_ru)}</span><span>{target.demonstrated ? t('Demonstrated','Подтверждено') : target.practised ? t('Practised','Отработано') : target.introduced ? t('Introduced','Изучено') : t('To practise','Нужна практика')}</span></li>)}</ul><p>{t('Prepare through activities or these focused exercises. Suggested activity practice: two successful tasks per topic across two activities. You can try the checkpoint at any time.','Готовьтесь в обычных занятиях или с помощью этих упражнений. Рекомендуем два успешных задания по каждой теме в двух видах занятий. Проверку можно пройти в любое время.')}</p><ul>{chapter.topics.map(topic=><li key={topic.id}><span>{t(topic.title,topic.title_ru)}</span><span>{topic.successful_tasks}/{topic.required_tasks}</span></li>)}</ul><p>{chapter.activity_count}/{chapter.required_activity_count} {t('activities used','видов занятий использовано')}</p></details>}
      {visibleCourse.release_id!=='a1-journey-v2' && <details class="course-target-coverage"><summary>{t('Milestone progress','Прогресс этапа')}</summary>
        {!!chapter.objectives?.length && <ul class="course-objectives">{chapter.objectives.map(item=><li key={item.en}>{t(item.en,item.ru)}</li>)}</ul>}
        <p class="quiet course-readiness">{t('Complete two successful tasks for each topic, using at least two activities.','Выполните два успешных задания по каждой теме, используя как минимум два вида занятий.')} {chapter.activity_count}/{chapter.required_activity_count} {t('activities used','видов занятий использовано')}.{chapter.topics.every(topic=>topic.completed) && chapter.activity_count<chapter.required_activity_count && <> {t('Try another activity, such as Writing or Speaking, to finish preparing.','Попробуйте другой вид занятий, например письмо или разговор, чтобы завершить подготовку.')}</>}</p>
      </details>}
    </> : <p role="alert">{t('This chapter could not be found.','Глава не найдена.')}</p> : <>
      <header class="course-heading course-overview-heading"><div><h1>{visibleCourse.completed ? t(`${visibleCourse.band} course complete`,`Курс ${visibleCourse.band} пройден`) : t('Your journey','Ваше путешествие')}</h1><p>{t(`${visibleCourse.band} · ${milestoneCount} of ${visibleCourse.chapters.length} milestones complete`,`${visibleCourse.band} · Пройдено этапов: ${milestoneCount} из ${visibleCourse.chapters.length}`)}</p></div><img src="/static/images/barsik-running-v1.webp" alt="" width="110" height="81" /></header>
      {visibleCourse.completed && <a class="cta" href="/curriculum#level-A2">{t('Explore A2 practice','Перейти к практике A2')} →</a>}
      {visibleCourse.release_upgrade && <details class="course-upgrade" open={upgradeOpen} onToggle={event=>setUpgradeOpen(event.currentTarget.open)}><summary>{t('Updated journey available','Доступно обновлённое путешествие')}</summary><p>{t(visibleCourse.release_upgrade.title,visibleCourse.release_upgrade.title_ru)}</p><p>{t(`Your ${visibleCourse.release_upgrade.retained_milestones} earlier milestones and saved answers stay available. The new route starts at ${visibleCourse.release_upgrade.starting_chapter_title ?? visibleCourse.release_upgrade.starting_chapter}.`,`Ваши прежние этапы (${visibleCourse.release_upgrade.retained_milestones}) и ответы сохранятся. Новый маршрут начинается: ${visibleCourse.release_upgrade.starting_chapter_title_ru ?? visibleCourse.release_upgrade.starting_chapter}.`)}</p>{visibleCourse.release_upgrade.retained_access.includes('A2') && <p>{t('Your A2 access is kept.','Доступ к A2 сохранится.')}</p>}{!!visibleCourse.release_upgrade.active_attempts.length && <><p>{t('You can finish these letters before or after switching:','Эти письма можно закончить до или после перехода:')}</p><ul>{visibleCourse.release_upgrade.active_attempts.map(saved=><li key={saved.id}><a href={`#journey/checkpoint/${encodeURIComponent(saved.id)}`}>{t(saved.title,saved.title_ru)}</a></li>)}</ul></>}<p>{t('Only practice that matches the new requirements counts towards its preparation. Earlier passes remain on the earlier route.','В подготовке нового маршрута учитывается только подходящая практика. Прежние пройденные этапы остаются в прежнем маршруте.')}</p><button type="button" class="cta" disabled={!!busy} onClick={()=>void switchRelease()}>{busy==='switch' ? t('Switching…','Переходим…') : t('Move to the updated journey','Перейти к обновлённому путешествию')} →</button></details>}
      <ol class="course-chapters">{visibleCourse.chapters.map(item=>item.status==='locked' ?
        <li class="course-chapter is-locked" key={item.id} aria-label={t(`Milestone ${item.number}, locked`,`Этап ${item.number}, пока недоступен`)}>
          <span class="course-chapter-number" aria-hidden="true">{item.number}</span>
          <div class="course-chapter-mystery" aria-hidden="true">
            <span class="course-mystery-caption" /><span class="course-mystery-title" />
            <span class="course-mystery-line" /><span class="course-mystery-line is-short" />
            <span class="course-mystery-progress" />
          </div>
        </li> :
        <li class={`course-chapter is-${item.status}`} key={item.id} aria-current={!visibleCourse.completed && item.id===visibleCourse.current_chapter_id ? 'step' : undefined}>
          <span class="course-chapter-number" aria-hidden="true">{item.status==='passed' ? '✓' : item.number}</span>
          <div>
            <div class="course-milestone-heading">
              <ChapterArtwork releaseId={visibleCourse.release_id} chapterId={item.id} />
              <div>
                <p class="kicker">{position(item.number)} · {stateText(item.status)}</p>
                <h2>{!visibleCourse.completed && item.id===visibleCourse.current_chapter_id ? t(item.title,item.title_ru) : <a class="course-chapter-link" href={courseHref(visibleCourse.release_id,item.id)}>{t(item.title,item.title_ru)}</a>}</h2>
              </div>
            </div>
            <p>{t(item.intro,item.intro_ru)}</p>
            <div class="course-chapter-footer">
              <div class="course-chapter-progress"><progress max={1} value={clamp(item.progress)} aria-label={t(`Chapter ${item.number} progress`,`Прогресс главы ${item.number}`)} /><span>{Math.round(clamp(item.progress)*100)}%</span></div>
              {!visibleCourse.completed && item.id===visibleCourse.current_chapter_id && <a class="cta course-chapter-link course-chapter-continue" href={courseHref(visibleCourse.release_id,item.id)}>{item.status==='ready' ? t('Open checkpoint','Открыть проверку') : t('Continue milestone','Продолжить этап')} →</a>}
            </div>
          </div>
        </li>)}</ol>
      {!!visibleCourse.previous_courses?.length && <details class="course-previous"><summary>{t('Earlier journeys and saved letters','Прежние путешествия и письма')}</summary>{visibleCourse.previous_courses.map(previous=><section key={previous.release_id}><h2>{t(previous.title,previous.title_ru)}</h2><ul>{previous.attempts.map(saved=><li key={saved.id}><a href={`#journey/checkpoint/${encodeURIComponent(saved.id)}`}>{t(saved.title,saved.title_ru)}{saved.status==='active' ? t(' · Continue',' · Продолжить') : ''}</a></li>)}</ul></section>)}</details>}
      <p class="course-practice-note"><a class="text-link" href="#activities">{t('Browse all practice activities','Все занятия для практики')} →</a><span>{t('Practice is always available. Your skill ratings stay in your profile.','Практика доступна всегда. Рейтинги навыков — в вашем профиле.')}</span></p>
    </>)}
  </section>;
}
