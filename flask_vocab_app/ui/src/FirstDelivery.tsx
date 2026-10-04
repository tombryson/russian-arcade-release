import { useEffect, useRef, useState } from 'preact/hooks';
import { Feedback } from './components';
import {firstDeliveryState,saveFirstDelivery,type FirstDeliveryAction,type FirstDeliveryState} from './first-delivery-api';
import {LessonAudio} from './LessonAudio';
import settingOffArt from './assets/barsik-setting-off-transparent-v2.webp';
import './styles/tutorial.css';

type IntroductionStep = 'coins' | 'progress' | 'alphabet' | 'words' | 'complete';
type NextAction = { href: string; label: string; description: string };
type RetryRequest={action:FirstDeliveryAction;body:unknown}|{action:'load'};

export function FirstDelivery({ next, onIntroduce, profileHref='/post/profiles', entryStep, introductionComplete=true }: { next: NextAction; onIntroduce?: (milestone: 'coins' | 'progress') => void; profileHref?:string;courseJourney?:boolean;entryStep?:'alphabet';introductionComplete?:boolean }) {
  const initialStep = useRef<IntroductionStep>(entryStep && introductionComplete ? entryStep : 'coins');
  const [step, setStep] = useState<IntroductionStep>(initialStep.current);
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
    const milestone = step === 'coins' ? 'coins' : step === 'progress' ? 'progress' : null;
    if (!onIntroduce || !milestone || introduced.current.has(milestone)) return;
    introduced.current.add(milestone);
    onIntroduce(milestone);
  }, [step, onIntroduce]);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [step, attempt?.question_index, attempt?.phase]);
  useEffect(() => { window.scrollTo(0, 0); }, [step, attempt?.question_index]);
  useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;};},[]);

  function showStep(nextStep:IntroductionStep) {
    // Keep browser Back and reload on the invitation when visiting the alphabet.
    if (/^#first-delivery(?:\?|$)/.test(window.location.hash)) {
      const hash=nextStep==='alphabet' ? '#first-delivery?step=alphabet' : '#first-delivery';
      window.history.replaceState(window.history.state,'',hash);
    }
    setStep(nextStep);
  }
  function accept(result:FirstDeliveryState,resume=true) {
    if (!mounted.current) return;
    setPractice(result);
    if (!resume || result.attempt?.version!=='first-delivery-v2') return;
    showStep(result.attempt.phase==='completed' ? 'complete' : 'words');
  }
  async function load() {
    if (inFlight.current) return;
    inFlight.current=true;setBusy(true);setError('');retryRequest.current={action:'load'};
    try {accept(await firstDeliveryState(),initialStep.current!=='alphabet');}
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
    showStep('coins');
    setPractice(current=>current?.reward ? {...current,reward:{...current.reward,awarded_now:false}} : current);
  }
  function openActivity() {
    if (!practice || busy) return;
    if(attempt?.version==='first-delivery-v2') showStep(attempt.phase==='completed' ? 'complete' : 'words');
    else void save('start',attempt ? {restart:true} : {});
  }

  const learning = step === 'words' && attempt?.phase === 'learn' && question?.lesson;
  const title = step === 'coins' ? 'Before we set off…'
    : step === 'progress' ? 'Help Barsik reach the next stop.'
    : step === 'alphabet' ? 'New to the Russian alphabet?'
    : step === 'words' ? (question ? (learning ? question.title : question.prompt) : 'Your first words')
    : 'Your first lesson is complete.';
  const caption = step === 'progress' ? 'One word at a time'
    : step === 'words' && question ? `${learning ? 'Learn' : 'Try'} · Word ${attempt!.question_index+1} of ${attempt!.total_questions}`
    : step === 'complete' ? 'Hello, Barsik!' : '';

  return <section class="page first-delivery lesson-player">
    <div class="lesson-player-nav">
      <a class="text-link" href="#first-steps"><span aria-hidden="true">← </span>First steps</a>
    </div>
    <div class={`first-delivery-stage${['coins','progress','alphabet'].includes(step) ? ' is-explainer' : ''}${step === 'alphabet' ? ' is-alphabet' : ''}`}>
      <header class="first-delivery-heading">
        <h1 ref={heading} tabIndex={-1}>{title}</h1>
        {caption && <p class="lesson-counter">{caption}</p>}
      </header>
      <div class={`first-delivery-content${step === 'progress' ? ' is-progress-introduction' : step === 'alphabet' ? ' is-alphabet-introduction' : ''}`}>
        {step === 'coins' ? <>
          <p class="onboarding-intro-copy">Practise Russian and help Barsik deliver your letter.</p>
          <div class="onboarding-coins">
            <div class="onboarding-coins-copy">
              <h2><span class="lingocoin" aria-hidden="true">Л</span>Earn coins as you learn.</h2>
              <p>Complete activities and review flashcards to earn Lingocoins. Spend them on new games in <a href="#shop">the shop</a>.</p>
              <p class="onboarding-bonus">Learn your first three words to earn <strong>3 Lingocoins</strong>.</p>
            </div>
            <img class="onboarding-coins-art" src={settingOffArt} width="1254" height="1254" decoding="async" alt="Barsik holding a Lingocoin." />
            <details class="onboarding-coin-rules"><summary>How do I earn coins?</summary>
              <ul><li>Complete an activity: <strong>3 coins</strong>, up to 12 per day.</li><li>Review a flashcard: <strong>1 coin</strong>, up to 10 per day.</li></ul>
              <p>Each activity or card earns coins once a day. Hints and mistakes don’t reduce your reward.</p>
              <p>The first-activity bonus is awarded once.</p>
            </details>
          </div>
        </> : step === 'progress' ? <>
          <p class="onboarding-intro-copy">The bar at the top shows Barsik’s progress.</p>
          <div class="tutorial-progress-introduction">
            <img class="tutorial-progress-barsik" src="/static/images/barsik-running-v1.webp" width="92" height="68" alt="Barsik running with his letter bag." />
            <div><h2>Your first steps</h2><p>Learn your first three Russian words, then build on them in four short lessons. We’ll take you through them in order.</p></div>
          </div>
        </> : step === 'alphabet' ? <>
          <p class="onboarding-intro-copy">Explore the alphabet and hear how each letter sounds.</p>
          <a class="tutorial-alphabet-invitation" href="#alphabet?from=first-delivery" aria-labelledby="alphabet-invitation-label">
            <span class="tutorial-alphabet-letters" lang="ru" aria-hidden="true"><span>Аа</span><span>Бб</span><span>Вв</span></span>
            <span id="alphabet-invitation-label" class="tutorial-alphabet-invitation-label">Learn the alphabet</span>
          </a>
        </> : step === 'words' ? <>
          {question ? learning ? <div class="tutorial-word-card">
            <p class="tutorial-new-word" lang="ru">{learning.word_display ?? learning.word}</p>
            <p class="tutorial-word-meaning" lang="en">{learning.meaning}</p>
            <LessonAudio key={question.id} src={learning.audio_url} label={learning.word}/>
            <p>{learning.explanation}</p>
            {learning.reading_help && <details class="tutorial-reading-help"><summary>Read this word</summary><p>{learning.reading_help}</p></details>}
          </div> : attempt?.phase === 'feedback' && feedback ? <>
            <p class="answer-label">{feedback.correct ? 'That’s right.' : 'Here’s the word you need.'}</p>
            <p class="answer-text" lang="ru">{feedback.correct_answer}</p>
            <Feedback>{feedback.feedback}</Feedback>
          </> : <>
            <div class="options">{question.choices.map(choice=><div class="tutorial-word-choice" key={choice.id}><button class="word" lang="ru" disabled={busy} onClick={()=>void save('answer',{question_id:question.id,answer:choice.id})}>{choice.text}</button><LessonAudio compact src={choice.audio_url} label={choice.text}/></div>)}</div>
            {question.hint ? <Feedback>{question.hint}</Feedback> : <button class="text-link" disabled={busy} onClick={()=>void save('hint',{question_id:question.id})}>Show a hint</button>}
            {busy && <p class="quiet" role="status">Saving…</p>}
          </> : <p>You’ve practised all three words.</p>}
        </> : <>
          <p>You’ve met Barsik and practised your first three Russian words. Next, help him check what’s in his bag.</p>
          {practice?.reward && practice.reward.amount>0 && (practice.reward.status==='pending' ? <div class="tutorial-reward"><p><strong>{practice.reward.amount} Lingocoins earned</strong></p><p>{profileHref.startsWith('/post/household') ? 'Choose a learner to start saving your practice.' : 'Create a profile to save your coins and first activity.'}</p><>{profileHref !== next.href && <a class="text-link" href={profileHref}>{profileHref.startsWith('/post/household') ? 'Choose a learner' : 'Create a profile'} <span aria-hidden="true">→</span></a>}</></div> : <div class="tutorial-reward" role="status"><p><strong>{practice.reward.awarded_now ? `+${practice.reward.amount} Lingocoins` : `${practice.reward.amount} Lingocoins earned`}</strong></p><p>{practice.reward.awarded_now ? 'Your first activity bonus is saved.' : 'Your first activity bonus is already saved.'}</p></div>)}
          {!!practice?.teaching_cards?.length && <details class="coin-rules"><summary>Revisit your first words</summary><ul class="tutorial-answer-review">{practice.teaching_cards.map(item=><li key={item.id}><p><strong lang="ru">{item.word_display ?? item.word}</strong> · <span lang="en">{item.meaning}</span></p><LessonAudio compact src={item.audio_url} label={item.word}/></li>)}</ul></details>}
          {!!practice?.previous_attempt?.answers.length && <details class="coin-rules"><summary>Earlier first activity</summary><ol class="tutorial-answer-review">{practice.previous_attempt.answers.map(item=><li key={item.question_id}><p><strong>{item.answer_text}</strong></p><p>{item.feedback}</p></li>)}</ol></details>}
          <p class="intro">{next.description}</p>
        </>}
      </div>
      <div class="action-row first-delivery-actions">
        {step === 'coins' ? <>
          <button class="cta" onClick={() => showStep('progress')}>Continue <span aria-hidden="true">→</span></button><a class="text-link" href="#activities">Go straight to activities</a>
        </> : step === 'progress' ? <>
          <button class="cta" onClick={() => showStep('alphabet')}>Continue <span aria-hidden="true">→</span></button><button class="text-link" onClick={() => showStep('coins')}>Back to Lingocoins</button>
        </> : step === 'alphabet' ? <>
          <button class="cta" disabled={busy || !practice} onClick={openActivity}>Continue <span aria-hidden="true">→</span></button>
        </> : step === 'words' ? <>
          {learning && question ? <button class="cta" disabled={busy} onClick={()=>void save('learn',{question_id:question.id})}>{busy ? 'Saving…' : attempt!.question_index+1===attempt!.total_questions ? 'Try these words' : 'Next word'} <span aria-hidden="true">→</span></button>
            : question && attempt?.phase === 'feedback' && feedback ? <button class="cta" disabled={busy} onClick={()=>void save('continue',{question_id:question.id})}>{busy ? 'Saving…' : attempt.question_index+1===attempt.total_questions ? 'Finish activity' : 'Next word'} <span aria-hidden="true">→</span></button>
            : !question && <button class="cta" disabled={busy} onClick={()=>void save('complete')}>{busy ? 'Saving…' : 'Finish activity'} <span aria-hidden="true">→</span></button>}
          <button class="text-link" disabled={busy} onClick={replay}>Back to the introduction</button>
        </> : <>
          <a class="cta" href={next.href}>{next.label} <span aria-hidden="true">→</span></a><button class="text-link" onClick={replay}>Revisit the introduction</button>
        </>}
      </div>
    </div>
    {error && <div class="tutorial-save-error" role="alert"><p>{error}</p><button class="text-link" disabled={busy} onClick={retry}>Try again</button></div>}
  </section>;
}
