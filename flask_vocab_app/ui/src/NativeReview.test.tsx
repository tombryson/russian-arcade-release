import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/preact';
import { NativeReview } from './NativeReview';
import { Flashcards } from './Flashcards';
import { api } from './learning-api';
import type { CardOverview, ReviewSession } from './review-types';

// jsdom does not implement the native dialog methods used by the browser.
const nativeShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal');
const nativeClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close');
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {configurable: true, value: function(this: HTMLDialogElement) {this.open = true;}});
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {configurable: true, value: function(this: HTMLDialogElement) {
    if (!this.open) return;
    this.open = false;
    this.dispatchEvent(new Event('close'));
  }});
});
afterAll(() => {
  if (nativeShowModal) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', nativeShowModal);
  else delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
  if (nativeClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', nativeClose);
  else delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
});

const response=(value:unknown,ok=true)=>Promise.resolve({ok,json:async()=>value});
const front:ReviewSession={id:'session',profile_id:'learner',revision:0,status:'active',phase:'front',total_cards:3,practised_cards:0,skipped_cards:0,server_now:1000,feedback:null,can_undo:false,
  item:{id:'occurrence',card_id:'card',type:'basic',direction:'ru-en',title:'Suggesting a game',title_ru:'Предлагаем игру',prompt:'Давай играть!',context:'Давай играть!',has_hint:true,assisted:false,assets:[]}};
const shown:ReviewSession={...front,revision:1,phase:'revealed',item:{...front.item!,answer:'Let’s play!',explanation:'Here давай suggests doing something together.'}};
const rated:ReviewSession={...front,revision:2,phase:'feedback',item:null,practised_cards:1,can_undo:true,feedback:{rating:'good',assisted:false,answer:'Let’s play!',prompt:'Давай играть!',due_at:1600}};
const nextCard:ReviewSession={...front,revision:3,practised_cards:1,can_undo:true,item:{...front.item!,id:'next-occurrence',card_id:'next-card',prompt:'Следующая карточка',context:undefined}};
const overview:CardOverview={profile_id:'learner',profile_name:'Learner',active_session_id:null,server_now:1000,new_limit:5,
  counts:{cards:2,words:1,due:1,new:1,new_allowance:4,ready:2,learning:1,reviewing:0,suspended:0,buried:0,practised_today:1,answers_today:3,next_due_at:null},
  cards:[{id:'card',version_id:'version',lemma:'давать',title:'Suggesting a game',direction:'ru-en',prompt:'Давай играть!',answer:'Let’s play!',context:'Давай играть!',decks:[{content_id:'deck',title:'Everyday situations'}],status:'learning',due:true,buried:false,due_at:900,revision:2}]};
afterEach(()=>vi.unstubAllGlobals());

describe('Native reviewer',()=>{
  it('keeps answers absent before reveal and records a self-report only afterwards',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/next')?nextCard:url.endsWith('/reveal')?shown:url.endsWith('/reviews')?rated:front));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);
    await screen.findByRole('button',{name:/Show answer/});expect(screen.queryByText('Let’s play!')).toBeNull();expect(screen.queryByRole('button',{name:'Good'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:/Show answer/}));await screen.findByText('Let’s play!');
    expect(screen.getByText('Here давай suggests doing something together.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Good'}));await screen.findByRole('heading',{name:'Следующая карточка'});
    expect(screen.queryByText('Answer saved')).toBeNull();expect(screen.queryByRole('button',{name:/Continue/})).toBeNull();
    expect(screen.queryByText('Let’s play!')).toBeNull();expect(screen.getByRole('button',{name:/Show answer/})).toBeTruthy();
    expect(screen.queryByText(/correct|coins earned/i)).toBeNull();
    const [,options]=fetch.mock.calls.find(([url])=>url.endsWith('/reviews')) as unknown as [string,RequestInit];
    expect(JSON.parse(options.body as string)).toMatchObject({item_id:'occurrence',rating:'good',expected_revision:1});
  });
  it('prevents rapid double taps and reuses an unconfirmed command on retry',async()=>{
    let attempts=0;
    const fetch=vi.fn((url:string,_options?:RequestInit)=>url.endsWith('/reviews')?++attempts===1?Promise.reject(new TypeError('connection lost')):response(rated):response(url.endsWith('/next')?nextCard:shown));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);
    const button=await screen.findByRole('button',{name:'Good'});
    await act(()=>{fireEvent.click(button);fireEvent.click(button);});
    fireEvent.click(await screen.findByRole('button',{name:'Retry saving'}));await screen.findByRole('heading',{name:'Следующая карточка'});
    const calls=fetch.mock.calls.filter(([url])=>url.endsWith('/reviews')) as unknown as [string,RequestInit][];
    expect(calls).toHaveLength(2);expect(calls[0][1].body).toEqual(calls[1][1].body);
  });
  it('recovers current server state after a stale tab without submitting another rating',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>url.endsWith('/reviews')?response({error:{code:'stale_revision',message:'changed',current_session:nextCard}},false):response(shown));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);fireEvent.click(await screen.findByRole('button',{name:'Good'}));
    await screen.findByRole('heading',{name:'Следующая карточка'});expect(screen.getByRole('alert').textContent).toContain('another tab');expect(screen.queryByRole('button',{name:'Retry saving'})).toBeNull();
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/reviews'))).toHaveLength(1);
  });
  it('records a confusing-card report separately from ratings',async()=>{
    const skipped={...front,revision:1,phase:'feedback',item:null,skipped_cards:1};
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/report')?skipped:front));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);await screen.findByRole('button',{name:/Show answer/});
    fireEvent.click(screen.getByText('Something wrong with this card?'));fireEvent.click(screen.getByRole('button',{name:'Translation seems wrong'}));
    await screen.findByText('Card set aside.');expect(screen.queryByRole('button',{name:'Undo last answer'})).toBeNull();
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/reviews'))).toBe(false);
  });
  it('resumes an old confirmation automatically and offers undo on the next card',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/undo')?{...shown,revision:4,item:{...shown.item,id:'new-occurrence'}}:url.endsWith('/next')?nextCard:rated));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);
    await screen.findByRole('heading',{name:'Следующая карточка'});
    fireEvent.click(await screen.findByRole('button',{name:'Undo last answer'}));await screen.findByRole('button',{name:'Good'});
    expect(screen.getByText('Here давай suggests doing something together.')).toBeTruthy();expect(fetch.mock.calls.filter(([url])=>url.endsWith('/undo'))).toHaveLength(1);
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/reviews'))).toBe(false);
  });
  it('retries only the next-card request if the rating was already saved',async()=>{
    let attempts=0;
    const fetch=vi.fn((url:string,_options?:RequestInit)=>url.endsWith('/next')?++attempts===1?Promise.reject(new TypeError('connection lost')):response(nextCard):response(url.endsWith('/reviews')?rated:shown));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);
    fireEvent.click(await screen.findByRole('button',{name:'Good'}));
    fireEvent.click(await screen.findByRole('button',{name:'Retry saving'}));await screen.findByRole('heading',{name:'Следующая карточка'});
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/reviews'))).toHaveLength(1);
    const calls=fetch.mock.calls.filter(([url])=>url.endsWith('/next'));
    expect(calls).toHaveLength(2);expect(calls[0][1]!.body).toBe(calls[1][1]!.body);
  });
  it('goes straight to the session summary after the final rating, with undo available',async()=>{
    const complete:ReviewSession={...rated,revision:3,status:'completed',phase:'completed',feedback:null};
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/next')?complete:url.endsWith('/reviews')?rated:url.endsWith('/undo')?{...shown,revision:4}:shown));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);
    fireEvent.click(await screen.findByRole('button',{name:'Good'}));await screen.findByRole('heading',{name:'Practice saved.'});
    expect(screen.queryByText('Answer saved')).toBeNull();expect(screen.queryByRole('button',{name:/Continue/})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Undo last answer'}));await screen.findByRole('button',{name:'Good'});
  });
  it('uses simple Russian controls and keeps the cloze target out of the front',async()=>{
    const cloze={...front,item:{...front.item!,type:'cloze',direction:'ru-cloze',title:'яблоко',title_ru:'яблоко',context:undefined,prompt:'Я ем [[blank]].'}};
    vi.stubGlobal('fetch',vi.fn(()=>response(cloze)));render(<NativeReview sessionId="session" profileId="learner" language="ru" />);
    await screen.findByRole('button',{name:/Показать ответ/});expect(screen.queryByText('яблоко')).toBeNull();expect(screen.getByText('[...]')).toBeTruthy();
  });
  it('does not grade with a keyboard shortcut before reveal or on a held key',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/reveal')?shown:front));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);const heading=await screen.findByRole('heading',{name:'Давай играть!'});
    fireEvent.keyDown(heading,{key:'2'});fireEvent.keyDown(heading,{key:' ',repeat:true});expect(fetch.mock.calls).toHaveLength(1);
    fireEvent.keyDown(heading,{key:' '});await screen.findByRole('button',{name:'Good'});expect(fetch.mock.calls.some(([url])=>url.endsWith('/reviews'))).toBe(false);
  });
  it('finishes a withdrawn session without presenting its answer',async()=>{
    const unavailable={...front,item:null};
    const fetch=vi.fn((url:string,_options?:RequestInit)=>url.endsWith('/finish')?response({...unavailable,revision:1,status:'completed',phase:'completed'}):response({error:{code:'content_unavailable',message:'This card was withdrawn.',current_session:unavailable}},false));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);fireEvent.click(await screen.findByRole('button',{name:'Finish for now'}));await screen.findByText('Practice saved.');expect(screen.queryByText('Let’s play!')).toBeNull();
  });
});

describe('Flashcard overview',()=>{
  it('uses server counts and opens one selected learner session with CSRF',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url==='/api/v1/household'?{csrf_token:'token'}:url==='/api/v1/review-sessions'?front:overview));vi.stubGlobal('fetch',fetch);await api('/api/v1/household');
    render(<Flashcards profileId="learner" />);
    fireEvent.change(await screen.findByRole('combobox',{name:'Session size'}),{target:{value:'20'}});
    expect(screen.getByText('Due').nextElementSibling?.textContent).toBe('1');
    expect(screen.getByText('Reviewed today').nextElementSibling?.textContent).toBe('1');
    fireEvent.click(screen.getByRole('button',{name:/Start practice/}));
    await vi.waitFor(()=>expect(window.location.hash).toBe('#review/session'));
    const [,options]=fetch.mock.calls.find(([url])=>url==='/api/v1/review-sessions') as unknown as [string,RequestInit];
    expect(options.headers).toMatchObject({'X-CSRF-Token':'token'});expect(JSON.parse(options.body as string)).toMatchObject({profile_id:'learner',scope:{},size:20});
  });
  it('resumes an existing session without another start command',async()=>{
    const fetch=vi.fn(()=>response({...overview,active_session_id:'existing'}));vi.stubGlobal('fetch',fetch);render(<Flashcards profileId="learner" />);
    const resume=await screen.findByRole('button',{name:/Continue practice/});
    expect(screen.queryByRole('combobox',{name:'Session size'})).toBeNull();
    fireEvent.click(resume);expect(window.location.hash).toBe('#review/existing');expect(fetch.mock.calls).toHaveLength(1);
  });
  it('browses card history without a review or scheduling write',async()=>{
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/history')?{profile_id:'learner',card_id:'card',events:[]}:overview));vi.stubGlobal('fetch',fetch);render(<Flashcards profileId="learner" />);
    await screen.findByRole('button',{name:/Start practice/});fireEvent.click(screen.getByRole('button',{name:'Open card: давать'}));fireEvent.click(screen.getByRole('button',{name:'History'}));await screen.findByText('No reviews yet.');
    expect(fetch.mock.calls.every((call)=>(call[1] as RequestInit)?.method==='GET')).toBe(true);
  });
});

describe('Rich card presentation',()=>{
  it('shows the image and separate recordings, changes playback speed, and reveals the example translation with the answer',async()=>{
    const assets=[{id:'picture',role:'prompt',kind:'image' as const,media_type:'image/png'},{id:'word',role:'prompt',kind:'word_audio' as const,media_type:'audio/mpeg'},{id:'sentence',role:'prompt',kind:'sentence_audio' as const,media_type:'audio/mpeg'}];
    const rich={...front,item:{...front.item!,assets,metadata:{pos:'VERB',grammar:{number:'plur'},topics:['daily_life'],lemma_difficulty:2}}};
    const fetch=vi.fn((url:string)=>response(url.endsWith('/reveal')?{...shown,item:{...rich.item,answer:'Let’s play!',context_meaning:'Let’s play a game together.'}}:rich));vi.stubGlobal('fetch',fetch);
    render(<NativeReview sessionId="session" profileId="learner" />);
    await screen.findByRole('img',{name:'Illustration of the example sentence'});
    expect(screen.getByLabelText('Word: Russian audio').getAttribute('src')).toBe('/api/v1/assets/word');
    expect(screen.getByLabelText('Example: Russian audio').getAttribute('src')).toBe('/api/v1/assets/sentence');
    expect((screen.getByLabelText('Example: playback speed') as HTMLSelectElement).value).toBe('1');
    fireEvent.change(screen.getByLabelText('Example: playback speed'),{target:{value:'0.75'}});
    expect((screen.getByLabelText('Example: Russian audio') as HTMLAudioElement).playbackRate).toBe(0.75);
    expect(screen.getByText('Verb')).toBeTruthy();expect(screen.getByText('Plural')).toBeTruthy();expect(screen.queryByText('Let’s play a game together.')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:/Show answer/}));expect(await screen.findByText('Let’s play a game together.')).toBeTruthy();
  });
  it('keeps grammar, difficulty and sort filters when searching the library',async()=>{
    const value={...overview,facets:{decks:[],topics:['food'],pos:['NOUN'],cases:['nomn']}};
    const fetch=vi.fn((_url:string)=>response(value));vi.stubGlobal('fetch',fetch);render(<Flashcards profileId="learner" personal />);
    fireEvent.click(await screen.findByRole('button',{name:/^Filters/}));
    fireEvent.change(screen.getByLabelText('Word type'),{target:{value:'NOUN'}});fireEvent.change(screen.getByLabelText('Case'),{target:{value:'nomn'}});
    fireEvent.change(screen.getByLabelText('Difficulty'),{target:{value:'2'}});fireEvent.change(screen.getByLabelText('Sort collection'),{target:{value:'alphabetical'}});
    fireEvent.click(screen.getByRole('button',{name:'Apply selection'}));
    await vi.waitFor(()=>expect(fetch.mock.calls.some(call=>String(call[0]).includes('pos=NOUN') && String(call[0]).includes('case=nomn') && String(call[0]).includes('difficulty=2') && String(call[0]).includes('sort=alphabetical'))).toBe(true));
    await screen.findByRole('button',{name:/^Filters/});
    expect((screen.getByLabelText('Word type') as HTMLSelectElement).value).toBe('NOUN');
    expect((screen.getByLabelText('Sort collection') as HTMLSelectElement).value).toBe('alphabetical');
    fireEvent.input(screen.getByRole('searchbox',{name:'Search cards'}),{target:{value:'давать'}});
    fireEvent.click(screen.getByRole('button',{name:'Search'}));
    await vi.waitFor(()=>{
      const query=new URL(String(fetch.mock.calls.at(-1)![0]),'http://localhost').searchParams;
      expect(Object.fromEntries(query)).toMatchObject({q:'давать',pos:'NOUN',case:'nomn',difficulty:'2',sort:'alphabetical'});
    });
  });
});

describe('Anki cloze recall',()=>{
  it.each([['Again','again','1'],['Hard','hard','2'],['Good','good','3'],['Easy','easy','4']])('saves %s by button and keyboard, including after a hint',async(label,rating,key)=>{
    const assisted={...shown,item:{...shown.item!,assisted:true,hint:'A hint'}};
    const saved={...rated,feedback:{...rated.feedback!,rating,assisted:true}};
    const fetch=vi.fn((url:string,_options?:RequestInit)=>response(url.endsWith('/next')?nextCard:url.endsWith('/reviews')?saved:assisted));vi.stubGlobal('fetch',fetch);
    const view=render(<NativeReview sessionId="session" profileId="learner" />);
    fireEvent.click(await screen.findByRole('button',{name:label}));
    await screen.findByRole('heading',{name:'Следующая карточка'});
    let calls=fetch.mock.calls.filter(([url])=>url.endsWith('/reviews'));
    expect(JSON.parse(calls[0][1]!.body as string).rating).toBe(rating);
    view.unmount();fetch.mockClear();
    render(<NativeReview sessionId="session" profileId="learner" />);
    fireEvent.keyDown(await screen.findByRole('heading',{name:'Давай играть!'}),{key});
    await screen.findByRole('heading',{name:'Следующая карточка'});
    calls=fetch.mock.calls.filter(([url])=>url.endsWith('/reviews'));
    expect(calls).toHaveLength(1);expect(JSON.parse(calls[0][1]!.body as string).rating).toBe(rating);
  });
  it('shows English on the front, links only the revealed Russian answer, and keeps the mnemonic optional',async()=>{
    const url='https://en.openrussian.org/ru/'+encodeURIComponent('конструкция');
    const cloze:ReviewSession={...front,item:{...front.item!,type:'cloze',direction:'ru-cloze',context:undefined,
      prompt:'Я занимаюсь изучением [[blank]] в русском языке.',cue_en:'structures',dictionary_url:url,
      assets:[{id:'scene',role:'prompt',kind:'image',media_type:'image/png'}]}};
    const reveal:ReviewSession={...cloze,phase:'revealed',revision:1,item:{...cloze.item!,answer:'конструкций',cue_en:'structures',hint:'Think of building blocks.',
      context:'Я занимаюсь изучением конструкций в русском языке.',context_meaning:'I am studying constructions in Russian.',
      assets:[...cloze.item!.assets,{id:'word',role:'answer',kind:'word_audio',media_type:'audio/mpeg'},{id:'sentence',role:'answer',kind:'sentence_audio',media_type:'audio/mpeg'}]}};
    vi.stubGlobal('fetch',vi.fn((endpoint:string)=>response(endpoint.endsWith('/reveal')?reveal:cloze)));
    render(<NativeReview sessionId="session" profileId="learner" />);
    await screen.findByRole('button',{name:/Show answer/});
    expect(screen.getByText('structures')).toBeTruthy();expect(screen.queryByText('Think of building blocks.')).toBeNull();expect(screen.queryByText('English cue')).toBeNull();
    // Older cached responses may contain a dictionary URL; the front must still never render it.
    expect(screen.getByText('[...]').closest('a')).toBeNull();expect(document.querySelector('a[href*="openrussian.org"]')).toBeNull();
    expect(screen.getByRole('img',{name:'Illustration of the example sentence'})).toBeTruthy();
    expect(screen.queryByText('конструкций')).toBeNull();expect(screen.queryByText('I am studying constructions in Russian.')).toBeNull();
    expect(screen.queryByLabelText('Word: Russian audio')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:/Show answer/}));
    await screen.findByText('I am studying constructions in Russian.');
    expect(screen.getByText('structures')).toBeTruthy();expect(screen.queryByText('English cue')).toBeNull();
    const hint=screen.getByText('Think of building blocks.').closest('details')!;
    expect(hint.open).toBe(false);
    fireEvent.click(screen.getByText('Hint'));
    await vi.waitFor(()=>expect(hint.open).toBe(true));
    fireEvent.click(screen.getByText('Hint'));
    await vi.waitFor(()=>expect(hint.open).toBe(false));
    for(const link of screen.getAllByRole('link',{name:'конструкций'})) {
      expect(link.getAttribute('href')).toBe(url);expect(link.getAttribute('target')).toBe('_blank');
    }
    expect(screen.getByLabelText('Word: Russian audio')).toBeTruthy();expect(screen.getByLabelText('Example: Russian audio')).toBeTruthy();
    for(const name of ['Again','Hard','Good','Easy']) expect(screen.getByRole('button',{name})).toBeTruthy();
  });
  it('keeps all four labels in collection history',async()=>{
    const events=['again','hard','good','easy'].map(rating=>({rating,at:1000,due_at:1600,assisted:false,undone:false}));
    vi.stubGlobal('fetch',vi.fn((url:string)=>response(url.endsWith('/history')?{profile_id:'learner',card_id:'card',events}:overview)));
    render(<Flashcards profileId="learner" />);
    await screen.findByRole('button',{name:/Start practice/});
    fireEvent.click(screen.getByRole('button',{name:'Open card: давать'}));
    fireEvent.click(screen.getByRole('button',{name:'History'}));await screen.findByText(/· Hard/);
    for(const label of ['Again','Hard','Good','Easy']) expect(screen.getByText(new RegExp('· '+label))).toBeTruthy();
  });
});
