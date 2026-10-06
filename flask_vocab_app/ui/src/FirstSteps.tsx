import { appUrl } from './app-url';
import {useEffect,useRef,useState} from 'preact/hooks';
import {Feedback} from './components';
import {IntroLessonCard} from './IntroLessonCard';
import {api,ApiError} from './learning-api';
import {firstStepsEndpoint,firstStepsHref,getFirstSteps,getFirstStepsLesson,saveFirstSteps,type FirstStepsAction,type FirstStepsChapter,type FirstStepsLesson,type FirstStepsSummary,type FirstStepsTeaching} from './first-steps-api';
import {LessonVisual} from './LessonVisual';
import {LessonAudio} from './LessonAudio';
import './styles/first-steps.css';


function ProfileSave({profileHref,pending}:{profileHref:string;pending:number}) {
  if(pending<=0)return null;
  const household=profileHref.startsWith('/post/household');
  return <p>{household ? 'Choose a learner to start saving your practice.' : 'Create a profile to save your lessons and coins.'} <a href={profileHref}>{household ? 'Choose a learner' : 'Create a profile'} <span aria-hidden="true">→</span></a></p>;
}
function RetryNotice({message,onRetry,busy=false}:{message:string;onRetry:()=>void;busy?:boolean}) {
  return <div class="first-steps-error" role="alert"><p>{message}</p><button class="text-link" disabled={busy} onClick={onRetry}>Try again</button></div>;
}
function PracticeActions({lessonId,chapter=false,version}:{lessonId?:string;chapter?:boolean;version?:string}) {
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const pending=useRef(false),mounted=useRef(true),last=useRef<'cards'|'jumble'>('cards');
  useEffect(()=>()=>{mounted.current=false;},[]);
  async function open(kind:'cards'|'jumble') {
    if(pending.current)return;
    pending.current=true;last.current=kind;setBusy(kind);setError('');
    try {
      if(kind==='cards') {
        const result=await api<{id:string}>(firstStepsEndpoint(`/${chapter ? 'chapter' : encodeURIComponent(lessonId!)}/flashcards`,version),{});
        if(mounted.current)window.location.hash=`generate/${result.id}`;
      } else {
        const result=await api<{url:string}>(firstStepsEndpoint('/practice/word-jumble',version),{});
        if(mounted.current)window.location.assign(appUrl(result.url));
      }
    } catch(cause) {if(mounted.current)setError(cause instanceof Error ? cause.message : 'Your practice could not open. Please try again.');}
    finally {pending.current=false;if(mounted.current)setBusy('');}
  }
  return <div class="first-steps-practice"><h2>More practice</h2><div class="action-row">
    <button class="text-link" disabled={!!busy} onClick={()=>void open('cards')}>{busy==='cards' ? 'Opening flashcards…' : chapter ? 'Make chapter flashcards' : 'Make flashcards'} <span aria-hidden="true">→</span></button>
    {chapter && <button class="text-link" disabled={!!busy} onClick={()=>void open('jumble')}>{busy==='jumble' ? 'Opening practice…' : 'Write with these words'} <span aria-hidden="true">→</span></button>}
    {chapter && <a class="text-link" href="#speaking/scenario/directions">Try a conversation <span aria-hidden="true">→</span></a>}
  </div>{error && <RetryNotice message={error} onRetry={()=>void open(last.current)} busy={!!busy}/>}</div>;
}
const actionLabel=(lesson:FirstStepsSummary)=>`${lesson.status==='active' ? 'Continue' : 'Start'} lesson ${lesson.position}`;
const nextLessonLabel=(lesson:FirstStepsSummary)=>`${lesson.status==='active' ? 'Continue' : 'Next'}: ${lesson.title}`;

export function FirstSteps({lessonId,version,profileHref='/post/profiles',journeyHref='#journey/release/a1-journey-v2/chapter/home'}:{lessonId?:string;version?:string;profileHref?:string;journeyHref?:string}) {
  return lessonId ? <FirstStepsPlayer key={`${version ?? ''}:${lessonId}`} lessonId={lessonId} version={version} profileHref={profileHref} journeyHref={journeyHref}/> : <FirstStepsOverview key={version} version={version} profileHref={profileHref} journeyHref={journeyHref}/>;
}
function FirstStepsOverview({profileHref,version,journeyHref}:{profileHref:string;version?:string;journeyHref:string}) {
  const [chapter,setChapter]=useState<FirstStepsChapter>();
  const [error,setError]=useState('');
  const [revision,setRevision]=useState(0);
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    const abort=new AbortController();setError('');
    void getFirstSteps(abort.signal,version).then(result=>{if(!abort.signal.aborted)setChapter(result);}).catch(cause=>{if(!abort.signal.aborted)setError(cause instanceof Error ? cause.message : 'Your lessons could not load.');});
    return()=>abort.abort();
  },[revision,version]);
  useEffect(()=>{heading.current?.focus({preventScroll:true});window.scrollTo(0,0);},[]);
  return <section class="page first-steps">
    <div class="lesson-head"><a class="text-link" href="#home">Back to home</a><a class="text-link" href="#activities">Choose an activity</a></div>
    <div class="first-steps-header"><div><h1 ref={heading} tabIndex={-1}>First steps with Barsik</h1><p class="intro">{version==='first-steps-v1' ? 'Revisit your earlier lessons and saved answers.' : 'Five short lessons to learn your first words, name familiar things, introduce yourself, recognise noun groups and say what is yours.'}</p></div><LessonVisual kind="bag" /></div>
    <p class="first-steps-alphabet-link"><a class="text-link alphabet-prompt-link" href="#alphabet?from=first-steps"><span class="alphabet-prompt-icon" lang="ru" aria-hidden="true">Аа</span><span>Learn the alphabet</span></a></p>
    {chapter ? <>
      {chapter.updated_chapter_href && <p class="first-steps-version-note">These lessons have been revised for beginners. <a href={chapter.updated_chapter_href}>Open the revised lessons</a></p>}
      <p class="first-steps-overview-progress">{chapter.completed_count} of {chapter.lessons.length} lessons complete</p>
      {chapter.next_lesson ? <div class="action-row"><a class="cta" href={chapter.next_lesson.href}>{actionLabel(chapter.next_lesson)} <span aria-hidden="true">→</span></a></div> : chapter.complete ? <div class="action-row"><a class="cta" href={journeyHref}>Start at home <span aria-hidden="true">→</span></a></div> : null}
      <ol class="first-steps-list" aria-label="First steps lessons">{chapter.lessons.map(lesson=>{
        const next=chapter.next_lesson?.id===lesson.id;
        const content=<><span class="first-steps-number" aria-hidden="true">{String(lesson.position).padStart(2,'0')}</span><div><h2>{lesson.title}</h2><p>{lesson.description}</p></div><div class="first-steps-status">{lesson.status==='completed' ? 'Completed · revisit' : lesson.status==='active' ? 'In progress' : lesson.status==='locked' ? 'Complete the earlier lessons' : 'Ready to begin'}<span aria-hidden="true">{lesson.status==='completed' ? '✓' : lesson.status==='locked' ? '—' : '→'}</span></div></>;
        return <li key={lesson.id}>{lesson.status==='locked' ? <div class="first-steps-row is-locked">{content}</div> : <a class={`first-steps-row${next ? ' is-next' : ''}${lesson.status==='completed' ? ' is-completed' : ''}`} href={lesson.href} aria-current={next ? 'step' : undefined}>{content}</a>}</li>;
      })}</ol>
      <ProfileSave profileHref={profileHref} pending={chapter.pending_reward ?? 0} />
      {chapter.previous_chapter && <p class="first-steps-version-note"><a href={chapter.previous_chapter.href}>{chapter.previous_chapter.title}</a> · {chapter.previous_chapter.completed_count} lessons complete</p>}
      {chapter.complete && chapter.profile_id && <PracticeActions chapter version={chapter.version ?? version}/>}
    </> : !error && <p role="status" class="first-steps-empty">Opening your lessons…</p>}
    {error && <RetryNotice message={error} onRetry={()=>setRevision(value=>value+1)} />}
  </section>;
}

function TeachingExamples({teaching}:{teaching:FirstStepsTeaching}) {
  const examples=teaching.examples ?? (teaching.example ? [{ru:teaching.example,en:teaching.translation ?? ''}] : []);
  return examples.length ? <ul class="first-steps-examples">{examples.map((example,index)=><li key={index}><p lang="ru">{example.ru}</p>{example.en && <p lang="en">{example.en}</p>}</li>)}</ul> : null;
}
function NamePractice() {
  const [name,setName]=useState('');
  return <div class="first-steps-name-slot"><label>Your name<input value={name} maxLength={60} autoComplete="off" onInput={event=>setName(event.currentTarget.value)} placeholder="Type your name"/></label>{name.trim() && <output><span lang="ru">Меня зовут</span> {name.trim()}.</output>}<p class="quiet">Try your name in Russian or your own alphabet. This isn’t graded.</p></div>;
}
function TeachingCard({teaching}:{teaching:FirstStepsTeaching}) {
  return <div class="first-steps-teaching">
    <div class="first-steps-teaching-main">
      <div class="first-steps-word-block">
        <div class="first-steps-pronunciation">
          <p class={`first-steps-word${teaching.word.length>28?' is-phrase':''}`} lang="ru">{teaching.word_display ?? teaching.word}</p>
          <LessonAudio inline key={teaching.id} src={teaching.audio_url} label={teaching.word}/>
        </div>
        <p class="first-steps-meaning" lang="en">{teaching.meaning}</p>
        <p class="first-steps-explanation">{teaching.explanation}</p>
      </div>
      {teaching.visual && <LessonVisual kind={teaching.visual}/>}
    </div>
    <TeachingExamples teaching={teaching}/>
    {teaching.name_slot && <NamePractice key={teaching.id}/>}
  </div>;
}

function FirstStepsPlayer({lessonId,version,profileHref,journeyHref}:{lessonId:string;version?:string;profileHref:string;journeyHref:string}) {
  const [state,setState]=useState<FirstStepsLesson>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [locked,setLocked]=useState(false);
  const heading=useRef<HTMLHeadingElement>(null),mounted=useRef(true),inFlight=useRef(false);
  const retryRequest=useRef<{action:FirstStepsAction;body:unknown}|{action:'load'}>({action:'load'});
  const attempt=state?.attempt;
  const teaching=attempt?.teaching;
  const question=attempt?.question;
  const feedback=attempt?.answers.find(item=>item.question_id===question?.id);
  const currentVersion=state?.version ?? version;
  const legacy=currentVersion==='first-steps-v1' || attempt?.version==='first-steps-v1';
  useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;};},[]);
  useEffect(()=>{heading.current?.focus({preventScroll:true});},[state?.lesson.id,attempt?.phase,attempt?.teaching_index,attempt?.question_index]);
  useEffect(()=>{window.scrollTo(0,0);},[state?.lesson.id,attempt?.teaching_index,attempt?.question_index]);
  function accept(result:FirstStepsLesson) {if(mounted.current)setState(result);}
  function report(cause:unknown) {
    if(!mounted.current)return;
    setError(cause instanceof Error ? cause.message : 'Your lesson could not be saved. Please try again.');
    setLocked(cause instanceof ApiError && cause.code==='lesson_locked');
  }
  async function load() {
    if(inFlight.current)return;
    inFlight.current=true;setBusy(true);setError('');setLocked(false);retryRequest.current={action:'load'};
    try {
      let result=await getFirstStepsLesson(lessonId,undefined,version);
      if(!mounted.current)return;
      accept(result);
      if(!result.attempt) {
        retryRequest.current={action:'start',body:{}};
        result=await saveFirstSteps(lessonId,'start',{},result.version ?? version);
        accept(result);
      }
    }catch(cause){report(cause);}finally{inFlight.current=false;if(mounted.current)setBusy(false);}
  }
  async function save(action:FirstStepsAction,body:unknown={}) {
    if(inFlight.current)return;
    inFlight.current=true;setBusy(true);setError('');retryRequest.current={action,body};
    try {
      let result=await saveFirstSteps(lessonId,action,body,currentVersion);accept(result);
      if(mounted.current && action==='continue' && result.attempt?.phase==='ready') {
        retryRequest.current={action:'complete',body:{}};result=await saveFirstSteps(lessonId,'complete',{},result.version ?? currentVersion);accept(result);
      }
    }catch(cause){report(cause);}finally{inFlight.current=false;if(mounted.current)setBusy(false);}
  }
  function retry(){const request=retryRequest.current;request.action==='load' ? void load() : void save(request.action,request.body);}
  const learning=attempt?.phase==='learn' && teaching;
  const completed=attempt?.phase==='completed';
  const answered=attempt?.phase==='feedback' && feedback;
  const counter=completed ? 'Lesson complete' : attempt?.phase==='ready' ? undefined
    : learning ? `Learn · ${attempt!.teaching_index+1} of ${attempt!.total_teaching}`
    : `Try · ${(attempt?.question_index ?? 0)+1} of ${attempt?.total_questions ?? 0}`;
  const title=completed ? state!.lesson.title : learning ? learning.title : question?.prompt ?? 'Practice complete';
  const sentenceChoices=question?.choices.some(choice=>choice.text.length>24);

  return <section class="page first-steps lesson-player intro-lesson-player">
    <div class="lesson-player-nav"><a class="text-link" href={firstStepsHref(currentVersion)}><span aria-hidden="true">← </span>First steps</a>{state && <span class="quiet lesson-name">{state.lesson.title}</span>}</div>
    {state?.updated_lesson_href && <p class="first-steps-version-note">This lesson has been revised for beginners. <a href={state.updated_lesson_href}>Start the revised lesson</a></p>}
    {!attempt && <h1 ref={heading} tabIndex={-1}>{state?.lesson.title ?? 'First steps with Barsik'}</h1>}
    {!attempt && !error && <p role="status" class="first-steps-empty">Opening your lesson…</p>}
    {state && attempt && <>
      <IntroLessonCard title={title} counter={counter} headingRef={heading} className="is-lesson-workspace"
        illustration={!learning && !completed && question?.visual ? <LessonVisual kind={question.visual} decorative={false}/> : undefined}
        actions={completed ? <>
          {state.next_lesson ? <a class="cta" href={state.next_lesson.href}>{nextLessonLabel(state.next_lesson)} <span aria-hidden="true">→</span></a> : <a class="cta" href={journeyHref}>Start at home <span aria-hidden="true">→</span></a>}
          <a class="text-link intro-lesson-secondary" href={firstStepsHref(currentVersion)}>All five lessons</a>
        </> : learning ? <button class="cta" disabled={busy} onClick={()=>void save('learn',{teaching_id:learning.id})}>{busy ? 'Saving…' : attempt.teaching_index+1===attempt.total_teaching ? 'Try what you’ve learned' : 'Continue'} <span aria-hidden="true">→</span></button>
        : question && answered ? <button class="cta" disabled={busy} onClick={()=>void save('continue',{question_id:question.id})}>{busy ? 'Saving…' : attempt.question_index+1===attempt.total_questions ? 'Finish lesson' : 'Continue'} <span aria-hidden="true">→</span></button>
        : question ? <>
          {question.hint_available===true && !question.hint && <button class="text-link" disabled={busy} onClick={()=>void save('hint',{question_id:question.id})}>Show a hint</button>}
        </> : <button class="cta" disabled={busy} onClick={()=>void save('complete')}>{busy ? 'Saving…' : 'Finish lesson'} <span aria-hidden="true">→</span></button>}>
        {completed ? <>
          <p class="first-steps-resolution">{state.resolution ?? 'You’ve finished this lesson. Ready for the next part?'}</p>
          {state.reward && state.reward.amount>0 ? <div class="first-steps-reward" role="status">
            <p><strong>{state.reward.awarded_now && state.reward.status==='credited' ? `+${state.reward.amount} Lingocoins` : `${state.reward.amount} Lingocoins earned`}</strong></p>
            <ProfileSave profileHref={profileHref} pending={state.reward.status==='pending' ? state.pending_reward : 0}/>
          </div> : <p>Your lesson is complete. No coins were added.</p>}
          {legacy ? <details class="first-steps-review"><summary>Your saved answers</summary><ol class="first-steps-review-list">{attempt.answers.map(item=><li key={item.question_id}><strong lang={item.choices_language ?? 'ru'}>{item.answer_text}</strong><p>{item.feedback}</p>{item.hint_used && <p class="quiet">You used a hint.</p>}</li>)}</ol></details>
            : <details class="first-steps-review"><summary>Revisit your words</summary><ul class="first-steps-review-list">{state.teaching_cards.map(item=><li key={item.id}><div class="first-steps-review-word"><strong lang="ru">{item.word_display ?? item.word}</strong><LessonAudio compact src={item.audio_url} label={item.word}/></div><p lang="en">{item.meaning}</p></li>)}</ul></details>}
        </> : learning ? <TeachingCard teaching={learning}/>
        : question ? <>
          {(question.passage || question.audio_url || question.transcript) && <div class="first-steps-question-context">
            {question.passage && <p class="first-steps-passage" lang="ru">{question.passage}</p>}
            <LessonAudio inline key={question.id} src={question.audio_url} label="the question"/>
            {question.transcript && <p lang="ru" class="first-steps-transcript">{question.transcript}</p>}
          </div>}
          {answered ? <>
            <p class="answer-label">{answered.correct ? 'That’s right.' : 'Here’s the answer.'}</p>
            <p class="answer-text" lang={question.choices_language ?? 'ru'}>{answered.correct_answer}</p>
            <Feedback>{answered.feedback}</Feedback>
          </> : <>
            <div class={`options${sentenceChoices ? ' is-sentence-choices' : ''}`}>{question.choices.map(choice=><div class="first-steps-choice" key={choice.id}><button class="word" lang={question.choices_language ?? 'ru'} disabled={busy} onClick={()=>void save('answer',{question_id:question.id,answer:choice.id})}>{choice.text}</button><LessonAudio compact src={choice.audio_url} label={choice.text}/></div>)}</div>
            {question.hint && <Feedback>{question.hint}</Feedback>}
            {busy && <p class="quiet" role="status">Saving…</p>}
          </>}
        </> : <p>You’ve finished every question. Let’s see how Barsik is getting on.</p>}
      </IntroLessonCard>
      {completed && state.profile_id && <PracticeActions lessonId={state.lesson.id} chapter={state.chapter_complete} version={currentVersion}/>}
    </>}
    {state?.previous_lesson && <p class="first-steps-version-note"><a href={state.previous_lesson.href}>{state.previous_lesson.title}</a></p>}
    {error && (locked ? <div class="first-steps-error" role="alert"><p>{error}</p><a class="text-link" href={firstStepsHref(currentVersion)}>See your next lesson <span aria-hidden="true">→</span></a></div> : <RetryNotice message={error} onRetry={retry} busy={busy}/>)}
  </section>;
}
