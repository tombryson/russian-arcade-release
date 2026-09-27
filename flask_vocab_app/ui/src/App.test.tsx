import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/preact';
import { App } from './App';

async function navigate(hash: string) {
  await act(() => {
    window.history.replaceState(null, '', `/#${hash}`);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}
const response = (value: unknown) => Promise.resolve({ ok: true, json: async () => value });
beforeEach(()=>vi.spyOn(window,'scrollTo').mockImplementation(()=>{}));
afterEach(() => {vi.unstubAllGlobals();vi.restoreAllMocks();});

describe('Russian Arcade activity home', () => {
  it('opens a direct chapter link and early test-out for a learner before any coin introduction',async()=>{
    window.history.replaceState(null,'','/#journey/chapter/first');
    const course={version:1,profile_id:'personal',band:'A1',unlocked_levels:['A1'],current_chapter_id:'first',progress:0,completed:false,chapters:[{id:'first',number:1,title:'The little post office',title_ru:'Маленькая почта',intro:'Your original letter stays sealed.',intro_ru:'Письмо закрыто.',status:'practice',progress:0,topics:[],activity_count:0,required_activity_count:2,last_attempt_id:null}]};
    const fetch=vi.fn((url:string)=>response(url==='/api/v1/course' ? course : {profile_id:'personal',balance:0,course,skill:{status:'not_calibrated'}}));
    vi.stubGlobal('fetch',fetch);render(<App initialProfile={{id:'personal',display_name:'Learner'}} initialOnboarding={{profile_id:'personal',coins_introduced:false,progress_introduced:false}}/>);
    expect(await screen.findByRole('heading',{name:'The little post office',level:1})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Test out of this milestone →'})).toBeTruthy();
    expect(screen.queryByRole('heading',{name:'Your first delivery'})).toBeNull();
    expect(fetch.mock.calls.some(([url])=>url==='/api/v1/course')).toBe(true);
    expect(fetch.mock.calls.some(([url])=>url.startsWith('/api/v1/journey'))).toBe(false);
  });

  it('opens the Games catalogue from navigation without starting or purchasing a game',async()=>{
    window.history.replaceState(null,'','/#home');
    const fetch=vi.fn((url:string)=>response(url==='/api/v1/games'?{profile_id:null,games:[]}:{profile_id:null,lessons:[],completed_count:0,complete:false,next_lesson:null}));
    vi.stubGlobal('fetch',fetch);render(<App initialProfile={null}/>);
    expect(screen.getByRole('link',{name:'Games',hidden:true}).getAttribute('href')).toBe('#games');
    await navigate('games');
    expect(await screen.findByRole('heading',{name:'Games',level:1})).toBeTruthy();
    expect(screen.getByLabelText('Activities').getAttribute('data-active')).toBe('true');
    expect(screen.getByRole('link',{name:'Games',hidden:true}).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link',{name:/Shop/}).getAttribute('href')).toBe('#shop');
    expect(fetch.mock.calls.every(([url])=>['/api/v1/games','/api/v1/first-steps'].includes(url))).toBe(true);
  });
  it.each(['pairs','mailbox-sort','missing-stamp','radio','detective','letter-back'])('opens the new %s game as a standalone activity',async id=>{
    window.history.replaceState(null,'',`/#games/${id}`);
    const fetch=vi.fn((url:string)=>response(url==='/api/v1/games'?{profile_id:null,games:[{id,title:'A discovered game',description:'A game from your lesson.',lesson_id:'bag',lesson_title:'What’s in the bag?',lesson_href:'#first-steps/bag',unlocked:true,new:true,active_session_id:null}]}:{}));
    vi.stubGlobal('fetch',fetch);render(<App initialProfile={null}/>);
    expect(await screen.findByRole('heading',{name:'A discovered game',level:1})).toBeTruthy();
    expect(screen.getByRole('button',{name:id==='radio'?'Tune in':'Let’s play'})).toBeTruthy();
    expect(screen.getByLabelText('Activities').getAttribute('data-active')).toBe('true');
    expect(fetch.mock.calls.every(([url])=>url==='/api/v1/games')).toBe(true);
  });
  it('opens an old post-office link as the chapter for a guest without loading the retired quiz', async () => {
    window.history.replaceState(null, '', '/#journey/post-office');
    const fetch=vi.fn((_url:string)=>response({profile_id:null,lessons:[],completed_count:0,complete:false,next_lesson:null}));
    vi.stubGlobal('fetch',fetch);
    render(<App initialProfile={null}/>);
    expect(await screen.findByRole('heading',{name:'First steps with Barsik'})).toBeTruthy();
    expect(window.location.hash).toBe('#first-steps');
    expect(fetch.mock.calls.every(([url])=>['/api/v1/first-steps','/api/v1/games'].includes(url))).toBe(true);
    expect(screen.queryByRole('heading',{name:/Create a profile/})).toBeNull();
  });
  it('keeps working activity routes discoverable without contacting household services in legacy mode', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(within(screen.getByRole('main')).getByRole('link', { name: /^Comprehension/ }).getAttribute('href')).toBe('/comprehension');
    expect(screen.getByText('Hello! I’m Barsik.')).toBeTruthy();
    await navigate('activities');
    for (const [name, href] of [['Comprehension', '/comprehension'], ['Word Jumble', '/word_jumble'], ['Translate a sentence', '/sentences'], ['Writing', '/writing'], ['Lessons', '/lessons'], ['^Speaking', '#speaking']]) {
      expect(within(screen.getByRole('main')).getByRole('link', { name: new RegExp(name) }).getAttribute('href')).toBe(href);
    }
    expect(screen.getByRole('link', { name: /Open existing Anki/ }).getAttribute('href')).toBe('/tools/anki/');
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Choose an activity.' }));
    expect(fetch.mock.calls.every(([url])=>['/api/v1/progression','/api/v1/first-steps','/api/v1/games'].includes(url))).toBe(true);
    expect(screen.queryByRole('link', {name:/^Conversation|^Live conversation/})).toBeNull();
  });
  it.each(['speaking','speaking/step','conversation','live-conversation'])('opens %s as Speaking without starting a call', async hash => {
    window.history.replaceState(null, '', `/#${hash}`);
    const fetch = vi.fn((url: string) => response(url.endsWith('/household')
      ? {adult:false,profile:{id:'personal',display_name:'Learner'},csrf_token:'csrf'}
      : {configured:true,notes_configured:true,max_seconds:300,sessions:[],scenarios:[]}));
    vi.stubGlobal('fetch',fetch);
    render(<App />);
    expect(await screen.findByRole('heading', {name:'Speaking'})).toBeTruthy();
    expect(window.location.hash).toBe('#speaking');
    expect(screen.queryByRole('group',{name:'Conversation mode'})).toBeNull();
    expect(screen.queryByRole('radio',{name:'Step-through',exact:true})).toBeNull();
    expect(screen.queryByRole('radio',{name:'Fluent conversation',exact:true})).toBeNull();
    expect(screen.getByLabelText('Activities').getAttribute('data-active')).toBe('true');
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/connect') || url === '/api/v1/conversations')).toBe(false);
  });
  it('preserves the curriculum level when opening and changing a scenario link',async()=>{
    window.history.replaceState(null,'','/#speaking/scenario/shop?level=A2');
    const fetch=vi.fn((url:string)=>response(url.endsWith('/household')
      ? {adult:false,profile:{id:'personal',display_name:'Learner'},csrf_token:'csrf'}
      : url.endsWith('/scenarios')
        ? {activity:{id:'speaking'},scenarios:[{id:'shop',title:'At the shops',title_ru:'В магазине',description:'Ask for what you need.',description_ru:'Попросите нужный товар.',role:'Shop assistant',role_ru:'Продавец',icon:'🛍️',sign:'МАГАЗИН',variant_count:2,levels:['A1','A2']}]}
        : {configured:true,notes_configured:true,max_seconds:300,sessions:[],scenario:{seed:'shop-link',scenario_id:'shop',title:'Find your size',description:'Ask for another size.',opening:'Какой размер вам нужен?',goals:[],target_level:url.includes('level=A2')?'A2':'A1'}}));
    vi.stubGlobal('fetch',fetch);render(<App/>);
    await screen.findByRole('heading',{name:'Find your size'});
    expect(fetch.mock.calls.filter(([url])=>url.includes('/options')).map(([url])=>url)).toEqual(['/api/v1/live-conversations/options?scenario_id=shop&level=A2']);
    await navigate('speaking/scenario/shop?level=A1');
    await vi.waitFor(()=>expect(fetch.mock.calls.filter(([url])=>url.includes('/options')).map(([url])=>url)).toEqual([
      '/api/v1/live-conversations/options?scenario_id=shop&level=A2',
      '/api/v1/live-conversations/options?scenario_id=shop&level=A1',
    ]));
    expect(fetch.mock.calls.some(([url])=>url==='/api/v1/live-conversations' || url==='/api/v1/step-conversations')).toBe(false);
  });
  it.each(['live-conversation/live-one','speaking/live-one'])('keeps saved live links working: %s', async hash => {
    window.history.replaceState(null, '', `/#${hash}`);
    vi.stubGlobal('fetch',vi.fn((url: string) => response(url.endsWith('/household')
      ? {adult:false,profile:{id:'personal',display_name:'Learner'},csrf_token:'csrf'} : url.endsWith('/options')
      ? {configured:true,notes_configured:true,max_seconds:300,sessions:[],scenarios:[]}
      : {id:'live-one',state:'completed',connected:false,captions:[{type:'session.output_transcript.delta',delta:'Здравствуйте!',start_ms:0,end_ms:1000}],recordings:[]})));
    render(<App />);
    expect(await screen.findByText('Здравствуйте!')).toBeTruthy();
    expect(window.location.hash).toBe('#speaking/live-one');
    expect(screen.getByRole('heading',{level:1,name:'Your conversation'})).toBeTruthy();
  });
  it('resumes a step-through link without opening a live conversation or regenerating it',async()=>{
    window.history.replaceState(null,'','/#speaking/step/guided-one');
    const fetch=vi.fn((url:string)=>response(url.endsWith('/household')
      ? {adult:false,profile:{id:'personal',display_name:'Learner'},csrf_token:'csrf'}
      : {id:'guided-one',state:'completed',scenario:{seed:'shop-one',title:'At the shop'},target_level:'A1',language:'en',created_at:1,error:null,retryable:false,turn_count:4,completed_turns:4,current_turn:null,transcript:[],ending:{russian:'Спасибо! До свидания!',english:'Thank you! Goodbye!'}}));
    vi.stubGlobal('fetch',fetch);render(<App />);
    expect(await screen.findByRole('heading',{name:'Conversation complete',level:1})).toBeTruthy();
    expect(window.location.hash).toBe('#speaking/step/guided-one');
    expect(fetch.mock.calls.some(([url])=>url==='/api/v1/step-conversations/guided-one')).toBe(true);
    expect(fetch.mock.calls.some(([url])=>url.includes('/live-conversations'))).toBe(false);
    expect(screen.getByLabelText('Activities').getAttribute('data-active')).toBe('true');
  });
  it.each(['conversation/old-one','speaking/recorded/old-one'])('opens recorded history under Speaking: %s', async hash => {
    window.history.replaceState(null, '', `/#${hash}`);
    const fetch = vi.fn((url: string) => response(url.endsWith('/household')
      ? {adult:false,profile:{id:'personal',display_name:'Learner'},csrf_token:'csrf'} : url.endsWith('/options')
      ? {configured:true,sessions:[],cases:[]}
      : {id:'old-one',mode:'conversation',state:'active',scenario:{opening:'Что будете пить?'},turns:[]}));
    vi.stubGlobal('fetch',fetch);render(<App />);
    await screen.findByText('Что будете пить?');
    expect(window.location.hash).toBe('#speaking/recorded/old-one');
    expect(screen.getByRole('heading',{name:'Saved conversation'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:/Tap to speak|Step into the café/})).toBeNull();
    expect(fetch.mock.calls.some(([url]) => url === '/api/v1/conversations')).toBe(false);
  });
  it.each(['speech-lab','speaking/lab'])('keeps the diagnostic lab reachable: %s', async hash => {
    window.history.replaceState(null, '', `/#${hash}`);
    vi.stubGlobal('fetch',vi.fn((url: string) => response(url.endsWith('/household')
      ? {adult:false,profile:{id:'personal',display_name:'Learner'},csrf_token:'csrf'}
      : {configured:true,sessions:[],cases:[]})));
    render(<App />);
    expect(await screen.findByRole('button',{name:/Start a speech test/})).toBeTruthy();
    expect(window.location.hash).toBe('#speaking/lab');
  });
  it('keeps the passport retired and preserves useful destinations for old links', async () => {
    render(<App />);
    await navigate('passport');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('A small letter.');
    expect(screen.queryByText(/passport|Misha|moon picnic/i)).toBeNull();
    await navigate('letter');
    expect(screen.getByRole('heading', { name: 'Choose an activity.' })).toBeTruthy();
    await navigate('pocket');
    expect(screen.getByRole('link', { name: /Open vocabulary library/ }).getAttribute('href')).toBe('/vocab');
    await navigate('main');
    expect(screen.getByRole('heading', { name: 'My words' })).toBeTruthy();
  });
  it('preserves direct links to the practice choices without leaving Home', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    render(<App />);
    await navigate('choose-practice');
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Choose what to practise' }));
    expect(within(screen.getByRole('main')).getByRole('link', { name: /^Comprehension/ }).getAttribute('href')).toBe('/comprehension');
    expect(screen.getByRole('link', { name: /^My words Find/ }).getAttribute('href')).toBe('/vocab');
    expect(screen.getByRole('link', { name: 'Home' }).getAttribute('aria-current')).toBe('page');
    expect(fetch.mock.calls.every(([url])=>['/api/v1/progression','/api/v1/first-steps','/api/v1/games'].includes(url))).toBe(true);
    await navigate('activities');
    await navigate('choose-practice');
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Choose what to practise' }));
  });
  it('opens the introductions without a duplicate greeting quiz or an early reward', async () => {
    const fetch = vi.fn((url:string,options?:RequestInit)=>response(['/api/v1/first-steps','/api/v1/games'].includes(url) ? {profile_id:null,lessons:Array(5).fill({}),next_lesson:{id:'hello',position:1,title:'Hello, Barsik!',description:'Meet Barsik.',status:'available',href:'#first-delivery'},complete:false} : url==='/api/v1/onboarding' ? {profile_id:null,coins_introduced:true,progress_introduced:JSON.parse(String(options?.body)).milestone==='progress'} : url==='/api/v1/onboarding/practice' ? {profile_id:null,attempt:null,pending_reward:0,reward:null} : {})); vi.stubGlobal('fetch', fetch);
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: /First steps · 1 of 5/ }));
    const introduction = await screen.findByRole('heading', { name: 'Before we set off…' });
    await vi.waitFor(() => expect(document.activeElement).toBe(introduction));
    expect(window.location.hash).toBe('#first-delivery');
    expect(screen.getByRole('link', { name: 'Home' }).getAttribute('aria-current')).toBe('page');
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByRole('button', { name: 'Learn your first words' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Which word means “hello”?' })).toBeNull();
    expect(screen.queryByText(/No coins were added/)).toBeNull();
    expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST').every(([url])=>url==='/api/v1/onboarding')).toBe(true);
  });
  it('resumes completed guest practice and points an unselected household to learner setup', async () => {
    window.history.replaceState(null, '', '/#first-delivery');
    const fetch = vi.fn((url:string,options?:RequestInit)=>response(url==='/api/v1/onboarding' ? {profile_id:null,coins_introduced:true,progress_introduced:JSON.parse(String(options?.body)).milestone==='progress'} : url==='/api/v1/onboarding/practice' ? {profile_id:null,attempt:{id:'intro',version:'first-delivery-v2',phase:'completed',question_index:3,total_questions:3,question:null,answers:[],completed_at:1},pending_reward:3,reward:{amount:3,status:'pending',awarded_now:false}} : { configured: true, adult: false, profile: null, csrf_token: 'test-csrf' }));
    vi.stubGlobal('fetch', fetch);
    render(<App householdEnabled />);
    await screen.findByRole('heading', { name: 'Your first lesson is complete.' });
    expect(screen.getByRole('link', { name: 'Choose a learner' }).getAttribute('href')).toBe('/post/household');
    expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/household')).toHaveLength(1);
    expect(fetch.mock.calls.every(([url])=>['/api/v1/household','/api/v1/onboarding','/api/v1/onboarding/practice'].includes(url))).toBe(true);
  });
  it('shows the setup action rather than fake progress when no learner is selected', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ configured: true, adult: false, profile: null, csrf_token: 'test-csrf' })));
    render(<App householdEnabled />);
    expect(await screen.findByRole('heading', { name: 'Who’s learning?' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /Continue practice/ })).toBeNull();
  });
  it('uses actual resumable sessions and does not offer unfinished native decks for play', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => response(url.endsWith('/household') ? { configured: true, adult: false, profile: { id: 'river', display_name: 'River' }, csrf_token: 'test-csrf' }
      : url.endsWith('/post') ? { profile: { id: 'river', display_name: 'River' }, content: [{ version_id: 'deck1', title: 'Unplayable native deck', kind: 'deck' }], sessions: [{ id: 'saved-session', title: 'Food words', status: 'active', content_status: 'published' }] }
        : { profile_id: 'river', evidence: [] })));
    render(<App householdEnabled />);
    expect((await screen.findByRole('link', { name: /Continue: Food words/ })).getAttribute('href')).toBe('#practice/saved-session');
    expect(screen.queryByText('Unplayable native deck')).toBeNull();
    expect(within(screen.getByRole('main')).queryByRole('link', { name: /Word Jumble/ })).toBeNull();
  });
  it('starts approved practice with the selected learner and a CSRF-protected command', async () => {
    const fetch = vi.fn((url: string, options?: RequestInit) => response(url.endsWith('/household') ? { configured: true, adult: false, profile: { id: 'river', display_name: 'River' }, csrf_token: 'test-csrf' }
      : url.endsWith('/post') ? { profile: { id: 'river', display_name: 'River' }, content: [{ version_id: 'food1', title: 'Food words', kind: 'activity' }], sessions: [] }
        : url.endsWith('/word-pocket') ? { profile_id: 'river', evidence: [] }
          : options?.method === 'POST' ? { id: 'saved-session' } : { id: 'saved-session', profile_id: 'river', title: 'Food words', status: 'active', completed_items: 0, total_items: 1, attempts: [], item: { id: 'apple', prompt: 'Choose apple', choices: [{ id: 'yes', text: 'яблоко' }], has_hint: false } }));
    vi.stubGlobal('fetch', fetch);
    render(<App householdEnabled />);
    fireEvent.click(await screen.findByRole('button', { name: 'Start practice: Food words' }));
    await screen.findByRole('heading', { name: 'Question 1 of 1' });
    const call = fetch.mock.calls.find(([url]) => url === '/api/v1/learning-sessions');
    const options = call?.[1];
    expect(options?.headers).toMatchObject({ 'X-CSRF-Token': 'test-csrf' });
    expect(JSON.parse(options?.body as string)).toMatchObject({ profile_id: 'river', version_id: 'food1' });
    expect(window.location.hash).toBe('#practice/saved-session');
  });
});

describe('Personal user sessions', () => {
  it.each(['top','sidebar'] as const)('shows the correct account entry throughout the %s layout', navigationLayout => {
    window.history.replaceState(null, '', '/#activities');
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'demo-preview',balance:0,skill:{status:'not_calibrated',skills:[]}})));
    const navigation={title:'Activities & tools',more:'More tools',activities:[],tools:[]};
    const profile={id:'demo-preview',display_name:'Demo'};
    const {container,rerender}=render(<App navigation={navigation} navigationLayout={navigationLayout} initialProfile={profile} accountMode="preview" signInAvailable />);
    const control=()=>container.querySelector(`${navigationLayout==='sidebar' ? '.sidebar-account' : 'header.top'} .user-session-link`)!;
    expect(control()).toBe(screen.getByRole('link',{name:'Sign in'}));
    expect(control().textContent).toBe('Sign in');
    expect(control().getAttribute('href')).toBe('/trial/account');
    expect(container.querySelectorAll('[data-user-session]')).toHaveLength(1);
    rerender(<App navigation={navigation} navigationLayout={navigationLayout} initialProfile={profile} accountMode="preview" language="ru" />);
    expect(control()).toBe(screen.getByRole('link',{name:'Аккаунт'}));
    expect(control().textContent).toBe('Аккаунт');
    expect(control().getAttribute('href')).toBe('/trial/account');
    rerender(<App navigation={navigation} navigationLayout={navigationLayout} initialProfile={{id:'hosted-personal',display_name:'Tom'}} accountMode="hosted" />);
    expect(control()).toBe(screen.getByRole('link',{name:'Account: Tom'}));
    expect(control().getAttribute('href')).toBe('/trial/account');
    expect(control().getAttribute('data-profile-id')).toBe('hosted-personal');
    expect(control().textContent).toBe('T');
    rerender(<App navigation={navigation} navigationLayout={navigationLayout} initialProfile={{id:'tom',display_name:'Tom'}} />);
    expect(control()).toBe(screen.getByRole('link',{name:'Profile: Tom'}));
    expect(control().getAttribute('href')).toBe('/post/profiles');
  });
  it('keeps the introduction public and offers a profile without fetching private progress', async () => {
    window.history.replaceState(null, '', '/#home');
    const fetch=vi.fn(); vi.stubGlobal('fetch',fetch);
    render(<App initialProfile={null} />);
    expect(screen.getByRole('link',{name:'Choose a profile'}).getAttribute('href')).toBe('/post/profiles');
    expect(screen.getByText('Hello! I’m Barsik.')).toBeTruthy();
    expect(fetch.mock.calls.every(([url])=>['/api/v1/first-steps','/api/v1/games'].includes(url))).toBe(true);
    await navigate('flashcards');
    expect(screen.getByRole('heading',{name:'Who’s learning?'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Choose your profile'}).getAttribute('href')).toBe('/post/profiles');
    expect(screen.queryByText(/grown-up/i)).toBeNull();
    expect(fetch.mock.calls.every(([url])=>['/api/v1/first-steps','/api/v1/games'].includes(url))).toBe(true);
  });
  it('identifies the selected profile from the server on every home visit', () => {
    window.history.replaceState(null, '', '/#home');
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'tom',wallet:0,journey:{worlds:[]}})));
    render(<App initialProfile={{id:'tom',display_name:'Tom'}} />);
    const link=screen.getByRole('link',{name:'Profile: Tom'});
    expect(link.getAttribute('data-profile-id')).toBe('tom');
    expect(link.textContent).toBe('T');
  });
});

describe('Stepwise header introduction',()=>{
  it('reveals coins on the second page and the bar on the third, including with a preview URL',async()=>{
    window.history.replaceState(null,'','/?progress-preview=50#home');
    const introduction={profile_id:'tom',coins_introduced:false,progress_introduced:false};
    const calls:string[]=[];
    vi.stubGlobal('fetch',vi.fn((url:string,options?:RequestInit)=>{
      if (url==='/api/v1/onboarding') {
        const milestone=JSON.parse(String(options?.body)).milestone;calls.push(milestone);
        introduction.coins_introduced=true;
        if (milestone==='progress') introduction.progress_introduced=true;
        return response({...introduction});
      }
      return response({profile_id:'tom',balance:42,skill:{status:'not_calibrated',skills:[]}});
    }));
    render(<App initialProfile={{id:'tom',display_name:'Tom'}} initialOnboarding={{...introduction}} />);
    expect(screen.queryByRole('link',{name:/Lingo coins/})).toBeNull();
    expect(document.querySelector('.skill-rail')).toBeNull();
    await navigate('first-delivery');
    await screen.findByRole('link',{name:'Lingo coins: 42'});
    expect(screen.getByRole('heading',{name:'Earn coins as you learn.'})).toBeTruthy();
    expect(document.querySelector('.skill-rail')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Continue'}));
    await vi.waitFor(()=>expect(document.querySelector('.skill-rail')).not.toBeNull());
    expect(screen.getByRole('heading',{name:'Help Barsik reach the next stop.'})).toBeTruthy();
    await vi.waitFor(()=>expect(calls).toEqual(['coins','progress']));
    await navigate('home');
    expect(screen.getByRole('link',{name:'Lingo coins: 42'})).toBeTruthy();
    expect(document.querySelector('.skill-rail')).toBeTruthy();
  });
  it('restores introduced controls from the profile snapshot without another tutorial visit',()=>{
    vi.stubGlobal('fetch',vi.fn(()=>response({profile_id:'tom',balance:42,skill:{status:'not_calibrated',skills:[]}})));
    render(<App initialProfile={{id:'tom',display_name:'Tom'}} initialOnboarding={{profile_id:'tom',coins_introduced:true,progress_introduced:true}} />);
    expect(screen.getByRole('link',{name:/Lingo coins/})).toBeTruthy();
    expect(document.querySelector('.skill-rail')).toBeTruthy();
  });
  it('introduces the guest counter and starting bar before profile creation',async()=>{
    vi.stubGlobal('fetch',vi.fn((url:string,options?:RequestInit)=>response(url==='/api/v1/onboarding/practice' ? {profile_id:null,attempt:null,pending_reward:0,reward:null} : {profile_id:null,coins_introduced:true,progress_introduced:JSON.parse(String(options?.body)).milestone==='progress'})));
    render(<App initialProfile={null} />);
    await navigate('first-delivery');
    await screen.findByRole('link',{name:'Lingo coins: 0'});
    expect(document.querySelector('.skill-rail')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Continue'}));
    await vi.waitFor(()=>expect(document.querySelector('.skill-rail-runner')).toBeTruthy());
    expect(screen.queryByText(/Loading skill progress/)).toBeNull();
  });
});

it('uses the published course welcome for a signed-out visitor',async()=>{
  window.history.replaceState(null,'','/#home');
  vi.stubGlobal('fetch',vi.fn((url:string)=>response(url==='/api/v1/first-steps'?{profile_id:null,lessons:[{id:'hello',position:1,title:'Hello, Barsik!',description:'Learn your first words.',status:'available',href:'#first-delivery'}],next_lesson:{id:'hello',position:1,title:'Hello, Barsik!',description:'Learn your first words.',status:'available',href:'#first-delivery'},complete:false}:{})));
  render(<App initialProfile={null} defaultCourseRelease="a1-journey-v2"/>);
  expect(await screen.findByText('Your first delivery · a little adventure')).toBeTruthy();
  expect(screen.queryByRole('link',{name:/See the journey/})).toBeNull();expect(screen.queryByRole('link',{name:/See all five lessons/})).toBeNull();
});
