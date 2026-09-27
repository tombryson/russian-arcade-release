import {useEffect,useRef,useState} from 'preact/hooks';
import type {Ref} from 'preact';
import {Feedback,Sheet} from './components';
import {api,ApiError} from './learning-api';
import {getFirstSteps,getFirstStepsLesson,saveFirstSteps,type FirstStepsAction,type FirstStepsChapter,type FirstStepsLesson,type FirstStepsSummary,type FirstStepsTeaching} from './first-steps-api';
import {LessonVisual} from './LessonVisual';
import {useGameText} from './GameLocale';
import './styles/first-steps.css';


function ProfileSave({profileHref,pending}:{profileHref:string;pending:number}) {
  if(pending<=0)return null;
  const household=profileHref.startsWith('/post/household');
  return <p>{household ? 'Choose a learner to start saving your practice.' : 'Create a profile to save your lessons and coins.'} <a href={profileHref}>{household ? 'Choose a learner' : 'Create a profile'} <span aria-hidden="true">→</span></a></p>;
}
function RetryNotice({message,onRetry,busy=false}:{message:string;onRetry:()=>void;busy?:boolean}) {
  return <div class="first-steps-error" role="alert"><p>{message}</p><button class="text-link" disabled={busy} onClick={onRetry}>Try again</button></div>;
}
function PracticeActions({lessonId,chapter=false}:{lessonId?:string;chapter?:boolean}) {
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const pending=useRef(false),mounted=useRef(true),last=useRef<'cards'|'jumble'>('cards');
  useEffect(()=>()=>{mounted.current=false;},[]);
  async function open(kind:'cards'|'jumble') {
    if(pending.current)return;
    pending.current=true;last.current=kind;setBusy(kind);setError('');
    try {
      if(kind==='cards') {
        const result=await api<{id:string}>(`/api/v1/first-steps/${chapter ? 'chapter' : encodeURIComponent(lessonId!)}/flashcards`,{});
        if(mounted.current)window.location.hash=`generate/${result.id}`;
      } else {
        const result=await api<{url:string}>('/api/v1/first-steps/practice/word-jumble',{});
        if(mounted.current)window.location.assign(result.url);
      }
    } catch(cause) {if(mounted.current)setError(cause instanceof Error ? cause.message : 'Your practice could not open. Please try again.');}
    finally {pending.current=false;if(mounted.current)setBusy('');}
  }
  return <div class="first-steps-practice"><h2>Keep these words going</h2><p>{chapter ? 'Revisit your words with flashcards, or use them to write something of your own.' : 'Make flashcards from this lesson to practise these words again.'}</p><div class="action-row">
    <button class="text-link" disabled={!!busy} onClick={()=>void open('cards')}>{busy==='cards' ? 'Opening flashcards…' : chapter ? 'Make chapter flashcards' : 'Make flashcards'} <span aria-hidden="true">→</span></button>
    {chapter && <button class="text-link" disabled={!!busy} onClick={()=>void open('jumble')}>{busy==='jumble' ? 'Opening practice…' : 'Write with these words'} <span aria-hidden="true">→</span></button>}
    {chapter && <a class="text-link" href="#speaking/scenario/directions">Try a conversation <span aria-hidden="true">→</span></a>}
  </div>{error && <RetryNotice message={error} onRetry={()=>void open(last.current)} busy={!!busy}/>}</div>;
}
const actionLabel=(lesson:FirstStepsSummary)=>`${lesson.status==='active' ? 'Continue' : 'Start'} lesson ${lesson.position}`;
const nextLessonLabel=(lesson:FirstStepsSummary)=>`${lesson.status==='active' ? 'Continue' : 'Next'}: ${lesson.title}`;

export function FirstSteps({lessonId,profileHref='/post/profiles'}:{lessonId?:string;profileHref?:string}) {
  return lessonId ? <FirstStepsPlayer key={lessonId} lessonId={lessonId} profileHref={profileHref} /> : <FirstStepsOverview profileHref={profileHref} />;
}
function FirstStepsOverview({profileHref}:{profileHref:string}) {
  const t=useGameText();
  const [chapter,setChapter]=useState<FirstStepsChapter>();
  const [error,setError]=useState('');
  const [revision,setRevision]=useState(0);
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    const abort=new AbortController();setError('');
    void getFirstSteps(abort.signal).then(result=>{if(!abort.signal.aborted)setChapter(result);}).catch(cause=>{if(!abort.signal.aborted)setError(cause instanceof Error ? cause.message : 'Your lessons could not load.');});
    return()=>abort.abort();
  },[revision]);
  useEffect(()=>{heading.current?.focus({preventScroll:true});window.scrollTo(0,0);},[]);
  return <section class="page first-steps">
    <div class="lesson-head"><a class="text-link" href="#home">Back to home</a><a class="text-link" href="#activities">Choose an activity</a></div>
    <div class="first-steps-header"><div><p class="kicker">A little adventure</p><h1 ref={heading} tabIndex={-1}>First steps with Barsik</h1><p class="intro">Five short lessons to get you started. Meet Barsik, pack his bag and help him find the way to the market.</p></div><LessonVisual kind="map" /></div>
    {chapter ? <>
      <p class="first-steps-overview-progress">{chapter.completed_count} of {chapter.lessons.length} lessons complete</p>
      {chapter.next_lesson ? <div class="action-row"><a class="cta" href={chapter.next_lesson.href}>{actionLabel(chapter.next_lesson)} <span aria-hidden="true">→</span></a></div> : chapter.complete ? <div class="action-row"><a class="cta" href="#activities">{t("Choose an activity")} <span aria-hidden="true">→</span></a></div> : null}
      <ol class="first-steps-list" aria-label="First steps lessons">{chapter.lessons.map(lesson=>{
        const next=chapter.next_lesson?.id===lesson.id;
        const content=<><span class="first-steps-number" aria-hidden="true">{String(lesson.position).padStart(2,'0')}</span><div><h2>{lesson.title}</h2><p>{lesson.description}</p></div><div class="first-steps-status">{lesson.status==='completed' ? 'Completed · revisit' : lesson.status==='active' ? 'In progress' : lesson.status==='locked' ? 'Complete the earlier lessons' : 'Ready to begin'}<span aria-hidden="true">{lesson.status==='completed' ? '✓' : lesson.status==='locked' ? '—' : '→'}</span></div></>;
        return <li key={lesson.id}>{lesson.status==='locked' ? <div class="first-steps-row is-locked">{content}</div> : <a class={`first-steps-row${next ? ' is-next' : ''}${lesson.status==='completed' ? ' is-completed' : ''}`} href={lesson.href} aria-current={next ? 'step' : undefined}>{content}</a>}</li>;
      })}</ol>
      <ProfileSave profileHref={profileHref} pending={chapter.pending_reward ?? 0} />
      {chapter.complete && chapter.profile_id && <PracticeActions chapter/>}
    </> : !error && <p role="status" class="first-steps-empty">Opening your lessons…</p>}
    {error && <RetryNotice message={error} onRetry={()=>setRevision(value=>value+1)} />}
  </section>;
}

function TeachingCard({teaching,headingRef}:{teaching:FirstStepsTeaching;headingRef:Ref<HTMLHeadingElement>}) {
  return <div class="first-steps-teaching"><div class="first-steps-card-head"><div><h1 class="lesson-task-heading" ref={headingRef} tabIndex={-1}>{teaching.title}</h1><p class="first-steps-word" lang="ru">{teaching.word}</p><p class="first-steps-meaning">{teaching.meaning}</p></div><LessonVisual kind={teaching.visual} /></div>
    <p>{teaching.explanation}</p>{teaching.example && <div class="first-steps-context"><p lang="ru">{teaching.example}</p>{teaching.translation && <p>{teaching.translation}</p>}</div>}
  </div>;
}
function FirstStepsPlayer({lessonId,profileHref}:{lessonId:string;profileHref:string}) {
  const t=useGameText();
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
      let result=await getFirstStepsLesson(lessonId);
      if(!mounted.current)return;
      accept(result);
      if(!result.attempt) {
        retryRequest.current={action:'start',body:{}};
        result=await saveFirstSteps(lessonId,'start');
        accept(result);
      }
    }catch(cause){report(cause);}finally{inFlight.current=false;if(mounted.current)setBusy(false);}
  }
  async function save(action:FirstStepsAction,body:unknown={}) {
    if(inFlight.current)return;
    inFlight.current=true;setBusy(true);setError('');retryRequest.current={action,body};
    try {
      let result=await saveFirstSteps(lessonId,action,body);accept(result);
      if(mounted.current && action==='continue' && result.attempt?.phase==='ready') {
        retryRequest.current={action:'complete',body:{}};result=await saveFirstSteps(lessonId,'complete');accept(result);
      }
    }catch(cause){report(cause);}finally{inFlight.current=false;if(mounted.current)setBusy(false);}
  }
  function retry(){const request=retryRequest.current;request.action==='load' ? void load() : void save(request.action,request.body);}
  return <section class="page first-steps lesson-player">
    <div class="lesson-player-nav"><a class="text-link" href="#first-steps"><span aria-hidden="true">← </span>First steps</a>{state && <span class="quiet lesson-name">{state.lesson.title}</span>}</div>
    {!attempt && <h1 ref={heading} tabIndex={-1}>{state?.lesson.title ?? 'First steps with Barsik'}</h1>}
    {!attempt && !error && <p role="status" class="first-steps-empty">Opening your lesson…</p>}
    {state && attempt && (attempt.phase==='completed' ? <>
      <p class="kicker">First steps · Lesson complete</p><h1 ref={heading} tabIndex={-1}>{state.lesson.title}</h1>
      <p class="intro">{state.resolution ?? 'You’ve finished this lesson. Ready for the next part?'}</p>
      <Sheet>
        {state.reward && state.reward.amount>0 ? <div class="first-steps-reward" role="status"><p><strong>{state.reward.awarded_now && state.reward.status==='credited' ? `+${state.reward.amount} Lingocoins` : `${state.reward.amount} Lingocoins earned`}</strong></p>{state.reward.status==='credited' && <p>{state.reward.awarded_now ? 'Your lesson and coins are saved.' : 'Your lesson and reward are already saved.'}</p>}<ProfileSave profileHref={profileHref} pending={state.reward.status==='pending' ? state.pending_reward : 0}/></div> : <p>Your lesson is complete. No coins were added.</p>}
        <details class="first-steps-review"><summary>Revisit what you learned</summary><ul class="first-steps-review-list">{state.teaching_cards.map(item=><li key={item.id}><strong lang="ru">{item.word}</strong><p>{item.meaning}</p><p>{item.explanation}</p>{item.example && <p lang="ru">{item.example}</p>}{item.translation && <p>{item.translation}</p>}</li>)}</ul></details>
        <details class="first-steps-review"><summary>Your saved answers</summary><ol class="first-steps-review-list">{attempt.answers.map(item=><li key={item.question_id}><strong lang="ru">{item.answer_text}</strong><p>{item.feedback}</p>{item.hint_used && <p class="quiet">You used a hint.</p>}</li>)}</ol></details>
      </Sheet>
      <div class="action-row"><a class="cta" href="#activities">{t("Choose an activity")} <span aria-hidden="true">→</span></a>{state.next_lesson ? <a class="text-link" href={state.next_lesson.href}>{nextLessonLabel(state.next_lesson)} <span aria-hidden="true">→</span></a> : <a class="text-link" href="#first-steps">Back to First steps <span aria-hidden="true">→</span></a>}</div>
      {state.profile_id && <PracticeActions lessonId={state.lesson.id} chapter={state.chapter_complete}/>}
    </> : <>
      <Sheet>{attempt.phase!=='ready' && <p class="lesson-counter">{attempt.phase==='learn' ? `Learn · ${attempt.teaching_index+1} of ${attempt.total_teaching}` : `Try · ${attempt.question_index+1} of ${attempt.total_questions}`}</p>}
        {attempt.phase==='learn' && teaching ? <><TeachingCard teaching={teaching} headingRef={heading}/><button class="cta" disabled={busy} onClick={()=>void save('learn',{teaching_id:teaching.id})}>{busy ? 'Saving…' : attempt.teaching_index+1===attempt.total_teaching ? 'Try what you’ve learned' : 'Continue'} <span aria-hidden="true">→</span></button></> : question ? <>
        {question.visual && <LessonVisual kind={question.visual} decorative={false}/>} {question.passage && <p class="first-steps-passage" lang="ru">{question.passage}</p>}<h1 class="lesson-task-heading" ref={heading} tabIndex={-1}>{question.prompt}</h1>
        {attempt.phase==='feedback' && feedback ? <><p class="answer-label">{feedback.correct ? 'That’s right.' : 'Here’s the answer.'}</p><p class="answer-text" lang="ru">{feedback.correct_answer}</p><Feedback>{feedback.feedback}</Feedback><button class="cta" disabled={busy} onClick={()=>void save('continue',{question_id:question.id})}>{busy ? 'Saving…' : attempt.question_index+1===attempt.total_questions ? 'Finish lesson' : 'Continue'} <span aria-hidden="true">→</span></button></> : <>
          <div class="options">{question.choices.map(choice=><button key={choice.id} class="word" lang="ru" disabled={busy} onClick={()=>void save('answer',{question_id:question.id,answer:choice.id})}>{choice.text}</button>)}</div>
          {question.hint ? <Feedback>{question.hint}</Feedback> : <button class="text-link" disabled={busy} onClick={()=>void save('hint',{question_id:question.id})}>Show a hint</button>}
          {busy && <p class="quiet" role="status">Saving…</p>}
        </>}
      </> : <><h1 class="lesson-task-heading" ref={heading} tabIndex={-1}>Practice complete</h1><p>You’ve finished every question. Let’s see how Barsik is getting on.</p><button class="cta" disabled={busy} onClick={()=>void save('complete')}>{busy ? 'Saving…' : 'Finish lesson'} <span aria-hidden="true">→</span></button></>}
      </Sheet>
    </>)}
    {error && (locked ? <div class="first-steps-error" role="alert"><p>{error}</p><a class="text-link" href="#first-steps">See your next lesson <span aria-hidden="true">→</span></a></div> : <RetryNotice message={error} onRetry={retry} busy={busy}/>)}
  </section>;
}
