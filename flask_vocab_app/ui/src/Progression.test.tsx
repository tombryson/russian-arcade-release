import { afterEach,describe,expect,it,vi } from 'vitest';
import { fireEvent,render,screen,waitFor } from '@testing-library/preact';
import { Journey,ProgressionBadge,useProgression,type ProgressionData } from './Progression';

const data:ProgressionData={profile_id:'personal',balance:42,earned_total:3,legacy_balance:39,preferred_level:'A1',levels:[],
  policy:{activity_coins:3,activity_daily_cap:12,review_coins:1,review_daily_cap:10},recent_rewards:[{id:'r1',amount:3,activity:'speaking',title:'A visit to the café',created_at:1720000000}],
  journey:{worlds:[{id:'post-office',title:'The post office',title_ru:'Почта',threshold:0,unlocked:true,visited:false,completed:false,scene_id:'first-letter'},
    {id:'market-town',title:'Market town',title_ru:'Городской рынок',threshold:12,unlocked:false,visited:false,completed:false,scene_id:'market-letter'}],next_world:null},skill:{status:'not_calibrated'}};
const scene={world:data.journey.worlds[1],scene:{title:'A letter for you',title_ru:'Письмо для вас',intro:'Barsik picks up your letter.',intro_ru:'Барсик берёт ваше письмо.',prompt:'What does привет mean?',prompt_ru:'Что означает слово «привет»?',choices:[{id:'hello',text:'Hello',text_ru:'Привет'},{id:'thanks',text:'Thank you',text_ru:'Спасибо'}],completed:false},progression:data};
const response=(value:unknown)=>Promise.resolve({ok:true,json:async()=>value});
const source=()=>({data,error:'',loading:false,refresh:vi.fn()});
afterEach(()=>{window.arcadeGameUnlocks?.reset();localStorage.clear();vi.useRealTimers();vi.unstubAllGlobals();window.history.replaceState(null,'','/');});

describe('Shared progression',()=>{
  it('shows the real balance and uses new earnings for journey progress',()=>{
    render(<Journey progression={source()} />);
    expect(screen.getByText('42')).toBeTruthy();
    expect(screen.getByText('3 earned through practice')).toBeTruthy();
    expect(screen.getByRole('link',{name:'Start →'}).getAttribute('href')).toBe('#first-steps');
    expect(screen.getByText('Earn 9 more Lingo coins and finish the previous stop to reach here.')).toBeTruthy();
    expect(screen.queryByRole('link',{name:/Market town/})).toBeNull();
    expect(screen.queryByText('A visit to the café')).toBeNull();
    expect(screen.getByText(/Your earlier 39 coins are saved/)).toBeTruthy();
    expect(screen.queryByText(/B2|Elo|You have mastered/)).toBeNull();
  });
  it('shows a missing prerequisite even when there are enough newly earned coins',()=>{
    render(<Journey progression={{...source(),data:{...data,earned_total:20}}} />);
    expect(screen.getByText('Finish the previous stop to continue here.')).toBeTruthy();
  });
  it('routes a completed post-office revisit into First steps and retains the next world link',()=>{
    const worlds=data.journey.worlds.map(world=>({...world,unlocked:true,visited:world.id==='post-office',completed:world.id==='post-office'}));
    render(<Journey progression={{...source(),data:{...data,journey:{worlds,next_world:worlds[1]}}}} />);
    expect(screen.getByRole('link',{name:'Visit again →'}).getAttribute('href')).toBe('#first-steps');
    expect(screen.getByRole('link',{name:'Start →'}).getAttribute('href')).toBe('#journey/market-town');
  });
  it('redirects an old post-office route without loading or submitting the legacy quiz',async()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
    window.history.replaceState(null,'','/#journey/post-office');
    render(<Journey worldId="post-office" progression={source()} />);
    await waitFor(()=>expect(window.location.hash).toBe('#first-steps'));
    expect(screen.getByRole('link',{name:'First steps →'}).getAttribute('href')).toBe('#first-steps');
    expect(screen.queryByRole('button')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('fetches the badge read-only and refreshes it independently on reward events',async()=>{
    let balance=42;
    const fetch=vi.fn(()=>response({...data,balance}));vi.stubGlobal('fetch',fetch);
    function Header(){return <ProgressionBadge progression={useProgression()} />;}
    render(<Header />);
    expect(await screen.findByRole('link',{name:'Lingo coins: 42'})).toBeTruthy();
    balance=45;window.dispatchEvent(new Event('lingo:progression'));
    expect(await screen.findByRole('link',{name:'Lingo coins: 45'})).toBeTruthy();
    expect(fetch.mock.calls).toHaveLength(2);
  });
  it('celebrates an earned game price once and keeps the shop link inside the demo',async()=>{
    window.history.replaceState(null,'','/demo/#flashcards');
    let balance=499;
    const fetch=vi.fn(()=>response({...data,balance,game_shop:{enabled:true,policy:'game-shop-v2',offers:[{id:'pack-bag',price:500}]}}));
    vi.stubGlobal('fetch',fetch);
    function Header(){return <ProgressionBadge progression={useProgression(true,'personal')} />;}
    const {unmount}=render(<Header />);
    await screen.findByRole('link',{name:'Lingo coins: 499'});
    expect(screen.queryByText('You can unlock a game!')).toBeNull();
    balance=502;window.dispatchEvent(new Event('lingo:progression'));
    await screen.findByText('You can unlock a game!');
    expect(screen.getByRole('link',{name:'Visit shop'}).getAttribute('href')).toBe('/demo/#shop');
    expect(document.querySelectorAll('.game-unlock-confetti')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button',{name:'Dismiss notification'}));
    window.dispatchEvent(new Event('lingo:progression'));
    await waitFor(()=>expect(fetch.mock.calls).toHaveLength(3));
    expect(screen.queryByText('You can unlock a game!')).toBeNull();
    unmount();
    expect(document.querySelector('.game-unlock-confetti')).toBeNull();
  });
  it.each([['unauthorized',401],['account_changed',409]])('removes the celebration on %s',async(code,status)=>{
    let value:unknown={...data,balance:499,game_shop:{enabled:true,policy:`game-shop-v2-${code}`,offers:[{id:'pack-bag',price:500}]}};
    let expired=false;
    vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve({ok:!expired,status:expired ? status : 200,json:async()=>value})));
    function Header(){return <ProgressionBadge progression={useProgression(true,'personal')} />;}
    render(<Header />);
    await screen.findByRole('link',{name:'Lingo coins: 499'});
    value={...(value as ProgressionData),balance:500};window.dispatchEvent(new Event('lingo:progression'));
    await screen.findByText('You can unlock a game!');
    expired=true;value={error:{code,message:'Sign in again.'}};
    window.dispatchEvent(new Event('lingo:progression'));
    await screen.findByRole('link',{name:'Lingo coins: unavailable'});
    expect(screen.queryByText('You can unlock a game!')).toBeNull();
    expect(document.querySelector('.game-unlock-confetti')).toBeNull();
  });
  it('celebrates a saved balance increase without celebrating reloads, profile switches or reversals',()=>{
    vi.useFakeTimers();
    const {container,rerender}=render(<ProgressionBadge progression={source()} />);
    const badge=()=>container.querySelector('.progression-badge')!;
    expect(badge().classList.contains('is-gaining')).toBe(false);
    rerender(<ProgressionBadge progression={{...source(),data:{...data,balance:45}}} />);
    expect(badge().classList.contains('is-gaining')).toBe(true);
    vi.advanceTimersByTime(1000);
    rerender(<ProgressionBadge progression={{...source(),data:{...data,balance:45}}} />);
    expect(badge().classList.contains('is-gaining')).toBe(false);
    rerender(<ProgressionBadge progression={{...source(),data:{...data,balance:99,profile_id:'other'}}} />);
    expect(badge().classList.contains('is-gaining')).toBe(false);
    rerender(<ProgressionBadge progression={{...source(),data:{...data,balance:96,profile_id:'other'}}} />);
    expect(badge().classList.contains('is-gaining')).toBe(false);
  });
  it('does not pretend that an unavailable balance is zero',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('Offline')));
    function Header(){return <ProgressionBadge progression={useProgression()} />;}
    render(<Header />);
    expect(await screen.findByRole('link',{name:'Lingo coins: unavailable'})).toBeTruthy();
    expect(screen.getByText('—')).toBeTruthy();expect(screen.queryByText('0')).toBeNull();
  });
  it('loads an authored scene without awarding coins and saves only the selected choice',async()=>{
    const fetch=vi.fn((_url:string,init?:RequestInit)=>response(init?.method==='POST' ? {...scene,coins_earned:3,scene:{...scene.scene,completed:true,feedback:{correct:true,text:'Привет means hello.',text_ru:'Привет — это приветствие.'}}} : scene));
    vi.stubGlobal('fetch',fetch);const progression=source();render(<Journey worldId="market-town" progression={progression} />);
    await screen.findByRole('heading',{name:'What does привет mean?'});
    expect(fetch.mock.calls).toHaveLength(1);expect(fetch.mock.calls[0][1]?.method).toBe('GET');
    fireEvent.click(screen.getByRole('button',{name:'Hello'}));
    expect(await screen.findByText('This part of the journey is complete.',{exact:false})).toBeTruthy();
    const post=fetch.mock.calls.find(([,init])=>init?.method==='POST')!;
    expect(post[0]).toBe('/api/v1/journey/market-town/answer');
    expect(JSON.parse(post[1]?.body as string)).toMatchObject({answer:'hello',submission_id:expect.any(String)});
    expect(progression.refresh).toHaveBeenCalledOnce();
    expect(screen.getByText('+3 Lingo coins earned')).toBeTruthy();
  });
  it('reuses the answer id after a network failure and keeps answers available after a wrong choice',async()=>{
    let failures=0;
    const fetch=vi.fn((_url:string,init?:RequestInit)=>{
      if (init?.method!=='POST') return response(scene);
      if (!failures++) return Promise.reject(new Error('Connection interrupted.'));
      return response({...scene,coins_earned:0,scene:{...scene.scene,feedback:{correct:false,text:'That means thank you. Try the greeting.',text_ru:'Это благодарность. Попробуйте приветствие.'}}});
    });
    vi.stubGlobal('fetch',fetch);render(<Journey worldId="market-town" progression={source()} />);
    fireEvent.click(await screen.findByRole('button',{name:'Thank you'}));
    await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Thank you'}));
    await screen.findByText('That means thank you. Try the greeting.');
    const posts=fetch.mock.calls.filter(([,init])=>init?.method==='POST');
    expect(posts[0][1]?.body).toBe(posts[1][1]?.body);
    expect(screen.getByRole('button',{name:'Hello'})).toBeTruthy();
    expect(screen.queryByText(/coins earned/)).toBeNull();
  });
  it('uses the authored Russian copy for the scene and choices',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>response(scene)));render(<Journey worldId="market-town" language="ru" progression={source()} />);
    expect(await screen.findByRole('heading',{name:'Письмо для вас'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Привет'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Hello'})).toBeNull();
  });
});
