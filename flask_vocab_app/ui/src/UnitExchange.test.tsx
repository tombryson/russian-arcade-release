import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {UnitExchange} from './UnitExchange';

vi.mock('./PilotRecording',()=>({PilotRecording:({disabled,onReady,onLockChange}:{disabled:boolean;onReady:(blob:Blob,filename:string)=>void;onLockChange:(locked:boolean)=>void})=><button disabled={disabled} onClick={()=>{onLockChange(true);onReady(new Blob(['original'],{type:'audio/webm'}),'reply.webm');}}>Record test reply</button>}));
const first={id:'x1',profile_id:'p1',revision:0,title:'Where shall we meet?',title_ru:'Где встретимся?',prompt:'Listen and reply to Nina. Two short replies.',current_turn:{id:'now',audio_url:'/api/v1/unit-exchanges/x1/prompts/now/audio',audio_available:true,listened:false,playbacks:0,plays_remaining:2},turns:[{id:'now',saved:false},{id:'next',saved:false}],work_state:'draft',availability:'available',condition:'unverified',origin:{href:'/curriculum/units/location-destination-v2?run=r1',title:'Where shall we meet?'}};
const heard={...first,revision:1,current_turn:{...first.current_turn,listened:true,playbacks:1,plays_remaining:1}};
const next={...first,revision:2,current_turn:{...first.current_turn,id:'next',listened:false},turns:[{id:'now',saved:true,recording_url:'/api/v1/unit-exchanges/x1/turns/now/audio'},{id:'next',saved:false}]};
const complete={...next,revision:4,current_turn:null,turns:[...next.turns.slice(0,1),{id:'next',saved:true,recording_url:'/api/v1/unit-exchanges/x1/turns/next/audio'}],work_state:'submitted'};
const response=(body:unknown,ok=true)=>Promise.resolve({ok,json:async()=>body});
beforeEach(()=>{vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

it.each(['en','ru'] as const)('offers owned study previews only after feedback in %s',async language=>{
  const action={kind:'phrasebook',href:'/feedback-study/unit_exchange/x1/phrasebook',label:'Save useful phrases',label_ru:'Сохранить полезные фразы'};
  const fetch=vi.fn((url:string)=>response(url.endsWith('/review')?{...complete,work_state:'reviewed',feedback:{summary:'Saved feedback'},study_actions:[action]}:{...complete,study_actions:[action]}));vi.stubGlobal('fetch',fetch);
  const meta=document.createElement('meta');meta.name='app-base-path';meta.content='/demo';document.head.append(meta);
  try{
    render(<UnitExchange id="x1" profileId="p1" language={language}/>);
    await screen.findByText(language==='ru'?'Оба ответа сохранены.':'Both replies are saved.');
    expect(screen.queryByRole('link',{name:action.label})).toBeNull();expect(screen.queryByRole('link',{name:action.label_ru})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:language==='ru'?'Получить отзыв':'Get feedback'}));
    const link=await screen.findByRole('link',{name:language==='ru'?action.label_ru:action.label});
    expect(link.getAttribute('href')).toBe('/demo'+action.href);expect(fetch).toHaveBeenCalledTimes(2);
  }finally{meta.remove();}
});

it('requires a saved listening receipt before recording and advances only after original audio is saved',async()=>{
  const fetch=vi.fn((url:string)=>response(url.endsWith('/listened')?heard:url.endsWith('/recording')?next:first));vi.stubGlobal('fetch',fetch);
  render(<UnitExchange id="x1" profileId="p1"/>);
  const audio=await screen.findByLabelText('Listen to Nina');
  expect((screen.getByRole('button',{name:'Record test reply'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.ended(audio);
  await waitFor(()=>expect((screen.getByRole('button',{name:'Record test reply'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Record test reply'}));
  fireEvent.click(await screen.findByRole('button',{name:'Send reply'}));
  await screen.findByLabelText('Saved reply 1');
  expect((screen.getByRole('button',{name:'Record test reply'}) as HTMLButtonElement).disabled).toBe(true);
  const upload=fetch.mock.calls.find(([url])=>url.endsWith('/recording'));
  expect(upload?.[0]).toContain('/turns/now/recording');
});

it('keeps an uncertain upload for explicit retry with the identical body',async()=>{
  let sends=0;
  const fetch=vi.fn((url:string,_options?:RequestInit)=>url.endsWith('/recording')?++sends===1?Promise.reject(new TypeError('Connection lost')):response(next):response(heard));vi.stubGlobal('fetch',fetch);
  render(<UnitExchange id="x1" profileId="p1"/>);
  fireEvent.click(await screen.findByRole('button',{name:'Record test reply'}));
  fireEvent.click(await screen.findByRole('button',{name:'Send reply'}));
  fireEvent.click(await screen.findByRole('button',{name:'Try saving again'}));
  await screen.findByLabelText('Saved reply 1');
  const uploads=fetch.mock.calls.filter(([url])=>url.endsWith('/recording'));
  expect(uploads).toHaveLength(2);expect(uploads[0][1]?.body).toBe(uploads[1][1]?.body);
});

it('reopens two saved replies without a paid review and retries feedback only when requested',async()=>{
  const fetch=vi.fn((url:string)=>response(url.endsWith('/review')?{...complete,work_state:'review_unavailable'}:complete));vi.stubGlobal('fetch',fetch);
  render(<UnitExchange id="x1" profileId="p1"/>);
  await screen.findByText('Both replies are saved.');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button',{name:'Record test reply'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Get feedback'}));
  await screen.findByText('Your replies are saved. Feedback is unavailable.');
  expect(screen.getByRole('button',{name:'Retry feedback'})).toBeTruthy();
  expect(screen.getByText(/Independent conditions were not checked/)).toBeTruthy();
});

it('does not offer an original spoken response when the authored recording is unavailable',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>response({...first,current_turn:{...first.current_turn,audio_url:null,audio_available:false},availability:'audio_unavailable'})));
  render(<UnitExchange id="x1" profileId="p1" language="ru"/>);
  await screen.findByText(/Аудио недоступно/);
  expect((screen.getByRole('button',{name:'Record test reply'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('link',{name:'Where shall we meet?'}).getAttribute('href')).toContain('?run=r1');
});


it('leaves Listen usable when autoplay is blocked without creating a listened receipt',async()=>{
  vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValue(new Error('Autoplay denied'));
  const fetch=vi.fn(()=>response(first));vi.stubGlobal('fetch',fetch);
  render(<UnitExchange id="x1" profileId="p1"/>);
  const player=await screen.findByLabelText('Listen to Nina') as HTMLAudioElement;
  await waitFor(()=>expect(HTMLMediaElement.prototype.play).toHaveBeenCalled());
  expect(player.controls).toBe(true);expect(fetch).toHaveBeenCalledTimes(1);
  expect((screen.getByRole('button',{name:'Record test reply'}) as HTMLButtonElement).disabled).toBe(true);
});

it('records the permitted replay before removing further playback controls',async()=>{
  const fetch=vi.fn((url:string)=>response(url.endsWith('/listened')?{...heard,revision:2,current_turn:{...heard.current_turn,playbacks:2,plays_remaining:0}}:heard));vi.stubGlobal('fetch',fetch);
  render(<UnitExchange id="x1" profileId="p1"/>);
  fireEvent.ended(await screen.findByLabelText('Listen to Nina'));
  await screen.findByText(/You have listened twice/);
  expect(screen.queryByLabelText('Listen to Nina')).toBeNull();
  expect((screen.getByRole('button',{name:'Record test reply'}) as HTMLButtonElement).disabled).toBe(false);
});

it('pauses Nina before recording and rejects late replay events while an unsent reply is present',async()=>{
  const fetch=vi.fn(()=>response(heard));vi.stubGlobal('fetch',fetch);
  render(<UnitExchange id="x1" profileId="p1"/>);
  const player=await screen.findByLabelText('Listen to Nina') as HTMLAudioElement;
  vi.mocked(HTMLMediaElement.prototype.pause).mockClear();
  fireEvent.click(screen.getByRole('button',{name:'Record test reply'}));
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  expect(player.controls).toBe(false);
  vi.mocked(HTMLMediaElement.prototype.pause).mockClear();
  fireEvent.play(player);
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  fireEvent.ended(player);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button',{name:'Send reply'})).toBeTruthy();
});

it.each(['en','ru'] as const)('shows the prescribed transfer situation in %s even without map places',async(language)=>{
  const scene={places:[],instruction:'You are at the pharmacy and are going to the café.',instruction_ru:'Вы сейчас в аптеке и идёте в кафе.'};
  vi.stubGlobal('fetch',vi.fn(()=>response({...first,scene})));
  render(<UnitExchange id="x1" profileId="p1" language={language}/>);
  const text=language==='ru'?scene.instruction_ru:scene.instruction;
  expect(await screen.findByText(text,{exact:false})).toBeTruthy();
  expect(screen.getByText(language==='ru'?'Ваша ситуация:':'Your situation:')).toBeTruthy();
  expect(screen.queryByText(/^(Places:|Места:)/)).toBeNull();
  expect(screen.queryByText(language==='ru'?scene.instruction:scene.instruction_ru,{exact:false})).toBeNull();
});
