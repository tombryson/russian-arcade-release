import {GameLanguage} from './GameLocale';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {GameCatalogue,JourneyGame,traceRoute} from './JourneyGames';
import type {GameBoard,GameCatalogueState,GameRound,GameState,GameSummary,JourneyGameId} from './journey-games-api';
import {AudioClue} from './GameAudio';

const games:GameSummary[]=[
  {id:'pack-bag',title:'Pack the bag',description:'Help Barsik choose what to take.',lesson_id:'bag',lesson_title:'What’s in the bag?',lesson_href:'#first-steps/bag',unlocked:true,unlock:{required_coins:12,earned_coins:12,remaining_coins:0},new:true,active_session_id:null},
  {id:'directions',title:'Follow the directions',description:'Guide Barsik through the streets.',lesson_id:'directions',lesson_title:'Which way?',lesson_href:'#first-steps/directions',unlocked:false,unlock:{required_coins:60,earned_coins:12,remaining_coins:48},new:false,active_session_id:null},
];
const objects=[{id:'letter',visual:'letter',label:'letter'},{id:'map',visual:'map',label:'map'},{id:'apple',visual:'apple',label:'apple'},{id:'cup',visual:'cup',label:'cup'}];
const packRounds:GameRound[]=[
  {id:'letter-round',prompt:'What goes in the bag?',clues:[{text:'Это письмо.',audio_key:'letter-audio'}],objects,max_choices:1},
  {id:'map-round',prompt:'What goes in the bag?',clues:[{text:'Это карта.',audio_key:'map-audio'}],objects,max_choices:1},
  {id:'both-round',prompt:'What goes in the bag?',clues:[{text:'Это письмо.',audio_key:'letter-audio'},{text:'Это карта.',audio_key:'map-audio'}],objects,max_choices:2},
];
const board:GameBoard={width:5,height:5,start:{x:2,y:3,heading:'north'},landmarks:[]};
const routeRound:GameRound={id:'route-round',prompt:'Which way should Barsik go?',clues:[{text:'Прямо, потом налево.',audio_key:'route-audio'}],board,max_choices:2};
const catalogue=():GameCatalogueState=>({profile_id:'tom',games:structuredClone(games)});
const state=(patch:Partial<GameState>={}):GameState=>({profile_id:'tom',id:'play-1',game_id:'pack-bag',title:'Pack the bag',phase:'play',round_index:0,total_rounds:3,round:structuredClone(packRounds[0]),result:null,reward:null,source:{lesson_id:'bag',title:'What’s in the bag?',href:'#first-steps/bag'},...patch});
const response=(value:unknown,ok=true)=>({ok,json:async()=>structuredClone(value)});
function server(initial=state(),overview=catalogue(),rounds=packRounds) {
  const api={state:structuredClone(initial),overview:structuredClone(overview),rounds,expected:{} as Record<string,string[]>,transcripts:{} as Record<string,string>,answerAudio:[] as {text:string;audio_key:string}[],fail:'',failCode:'unavailable',changeOwner:false,hold:'',release:undefined as undefined|(()=>void),media:'ready'};
  const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
    const action=request?.method==='GET' ? 'load' : url.split('/').at(-1)!;
    if(api.hold===action){api.hold='';await new Promise<void>(resolve=>{api.release=resolve;});}
    if(api.fail===action){api.fail='';return response({error:{code:api.failCode,message:'Please reopen or try saving again.'}},false);}
    if(url.includes('/media/'))return response(api.media==='ready'?{status:'ready',url:'/media/russian.mp3'}:{status:'unavailable',message:'Audio is unavailable. You can read the Russian clue.'});
    if(url==='/api/v1/games')return response(api.overview);
    if(request?.method==='GET'||action==='start')return response(api.state);
    const body=JSON.parse(request?.body as string);
    if(action==='hint')api.state.round={...api.state.round!,hint:'This is a letter.'};
    if(action==='listen'){const support=api.state.round!.support??{listened_audio_keys:[],transcript:false};api.state.round!.support={...support,listened_audio_keys:[...new Set([...support.listened_audio_keys,body.audio_key])]};}
    if(action==='transcript'){api.state.round!.support={listened_audio_keys:api.state.round!.support?.listened_audio_keys??[],transcript:true};api.state.round!.clues=api.state.round!.clues.map(clue=>({...clue,text:api.transcripts[clue.audio_key]??'Барсик, налево!'}));}
    if(action==='answer'){
      expect(body.round_id).toBe(api.state.round!.id);
      const expected=api.expected[api.state.round!.id]??(api.state.game_id==='directions'?['straight','left']:api.state.round_index===0?['letter']:api.state.round_index===1?['map']:['letter','map']);
      api.state.result={answer:body.answer,expected_answer:expected,correct:JSON.stringify(body.answer)===JSON.stringify(expected),feedback:'Barsik needs the letter.',answer_audio:api.answerAudio};api.state.phase='feedback';
      if(api.state.game_id==='radio')api.state.round!.clues=api.state.round!.clues.map(clue=>({...clue,text:api.transcripts[clue.audio_key]??'Барсик, налево!'}));
    }
    if(action==='retry'){api.state.practice={mode:'correction',index:0,total:1};api.state.phase='practice';api.state.result=null;}
    if(action==='practice_answer'){api.state.result={answer:body.answer,expected_answer:['letter'],correct:body.answer[0]==='letter',feedback:'Это письмо. — This is a letter.'};api.state.phase='practice_feedback';}
    if(action==='practice_continue'){api.state.practice=undefined;api.state.round_index++;api.state.result=null;api.state.round=structuredClone(api.rounds[api.state.round_index]??null);api.state.phase=api.state.round?'play':'completed';}
    if(action==='review'){api.state.practice={mode:'review',index:0,total:1};api.state.phase='practice';api.state.round=structuredClone(packRounds[0]);api.state.result=null;}
    if(action==='practice_exit'){api.state.practice=undefined;api.state.phase='completed';api.state.round=null;api.state.result=null;}
    if(action==='continue'){api.state.round_index++;api.state.result=null;api.state.round=structuredClone(api.rounds[api.state.round_index] ?? null);api.state.phase=api.state.round?'play':'ready';}
    if(action==='complete'){api.state.phase='completed';api.state.reward={amount:3,status:'credited',awarded_now:true};}
    if(api.changeOwner)api.state.profile_id='someone-else';
    return response(api.state);
  });
  vi.stubGlobal('fetch',fetch);
  return {...api,raw:api,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};
}
async function click(name:string){fireEvent.click(await screen.findByRole('button',{name,exact:true}));}
beforeEach(()=>{vi.stubGlobal('scrollTo',vi.fn());window.location.hash='games/pack-bag';});
afterEach(()=>vi.unstubAllGlobals());

describe('Discovering games',()=>{
  it('lists all games on the Games page, opening owned games and directing locked games to the shop',async()=>{
    const api=server();render(<GameCatalogue context="games"/>);
    expect(await screen.findByRole('heading',{name:'Pack the bag',level:2})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Pack the bag'}).getAttribute('href')).toBe('#games/pack-bag');
    expect(screen.getByRole('heading',{name:'Follow the directions',level:2})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Follow the directions — In the shop'}).getAttribute('href')).toBe('#shop');
    expect(screen.queryByRole('heading',{name:'Games to discover'})).toBeNull();
    expect(api.posts()).toHaveLength(0);
  });
  it('routes a retired Pairs setup bookmark to the replacement without starting a game',async()=>{
    const api=server();render(<JourneyGame gameId="pairs"/>);
    await waitFor(()=>expect(window.location.hash).toBe('#games/scene-builder'));
    expect(api.posts()).toHaveLength(0);
  });
  it('shows owned games and one shop link without automatic coin milestones',async()=>{
    const api=server();render(<GameCatalogue/>);
    expect(await screen.findByRole('heading',{name:'Pack the bag'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Pack the bag'}).getAttribute('href')).toBe('#games/pack-bag');
    expect(screen.getByRole('link',{name:/Visit the shop/}).getAttribute('href')).toBe('#shop');
    expect(screen.queryByText(/Lingocoins earned/)).toBeNull();
    expect(screen.queryByText(/brought-forward coins/)).toBeNull();
    expect(screen.queryByRole('heading',{name:'Follow the directions'})).toBeNull();
    expect(api.posts()).toHaveLength(0);
  });
  it('explains the shop in Russian without directing the learner back to the introduction',async()=>{
    server();render(<GameLanguage.Provider value="ru"><GameCatalogue/></GameLanguage.Provider>);
    expect(await screen.findByRole('link',{name:/В магазин/})).toBeTruthy();
    expect(screen.getByText('Открывайте новые игры за лингокоины в магазине.')).toBeTruthy();
    expect(screen.queryByRole('link',{name:'Which way?'})).toBeNull();
    expect(screen.queryByText(/Заработано лингокоинов/)).toBeNull();
  });
  it('describes public samples without the activity-coin unlock policy',async()=>{
    const overview=catalogue();overview.public_demo=true;
    overview.games[0].availability='sample';overview.games[1].availability='local-only';
    server(state(),overview);render(<GameCatalogue/>);
    expect(await screen.findByText('Sample game')).toBeTruthy();
    expect(screen.getByText('Build on words you know, meet new ones and try a different way to practise.')).toBeTruthy();
    expect(screen.queryByText('Earn Lingocoins from reading, writing, speaking and other activities to open new games.')).toBeNull();
    expect(screen.queryByText(/brought-forward coins/)).toBeNull();
    expect(screen.queryByRole('link',{name:'Choose an activity'})).toBeNull();
  });
  it('retains an unfinished game when its new milestone has not been reached',async()=>{
    const overview=catalogue();overview.games[1].active_session_id='saved-route';
    const api=server(state(),overview);render(<GameCatalogue/>);
    expect(await screen.findByRole('link',{name:'Follow the directions'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Follow the directions'}).getAttribute('href')).toBe('#games/session/saved-route');
    expect(screen.getByText('Continue playing')).toBeTruthy();
    expect(screen.queryByText('Opens after earning 60 Lingocoins in activities.')).toBeNull();
    expect(api.posts()).toHaveLength(0);
  });
  it('continues an existing game from the catalogue instead of starting a second session',async()=>{
    const overview=catalogue();overview.games[0].active_session_id='saved-game';server(state(),overview);render(<GameCatalogue context="journey"/>);
    expect(await screen.findByRole('link',{name:'Pack the bag'})).toBeTruthy();
    expect(screen.getByText('Continue playing')).toBeTruthy();
    expect(screen.getByRole('link',{name:'Pack the bag'}).getAttribute('href')).toBe('#games/session/saved-game');
    expect(screen.getByRole('heading',{name:'Games along the way'})).toBeTruthy();
  });
  it('recovers a catalogue error without inventing an unlocked game',async()=>{
    const api=server();api.raw.fail='load';render(<GameCatalogue/>);await screen.findByRole('alert');expect(screen.queryByRole('link',{name:'Pack the bag'})).toBeNull();await click('Try again');expect(await screen.findByRole('link',{name:'Pack the bag'})).toBeTruthy();
  });
  it('shows a recoverable error for a malformed catalogue instead of crashing the activity page',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>response({status:'ok'})));render(<GameCatalogue/>);expect(await screen.findByRole('alert')).toBeTruthy();expect(screen.getByText('Your games could not load. Please try again.')).toBeTruthy();expect(screen.queryByRole('link',{name:'Pack the bag'})).toBeNull();
  });
});

describe('A game with Barsik',()=>{
  it('waits for an explicit start and retries the same request ID after a failed start',async()=>{
    const api=server();render(<JourneyGame gameId="pack-bag"/>);await screen.findByRole('button',{name:'Let’s play'});expect(api.posts()).toHaveLength(0);
    api.raw.fail='start';await click('Let’s play');await screen.findByRole('alert');const first=JSON.parse(api.posts()[0][1]!.body as string);expect(first.request_id).toBeTruthy();
    await click('Try again');await screen.findByRole('button',{name:'Pack letter'});expect(JSON.parse(api.posts()[1][1]!.body as string)).toEqual(first);expect(window.location.hash).toBe('#games/session/play-1');
  });
  it('sends a locked game to the shop without setup controls or a start button',async()=>{
    const api=server();render(<JourneyGame gameId="directions"/>);
    expect(await screen.findByText('Unlock this game in the shop with Lingocoins.')).toBeTruthy();
    expect(screen.getByRole('link',{name:/Visit the shop/}).getAttribute('href')).toBe('#shop');
    expect(screen.queryByRole('button',{name:'Let’s play'})).toBeNull();expect(api.posts()).toHaveLength(0);
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByRole('link',{name:'Which way?'})).toBeNull();
  });
  it('starts the town mission shown as selected even when older deliveries precede it in the catalogue',async()=>{
    const overview=catalogue();overview.games[1].unlocked=true;
    overview.deliveries=[
      {mission_id:'old-letter',title:'A familiar letter route',title_ru:'Знакомый маршрут',area:'park',summary:'Follow the park route.',summary_ru:'Пройди через парк.'},
      {mission_id:'town-parcel',title:'Collect the parcel',title_ru:'Забрать посылку',area:'town',summary:'Find the parcel and deliver it.',summary_ru:'Найди и доставь посылку.'},
    ];
    const api=server(state({game_id:'directions',round:routeRound}),overview);render(<JourneyGame gameId="directions"/>);
    const selected=await screen.findByRole('radio',{name:/Collect the parcel/});
    expect((selected as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByText('One letter · Three connected stops')).toBeNull();
    await click('Let’s play');
    expect(JSON.parse(api.posts()[0][1]!.body as string).options.delivery_id).toBe('town-parcel');
  });
  it.each(['town-generated','town-procedural'])('starts %s without disclosing authored puzzles from a mixed catalogue',async(missionId)=>{
    const overview=catalogue();overview.games[1].unlocked=true;
    overview.deliveries=[
      {mission_id:'town-detour',title:'The closed bridge',title_ru:'Закрытый мост',area:'town',summary:'Find another river crossing.',summary_ru:'Найди другую переправу.'},
      {mission_id:'old-letter',title:'A familiar letter route',title_ru:'Знакомый маршрут',area:'park',summary:'Follow the park route.',summary_ru:'Пройди через парк.'},
      {mission_id:missionId,title:'A delivery for Barsik',title_ru:'Доставка для Барсика',area:'town',summary:'Each delivery takes a different route.',summary_ru:'У каждой доставки свой маршрут.'},
    ];
    const api=server(state({game_id:'directions',round:routeRound}),overview);render(<JourneyGame gameId="directions"/>);
    expect(await screen.findByRole('heading',{name:'A delivery for Barsik'})).toBeTruthy();
    expect(screen.queryByText('The closed bridge')).toBeNull();
    expect(screen.queryByText('Find another river crossing.')).toBeNull();
    expect(screen.queryByText('A familiar letter route')).toBeNull();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(api.posts()).toHaveLength(0);
    await click('Let’s play');
    expect(JSON.parse(api.posts()[0][1]!.body as string).options.delivery_id).toBe(missionId);
  });
  it('shows paused delivery preparation without calling it an obsolete saved game',async()=>{
    const pending=state({game_id:'directions',phase:'preparing',round:null,source:{kind:'route',title:'Town deliveries',href:'#games/directions'},
      preparation:{status:'failed',ready:2,total:8,stage:'audio',message:'Preparing the voices.',error:'The recording could not be prepared.'}});
    const api=server(pending);render(<JourneyGame sessionId="play-1"/>);
    await screen.findByRole('button',{name:/Retry preparation/});
    expect(screen.queryByText('This is a saved route from the earlier game.')).toBeNull();
    expect(api.posts()).toHaveLength(0);
  });
  it('explicitly requests a new game when exploring another town even without a listed active session',async()=>{
    const overview=catalogue();overview.games[1].unlocked=true;
    overview.deliveries=[{mission_id:'town-procedural',title:'A delivery for Barsik',title_ru:'Доставка для Барсика',area:'town',summary:'Follow Russian directions.',summary_ru:'Следуй указаниям.'}];
    const api=server(state({game_id:'directions',round:routeRound}),overview);render(<JourneyGame gameId="directions"/>);
    fireEvent.click(await screen.findByRole('checkbox',{name:'Explore a new town'}));
    expect(api.posts()).toHaveLength(0);
    await click('Let’s play');
    const body=JSON.parse(api.posts()[0][1]!.body as string);
    expect(body.new_game).toBe(true);
    expect(body.options.delivery_id).toBe('town-procedural');
    expect(body.options.delivery_new_town).toBe(true);
  });
  it('keeps the saved town by default when starting a procedural delivery',async()=>{
    const overview=catalogue();overview.games[1].unlocked=true;
    overview.deliveries=[{mission_id:'town-procedural',title:'A delivery for Barsik',title_ru:'Доставка для Барсика',area:'town',summary:'Follow Russian directions.',summary_ru:'Следуй указаниям.'}];
    const api=server(state({game_id:'directions',round:routeRound}),overview);render(<JourneyGame gameId="directions"/>);
    expect((await screen.findByRole('checkbox',{name:'Explore a new town'}) as HTMLInputElement).checked).toBe(false);
    await click('Let’s play');
    const body=JSON.parse(api.posts()[0][1]!.body as string);
    expect(body.new_game).toBeUndefined();
    expect(body.options.delivery_new_town).toBeUndefined();
  });
  it('uses illustrated objects in a bag, supports removing a choice, and only checks after the user asks',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Pack letter'});expect((screen.getByRole('button',{name:'Check the bag'}) as HTMLButtonElement).disabled).toBe(true);
    await click('Pack letter');expect(screen.getByRole('button',{name:'Take letter out of the bag'})).toBeTruthy();expect(screen.getByRole('button',{name:'Remove letter'}).getAttribute('aria-pressed')).toBe('true');expect(api.posts()).toHaveLength(0);
    await click('Take letter out of the bag');expect(screen.queryByRole('button',{name:'Take letter out of the bag'})).toBeNull();await click('Pack letter');await click('Check the bag');
    await screen.findByRole('heading',{name:'Just what Barsik needed.'});expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({round_id:'letter-round',answer:['letter']});expect((screen.getByRole('button',{name:'Take letter out of the bag'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('keeps English hints optional and does not erase the current bag when a hint is saved',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Pack letter'});expect(screen.queryByText('This is a letter.')).toBeNull();await click('Pack letter');await click('Show a hint');
    expect(await screen.findByText('This is a letter.')).toBeTruthy();expect(screen.getByRole('button',{name:'Take letter out of the bag'})).toBeTruthy();expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({round_id:'letter-round'});
  });
  it('preserves the submitted answer for an exact retry and prevents duplicate checks while saving',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await click('Pack letter');api.raw.fail='answer';await click('Check the bag');await screen.findByRole('alert');const first=api.posts()[0][1]!.body;
    expect((screen.getByRole('button',{name:'Take letter out of the bag'}) as HTMLButtonElement).disabled).toBe(true);expect((screen.getByRole('button',{name:'Check the bag'}) as HTMLButtonElement).disabled).toBe(true);expect((screen.getByRole('button',{name:'Show a hint'}) as HTMLButtonElement).disabled).toBe(true);
    api.raw.hold='answer';await click('Try again');expect((screen.getByRole('button',{name:'Saving…'}) as HTMLButtonElement).disabled).toBe(true);expect(api.posts()).toHaveLength(2);await act(async()=>api.raw.release?.());await screen.findByRole('button',{name:'Next round'});expect(api.posts()[1][1]!.body).toBe(first);
  });
  it('recovers a server-saved answer after a conflicting response without trapping the user in retries',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await click('Pack letter');api.raw.state.result={answer:['map'],expected_answer:['letter'],correct:false,feedback:'Your earlier answer was saved.'};api.raw.state.phase='feedback';api.raw.fail='answer';api.raw.failCode='answer_already_saved';await click('Check the bag');
    expect(await screen.findByText('Your earlier answer was saved.')).toBeTruthy();expect(screen.getByRole('button',{name:'Take map out of the bag'})).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByRole('button',{name:'Next round'})).toBeTruthy();
  });
  it('requires each saved feedback before moving on and completes only after the final one',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await click('Pack letter');await click('Check the bag');await click('Next round');await screen.findByText('Round 2 of 3');expect(screen.queryByRole('button',{name:'Take letter out of the bag'})).toBeNull();
    await click('Pack map');await click('Check the bag');await click('Next round');await screen.findByText('Round 3 of 3');await click('Pack letter');await click('Pack map');await click('Check the bag');
    await screen.findByRole('button',{name:'Finish game'});expect(api.posts().filter(([url])=>url.endsWith('/complete'))).toHaveLength(0);await click('Finish game');expect(await screen.findByRole('heading',{name:'Packed and ready.'})).toBeTruthy();expect(screen.getByText('+3 Lingocoins')).toBeTruthy();expect(api.posts().filter(([url])=>url.endsWith('/complete'))).toHaveLength(1);
  });
  it('reopens saved feedback read-only without checking or awarding it again',async()=>{
    const initial=state({phase:'feedback',result:{answer:['map'],expected_answer:['letter'],correct:false,feedback:'Barsik needs the letter.'}});const api=server(initial);render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('heading',{name:'Let’s take another look.'});expect(screen.queryByRole('button',{name:'Check the bag'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });
  it('marks the expected shelf picture green and a wrong selection with a cross after checking',async()=>{
    const initial=state({phase:'feedback',round:packRounds[1],result:{answer:['apple'],expected_answer:['map'],correct:false,feedback:'Карта means a map.'}});server(initial);render(<JourneyGame sessionId="play-1"/>);const needed=await screen.findByRole('button',{name:'Needed in the bag: map'}),wrong=screen.getByRole('button',{name:'Not needed: apple'});
    expect(needed.classList.contains('is-needed')).toBe(true);expect(needed.textContent).toContain('✓');expect(wrong.classList.contains('is-unneeded')).toBe(true);expect(wrong.classList.contains('is-packed')).toBe(false);expect(wrong.textContent).toContain('×');expect(wrong.textContent).not.toContain('✓');expect(screen.getByText('What Barsik needed')).toBeTruthy();
  });
  it('explains an already-rewarded replay without claiming the daily cap was reached',async()=>{
    server(state({phase:'completed',round:null,reward:{amount:0,status:'credited',awarded_now:false,reason:'already_rewarded'}}));render(<JourneyGame sessionId="play-1"/>);expect(await screen.findByText('You’ve already earned coins for this game today. You can keep playing.')).toBeTruthy();expect(screen.queryByText(/coin limit/)).toBeNull();
  });
  it('lets a guest keep the result without promising an unclaimed coin balance',async()=>{
    server(state({profile_id:null,phase:'completed',round:null,reward:{amount:3,status:'pending',awarded_now:false,reason:'profile_needed'}}));render(<JourneyGame sessionId="play-1"/>);expect(await screen.findByRole('link',{name:'Create a profile to keep it.'})).toBeTruthy();expect(screen.queryByText(/3 Lingocoins/)).toBeNull();
  });
  it('clears the old learner’s game if a mutation reports a profile change',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await click('Pack letter');api.raw.fail='answer';api.raw.failCode='profile_changed';await click('Check the bag');await screen.findByRole('alert');expect(screen.queryByRole('button',{name:'Pack map'})).toBeNull();expect(screen.queryByRole('button',{name:'Try again'})).toBeNull();expect(screen.getByRole('link',{name:'Reopen activities'})).toBeTruthy();
  });
  it('rejects a successful response for another learner before displaying it',async()=>{
    const api=server();render(<JourneyGame sessionId="play-1"/>);await click('Pack letter');api.raw.changeOwner=true;await click('Check the bag');await screen.findByRole('alert');expect(screen.queryByRole('heading',{name:'Just what Barsik needed.'})).toBeNull();expect(screen.getByText('Your profile changed. Reopen this page before continuing.')).toBeTruthy();
  });
  it('does not create a session after the start page has been left during its initial read',async()=>{
    const api=server();api.raw.hold='load';const view=render(<JourneyGame gameId="pack-bag"/>);await waitFor(()=>expect(api.raw.release).toBeDefined());view.unmount();await act(async()=>api.raw.release?.());expect(api.posts()).toHaveLength(0);
  });
  it('does not navigate from a delayed start response after leaving the page',async()=>{
    const api=server();const view=render(<JourneyGame gameId="pack-bag"/>);await screen.findByRole('button',{name:'Let’s play'});api.raw.hold='start';await click('Let’s play');view.unmount();window.location.hash='home';await act(async()=>api.raw.release?.());expect(window.location.hash).toBe('#home');
  });
});

describe('Following directions',()=>{
  it('fits the full vocabulary street grid and its outer picture landmarks inside the map',async()=>{
    const largeBoard:GameBoard={width:7,height:7,start:{x:5,y:5,heading:'east'},landmarks:[{x:6,y:6,visual:'postcard',label:'A storm over a town',image_url:'/media/storm.webp'}]};server(state({game_id:'directions',round:{...routeRound,board:largeBoard}}));const view=render(<JourneyGame sessionId="play-1"/>);const map=await screen.findByRole('img',{name:/column 6, row 6, facing right/});expect(map.getAttribute('viewBox')).toBe('0 0 420 420');expect(view.container.querySelector('path[d="M30 390H390"]')).toBeTruthy();expect(view.container.querySelector('image[href="/media/storm.webp"]')?.parentElement?.getAttribute('transform')).toBe('translate(390 390)');await click('Go straight');expect(screen.getByRole('img',{name:/column 7, row 6, facing right/})).toBeTruthy();
  });
  it('turns relative to Barsik’s current heading, with no translated destination before checking',async()=>{
    const api=server(state({game_id:'directions',title:'Follow the directions',round:routeRound}));render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Go straight'});expect(screen.queryByText(/dotted green line/)).toBeNull();
    await click('Go straight');await click('Turn left');expect(screen.getByRole('img',{name:/column 2, row 3, facing left/})).toBeTruthy();expect((screen.getByRole('button',{name:'Turn right'}) as HTMLButtonElement).disabled).toBe(true);
    await click('Undo');expect(screen.getByRole('img',{name:/column 3, row 3, facing up/})).toBeTruthy();await click('Turn left');await click('Check the route');await screen.findByRole('heading',{name:'That’s the way.'});expect(screen.getByText(/dotted green line/)).toBeTruthy();expect(JSON.parse(api.posts()[0][1]!.body as string).answer).toEqual(['straight','left']);
  });
  it('can clear a planned route before submitting',async()=>{
    server(state({game_id:'directions',title:'Follow the directions',round:routeRound}));render(<JourneyGame sessionId="play-1"/>);await click('Turn right');await click('Start over');expect(screen.getByRole('img',{name:/column 3, row 4, facing up/})).toBeTruthy();expect((screen.getByRole('button',{name:'Check the route'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('traces successive relative turns rather than treating left and right as fixed map coordinates',()=>{
    expect(traceRoute(board,['left','right','right'])).toEqual([{x:2,y:3,heading:'north'},{x:1,y:3,heading:'west'},{x:1,y:2,heading:'north'},{x:2,y:2,heading:'east'}]);
  });
});

describe('Shared Russian recordings',()=>{
  it('only prepares audio after Listen and reuses the same recording on replay',async()=>{
    const audio={play:vi.fn(async()=>{}),pause:vi.fn(),currentTime:0,onended:undefined as undefined|(()=>void),onerror:undefined};vi.stubGlobal('Audio',vi.fn(function(){return audio;}));const api=server();render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Listen: Это письмо.'});expect(api.posts()).toHaveLength(0);
    await click('Listen: Это письмо.');await screen.findByRole('button',{name:'Stop recording: Это письмо.'});expect(api.posts()[0][0]).toBe('/api/v1/games/media/letter-audio/prepare');await act(async()=>audio.onended?.());await click('Listen: Это письмо.');await waitFor(()=>expect(audio.play).toHaveBeenCalledTimes(2));expect(api.posts()).toHaveLength(1);
  });
  it('keeps the Russian clue playable as text when audio is unavailable and offers explicit retry',async()=>{
    const api=server();api.raw.media='unavailable';render(<JourneyGame sessionId="play-1"/>);await click('Listen: Это письмо.');expect(await screen.findByText('Audio is unavailable. You can read the Russian clue.')).toBeTruthy();expect(screen.getByText('Это письмо.')).toBeTruthy();expect(screen.getByRole('button',{name:'Pack letter'})).toBeTruthy();expect(api.posts()).toHaveLength(1);
  });
  it('stops the previous recording before playing a different clue',async()=>{
    const clips:{play:ReturnType<typeof vi.fn>;pause:ReturnType<typeof vi.fn>;currentTime:number}[]=[];vi.stubGlobal('Audio',vi.fn(function(){const clip={play:vi.fn(async()=>{}),pause:vi.fn(),currentTime:0};clips.push(clip);return clip;}));server(state({round:packRounds[2]}));render(<JourneyGame sessionId="play-1"/>);await click('Listen: Это письмо.');await screen.findByRole('button',{name:'Stop recording: Это письмо.'});await click('Listen: Это карта.');await screen.findByRole('button',{name:'Stop recording: Это карта.'});expect(clips[0].pause).toHaveBeenCalledTimes(1);expect(screen.getByRole('button',{name:'Listen: Это письмо.'})).toBeTruthy();
  });
});

const pairsRound:GameRound={id:'pairs-1',prompt:'Match each postcard.',clues:[],max_choices:2,left:[{id:'r0',text:'Это письмо.',audio_key:'letter-audio'},{id:'r1',text:'Это карта.',audio_key:'map-audio'}],right:[{id:'p0',visual:'map',label:'Map'},{id:'p1',visual:'letter',label:'Letter'}]};
const sortRound:GameRound={id:'mailbox-sort-1',prompt:'Sort the messages.',clues:[],max_choices:3,sentences:[{id:'n0',text:'Это карта.',audio_key:'map-audio'},{id:'n1',text:'Барсик, налево!',audio_key:'left-audio'},{id:'n2',text:'Где рынок?',audio_key:'market-audio'}],bins:[{id:'name',label:'Name a thing'},{id:'direction',label:'Give directions'},{id:'help',label:'Ask for help'}]};
const clozeRound:GameRound={id:'missing-stamp-1',prompt:'Complete the message.',clues:[],max_choices:1,sentence:'Это [[blank]].',translation:'This is a letter.',visual:'letter',choices:[{id:'letter',text:'письмо'},{id:'bag',text:'сумка'},{id:'map',text:'карта'}]};
const radioRound:GameRound={id:'radio-1',prompt:'Listen, then choose an arrow.',clues:[{audio_key:'radio-left'}],max_choices:1,choices:[{id:'left',visual:'left',label:'Left'},{id:'right',visual:'right',label:'Right'},{id:'straight',visual:'straight',label:'Straight ahead'}],support:{listened_audio_keys:[],transcript:false}};
const detectiveRound:GameRound={id:'detective-1',prompt:'Use both clues.',clues:[{text:'Это письмо.',audio_key:'letter-audio'},{text:'Барсик, налево!',audio_key:'left-audio'}],max_choices:1,destinations:[{id:'a',visual:'letter',route:['left'],label:'Letter: left'},{id:'b',visual:'map',route:['left'],label:'Map: left'},{id:'c',visual:'letter',route:['right'],label:'Letter: right'},{id:'d',visual:'map',route:['right'],label:'Map: right'}]};
const replyRound:GameRound={id:'letter-back-1',prompt:'Greet the clerk politely, then ask where the market is.',clues:[],max_choices:2,tiles:[{id:'greet',text:'Здравствуйте!'},{id:'where',text:'Где рынок?'},{id:'thanks',text:'Спасибо!'},{id:'show',text:'Покажите, пожалуйста.'}]};
function newGame(gameId:JourneyGameId,round:GameRound,expected:string[]) {
  const rounds=[0,1,2].map(index=>({...structuredClone(round),id:`${gameId}-${index+1}`}));
  const api=server(state({game_id:gameId,title:gameId,round:rounds[0]}),catalogue(),rounds);
  rounds.forEach(item=>{api.raw.expected[item.id]=expected;});return api;
}
function mockAudio(){const clips:{play:ReturnType<typeof vi.fn>;pause:ReturnType<typeof vi.fn>;currentTime:number;source:string}[]=[];vi.stubGlobal('Audio',vi.fn(function(source:string){const clip={play:vi.fn(async()=>{}),pause:vi.fn(),currentTime:0,source};clips.push(clip);return clip;}));return clips;}

describe('The six new games',()=>{
  it('pairs Russian sentences with pictures, allows reassignment, and requires every pair before checking',async()=>{
    const api=newGame('pairs',pairsRound,['r0:p1','r1:p0']);render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Это письмо.'});
    await click('Match with Map');expect((screen.getByRole('button',{name:'Check the pairs'}) as HTMLButtonElement).disabled).toBe(true);
    await click('Это письмо.');await click('Match with Letter');await click('Match with Map');await click('Check the pairs');await screen.findByRole('heading',{name:'Those pairs belong together.'});
    expect(JSON.parse(api.posts().find(([url])=>url.endsWith('/answer'))![1]!.body as string).answer).toEqual(['r0:p1','r1:p0']);expect(screen.getByText('The matching postcards')).toBeTruthy();expect(screen.getByRole('button',{name:'Listen: Это письмо.'})).toBeTruthy();
  });
  it('preserves existing pairs when a learner opens a hint',async()=>{
    newGame('pairs',pairsRound,['r0:p1','r1:p0']);render(<JourneyGame sessionId="play-1"/>);await click('Match with Letter');await click('Show a hint');await screen.findByText('This is a letter.');expect(screen.getByLabelText('Paired with postcard 1')).toBeTruthy();await click('Match with Map');expect((screen.getByRole('button',{name:'Check the pairs'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('sorts context messages into mailboxes and supplies audio beside each message',async()=>{
    const api=newGame('mailbox-sort',sortRound,['n0:name','n1:direction','n2:help']);render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Listen: Где рынок?'});await click('Put the message in Name a thing');await click('Put the message in Give directions');await click('Put the message in Ask for help');await click('Check the mail');await screen.findByRole('heading',{name:'Every message has a place.'});expect(JSON.parse(api.posts()[0][1]!.body as string).answer).toEqual(['n0:name','n1:direction','n2:help']);expect(screen.getAllByText('Belongs here')).toHaveLength(3);
  });
  it('shows the full English translation for a cloze but keeps complete-sentence audio behind the answer',async()=>{
    const api=newGame('missing-stamp',clozeRound,['letter']);api.raw.answerAudio=[{text:'Это письмо.',audio_key:'letter-audio'}];render(<JourneyGame sessionId="play-1"/>);await screen.findByText('This is a letter.');expect(screen.queryByText('Это письмо.')).toBeNull();expect(screen.queryByRole('button',{name:'Listen to the complete message'})).toBeNull();await click('письмо');await click('Check the postcard');expect(await screen.findByRole('button',{name:'Listen to the complete message'})).toBeTruthy();expect(screen.getByRole('button',{name:'письмо'}).classList.contains('is-correct')).toBe(true);
  });
  it('does not place a radio transcript in visible text, hidden text or audio labels before it is requested',async()=>{
    newGame('radio',radioRound,['left']);const view=render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Listen to the message'});expect(view.container.textContent).not.toContain('Барсик, налево!');expect(view.container.innerHTML).not.toContain('Барсик, налево!');await click('Left');expect((screen.getByRole('button',{name:'Check what I heard'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('records listening only after audio begins, then allows checking and later replaying the answer',async()=>{
    mockAudio();const api=newGame('radio',radioRound,['left']);render(<JourneyGame sessionId="play-1"/>);await click('Listen to the message');await waitFor(()=>expect(api.posts().some(([url])=>url.endsWith('/listen'))).toBe(true));expect(JSON.parse(api.posts().find(([url])=>url.endsWith('/listen'))![1]!.body as string)).toEqual({round_id:'radio-1',audio_key:'radio-left'});await click('Left');await click('Check what I heard');await screen.findByRole('heading',{name:'You caught the message.'});expect(screen.getByText('Барсик, налево!')).toBeTruthy();expect((screen.getByRole('button',{name:'Stop recording'}) as HTMLButtonElement).disabled).toBe(false);expect(api.posts().filter(([url])=>url.endsWith('/transcript'))).toHaveLength(0);
  });
  it('keeps an audio failure recoverable through the saved transcript option, retaining the chosen arrow',async()=>{
    const api=newGame('radio',radioRound,['left']);api.raw.media='unavailable';render(<JourneyGame sessionId="play-1"/>);await click('Left');await click('Listen to the message');await screen.findByText('Audio is unavailable. You can read the Russian clue.');expect(api.posts().filter(([url])=>url.endsWith('/listen'))).toHaveLength(0);await click('Show the Russian text');await screen.findByText('Барсик, налево!');expect(screen.getByRole('button',{name:'Left'}).getAttribute('aria-pressed')).toBe('true');expect((screen.getByRole('button',{name:'Check what I heard'}) as HTMLButtonElement).disabled).toBe(false);expect(JSON.parse(api.posts().find(([url])=>url.endsWith('/transcript'))![1]!.body as string)).toEqual({round_id:'radio-1'});
  });
  it('makes detective choices distinguish both the object and the route, without marking a destination before checking',async()=>{
    const api=newGame('detective',detectiveRound,['a']);render(<JourneyGame sessionId="play-1"/>);await screen.findByRole('button',{name:'Letter: left'});expect(screen.getByRole('button',{name:'Letter: right'})).toBeTruthy();expect(screen.getByRole('button',{name:'Map: left'})).toBeTruthy();expect(screen.queryByLabelText('Correct')).toBeNull();await click('Letter: left');await click('Check the clues');await screen.findByRole('heading',{name:'Both clues fit.'});expect(JSON.parse(api.posts()[0][1]!.body as string).answer).toEqual(['a']);
  });
  it('builds a reply in the learner’s chosen order and lets them remove or replace phrase tiles',async()=>{
    const api=newGame('letter-back',replyRound,['greet','where']);api.raw.answerAudio=[{text:'Здравствуйте!',audio_key:'greeting-audio'},{text:'Где рынок?',audio_key:'market-audio'}];render(<JourneyGame sessionId="play-1"/>);await click('Спасибо!');await click('Remove Спасибо! from your reply');await click('Здравствуйте!');expect((screen.getByRole('button',{name:'Send the reply'}) as HTMLButtonElement).disabled).toBe(true);await click('Где рынок?');await click('Send the reply');await screen.findByRole('heading',{name:'That reply does the job.'});expect(JSON.parse(api.posts()[0][1]!.body as string).answer).toEqual(['greet','where']);expect(screen.getByText('Здравствуйте! Где рынок?')).toBeTruthy();expect(screen.getByRole('button',{name:'Listen to phrase 1'})).toBeTruthy();
  });
  it('uses audio-first reply reconstruction with English context and retains selected tiles after listening',async()=>{
    mockAudio();const api=newGame('letter-back',{...replyRound,audio_required:true,translation:'Hello! Where is the market?',clues:[{audio_key:'reply-recording'}],support:{listened_audio_keys:[],transcript:false}},['greet','where']);api.raw.transcripts['reply-recording']='Здравствуйте! Где рынок?';const view=render(<JourneyGame sessionId="play-1"/>);await screen.findByText('Hello! Where is the market?');expect(view.container.innerHTML).not.toContain('Здравствуйте! Где рынок?');await click('Здравствуйте!');await click('Где рынок?');expect((screen.getByRole('button',{name:'Check the message'}) as HTMLButtonElement).disabled).toBe(true);await click('Listen to the message');await waitFor(()=>expect((screen.getByRole('button',{name:'Check the message'}) as HTMLButtonElement).disabled).toBe(false));expect(screen.getByRole('button',{name:'Remove Здравствуйте! from your message'})).toBeTruthy();expect(screen.getByRole('button',{name:'Remove Где рынок? from your message'})).toBeTruthy();expect(api.posts().filter(([url])=>url.endsWith('/listen'))).toHaveLength(1);expect(api.posts().filter(([url])=>url.endsWith('/transcript'))).toHaveLength(0);
  });
  it('lets an audio-first reply reveal its saved Russian text without resetting its draft',async()=>{
    const api=newGame('letter-back',{...replyRound,audio_required:true,translation:'Hello! Where is the market?',clues:[{audio_key:'reply-recording'}],support:{listened_audio_keys:[],transcript:false}},['greet','where']);api.raw.transcripts['reply-recording']='Здравствуйте! Где рынок?';api.raw.media='unavailable';render(<JourneyGame sessionId="play-1"/>);await click('Здравствуйте!');await click('Где рынок?');await click('Listen to the message');await screen.findByText('Audio is unavailable. You can read the Russian clue.');await click('Show the Russian text');await screen.findByText('Здравствуйте! Где рынок?');expect(screen.getByRole('button',{name:'Remove Где рынок? from your message'})).toBeTruthy();expect((screen.getByRole('button',{name:'Check the message'}) as HTMLButtonElement).disabled).toBe(false);expect(api.posts().filter(([url])=>url.endsWith('/transcript'))).toHaveLength(1);expect(api.posts().filter(([url])=>url.endsWith('/listen'))).toHaveLength(0);
  });
  it('finishes a three-round reply pack and offers replay plus the originating lesson',async()=>{
    const api=newGame('letter-back',replyRound,['greet','where']);render(<JourneyGame sessionId="play-1"/>);for(let index=0;index<3;index++){await click('Здравствуйте!');await click('Где рынок?');await click('Send the reply');await click(index===2?'Finish game':'Next round');}expect(await screen.findByRole('heading',{name:'A reply for Barsik.'})).toBeTruthy();expect(screen.getByRole('link',{name:'Play again'}).getAttribute('href')).toBe('#games/letter-back');expect(api.posts().filter(([url])=>url.endsWith('/complete'))).toHaveLength(1);
  });
  it('changes the cached recording when a reused clue component receives a new audio key',async()=>{
    const clips=mockAudio();const api=server();const view=render(<AudioClue text="Это письмо." audioKey="letter-audio"/>);await click('Listen: Это письмо.');await screen.findByRole('button',{name:'Stop recording: Это письмо.'});view.rerender(<AudioClue text="Это карта." audioKey="map-audio"/>);await click('Listen: Это карта.');await screen.findByRole('button',{name:'Stop recording: Это карта.'});expect(clips).toHaveLength(2);expect(clips[0].pause).toHaveBeenCalled();expect(api.posts().map(([url])=>url)).toEqual(['/api/v1/games/media/letter-audio/prepare','/api/v1/games/media/map-audio/prepare']);
  });
});

describe('Correction practice and translated controls',()=>{
  it('reopens a wrong answer, saves a separate correction, then continues',async()=>{
    const initial=state({phase:'feedback',result:{answer:['apple'],correct:false,expected_answer:['letter'],feedback:'Это письмо.'}});
    const api=server(initial);render(<JourneyGame sessionId="play-1"/>);
    await click('Try again');
    expect(await screen.findByText('This is practice. Your first result is saved.')).toBeTruthy();
    await click('Pack letter');await click('Check the bag');
    expect(await screen.findByText('Just what Barsik needed.')).toBeTruthy();
    const saved=api.posts().find(([url])=>url.endsWith('/practice_answer'));
    expect(JSON.parse(saved![1]!.body as string)).toMatchObject({round_id:'letter-round',answer:['letter'],request_id:expect.any(String)});
    expect(api.posts().filter(([url])=>url.endsWith('/answer'))).toHaveLength(0);
    await click('Continue');expect(await screen.findByText('Round 2 of 3')).toBeTruthy();
  });
  it('offers missed-item review only when there are mistakes and keeps the saved score',async()=>{
    const completed=state({phase:'completed',round:null,summary:{correct_rounds:2,total_rounds:3,missed_rounds:1,matched:2,total:3},reward:{amount:3,status:'credited',awarded_now:false}});
    server(completed);render(<JourneyGame sessionId="play-1"/>);
    expect(await screen.findByText('2 / 3')).toBeTruthy();await click('Practise missed items');
    expect(await screen.findByText('Review 1 of 1')).toBeTruthy();await click('Close review');
    expect(await screen.findByText('2 / 3')).toBeTruthy();
  });
  it('uses Russian catalogue and play controls from the app language',async()=>{
    const api=server();const view=render(<GameLanguage.Provider value="ru"><GameCatalogue/></GameLanguage.Provider>);
    expect(await screen.findByRole('heading',{name:'Собери сумку'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Собери сумку'})).toBeTruthy();view.unmount();
    render(<GameLanguage.Provider value="ru"><JourneyGame sessionId="play-1"/></GameLanguage.Provider>);
    expect(await screen.findByRole('button',{name:'Проверить сумку'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Показать подсказку'})).toBeTruthy();expect(api.posts()).toHaveLength(0);
  });
  it('renders built-in landmarks even without generated pictures',async()=>{
    const route={...routeRound,board:{...board,landmarks:[{x:0,y:0,visual:'post-office'},{x:4,y:0,visual:'market'}]}};
    server(state({game_id:'directions',round:route}));render(<JourneyGame sessionId="play-1"/>);
    expect(await screen.findByText('Post office',{selector:'title'})).toBeTruthy();expect(screen.getByText('Market',{selector:'title'})).toBeTruthy();
  });
  it('does not offer paid preparation or audio in an authored demo sample',async()=>{
    const api=server(state({sample:true}));render(<JourneyGame sessionId="play-1"/>);
    await screen.findByRole('button',{name:'Pack letter'});
    expect(screen.queryByRole('button',{name:/Listen/})).toBeNull();expect(api.posts()).toHaveLength(0);
  });
  it('explains unavailable demo games before sending visitors through an unlock',async()=>{
    const overview=catalogue();overview.public_demo=true;overview.games[1].availability='local-only';server(state(),overview);
    render(<GameCatalogue/>);expect(await screen.findByText('Available in your own installation.')).toBeTruthy();
    expect(screen.queryByRole('link',{name:'Which way?'})).toBeNull();
  });
});
