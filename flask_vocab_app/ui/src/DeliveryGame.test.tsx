import {afterEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/preact';
import {useState} from 'preact/hooks';
import {DeliveryGame,guideChoices,guideInstructions} from './DeliveryGame';
import {GameLanguage} from './GameLocale';
import type {GameState} from './journey-games-api';

function fixture():GameState {
  const nina={name:'Нина',name_en:'Nina',role:'На почте',role_en:'Postal worker',portrait:'postmaster'};
  const sasha={name:'Саша',name_en:'Sasha',role:'У фонтана',role_en:'By the fountain',portrait:'sasha'};
  return {id:'test-delivery',profile_id:'me',game_id:'directions',title:'A letter for Anna',phase:'play',round_index:0,total_rounds:3,round:null,result:null,reward:null,source:{title:'Deliveries',href:'#activities',kind:'route'},delivery:{
    revision:0,phase:'dialogue',leg:0,title_ru:'Письмо для Анны',envelope:'Анне',position:'post',heading:'east',draft:['post'],last_path:[],
    map:{nodes:[{id:'post',x:1,y:3,label:'Почта',label_en:'Post office',kind:'post'},{id:'corner',x:2,y:3,label:'Улица',label_en:'Street',kind:'street'},{id:'fountain',x:3,y:3,label:'Фонтан',label_en:'Fountain',kind:'fountain'}],edges:[['post','corner'],['corner','fountain']]},
    objective:'Find Sasha',objective_ru:'Найди Сашу',speaker:nina,arrival_speaker:sasha,
    lines:[{id:'clue',text:'Иди прямо до фонтана.',audio_url:'/static/audio/deliveries/test.mp3'}],support:{},feedback:null,notebook:[],glossary:[{form:'фонтана',lemma:'фонтан'}],first_checks:[],
  }};
}
function Harness({initial=fixture(),ru=false}:{initial?:GameState;ru?:boolean}) {
  const [state,setState]=useState(initial);
  return <GameLanguage.Provider value={ru?'ru':'en'}><DeliveryGame state={state} onState={setState}/></GameLanguage.Provider>;
}
function reply(state:GameState){return {ok:true,json:async()=>structuredClone(state)};}
function reducedMotion(){vi.stubGlobal('matchMedia',vi.fn((query:string)=>({matches:query.includes('prefers-reduced-motion')})));}
afterEach(()=>vi.unstubAllGlobals());

it('plans connected streets before moving, then opens the next character encounter',async()=>{
  reducedMotion();let saved=fixture();
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string),d=saved.delivery!;
    d.revision++;
    if(body.action==='begin')d.phase='planning';
    if(body.action==='plan')d.draft=body.payload.path;
    if(body.action==='go'){d.phase='arrived';d.position='fountain';d.last_path=body.payload.path;}
    if(body.action==='talk'){d.phase='dialogue';d.leg=1;d.speaker=d.arrival_speaker;d.objective='Find Olya';d.draft=['fountain'];d.lines=[{id:'next',text:'Перед мостом поверни налево.',audio_url:'/bridge.mp3'}];}
    return reply(saved);
  });vi.stubGlobal('fetch',fetch);
  render(<Harness/>);
  expect(fetch).not.toHaveBeenCalled();
  expect(screen.queryByText('Walk straight to the fountain.')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Plan the route'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Go'}).hasAttribute('disabled')).toBe(true));
  fireEvent.keyDown(screen.getByRole('button',{name:'Walk to: Street'}),{key:'Enter'});
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('button',{name:'Go'}).hasAttribute('disabled')).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Fountain'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Go'}).hasAttribute('disabled')).toBe(false));
  expect(saved.delivery!.position).toBe('post');
  fireEvent.click(screen.getByRole('button',{name:'Go'}));
  fireEvent.click(await screen.findByRole('button',{name:'Talk to Sasha →'}));
  expect(await screen.findByRole('heading',{name:'Find Olya'})).toBeTruthy();
  expect(saved.delivery!.position).toBe('fountain');
  expect(fetch.mock.calls.every(call=>call[0]==='/api/v1/games/sessions/test-delivery/route-command')).toBe(true);
});

it('retries an uncertain save with the same request instead of sending another move',async()=>{
  reducedMotion();const next=fixture();next.delivery!.phase='planning';next.delivery!.revision=1;
  const fetch=vi.fn().mockRejectedValueOnce(new TypeError('Connection lost')).mockResolvedValue(reply(next));vi.stubGlobal('fetch',fetch);
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'Plan the route'}));
  const retry=await screen.findByRole('button',{name:'Retry saving'});
  fireEvent.click(retry);
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch.mock.calls[0][1].body).toEqual(fetch.mock.calls[1][1].body);
  await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
});

it('reloads saved position after another tab changes the delivery',async()=>{
  reducedMotion();const next=fixture();next.delivery!.phase='arrived';next.delivery!.position='fountain';next.delivery!.revision=4;
  const fetch=vi.fn().mockResolvedValueOnce({ok:false,json:async()=>({error:{code:'state_conflict',message:'Changed elsewhere'}})}).mockResolvedValue(reply(next));vi.stubGlobal('fetch',fetch);
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'Plan the route'}));
  expect(await screen.findByRole('heading',{name:'You found Sasha.'})).toBeTruthy();
  expect(fetch.mock.calls[1][1].method).toBe('GET');
  expect(screen.getByRole('alert').textContent).toContain('latest saved position');
});

it('uses Russian interface copy without exposing English instructions by default',()=>{
  const state=fixture();state.delivery!.phase='arrived';
  render(<Harness initial={state} ru/>);
  expect(screen.getByRole('heading',{name:'Саша здесь.'})).toBeTruthy();
  expect(screen.getByRole('button',{name:'Поговорить: Саша →'})).toBeTruthy();
  expect(screen.queryByText('You found Sasha.')).toBeNull();
});

it('pauses the previous recording when another character line is played',async()=>{
  const players:{pause:ReturnType<typeof vi.fn>;onpause?:()=>void}[]=[];
  class Player {
    onpause?:()=>void;onended?:()=>void;currentTime=0;playbackRate=1;
    play=vi.fn(async()=>{});pause=vi.fn(()=>this.onpause?.());
    constructor(_url:string){players.push(this);}
  }
  vi.stubGlobal('Audio',Player);
  const state=fixture();state.delivery!.lines.push({id:'second',text:'Там Саша.',audio_url:'/sasha.mp3'});
  render(<Harness initial={state}/>);
  fireEvent.click(screen.getByRole('button',{name:'Listen: Иди прямо до фонтана.'}));
  await waitFor(()=>expect(screen.getAllByText('Pause',{exact:false}).length).toBe(1));
  fireEvent.click(screen.getByRole('button',{name:'Listen: Там Саша.'}));
  await waitFor(()=>expect(players[0].pause).toHaveBeenCalled());
  expect(screen.getAllByText('Pause',{exact:false}).length).toBe(1);
});

it('keeps listening text out of labels and queues a finished recording behind a pending route save',async()=>{
  reducedMotion();
  let player:{onended?:()=>void}|undefined;
  class Player {onended?:()=>void;onpause?:()=>void;play=vi.fn(async()=>{});pause=vi.fn();constructor(){player=this;}}
  vi.stubGlobal('Audio',Player);
  const state=fixture(),d=state.delivery!;
  d.phase='planning';d.mode='listening';d.text_visible=false;d.can_go=false;d.heard=[];delete d.lines[0].text;
  d.glossary=[];d.notebook=[{speaker:d.speaker,lines:d.lines}];
  let finishPlan:((value:ReturnType<typeof reply>)=>void)|undefined;
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);
    if(body.action==='plan')return new Promise<ReturnType<typeof reply>>(resolve=>{finishPlan=resolve;});
    expect(body.action).toBe('listen');expect(body.revision).toBe(1);
    d.revision=2;d.heard=['clue'];d.can_go=true;
    return reply(state);
  });vi.stubGlobal('fetch',fetch);
  render(<Harness initial={state}/>);
  expect(screen.queryByText('Иди прямо до фонтана.')).toBeNull();
  expect(within(screen.getByRole('complementary')).getByRole('button',{name:'Listen: Message 1'})).toBeTruthy();
  fireEvent.click(within(screen.getByRole('complementary')).getByRole('button',{name:'Listen: Message 1'}));
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Street'}));
  await waitFor(()=>expect(finishPlan).toBeTruthy());
  player!.onended?.();
  expect(fetch).toHaveBeenCalledTimes(1);
  d.revision=1;d.draft=['post','corner'];finishPlan!(reply(state));
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Walk to: Fountain'}).getAttribute('aria-disabled')).toBe('false'));
  expect(JSON.parse(fetch.mock.calls[1][1].body as string).payload).toEqual({line_id:'clue',leg:0});
});

it('can reveal directions when a recording fails',async()=>{
  class Player {onended?:()=>void;onpause?:()=>void;play=vi.fn(async()=>{throw new Error('Unavailable');});pause=vi.fn();}
  vi.stubGlobal('Audio',Player);
  const state=fixture();state.delivery!.text_visible=false;state.delivery!.mode='listening';delete state.delivery!.lines[0].text;
  const next=structuredClone(state);next.delivery!.text_visible=true;next.delivery!.lines[0].text='Иди прямо до фонтана.';
  const fetch=vi.fn(async()=>reply(next));vi.stubGlobal('fetch',fetch);
  render(<Harness initial={state}/>);
  fireEvent.click(within(screen.getByRole('complementary')).getByRole('button',{name:'Listen: Message 1'}));
  expect(await screen.findByRole('status')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Read the directions'}));
  expect(await screen.findByText('Иди прямо до фонтана.')).toBeTruthy();
  expect(JSON.parse((fetch.mock.calls as unknown as [string,RequestInit][])[0][1].body as string).payload).toEqual({kind:'transcript'});
});

it('uses the saved encounter names and exits section practice without delivering again',async()=>{
  reducedMotion();const state=fixture(),d=state.delivery!;
  d.stages=[{name:'Boris',name_ru:'Борис',title:'Finding the market',title_ru:'Поиск рынка'},{name:'Lena',name_ru:'Лена',title:'Across the bridge',title_ru:'Через мост'},{name:'The letter',name_ru:'Письмо',title:'Finding the address',title_ru:'Поиск адреса'}];
  d.phase='arrived';d.leg=2;d.reviewing=true;state.phase='practice';
  const fetch=vi.fn(async()=>reply(state));vi.stubGlobal('fetch',fetch);
  render(<Harness initial={state}/>);
  expect(screen.getByText('Boris')).toBeTruthy();
  expect(screen.getByText('Lena')).toBeTruthy();
  expect(screen.queryByRole('button',{name:/Deliver the letter/})).toBeNull();
  expect(screen.queryByRole('button',{name:/Talk to/})).toBeNull();
  fireEvent.click(screen.getAllByRole('button',{name:/Back to delivery results/})[0]);
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
  expect(JSON.parse((fetch.mock.calls as unknown as [string,RequestInit][])[0][1].body as string).action).toBe('review_exit');
});

function townFixture():GameState {
  const state=fixture(),d=state.delivery!;
  d.map={...d.map,scene:'town',width:17,height:13,tile_size:100,tiles:[],districts:[]};
  d.stages=[{name:'Collect the parcel',name_ru:'Забрать посылку',title:'Collect the parcel',title_ru:'Забрать посылку'},{name:'Find the recipient',name_ru:'Найти получателя',title:'Find the recipient',title_ru:'Найти получателя'}];
  state.title='A parcel across town';d.title_ru='Посылка через весь город';
  return state;
}

it('asks a required question before planning and displays only the saved reply once',async()=>{
  const state=townFixture(),d=state.delivery!;
  d.question_required=true;d.questions=[{id:'where',text:'Где находится аптека?',text_en:'Where is the pharmacy?'},{id:'bridge',text:'Нужно перейти мост?',text_en:'Should I cross the bridge?'}];
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);
    expect(body.action).toBe('ask');expect(body.payload).toEqual({question_id:'where'});
    d.question_required=false;d.revision++;
    const answer={id:'where-reply',text:'Аптека рядом с фонтаном.',audio_url:'/pharmacy.mp3'};
    d.questions![0].reply=answer;d.lines.push(answer);
    return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  expect((screen.getByRole('button',{name:'Plan the route'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText('Аптека рядом с фонтаном.')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Где находится аптека?'}));
  const panel=within(screen.getByRole('complementary'));
  await panel.findByText('Аптека рядом с фонтаном.');
  expect(panel.getAllByText('Аптека рядом с фонтаном.')).toHaveLength(1);
  expect((screen.getByRole('button',{name:'Plan the route'}) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole('button',{name:'Нужно перейти мост?'}) as HTMLButtonElement).disabled).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('shows a collected parcel and the task-specific arrival action without inventing a letter',async()=>{
  const state=townFixture(),d=state.delivery!;d.phase='arrived';
  d.inventory=[{id:'parcel',label:'A parcel for Anna',label_ru:'Посылка для Анны'}];
  d.arrival_text='The parcel is ready. Take it to Anna.';d.arrival_action_label='Take the parcel';
  const fetch=vi.fn(async()=>reply(state));vi.stubGlobal('fetch',fetch);
  render(<Harness initial={state}/>);
  expect(screen.getByLabelText('In your bag').textContent).toContain('A parcel for Anna');
  expect(screen.getByText('The parcel is ready. Take it to Anna.')).toBeTruthy();
  expect(screen.queryByText(/One letter|Give them the letter/)).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Take the parcel →'}));
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
  expect(JSON.parse((fetch.mock.calls as unknown as [string,RequestInit][])[0][1].body as string).action).toBe('talk');
});

it('boards before choosing transport stops and grades only after getting off',async()=>{
  reducedMotion();const state=townFixture(),d=state.delivery!;
  d.phase='planning';d.transport_leg=true;d.transport={id:'bus-4',label:'Bus 4',label_ru:'Автобус 4',board:'post',status:'waiting',stops:[{id:'post',label:'Post office',label_ru:'Почта'},{id:'fountain',label:'Fountain',label_ru:'Фонтан'}]};
  const actions:string[]=[];
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);actions.push(body.action);d.revision++;
    if(body.action==='board'){expect(body.payload).toEqual({transport_id:'bus-4'});d.transport!.status='aboard';d.transport!.stop_id='post';}
    if(body.action==='ride'){expect(body.payload).toEqual({stop_id:'fountain'});d.transport!.stop_id='fountain';d.position='fountain';}
    if(body.action==='alight'){expect(body.payload).toEqual({});d.phase='arrived';d.transport!.status='arrived';}
    return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  expect(screen.queryByRole('button',{name:'Go'})).toBeNull();
  expect(screen.queryByRole('radio',{name:/Фонтан/})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Board Bus 4'}));
  const stop=await screen.findByRole('radio',{name:/Фонтан/});
  expect((screen.getByRole('button',{name:'Get off here'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(stop);fireEvent.click(screen.getByRole('button',{name:'Travel to this stop →'}));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Get off here'}) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.queryByRole('heading',{name:'You’ve arrived.'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Get off here'}));
  expect(await screen.findByRole('heading',{name:'You’ve arrived.'})).toBeTruthy();
  expect(actions).toEqual(['board','ride','alight']);
});

it('keeps transport boarding gated by the saved listening requirement',()=>{
  const state=townFixture(),d=state.delivery!;d.phase='planning';d.transport_leg=true;d.can_go=false;
  d.transport={id:'tram',label:'Tram 2',label_ru:'Трамвай 2',board:'post',status:'waiting',stops:[]};
  render(<Harness initial={state}/>);
  expect((screen.getByRole('button',{name:'Board Tram 2'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText('Listen to the messages or read the directions before boarding.')).toBeTruthy();
});

it('builds guide directions from the actual heading and graph, then sends the planned route',async()=>{
  reducedMotion();const state=townFixture(),d=state.delivery!;d.phase='planning';d.interaction='guide';
  d.map.nodes.find(node=>node.id==='fountain')!.x=2;d.map.nodes.find(node=>node.id==='fountain')!.y=2;
  const actions:{action:string;payload:{path?:string[]}}[]=[];
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);actions.push(body);d.revision++;
    if(body.action==='plan')d.draft=body.payload.path;
    if(body.action==='go'){d.phase='arrived';d.position='fountain';}
    return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  expect((screen.getByRole('button',{name:/^Налево/}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:/^Прямо/}));
  await waitFor(()=>expect((screen.getByRole('button',{name:/^Налево/}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:/^Налево/}));
  await screen.findByText('Facing north at the end of your route. Choose the next junction or landmark.');
  expect(guideChoices(d).heading).toBe('north');
  fireEvent.click(screen.getByRole('button',{name:'Try these directions'}));
  await screen.findByRole('heading',{name:'You’ve arrived.'});
  expect(actions.map(item=>item.action)).toEqual(['plan','plan','go']);
  expect(actions.at(-1)?.payload.path).toEqual(['post','corner','fountain']);
});

it('uses the mission completion text for a task that is not a letter delivery',()=>{
  const state=townFixture(),d=state.delivery!;d.phase='completed';state.phase='completed';d.leg=1;
  d.completion_text='You helped the visitor find the station.';d.completion_text_ru='Ты помог гостю найти вокзал.';
  render(<Harness initial={state}/>);
  expect(screen.getByRole('heading',{name:'Task complete.'})).toBeTruthy();
  expect(screen.getByText('You helped the visitor find the station.')).toBeTruthy();
  expect(screen.queryByText('You helped Barsik find his way, meet the neighbours and deliver a letter.')).toBeNull();
});

it('advances a guide phrase through the straight corridor only to its first junction and undoes that whole phrase',async()=>{
  const state=townFixture(),d=state.delivery!;d.phase='planning';d.interaction='guide';
  const node=(id:string,x:number,y:number,kind='street')=>({id,x,y,kind,label:kind==='library'?'Библиотека':'Улица',label_en:kind==='library'?'Library':'Street'});
  d.map.nodes=[node('post',0,1,'post'),node('a',1,1),node('b',2,1),node('junction',3,1),node('east',4,1),node('north',3,0,'library')];
  d.map.edges=[['post','a'],['a','b'],['b','junction'],['junction','east'],['junction','north']];
  const paths:string[][]=[];
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);expect(body.action).toBe('plan');paths.push(body.payload.path);d.draft=body.payload.path;d.revision++;
    return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  fireEvent.click(screen.getByRole('button',{name:/^Прямо/}));
  await screen.findByText('Идите прямо до перекрёстка.');
  expect(paths[0]).toEqual(['post','a','b','junction']);
  expect((screen.getByRole('button',{name:/^Налево/}) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Undo'}));
  await waitFor(()=>expect(paths).toHaveLength(2));
  expect(paths[1]).toEqual(['post']);
  expect(screen.queryByLabelText('Your Russian directions')).toBeNull();
});

it.each([
  ['meeting','У северного моста','северного моста'],
  ['meeting','У южного моста','южного моста'],
  ['bridge','Северный мост','северного моста'],
  ['bridge','Южный мост','южного моста'],
])('names the %s landmark %s in guide directions', (kind,label,destination)=>{
  const d=townFixture().delivery!;
  Object.assign(d.map.nodes.find(node=>node.id==='corner')!,{kind,label});
  const forward=guideChoices(d).choices.find(choice=>choice.turn===0)!;
  expect(forward.path).toEqual(['post','corner']);
  expect(forward.phrase).toBe(`Идите прямо до ${destination}.`);
  expect(guideInstructions({...d,draft:['post','corner']})[0].phrase).toBe(forward.phrase);
});

it('describes a saved straight-street endpoint as a point and only a bend as a turn',()=>{
  const d=townFixture().delivery!;d.draft=['post','corner'];
  expect(guideInstructions(d)[0].phrase).toBe('Идите прямо до отмеченной точки.');
  Object.assign(d.map.nodes.find(node=>node.id==='fountain')!,{x:2,y:2});
  expect(guideInstructions(d)[0].phrase).toBe('Идите прямо до поворота.');
});

it('distinguishes a pedestrian entrance from a road junction in guide phrases',()=>{
  const d=townFixture().delivery!;
  d.map.nodes=[
    {id:'post',x:0,y:1,kind:'post',label:'Почта',label_en:'Post office'},
    {id:'branch',x:1,y:1,kind:'street',label:'Улица',label_en:'Street'},
    {id:'east',x:2,y:1,kind:'street',label:'Улица',label_en:'Street'},
    {id:'entry',x:1,y:0,kind:'library',label:'Библиотека',label_en:'Library'},
  ];
  d.map.edges=[['post','branch'],['branch','east'],['branch','entry']];
  d.map.street_segments=d.map.edges.map(([from,to])=>({from,to,kind:to==='entry'?'path':'main'}));
  const forward=()=>guideChoices(d).choices.find(choice=>choice.turn===0)!.phrase;
  expect(forward()).toBe('Идите прямо до пешеходной дорожки.');
  d.map.street_segments[2].kind='residential';
  expect(forward()).toBe('Идите прямо до перекрёстка.');
});

it('treats an intermediate town stop as navigation and continues from the saved position without a penalty message',async()=>{
  reducedMotion();const state=townFixture(),d=state.delivery!;
  d.phase='feedback';d.position='corner';d.walked=['post','corner'];d.draft=[...d.walked];
  d.feedback={correct:false,code:'keep_going',navigation:true,en:'You crossed the river. Continue to the library entrance.',ru:'Ты перешёл реку. Продолжай путь до входа в библиотеку.',checks:[
    {id:'crossing',label:'Cross the river',label_ru:'Перейти реку',complete:true},
    {id:'destination',label:'Reach the library entrance',label_ru:'Дойти до входа в библиотеку',complete:false},
  ]};
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);
    expect(body.action).toBe('continue');expect(body.payload).toEqual({});
    d.phase='planning';d.feedback=null;d.revision++;return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  expect(screen.getByRole('heading',{name:'Keep going.'})).toBeTruthy();
  const progress=within(screen.getByRole('list',{name:'Route progress'}));
  expect(progress.getByText('Done:')).toBeTruthy();
  expect(progress.getByText('Still to do:')).toBeTruthy();
  expect(progress.getByText('Cross the river')).toBeTruthy();
  expect(screen.queryByText(/Your first attempt is saved/)).toBeNull();
  expect(screen.queryByRole('button',{name:/Try from the last stop/})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Continue from here →'}));
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Go'}) as HTMLButtonElement).disabled).toBe(true));
  expect(d.position).toBe('corner');expect(d.first_checks).toEqual([]);
});

it('allows a town street stop and keeps the already walked route when undoing or clearing later plans',async()=>{
  reducedMotion();const state=townFixture(),d=state.delivery!;d.phase='planning';
  const actions:{action:string;payload:{path?:string[]}}[]=[];
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);actions.push(body);d.revision++;
    if(body.action==='plan')d.draft=body.payload.path;
    if(body.action==='go'){d.position=d.draft.at(-1)!;d.walked=[...d.draft];d.phase='feedback';d.feedback={correct:false,navigation:true,code:'keep_going',en:'Continue along the street.',ru:'Продолжай идти по улице.'};}
    if(body.action==='continue'){d.phase='planning';d.feedback=null;d.draft=[...d.walked!];}
    return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  // Adjacent street dots remain selectable even when a corridor shortcut also exists.
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Street'}));
  await waitFor(()=>expect(actions[0].payload.path).toEqual(['post','corner']));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Go'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Go'}));
  fireEvent.click(await screen.findByRole('button',{name:'Continue from here →'}));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Undo'}) as HTMLButtonElement).disabled).toBe(true));
  expect((screen.getByRole('button',{name:'Clear route'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Fountain'}));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Undo'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Undo'}));
  await waitFor(()=>expect(actions.at(-1)?.payload.path).toEqual(['post','corner']));
  fireEvent.click(screen.getByRole('button',{name:'Walk to: Fountain'}));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Clear route'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Clear route'}));
  await waitFor(()=>expect(actions.at(-1)?.payload.path).toEqual(['post','corner']));
  expect(d.walked).toEqual(['post','corner']);expect(d.position).toBe('corner');
});

it('removes only unwalked guide phrases when undoing a continued route',async()=>{
  const state=townFixture(),d=state.delivery!;d.phase='planning';d.interaction='guide';
  Object.assign(d.map.nodes.find(node=>node.id==='fountain')!,{x:2,y:2});
  d.walked=['post','corner'];d.position='corner';d.draft=['post','corner','fountain'];
  expect(guideInstructions(d)).toEqual([{phrase:'Поверните налево и идите до фонтана.',from:1,to:2}]);
  const fetch=vi.fn(async(_url:string,request:RequestInit)=>{
    const body=JSON.parse(request.body as string);expect(body.action).toBe('plan');expect(body.payload.path).toEqual(['post','corner']);
    d.draft=body.payload.path;d.revision++;return reply(state);
  });vi.stubGlobal('fetch',fetch);render(<Harness initial={state}/>);
  fireEvent.click(screen.getByRole('button',{name:'Undo'}));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Undo'}) as HTMLButtonElement).disabled).toBe(true));
  expect(screen.queryByLabelText('Your Russian directions')).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('labels only supplied contacts on the town map so a named meeting place is visible',()=>{
  const state=townFixture(),d=state.delivery!;
  d.encounters=[{position:'corner',speaker:{name:'Сергей',name_en:'Sergei',role:'У моста',role_en:'By the bridge',portrait:'sergei'}}];
  render(<Harness initial={state}/>);
  const marker=screen.getByLabelText('Sergei');
  expect(marker.textContent).toContain('Sergei');
  expect(screen.queryByLabelText('You met: Sergei')).toBeNull();
  expect(screen.queryByLabelText('Sasha')).toBeNull();
});
