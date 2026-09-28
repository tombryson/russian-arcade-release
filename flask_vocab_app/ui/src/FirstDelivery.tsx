import { useEffect, useRef, useState } from 'preact/hooks';
import { Feedback, Sheet } from './components';
import {firstDeliveryState,saveFirstDelivery,type FirstDeliveryAction,type FirstDeliveryState} from './first-delivery-api';
import {LessonAudio} from './LessonAudio';
import settingOffArt from './assets/barsik-setting-off-transparent-v2.webp';
import './styles/tutorial.css';

type NextAction = { href: string; label: string; description: string };
type RetryRequest={action:FirstDeliveryAction;body:unknown}|{action:'load'};

export function FirstDelivery({ next, onIntroduce, profileHref='/post/profiles' }: { next: NextAction; onIntroduce?: (milestone: 'coins' | 'progress') => void; profileHref?:string;courseJourney?:boolean }) {
  const [step, setStep] = useState(0);
  const [practice,setPractice]=useState<FirstDeliveryState>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const introduced = useRef(new Set<'coins' | 'progress'>());
  const mounted=useRef(true),inFlight=useRef(false);
  const retryRequest=useRef<RetryRequest>({action:'load'});
  const attempt=practice?.attempt;
  const question=attempt?.question;
  const feedback=attempt?.answers.find(item=>item.question_id===question?.id);
  useEffect(() => {
    const milestone = step === 0 ? 'coins' : step === 1 ? 'progress' : null;
    if (!onIntroduce || !milestone || introduced.current.has(milestone)) return;
    introduced.current.add(milestone);
    onIntroduce(milestone);
  }, [step, onIntroduce]);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [step, attempt?.question_index, attempt?.phase]);
  useEffect(() => { window.scrollTo(0, 0); }, [step, attempt?.question_index]);
  useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;};},[]);

  function accept(result:FirstDeliveryState,resume=false) {
    if (!mounted.current) return;
    setPractice(result);
    if (result.attempt?.version!=='first-delivery-v2') return;
    if (result.attempt.phase==='completed') setStep(3);
    else if (resume) setStep(2);
  }
  async function load() {
    if (inFlight.current) return;
    inFlight.current=true;setBusy(true);setError('');retryRequest.current={action:'load'};
    try {accept(await firstDeliveryState(),true);}
    catch(cause) {if(mounted.current)setError(cause instanceof Error ? cause.message : 'Your activity could not load. Please try again.');}
    finally {inFlight.current=false;if(mounted.current)setBusy(false);}
  }
  async function save(action:FirstDeliveryAction,body:unknown={}) {
    if (inFlight.current) return;
    inFlight.current=true;setBusy(true);setError('');retryRequest.current={action,body};
    try {
      let result=await saveFirstDelivery(action,body);
      accept(result,true);
      if (mounted.current && action==='continue' && result.attempt?.phase==='ready') {
        retryRequest.current={action:'complete',body:{}};
        result=await saveFirstDelivery('complete');
        accept(result);
      }
    } catch(cause) {if(mounted.current)setError(cause instanceof Error ? cause.message : 'Your answer could not be saved. Please try again.');}
    finally {inFlight.current=false;if(mounted.current)setBusy(false);}
  }
  function retry() {
    const request=retryRequest.current;
    if(request.action==='load')void load();else void save(request.action,request.body);
  }
  function replay() {
    setStep(0);
    setPractice(current=>current?.reward ? {...current,reward:{...current.reward,awarded_now:false}} : current);
  }
  function openActivity() {
    if(attempt?.version==='first-delivery-v2') setStep(attempt.phase==='completed' ? 3 : 2);
    else void save('start',attempt ? {restart:true} : {});
  }

  return <section class={`page first-delivery lesson-player${step === 0 ? ' first-delivery-intro' : ''}`}>
    <div class="lesson-player-nav">
      <a class="text-link" href="#first-steps"><span aria-hidden="true">← </span>First steps</a>
    </div>
    {step === 0 ? <>
      <h1 ref={heading} tabIndex={-1}>Before we set off…</h1>
      <div class="onboarding-coins">
        <div class="onboarding-coins-copy">
          <h2><span class="lingocoin" aria-hidden="true">Л</span>Lingocoins</h2>
          <p>Earn Lingocoins from activities and flashcards to buy games in <a href="#shop">the shop</a>.</p>
          <p class="onboarding-bonus">Your first activity earns <strong>3 coins.</strong></p>
        </div>
        <img class="onboarding-coins-art" src={settingOffArt} width="1254" height="1254" decoding="async" alt="Barsik holding a Lingocoin." />
        <details class="onboarding-coin-rules"><summary>How do I earn coins?</summary>
          <ul><li>Complete an activity: <strong>3 coins</strong>, up to 12 per day.</li><li>Review a flashcard: <strong>1 coin</strong>, up to 10 per day.</li></ul>
          <p>Each activity or card earns coins once a day. Hints and mistakes don’t reduce your reward.</p>
          <p>The first-activity bonus is awarded once.</p>
        </details>
      </div>
      <div class="action-row onboarding-intro-actions"><button class="cta" onClick={() => setStep(1)}>Continue <span aria-hidden="true">→</span></button><a class="text-link" href="#activities">Go straight to activities</a></div>
    </> : step === 1 ? <>
      <p class="kicker">One word at a time</p><h1 ref={heading} tabIndex={-1}>Help Barsik reach the next stop.</h1>
      <p class="intro">Practise the topics at each stop to move Barsik along the bar.</p>
      <Sheet><div class="tutorial-progress-introduction"><img class="tutorial-progress-barsik" src="/static/images/barsik-running-v1.webp" width="92" height="68" alt="Barsik running with his letter bag." />
          <div><h2>Choose what to practise</h2><p>Tap Barsik on the bar to see your journey and find activities for your next stop.</p><p>You can also practise from the Activities menu.</p></div></div>
      </Sheet>
      <div class="action-row"><button class="cta" disabled={busy} onClick={openActivity}>Learn your first words <span aria-hidden="true">→</span></button><button class="text-link" onClick={() => setStep(0)}>Back to Lingocoins</button></div>
    </> : step === 2 ? <>
      {question ? <Sheet>
        <p class="lesson-counter">{`${attempt!.phase==='learn' ? 'Learn' : 'Try'} · Word ${attempt!.question_index+1} of ${attempt!.total_questions}`}</p>
        <h1 class="lesson-task-heading" ref={heading} tabIndex={-1}>{attempt?.phase==='learn' && question.lesson ? question.title : question.prompt}</h1>
        {attempt?.phase==='learn' && question.lesson ? <div class="tutorial-word-card">
          <p class="tutorial-new-word" lang="ru">{question.lesson.word_display ?? question.lesson.word}</p>
          <p class="tutorial-word-meaning" lang="en">{question.lesson.meaning}</p>
          <LessonAudio key={question.id} src={question.lesson.audio_url} label={question.lesson.word}/>
          <p>{question.lesson.explanation}</p>
          {question.lesson.reading_help && <details class="tutorial-reading-help"><summary>Read this word</summary><p>{question.lesson.reading_help}</p></details>}
          <button class="cta" disabled={busy} onClick={()=>void save('learn',{question_id:question.id})}>{busy ? 'Saving…' : attempt.question_index+1===attempt.total_questions ? 'Try these words' : 'Next word'} <span aria-hidden="true">→</span></button>
        </div> : <>
          {attempt?.phase==='feedback' && feedback ? <>
            <p class="answer-label">{feedback.correct ? 'That’s right.' : 'Here’s the word you need.'}</p>
            <p class="answer-text" lang="ru">{feedback.correct_answer}</p>
            <Feedback>{feedback.feedback}</Feedback>
            <button class="cta" disabled={busy} onClick={()=>void save('continue',{question_id:question.id})}>{busy ? 'Saving…' : attempt.question_index+1===attempt.total_questions ? 'Finish activity' : 'Next word'} <span aria-hidden="true">→</span></button>
          </> : <>
            <div class="options">{question.choices.map(choice=><div class="tutorial-word-choice" key={choice.id}><button class="word" lang="ru" disabled={busy} onClick={()=>void save('answer',{question_id:question.id,answer:choice.id})}>{choice.text}</button><LessonAudio compact src={choice.audio_url} label={choice.text}/></div>)}</div>
            {question.hint ? <Feedback>{question.hint}</Feedback> : <button class="text-link" disabled={busy} onClick={()=>void save('hint',{question_id:question.id})}>Show a hint</button>}
            {busy && <p class="quiet" role="status">Saving…</p>}
          </>}
        </>}
      </Sheet> : <Sheet><h1 class="lesson-task-heading" ref={heading} tabIndex={-1}>Your first words</h1><p>You’ve practised all three words.</p><button class="cta" disabled={busy} onClick={()=>void save('complete')}>{busy ? 'Saving…' : 'Finish activity'} <span aria-hidden="true">→</span></button></Sheet>}
      <button class="text-link tutorial-back" disabled={busy} onClick={replay}>Back to the introduction</button>
    </> : <>
      <p class="kicker">Hello, Barsik!</p><h1 ref={heading} tabIndex={-1}>Your first lesson is complete.</h1>
      <Sheet><p>You’ve met Barsik and practised your first three Russian words. Next, help him check what’s in his bag.</p>
        {practice?.reward && practice.reward.amount>0 && (practice.reward.status==='pending' ? <div class="tutorial-reward"><p><strong>{practice.reward.amount} Lingocoins earned</strong></p><p>{profileHref.startsWith('/post/household') ? 'Choose a learner to start saving your practice.' : 'Create a profile to save your coins and first activity.'}</p><>{profileHref !== next.href && <a class="text-link" href={profileHref}>{profileHref.startsWith('/post/household') ? 'Choose a learner' : 'Create a profile'} <span aria-hidden="true">→</span></a>}</></div> : <div class="tutorial-reward" role="status"><p><strong>{practice.reward.awarded_now ? `+${practice.reward.amount} Lingocoins` : `${practice.reward.amount} Lingocoins earned`}</strong></p><p>{practice.reward.awarded_now ? 'Your first activity bonus is saved.' : 'Your first activity bonus is already saved.'}</p></div>)}
        {!!practice?.teaching_cards?.length && <details class="coin-rules"><summary>Revisit your first words</summary><ul class="tutorial-answer-review">{practice.teaching_cards.map(item=><li key={item.id}><p><strong lang="ru">{item.word_display ?? item.word}</strong> · <span lang="en">{item.meaning}</span></p><LessonAudio compact src={item.audio_url} label={item.word}/></li>)}</ul></details>}
        {!!practice?.previous_attempt?.answers.length && <details class="coin-rules"><summary>Earlier first activity</summary><ol class="tutorial-answer-review">{practice.previous_attempt.answers.map(item=><li key={item.question_id}><p><strong>{item.answer_text}</strong></p><p>{item.feedback}</p></li>)}</ol></details>}
      </Sheet>
      <p class="intro">{next.description}</p><div class="action-row"><a class="cta" href={next.href}>{next.label} <span aria-hidden="true">→</span></a><button class="text-link" onClick={replay}>Revisit the introduction</button></div>
    </>}
    {error && <div class="tutorial-save-error" role="alert"><p>{error}</p><button class="text-link" disabled={busy} onClick={retry}>Try again</button></div>}
  </section>;
}
