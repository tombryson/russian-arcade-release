import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {JourneyGame} from './JourneyGames';
import {VocabularyPicture} from './GameBoards';
import type {GameCatalogueState,GameState} from './journey-games-api';

const response=(data:unknown,ok=true)=>({ok,json:async()=>structuredClone(data)});
const catalogue:GameCatalogueState={profile_id:'tom',sources:{word_count:318,form_count:1886,topics:['Travel','Nature'],lessons:[{id:'lesson-1',title:'A walk through Siberia',count:27}]},games:[{id:'pairs',title:'Postcard Pairs',description:'Match Russian to pictures.',lesson_id:'bag',lesson_title:'What’s in the bag?',lesson_href:'#first-steps/bag',unlocked:true,new:false,active_session_id:null}]};
const ready:GameState={profile_id:'tom',id:'vocab-game',game_id:'pairs',title:'Postcard Pairs',phase:'play',round_index:0,total_rounds:5,round:{id:'round-1',prompt:'Match the sentences to their pictures.',clues:[],max_choices:2,left:[{id:'l0',text:'Гроза прошла.',audio_key:'storm-audio'},{id:'l1',text:'Я изучаю русский язык.',audio_key:'study-audio'}],right:[{id:'r0',visual:'scene',label:'A person studying',image_url:'/media/studying.webp'},{id:'r1',visual:'scene',label:'A storm has passed',image_url:'/media/storm.webp'}]},result:null,reward:null,source:{kind:'vocabulary',title:'My vocabulary',href:'#words'}};
const preparing:GameState={...ready,phase:'preparing',round:null,preparation:{status:'pending',ready:0,total:15,stage:'examples',message:'Preparing examples from your vocabulary.'}};
function service(initial=preparing){const state={catalogue:structuredClone(catalogue),initial:structuredClone(initial),queue:[structuredClone(ready)],hold:false,release:undefined as undefined|(()=>void),fail:false};const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
  if(url==='/api/v1/games')return response(state.catalogue);
  if(url.endsWith('/start'))return response(state.initial);
  if(url.endsWith('/prepare')){if(state.hold){state.hold=false;await new Promise<void>(resolve=>{state.release=resolve;});}if(state.fail){state.fail=false;return response({error:{code:'unavailable',message:'The connection paused. Try again.'}},false);}return response(state.queue.shift()??ready);}
  if(request?.method==='GET')return response(state.initial);
  throw new Error(`Unexpected request ${url}`);
});vi.stubGlobal('fetch',fetch);return {state,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};}
async function click(name:string){fireEvent.click(await screen.findByRole('button',{name,exact:true}));}
beforeEach(()=>{window.location.hash='games/pairs';vi.stubGlobal('scrollTo',vi.fn());});afterEach(()=>vi.unstubAllGlobals());

describe('Vocabulary-driven game setup',()=>{
  it('defaults to the real vocabulary pool and creates five rounds only after an explicit start',async()=>{
    const api=service();const view=render(<JourneyGame gameId="pairs"/>);await screen.findByText(/318 words/);expect(api.posts()).toHaveLength(0);expect((screen.getByLabelText('Word source') as HTMLSelectElement).value).toBe('vocabulary');expect((screen.getByLabelText('Game length') as HTMLSelectElement).value).toBe('5');await click('Let’s play');await screen.findByText('Opening your saved game…');expect(api.posts()).toHaveLength(1);view.rerender(<JourneyGame key="session" sessionId="vocab-game"/>);await screen.findByRole('button',{name:'Гроза прошла.'});
    expect(JSON.parse(api.posts()[0][1]!.body as string)).toMatchObject({options:{source:'vocabulary',rounds:5}});expect(api.posts().filter(([url])=>url.endsWith('/prepare'))).toHaveLength(1);expect(api.posts().some(([url])=>url.includes('/media/'))).toBe(false);expect(screen.getByRole('link',{name:'Back to vocabulary'}).getAttribute('href')).toBe('#words');
  });
  it('uses the selected lesson and removes vocabulary-only topic and difficulty filters',async()=>{
    const api=service();const view=render(<JourneyGame gameId="pairs"/>);await screen.findByText(/318 words/);fireEvent.change(screen.getByLabelText('Topic'),{target:{value:'Nature'}});fireEvent.change(screen.getByLabelText('Vocabulary difficulty'),{target:{value:'3'}});fireEvent.change(screen.getByLabelText('Word source'),{target:{value:'lesson:lesson-1'}});expect(screen.queryByLabelText('Topic')).toBeNull();expect(screen.queryByLabelText('Vocabulary difficulty')).toBeNull();fireEvent.change(screen.getByLabelText('Game length'),{target:{value:'10'}});await click('Let’s play');await screen.findByText('Opening your saved game…');view.rerender(<JourneyGame key="session" sessionId="vocab-game"/>);await screen.findByRole('button',{name:'Гроза прошла.'});expect(JSON.parse(api.posts()[0][1]!.body as string).options).toEqual({source:'lesson',lesson_id:'lesson-1',rounds:10});
  });
  it('lets new learners start with fresh words when their vocabulary is empty',async()=>{
    const api=service();api.state.catalogue.sources!.word_count=0;render(<JourneyGame gameId="pairs"/>);await screen.findByText(/0 words/);expect((screen.getByRole('button',{name:'Let’s play'}) as HTMLButtonElement).disabled).toBe(false);expect(screen.queryByText(/Add words to/)).toBeNull();expect(api.posts()).toHaveLength(0);
  });
  it('sends topic and difficulty filters when practising the vocabulary library',async()=>{
    const api=service();render(<JourneyGame gameId="pairs"/>);await screen.findByText(/318 words/);fireEvent.change(screen.getByLabelText('Topic'),{target:{value:'Nature'}});fireEvent.change(screen.getByLabelText('Vocabulary difficulty'),{target:{value:'3'}});await click('Let’s play');await screen.findByText('Opening your saved game…');expect(JSON.parse(api.posts()[0][1]!.body as string).options).toEqual({source:'vocabulary',topic:'Nature',difficulty:3,rounds:5});
  });
  it('offers a recoverable error for an incomplete source catalogue',async()=>{
    const api=service();api.state.catalogue.sources={word_count:318} as never;render(<JourneyGame gameId="pairs"/>);await screen.findByText('Your word sources could not load. Please try again.');expect(screen.getByRole('button',{name:'Try again'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Let’s play'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });
  it('offers a direct saved-game link while a new game explicitly uses the selected vocabulary options',async()=>{
    const api=service();api.state.catalogue.games[0].active_session_id='saved-before';render(<JourneyGame gameId="pairs"/>);expect((await screen.findByRole('link',{name:'Continue saved game'})).getAttribute('href')).toBe('#games/session/saved-before');expect(api.posts()).toHaveLength(0);fireEvent.change(screen.getByLabelText('Game length'),{target:{value:'10'}});await click('Start a new game');await screen.findByText('Opening your saved game…');expect(JSON.parse(api.posts()[0][1]!.body as string)).toMatchObject({new_game:true,options:{source:'vocabulary',rounds:10}});
  });
  it('uses generated vocabulary pictures rather than showing an unrelated letter illustration',async()=>{
    service(ready);const view=render(<JourneyGame sessionId="vocab-game"/>);await screen.findByRole('button',{name:'Match with A storm has passed'});expect(view.container.querySelector('img[src="/media/storm.webp"]')).toBeTruthy();expect(view.container.querySelector('img[src="/media/studying.webp"]')).toBeTruthy();
  });
  it('keeps a legacy illustration when a saved old game has no generated image URL',()=>{
    const view=render(<VocabularyPicture visual="map"/>);expect(view.container.querySelector('svg')).toBeTruthy();expect(view.container.querySelector('img')).toBeNull();
  });
});

describe('Saved game preparation',()=>{
  it('resumes pending preparation on refresh and progresses to the prepared game',async()=>{
    const api=service();render(<JourneyGame sessionId="vocab-game"/>);await screen.findByRole('button',{name:'Гроза прошла.'});expect(api.posts()).toHaveLength(1);expect(api.posts()[0][0]).toBe('/api/v1/games/sessions/vocab-game/prepare');expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({});
  });
  it('keeps a single preparation loop while completed media progress advances',async()=>{
    const api=service();api.state.queue=[{...preparing,preparation:{...preparing.preparation!,status:'running',ready:6}},ready];render(<JourneyGame sessionId="vocab-game"/>);await screen.findByText('6 of 15 ready');expect(screen.getAllByRole('progressbar',{name:'Game preparation'})).toHaveLength(1);await screen.findByRole('button',{name:'Гроза прошла.'}, {timeout:2500});expect(api.posts()).toHaveLength(2);expect(api.posts().every(([url])=>url==='/api/v1/games/sessions/vocab-game/prepare')).toBe(true);
  });
  it('does not restart a failed preparation until Retry is clicked',async()=>{
    const api=service({...preparing,preparation:{...preparing.preparation!,status:'failed',ready:4,error:'One picture could not be saved.'}});render(<JourneyGame sessionId="vocab-game"/>);await screen.findByText('One picture could not be saved.');expect(api.posts()).toHaveLength(0);await click('Retry preparation');await screen.findByRole('button',{name:'Гроза прошла.'});expect(JSON.parse(api.posts()[0][1]!.body as string)).toEqual({retry:true});
  });
  it('stops a successful HTTP preparation response marked failed and preserves its progress for retry',async()=>{
    const api=service();api.state.queue=[{...preparing,preparation:{...preparing.preparation!,status:'failed',ready:8,error:'Audio needs a retry.'}},ready];render(<JourneyGame sessionId="vocab-game"/>);await screen.findByText('Audio needs a retry.');expect(screen.getByText('8 of 15 ready')).toBeTruthy();expect(api.posts()).toHaveLength(1);await click('Retry preparation');await screen.findByRole('button',{name:'Гроза прошла.'});expect(api.posts()).toHaveLength(2);
  });
  it('recovers a lost preparation response without starting a second game',async()=>{
    const api=service();api.state.fail=true;render(<JourneyGame sessionId="vocab-game"/>);await screen.findByText('The connection paused. Try again.');await click('Retry preparation');await screen.findByRole('button',{name:'Гроза прошла.'});expect(api.posts().map(([url])=>url)).toEqual(['/api/v1/games/sessions/vocab-game/prepare','/api/v1/games/sessions/vocab-game/prepare']);
  });
  it('clears the game if preparation responds for a different profile',async()=>{
    const api=service();api.state.queue=[{...ready,profile_id:'other'}];render(<JourneyGame sessionId="vocab-game"/>);await screen.findByRole('alert');expect(screen.getByRole('link',{name:'Reopen activities'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Гроза прошла.'})).toBeNull();
  });
  it('ignores an in-flight preparation when the learner leaves the game',async()=>{
    const api=service();api.state.hold=true;const view=render(<JourneyGame sessionId="vocab-game"/>);await waitFor(()=>expect(api.state.release).toBeDefined());view.unmount();window.location.hash='home';await act(async()=>api.state.release?.());expect(window.location.hash).toBe('#home');expect(api.posts()).toHaveLength(1);
  });
});
