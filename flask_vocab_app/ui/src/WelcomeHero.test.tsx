import {createRef} from 'preact';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/preact';
import {WelcomeHero} from './WelcomeHero';
const lessons=['hello','bag','directions','help','set-off'].map((id,index)=>({id,position:index+1,title:['Hello, Barsik!','What’s in the bag?','Which way?','Ask for help','Ready to set off'][index],description:'Learn and use these words.',status:'available',href:id==='hello'?'#first-delivery':`#first-steps/${id}`}));
const response=(value:unknown)=>Promise.resolve({ok:true,json:async()=>value});
afterEach(()=>vi.unstubAllGlobals());
describe('Saved First steps home ticket',()=>{
  it('starts a genuine five-lesson sequence with approved hero copy',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:null,lessons,next_lesson:lessons[0],complete:false,completed_count:0})));
    render(<WelcomeHero headingRef={createRef()}/>);
    expect(await screen.findByText('First steps · 1 of 5')).toBeTruthy();
    expect(screen.getByText('Barsik has a letter for you.')).toBeTruthy();
    expect(screen.getByText('Help him deliver it, one word at a time.')).toBeTruthy();
    expect(screen.getByRole('link',{name:/Hello, Barsik!/}).getAttribute('href')).toBe('#first-delivery');
    expect(screen.getByRole('link',{name:/See all five lessons/}).getAttribute('href')).toBe('#first-steps');
  });
  it('returns to the actual active lesson',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'p',lessons,next_lesson:{...lessons[2],status:'active'},complete:false,completed_count:2})));
    render(<WelcomeHero headingRef={createRef()} profileKey="p"/>);
    expect(await screen.findByText('First steps · 3 of 5')).toBeTruthy();
    expect(screen.getByRole('link',{name:/Which way.*Continue/}).getAttribute('href')).toBe('#first-steps/directions');
  });
  it('continues into a real journey destination after the chapter',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'p',lessons,next_lesson:null,complete:true,completed_count:5})));
    render(<WelcomeHero headingRef={createRef()} profileKey="p" nextDestination={{title:'The market town',href:'#journey/market-town'}}/>);
    expect(await screen.findByText('The market town')).toBeTruthy();
    expect(screen.getByRole('link',{name:/Introduction complete/}).getAttribute('href')).toBe('#journey/market-town');
  });
  it('refreshes the next lesson after another activity updates progress',async()=>{
    let next=lessons[1];
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'p',lessons,next_lesson:next,complete:false})));
    render(<WelcomeHero headingRef={createRef()} profileKey="p"/>);
    await screen.findByText('First steps · 2 of 5');
    next=lessons[2];window.dispatchEvent(new Event('lingo:progression'));
    expect(await screen.findByText('First steps · 3 of 5')).toBeTruthy();
  });
  it('rejects another profile’s snapshot and retries without claiming a false next lesson',async()=>{
    const fetch=vi.fn().mockImplementationOnce(()=>response({profile_id:'other',lessons,next_lesson:lessons[3]})).mockImplementation(()=>response({profile_id:'p',lessons,next_lesson:lessons[1],complete:false}));
    vi.stubGlobal('fetch',fetch);render(<WelcomeHero headingRef={createRef()} profileKey="p"/>);
    await screen.findByText(/Your place could not load/);
    expect(screen.queryByText('Ask for help')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));
    expect(await screen.findByText('First steps · 2 of 5')).toBeTruthy();
  });
});

describe('Milestone course welcome',()=>{
  it('moves from the single welcome into Home without requiring five introductory lessons',async()=>{
    const current=lessons.map(lesson=>({...lesson,status:lesson.id==='hello'?'completed':'available'}));
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'p',lessons:current,next_lesson:current[1],complete:false,completed_count:1})));
    render(<WelcomeHero headingRef={createRef()} profileKey="p" courseJourney nextDestination={{title:'Leaving home',href:'#journey/chapter/home'}}/>);
    expect(await screen.findByText('Leaving home')).toBeTruthy();
    expect(screen.getByRole('link',{name:/Your journey.*Leaving home/}).getAttribute('href')).toBe('#journey/chapter/home');
    expect(screen.queryByRole('link',{name:/See all five lessons/})).toBeNull();
    expect(screen.getByText('Help him deliver it, one word at a time.')).toBeTruthy();
  });
  it('offers the welcome first for a new learner on the milestone route',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'p',lessons,next_lesson:lessons[0],complete:false,completed_count:0})));
    render(<WelcomeHero headingRef={createRef()} profileKey="p" courseJourney nextDestination={{title:'Leaving home',href:'#journey/chapter/home'}}/>);
    expect(await screen.findByText('Your first delivery · a little adventure')).toBeTruthy();
    expect(screen.getByRole('link',{name:/Hello, Barsik!/}).getAttribute('href')).toBe('#first-delivery');
  });
});
