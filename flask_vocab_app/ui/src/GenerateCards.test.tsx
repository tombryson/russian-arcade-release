import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/preact';
import { GenerateCards } from './GenerateCards';
import { App } from './App';

const response=(value:unknown) => Promise.resolve({ok:true,json:async()=>value});
const settings={configured:true,household:false,topics:['Food'],max_quantity:20};
const pending={id:'batch',saved:0,total:1,complete:false,household:false,items:[{id:'item',word:'кофе',status:'pending'}]};
const complete={...pending,saved:1,complete:true,items:[{id:'item',word:'кофе',status:'saved',english:'coffee',sentence:'Это кофе.',card_version_id:'version'}]};
afterEach(()=>vi.unstubAllGlobals());

describe('Automatic flashcard generation',()=>{
  it('uses the server batch limit for the hosted demo',async()=>{
    vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.includes('/options')?{...settings,max_quantity:5}:{words:[]})));
    render(<GenerateCards />);
    await screen.findByText('Up to 5 cards per demo batch.');
    const quantity=screen.getByLabelText('Number of cards') as HTMLInputElement;
    expect(quantity.max).toBe('5');
    fireEvent.input(quantity,{target:{value:'6'}});
    expect(quantity.validity.rangeOverflow).toBe(true);
  });

  it('offers the original selection controls without asking the user to author the answer',async()=>{
    const fetch=vi.fn((url:string)=>response(url.includes('/options')?settings:url.endsWith('/batches')?pending:{words:[{word_id:1,form:'кофе'}]}));
    vi.stubGlobal('fetch',fetch);render(<GenerateCards />);
    expect(await screen.findByText('кофе')).toBeTruthy();
    for (const label of ['Card type','Number of cards','Difficulty','Word type','Case','Topic']) expect(screen.getByLabelText(label)).toBeTruthy();
    expect((screen.getByLabelText('Number of cards') as HTMLInputElement).max).toBe('20');
    expect(screen.queryByText(/per demo batch/)).toBeNull();
    expect(screen.queryByLabelText('Russian sentence')).toBeNull();
    expect(screen.queryByText(/approve|grown-up|PIN/)).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:/Generate cards/}));
    await vi.waitFor(()=>expect(fetch.mock.calls.some(([url])=>url==='/api/v1/card-generation/batches')).toBe(true));
    expect(screen.queryByLabelText('Answer')).toBeNull();
  });
  it('finishes generation with Study and Edit actions, without a publication gate',async()=>{
    const fetch=vi.fn((url:string)=>response(url.includes('/options')?settings:url.endsWith('/next')?complete:pending));
    vi.stubGlobal('fetch',fetch);render(<GenerateCards batchId="batch" />);
    expect(await screen.findByText('Your cards are ready')).toBeTruthy();
    expect(screen.getByRole('link',{name:'Study flashcards'}).getAttribute('href')).toBe('#flashcards');
    expect(screen.getByRole('link',{name:'Edit card'}).getAttribute('href')).toContain('edit=version');
    expect(screen.getByText('coffee')).toBeTruthy();
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/next'))).toHaveLength(1);
    expect(screen.queryByText(/approve|grown-up|PIN/)).toBeNull();
  });
  it('reopens completed batches without regenerating their cards',async()=>{
    const fetch=vi.fn((url:string)=>response(url.includes('/options')?settings:complete));
    vi.stubGlobal('fetch',fetch);render(<GenerateCards batchId="batch" />);
    await screen.findByText('Your cards are ready');
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/next'))).toBe(false);
  });
  it('opens personal flashcards without presenting household setup',async()=>{
    window.history.replaceState(null,'','/#flashcards');
    const overview={profile_id:'me',cards:[],active_session_id:null,counts:{cards:0,words:0,ready:0,new:0,new_allowance:5,due:0,practised_today:0}};
    const fetch=vi.fn((url:string)=>response(url==='/api/v1/household'?{mode:'personal',configured:true,adult:false,profile:{id:'me',display_name:'Me'},csrf_token:'token'}:url==='/api/v1/post'?{profile:{id:'me',display_name:'Me'},content:[],sessions:[]}:url==='/api/v1/word-pocket'?{profile_id:'me',evidence:[]}:overview));
    vi.stubGlobal('fetch',fetch);render(<App />);
    await screen.findByRole('heading',{name:'Flashcards',exact:true});
    expect(await screen.findByRole('link',{name:/Generate cards/})).toBeTruthy();
    expect(screen.queryByText(/PIN|grown-up|Choose a learner/)).toBeNull();
    await act(()=>{window.history.replaceState(null,'','/');});
  });
});

describe('Generation media options and recovery',()=>{
  it('includes audio and pictures by default and lets the user turn either off',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.includes('/options')?settings:url.endsWith('/batches')?pending:{words:[{word_id:1,form:'кофе'}]}));
    vi.stubGlobal('fetch',fetch);render(<GenerateCards />);await screen.findByText('кофе');
    expect((screen.getByLabelText('Picture') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Russian audio · word & example') as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByLabelText('Picture'));await screen.findByText('кофе');
    fireEvent.click(screen.getByRole('button',{name:/Generate cards/}));
    await vi.waitFor(()=>expect(fetch.mock.calls.some(([url])=>url.endsWith('/batches'))).toBe(true));
    const call=fetch.mock.calls.find(([url])=>url.endsWith('/batches'))!;
    expect(JSON.parse(call[1]!.body as string).options).toMatchObject({audio:true,image:false});
  });
  it('keeps saved cards visible when media fails and retries only media',async()=>{
    const partial={...complete,items:[{...complete.items[0],media_jobs:[{kind:'image',status:'failed'},{kind:'word_audio',status:'saved'},{kind:'sentence_audio',status:'saved'}]}]};
    const fetch=vi.fn((url:string)=>response(url.includes('/options')?settings:url.endsWith('/retry-media')?{...partial,complete:false}:url.endsWith('/next')?complete:partial));
    vi.stubGlobal('fetch',fetch);render(<GenerateCards batchId="batch" />);
    fireEvent.click(await screen.findByRole('button',{name:'Retry missing media'}));await screen.findByText('Your cards are ready');
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/retry-media'))).toBe(true);
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/batches'))).toBe(false);
  });
});

describe('Unfinished generation setup',()=>{
  it('keeps choices when returning to the tab in individual mode',async()=>{
    window.history.replaceState(null,'','/#generate');
    const profile={id:'me',display_name:'Me'};
    const fetch=vi.fn((url:string)=>response(url.endsWith('/household')?{mode:'personal',configured:true,adult:false,profile,csrf_token:'token'}:url.endsWith('/post')?{profile,content:[],sessions:[]}:url.endsWith('/word-pocket')?{profile_id:'me',evidence:[]}:url.includes('/options')?settings:{words:[{word_id:1,form:'кофе'}]}));
    vi.stubGlobal('fetch',fetch);render(<App />);
    await screen.findByLabelText('Card type');
    fireEvent.change(screen.getByLabelText('Card type'),{target:{value:'en-ru'}});
    fireEvent.input(screen.getByLabelText('Number of cards'),{target:{value:'7'}});
    await screen.findByText('кофе');
    await act(()=>{document.dispatchEvent(new Event('visibilitychange'));});
    await screen.findByLabelText('Card type');
    expect((screen.getByLabelText('Card type') as HTMLSelectElement).value).toBe('en-ru');
    expect((screen.getByLabelText('Number of cards') as HTMLInputElement).value).toBe('7');
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/post') || url.endsWith('/word-pocket'))).toBe(false);
  });
});


it('keeps a lesson generation batch connected to its source and filtered collection',async()=>{
  const source={lesson_id:'lesson-one',title:'Museum visit',url:'/lessons/load/lesson-one?view=flashcards',first_page:2,last_page:4,report:[{added:1,reused:0,requested:1}]};
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.includes('/options')?settings:{...complete,source})));
  render(<GenerateCards batchId="batch" />);
  await screen.findByText('Your cards are ready');
  expect(screen.getByRole('link',{name:'Study flashcards'}).getAttribute('href')).toBe('#flashcards?lesson_id=lesson-one');
  expect(screen.getByRole('link',{name:/Back to lesson/}).getAttribute('href')).toBe(source.url);
  expect(screen.getByRole('link',{name:'Generate more'}).getAttribute('href')).toBe(source.url);
  expect(screen.queryByText(/make them from your vocabulary/)).toBeNull();
});

it('names a game source correctly and offers another game rather than regenerating the same saved pack',async()=>{
  const first_steps={lesson_id:'game:pairs',title:'Postcard Pairs',url:'/#games/session/game-one',study_url:'#flashcards?topic=First%20steps',reused:1};
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.includes('/options')?settings:{...complete,first_steps})));
  render(<GenerateCards batchId="batch"/>);await screen.findByText('Your cards are ready');
  expect(screen.getByRole('link',{name:/Back to game/}).getAttribute('href')).toBe(first_steps.url);
  expect(screen.getByRole('link',{name:'Choose another game'}).getAttribute('href')).toBe('#activities');
  expect(screen.getByRole('link',{name:'Study flashcards'}).getAttribute('href')).toBe(first_steps.study_url);
  expect(screen.queryByRole('link',{name:'Generate more'})).toBeNull();expect(screen.queryByRole('link',{name:/Back to lesson/})).toBeNull();
  expect(screen.getByText(/1 existing card is included/)).toBeTruthy();
});

it('offers existing lesson cards when a new revision reuses the whole set',async()=>{
  const source={lesson_id:'lesson-one',title:'Museum visit',url:'/lessons/load/lesson-one?view=flashcards',first_page:2,last_page:4,report:[{added:0,reused:5,requested:5}]};
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.includes('/options')?settings:{...complete,saved:0,total:0,items:[],source})));
  render(<GenerateCards batchId="batch" />);
  await screen.findByText('These cards are already in your collection');
  expect(screen.getByRole('link',{name:'Study flashcards'}).getAttribute('href')).toBe('#flashcards?lesson_id=lesson-one');
  expect(screen.queryByText('No cards were generated')).toBeNull();
});
