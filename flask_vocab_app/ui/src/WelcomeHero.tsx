import type { RefObject } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { Art } from './components';
import { api } from './learning-api';

type NextLesson={id:string;position:number;title:string;description:string;status:string;href:string};
type Chapter={profile_id:string|null;lessons:NextLesson[];next_lesson:NextLesson|null;complete:boolean;completed_count:number};

export function WelcomeHero({ headingRef, profileKey, nextDestination, courseJourney=false }: { headingRef: RefObject<HTMLHeadingElement>; profileKey?:string; nextDestination?:{title:string;href:string};courseJourney?:boolean }) {
  const [chapter,setChapter]=useState<Chapter>();
  const [failed,setFailed]=useState(false);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const abort=new AbortController();setFailed(false);setChapter(undefined);
    void api<Chapter>('/api/v1/first-steps',undefined,abort.signal).then(value=>{
      if(abort.signal.aborted)return;
      if(!Array.isArray(value.lessons) || (profileKey && value.profile_id!==profileKey))throw new Error('Your first steps could not load.');
      setChapter(value);
    }).catch(()=>{if(!abort.signal.aborted)setFailed(true);});
    return()=>abort.abort();
  },[profileKey,revision]);
  useEffect(()=>{
    let timer:ReturnType<typeof setTimeout>;
    const refresh=()=>{clearTimeout(timer);timer=setTimeout(()=>setRevision(value=>value+1),150);};
    const visible=()=>{if(document.visibilityState==='visible')refresh();};
    window.addEventListener('lingo:progression',refresh);
    document.addEventListener('visibilitychange',visible);
    return()=>{clearTimeout(timer);window.removeEventListener('lingo:progression',refresh);document.removeEventListener('visibilitychange',visible);};
  },[]);
  const next=courseJourney ? chapter?.lessons.find(lesson=>lesson.id==='hello') : chapter?.next_lesson;
  const complete=courseJourney ? !!chapter?.lessons.find(lesson=>lesson.id==='hello' && lesson.status==='completed') || !!chapter?.complete : chapter?.complete;
  const title=complete ? nextDestination?.title ?? 'Barsik’s journey' : next?.title ?? 'First steps with Barsik';
  const href=complete ? nextDestination?.href ?? '#journey' : next?.href ?? '#first-steps';
  const label=complete ? courseJourney ? 'Your journey' : 'Introduction complete · the journey continues' : courseJourney ? 'Your first delivery · a little adventure' : next ? `First steps · ${next.position} of ${chapter!.lessons.length}` : 'Five short lessons to get started';
  const action=complete ? 'Continue the journey' : !next ? 'Open first steps' : next.status==='active' ? 'Continue' : next.position>1 ? 'Next lesson' : 'Let’s begin';
  return <section class="hero" aria-labelledby="welcome-title">
    <div class="hero-copy">
      <p class="kicker">Learn Russian with Barsik</p>
      <h1 id="welcome-title" ref={headingRef} tabIndex={-1} class="headline">
        A small letter. <span class="big">A big</span> adventure.
      </h1>
      <p class="intro"><strong>Barsik has a letter for you.</strong><br />Help him deliver it, one word at a time.</p>
    </div>
    <div class="hero-illustration">
      <figure class="art"><Art /></figure>
      <p class="greeting"><strong lang="ru">Привет!</strong><span>Hello! I’m Barsik.</span></p>
    </div>
    <a class="delivery-ticket" href={href}>
      <span class="ticket-stub" aria-hidden="true">{complete ? '✓' : next ? String(next.position).padStart(2,'0') : '→'}</span>
      <span class="ticket-copy"><span class="ticket-label">{label}</span>{' '}
        <strong>{title}</strong>{' '}<span>{complete ? 'Keep practising and help Barsik carry your letter onward.' : next?.description ?? 'Meet Barsik and learn your first three Russian words.'}</span>
      </span>
      <span class="ticket-action">{action} <span aria-hidden="true">↗</span></span>
    </a>
    {(!courseJourney || failed) && <div class="first-steps-home-link">{!courseJourney && <a class="text-link" href="#first-steps">See all five lessons <span aria-hidden="true">→</span></a>}{failed && <span role="status"> Your place could not load. <button class="text-link" onClick={()=>setRevision(v=>v+1)}>Try again</button></span>}</div>}
  </section>;
}
