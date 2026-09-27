import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {JourneyGame} from './JourneyGames';
import {GameWords} from './GameWords';
import type {GameState,GameWordLookup} from './journey-games-api';

const response=(data:unknown,ok=true)=>({ok,json:async()=>structuredClone(data)});
const script='Доброе утро! Сегодня в городе открылся новый книжный магазин.';
const round={id:'q1',prompt:'Что открылось в городе?',clues:[],max_choices:1,choices:[{id:'bookshop',text:'Книжный магазин'},{id:'cafe',text:'Новое кафе'},{id:'museum',text:'Музей'},{id:'school',text:'Школа'}]};
const initial:GameState={id:'broadcast-1',profile_id:'tom',game_id:'radio',title:'Post Office Radio',phase:'listening',broadcast:{title:'Good news in town',audio_key:'full-programme',duration_seconds:62,listened:false,transcript:false},round_index:0,total_rounds:4,round:null,result:null,reward:null,source:{kind:'vocabulary',title:'My vocabulary',href:'#words'}};
function service(start=initial){const state={game:structuredClone(start),fail:'',word:{word:'книжный',lemma:'книжный',in_vocabulary:false,can_add:true,context:'Сегодня в городе открылся новый книжный магазин.',meaning:'book (relating to books)',choices:[],dictionary_url:'https://en.openrussian.org/ru/книжный'} as GameWordLookup};
  const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
    const action=url.split('/').at(-1)!;
    if(action===state.fail){state.fail='';return response({error:{code:'unavailable',message:'The connection paused.'}},false);}
    if(url.includes('/media/'))return response({status:'ready',url:'/media/whole-show.mp3'});
    if(url.includes('/words?'))return response(state.word);
    if(action==='words'){const body=JSON.parse(request!.body as string);state.word={...state.word,lemma:body.lemma,pos:body.pos,in_vocabulary:true,can_add:false,added:true,choices:[]};return response(state.word);}
    if(url==='/api/v1/games')return response({profile_id:'tom',sources:{word_count:0,form_count:0,topics:['Town','Travel'],lessons:[]},games:[{id:'radio',title:'Post Office Radio',description:'Listen to a programme.',lesson_id:'cafe',lesson_title:'A café stop',lesson_href:'#first-steps/cafe',unlocked:true,new:false,active_session_id:null}]});
    if(action==='listen')state.game.broadcast!.listened=true;
    if(action==='transcript'){state.game.broadcast!.transcript=true;state.game.broadcast!.script=script;}
    if(action==='quiz'){state.game.phase='play';state.game.round=structuredClone(round);}
    if(action==='hint')state.game.round!.hint='What new place opened?';
    if(action==='answer'){const body=JSON.parse(request!.body as string);state.game.phase='feedback';state.game.result={answer:body.answer,correct:true,expected_answer:['bookshop'],feedback:'В городе открылся книжный магазин.'};}
    if(action==='continue'){state.game.phase='ready';state.game.round=null;}
    if(action==='complete'){state.game.phase='completed';state.game.broadcast!.script=script;state.game.words=[{lemma:'книжный',form:'книжный',in_vocabulary:false}];}
    return response(state.game);
  });vi.stubGlobal('fetch',fetch);return {state,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};
}
async function click(name:string){fireEvent.click(await screen.findByRole('button',{name,exact:true}));}
beforeEach(()=>{vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

describe('A full radio programme',()=>{
  it('offers a one-minute programme without picture preparation, a word-source selector or a round-length choice',async()=>{
    const api=service();render(<JourneyGame gameId="radio"/>);await screen.findByText('About a minute · 4 questions');expect(screen.queryByLabelText('Word source')).toBeNull();expect(screen.queryByLabelText('Game length')).toBeNull();expect((screen.getByRole('button',{name:'Tune in'}) as HTMLButtonElement).disabled).toBe(false);expect(api.posts()).toHaveLength(0);
  });
  it('records listening only after the programme ends, then explicitly opens four text questions',async()=>{
    const api=service();const view=render(<JourneyGame sessionId="broadcast-1"/>);const player=await screen.findByLabelText('Listen to the radio programme');const begin=screen.getByRole('button',{name:'Answer the questions'}) as HTMLButtonElement;expect(begin.disabled).toBe(true);expect(view.container.querySelector('img')).toBeNull();expect(screen.queryByText(round.prompt)).toBeNull();expect(screen.queryByText(script)).toBeNull();fireEvent.play(player);expect(api.posts()).toHaveLength(0);fireEvent.ended(player);await waitFor(()=>expect(begin.disabled).toBe(false));expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({round_id:'broadcast',audio_key:'full-programme'});await click('Answer the questions');await screen.findByText('Question 1 of 4');expect(screen.getByRole('heading',{name:round.prompt})).toBeTruthy();expect(screen.getAllByRole('button',{pressed:false}).length).toBe(4);expect(screen.getByLabelText('Listen to the radio programme')).toBe(player);expect(api.posts().map(([url])=>url.split('/').at(-1))).toEqual(['listen','quiz']);expect(api.fetch.mock.calls.filter(([url])=>url.includes('/media/'))).toHaveLength(1);
  });
  it('keeps the transcript optional and allows assisted practice without an audio receipt',async()=>{
    const api=service();render(<JourneyGame sessionId="broadcast-1"/>);await click('Show transcript');await screen.findByText('Programme transcript');expect(screen.getByRole('button',{name:'Сегодня'})).toBeTruthy();await click('Answer the questions');await screen.findByText('Question 1 of 4');expect(api.posts().some(([url])=>url.endsWith('/listen'))).toBe(false);
  });
  it('preserves the selected answer when the learner opens the transcript or asks for a hint',async()=>{
    const api=service({...initial,phase:'play',round,broadcast:{...initial.broadcast!,listened:true}});render(<JourneyGame sessionId="broadcast-1"/>);await click('Книжный магазин');await click('Show transcript');await screen.findByText('Programme transcript');expect(screen.getByRole('button',{name:'Книжный магазин'}).getAttribute('aria-pressed')).toBe('true');await click('Show a hint');await screen.findByText('What new place opened?');expect(screen.getByRole('button',{name:'Книжный магазин'}).getAttribute('aria-pressed')).toBe('true');await click('Check answer');await screen.findByText('That’s right.');expect(JSON.parse(api.posts().find(([url])=>url.endsWith('/answer'))![1]!.body as string).answer).toEqual(['bookshop']);
  });
  it('lets a failed audio receipt be retried without creating another programme',async()=>{
    const api=service();api.state.fail='listen';render(<JourneyGame sessionId="broadcast-1"/>);fireEvent.ended(await screen.findByLabelText('Listen to the radio programme'));await screen.findByText('The connection paused.');expect((screen.getByRole('button',{name:'Answer the questions'}) as HTMLButtonElement).disabled).toBe(true);await click('Try again');await waitFor(()=>expect((screen.getByRole('button',{name:'Answer the questions'}) as HTMLButtonElement).disabled).toBe(false));expect(api.posts().map(([url])=>url.split('/').at(-1))).toEqual(['listen','listen']);
  });
  it('shows the recorded quiz result when reopening a completed programme',async()=>{
    service({...initial,phase:'completed',summary:{correct_rounds:3,total_rounds:4,matched:3,total:4}});render(<JourneyGame sessionId="broadcast-1"/>);await screen.findByText('Thanks for listening.');expect(screen.getByText('3 / 4')).toBeTruthy();expect(screen.queryByText('Question 1 of 4')).toBeNull();
  });
});

describe('Discovering words in game context',()=>{
  it.each(['lookup','add'])('removes the New badge after vocabulary membership is confirmed by %s',async method=>{
    const api=service();if(method==='lookup')api.state.word={...api.state.word,in_vocabulary:true,can_add:false};render(<GameWords sessionId="broadcast-1" words={[{lemma:'книжный',form:'книжный',in_vocabulary:false}]}/>);expect(screen.getByText('New')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:/книжный.*New/}));await screen.findByText('book (relating to books)');if(method==='add'){expect(screen.getByText('New')).toBeTruthy();await click('Add to my words');await screen.findByText('Added to your vocabulary.');}expect(screen.queryByText('New')).toBeNull();expect(screen.getByRole('button',{name:'книжный'})).toBeTruthy();expect(api.posts()).toHaveLength(method==='add'?1:0);
  });
  it('looks up a transcript word only on selection and saves it only on an explicit add',async()=>{
    const api=service();render(<GameWords sessionId="broadcast-1" text={script}/>);expect(api.fetch).not.toHaveBeenCalled();await click('книжный');await screen.findByText('book (relating to books)');expect(api.posts()).toHaveLength(0);await click('Add to my words');await screen.findByText('Added to your vocabulary.');expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({word:'книжный',lemma:'книжный'});expect(screen.queryByRole('button',{name:'Add to my words'})).toBeNull();
  });
  it('keeps homographic noun and verb entries separate and sends the chosen part of speech',async()=>{
    const api=service();api.state.word={word:'печь',lemma:'',in_vocabulary:false,can_add:false,choices:[{lemma:'печь',pos:'Noun',label:'печь · Noun',in_vocabulary:true,can_add:false},{lemma:'печь',pos:'Verb',label:'печь · Verb',in_vocabulary:false,can_add:true}]};render(<GameWords sessionId="broadcast-1" text="Будем печь хлеб."/>);await click('печь');await screen.findByText('Which word is used here?');fireEvent.click(screen.getByRole('radio',{name:'печь · Noun'}));expect(screen.getByText('Already in your vocabulary.')).toBeTruthy();expect(screen.queryByRole('button',{name:'Add to my words'})).toBeNull();fireEvent.click(screen.getByRole('radio',{name:'печь · Verb'}));await click('Add to my words');await screen.findByText('Added to your vocabulary.');expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({word:'печь',lemma:'печь',pos:'Verb'});
  });
  it('explains a word that the dictionary cannot resolve instead of showing an empty lookup',async()=>{
    const api=service();api.state.word={word:'Барсик',lemma:null,pos:null,grammar:{},in_vocabulary:false,can_add:false,choices:[],message:'This spelling could not be found in the Russian dictionary.'};render(<GameWords sessionId="broadcast-1" text="Барсик идёт домой."/>);await click('Барсик');await screen.findByText('This spelling could not be found in the Russian dictionary.');expect(screen.queryByRole('button',{name:'Add to my words'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });
});
