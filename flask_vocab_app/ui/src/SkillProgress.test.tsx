import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/preact';
import {SkillProgress} from './SkillProgress';
import {useProgression,type ProgressionData} from './Progression';
import type {CourseData} from './CourseJourney';
const course=(progress=.2):CourseData=>({version:'a1-v1',profile_id:'personal',band:'A1',unlocked_levels:['A1'],current_chapter_id:'first',progress,completed:false,chapters:Array.from({length:4},(_,index)=>({id:index===0 ? 'first' : `chapter-${index+1}`,number:index+1,title:'A small message',title_ru:'Короткое сообщение',intro:'',intro_ru:'',status:index===0 ? 'practice' : 'locked',progress:index===0 ? progress : 0,topics:[],activity_count:0,required_activity_count:6,last_attempt_id:null}))});
const data=(progress=.2,profile='personal'):ProgressionData=>({profile_id:profile,balance:42,earned_total:3,legacy_balance:39,preferred_level:'A1',levels:[],policy:{activity_coins:3,activity_daily_cap:12,review_coins:1,review_daily_cap:10},recent_rewards:[],journey:{worlds:[],next_world:null},skill:{status:'provisional',active_skill:'reading',skills:[{id:'reading',label:'Reading',label_ru:'Чтение',status:'provisional',rating:1040,stage:1,stage_start:1000,stage_end:1200,progress:.9,observations:3,last_updated:null,points_to_next:160}]},course:{...course(progress),profile_id:profile}});
const source=(value:ProgressionData|undefined=data(),error='')=>({data:value,error,loading:false,refresh:vi.fn()});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
describe('Header chapter progress',()=>{
  it('links to the chapter journey and preserves the exact silent Barsik rail',()=>{
    const {container}=render(<><input aria-label="Draft" value="Мой ответ"/><SkillProgress progression={source()}/></>);
    expect(screen.getByRole('link',{name:'Chapter 1 of 4 · A small message · 20% prepared for checkpoint. Open your journey'}).getAttribute('href')).toBe('/#journey');
    expect(container.querySelector('.skill-rail')?.textContent).toBe('');expect(container.querySelector('details')).toBeNull();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('20');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/static/images/barsik-progress-run-v1.webp');
    expect((screen.getByLabelText('Draft') as HTMLInputElement).value).toBe('Мой ответ');
  });
  it('keeps an empty starting line when course data is absent without falling back to Elo',()=>{
    const value=data();delete value.course;const {container}=render(<SkillProgress progression={source(value)}/>);
    expect(screen.getByRole('link',{name:'Open your journey'})).toBeTruthy();expect(screen.queryByRole('progressbar')).toBeNull();
    expect((container.querySelector('.skill-rail') as HTMLElement).style.getPropertyValue('--skill-progress')).toBe('0');
    expect(container.innerHTML).not.toMatch(/Elo|1,040|Getting started/);
  });
  it('distinguishes full preparation from a passed checkpoint',()=>{
    const ready=data(1);ready.course!.chapters[0].status='ready';
    const {rerender}=render(<SkillProgress progression={source(ready)}/>);
    expect(screen.getByRole('progressbar').getAttribute('aria-valuetext')).toContain('100% prepared for checkpoint');
    expect(screen.queryByRole('link',{name:/Milestone passed/})).toBeNull();
    const passed=data(1);passed.course!.chapters[0].status='passed';
    rerender(<SkillProgress progression={source(passed)}/>);
    expect(screen.getByRole('progressbar').getAttribute('aria-valuetext')).toContain('Milestone passed');
  });
  it('keeps loading and failed states accessible',()=>{
    const {container,rerender}=render(<SkillProgress progression={{data:undefined,error:'',loading:true,refresh:vi.fn()}}/>);
    expect(screen.getByRole('link',{name:/Loading chapter progress/})).toBeTruthy();expect(container.querySelector('.skill-rail-runner')).toBeNull();
    rerender(<SkillProgress progression={{data:undefined,error:'Offline',loading:false,refresh:vi.fn()}}/>);
    expect(screen.getByRole('link',{name:/Chapter progress unavailable/}).getAttribute('href')).toBe('/#journey');
  });
  it('animates earned progress only within the same learner, course version and chapter',()=>{
    vi.useFakeTimers();const {container,rerender}=render(<SkillProgress progression={source(data(0))}/>);
    const moving=()=>container.querySelector('.skill-rail')!.classList.contains('is-moving');
    expect(moving()).toBe(false);rerender(<SkillProgress progression={source(data(.1))}/>);expect(moving()).toBe(true);
    vi.advanceTimersByTime(900);rerender(<SkillProgress progression={source(data(.1))}/>);expect(moving()).toBe(false);
    rerender(<SkillProgress progression={source(data(.05))}/>);expect(moving()).toBe(false);
    rerender(<SkillProgress progression={source(data(.4,'another'))}/>);expect(moving()).toBe(false);
    const version=data(.7,'another');version.course!.version='a1-v2';rerender(<SkillProgress progression={source(version)}/>);expect(moving()).toBe(false);
    const next=data(.9,'another');next.course!.version='a1-v2';next.course!.current_chapter_id='chapter-2';next.course!.chapters[1].progress=.2;
    rerender(<SkillProgress progression={source(next)}/>);expect(moving()).toBe(false);
  });
  it('does not animate a release change as newly earned progress',()=>{
    const first=data(.1);first.course!.release_id='a1-v1';
    const {container,rerender}=render(<SkillProgress progression={source(first)}/>);
    const next=data(.8);next.course!.release_id='a1-journey-v2';
    rerender(<SkillProgress progression={source(next)}/>);
    expect(container.querySelector('.skill-rail')!.classList.contains('is-moving')).toBe(false);
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('80');
  });
  it.each([[1.3,'100'],[-.2,'0'],[Number.NaN,'0']])('bounds progress %s and retains saved data during temporary errors', (progress,expected)=>{
    render(<SkillProgress progression={source(data(progress),'Offline')}/>);expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe(expected);
  });
  it('preserves onboarding gating and a visual-only 50% preview',()=>{
    const {container,rerender}=render(<SkillProgress introductory progression={source()}/>);
    expect(screen.queryByRole('progressbar')).toBeNull();expect((container.querySelector('.skill-rail') as HTMLElement).style.getPropertyValue('--skill-progress')).toBe('0');
    window.history.replaceState(null,'','/?progress-preview=50');rerender(<SkillProgress introductory progression={source()}/>);
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50');expect(screen.getByRole('link',{name:/saved progress unchanged/})).toBeTruthy();
  });
  it.each(['locked','profile_changed'])('clears stale learner data on %s',async code=>{
    let expired=false;vi.stubGlobal('fetch',vi.fn(async()=>expired ? {ok:false,json:async()=>({error:{code,message:'Session changed'}})} : {ok:true,json:async()=>data()}));
    function Header(){return <SkillProgress progression={useProgression(true,'personal')}/>;}
    const {container}=render(<Header/>);await screen.findByRole('link',{name:/Chapter 1 of 4/});expired=true;window.dispatchEvent(new Event('lingo:progression'));
    await screen.findByRole('link',{name:/Chapter progress unavailable/});expect(container.querySelector('.skill-rail-runner')).toBeNull();expect(screen.queryByRole('progressbar')).toBeNull();
  });
  it('uses Russian chapter labels while preserving a journey destination for household callers',()=>{
    render(<SkillProgress language="ru" progression={source()} profileHref="/post/household#skill-progress"/>);
    expect(screen.getByRole('link',{name:/Глава 1 из 4 · Короткое сообщение.*Открыть путешествие/}).getAttribute('href')).toBe('/#journey');
  });
});
