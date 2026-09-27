import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {fireEvent, render, screen, within} from '@testing-library/preact';
import {JourneyGame} from './JourneyGames';
import {SceneBuilder} from './SceneBuilder';
import {GameLanguage} from './GameLocale';
import type {GameRound, GameState, MotionVisual} from './journey-games-api';

const round:GameRound={id:'under-table',mechanic:'scene-builder',objective:'grammar',prompt:'Complete the Russian sentence to describe the scene.',clues:[],max_choices:2,scene_builder:{family:'location',scenario:'Barsik is sitting under the table.',scenario_ru:'Барсик прячется внизу, под столом.',scene:'cat-under-table',segments:['Барсик сидит ',' ','.'],slots:[{id:'preposition',label:'Choose the preposition',label_ru:'Выберите предлог',choices:[{id:'preposition:on',text:'на'},{id:'preposition:under',text:'под'},{id:'preposition:behind',text:'за'}]},{id:'noun',label:'Choose the ending',label_ru:'Выберите окончание',choices:[{id:'noun:nominative',text:'стол'},{id:'noun:prepositional',text:'столе'},{id:'noun:instrumental',text:'столом'}]}]}};
const initial=():GameState=>({id:'scene-test',profile_id:'me',game_id:'scene-builder',title:'Describe the scene',phase:'play',round_index:0,total_rounds:5,round:structuredClone(round),result:null,reward:null,source:{kind:'grammar',title:'Russian grammar',href:'#games/scene-builder'}});
const response=(value:unknown,ok=true)=>({ok,json:async()=>structuredClone(value)});
function service() {
  const model={state:initial(),failAnswer:false};
  const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
    if(url==='/api/v1/games')return response({profile_id:'me',games:[{id:'scene-builder',title:'Describe the scene',description:'Build the sentence.',lesson_id:'bag',lesson_title:'What’s in the bag?',lesson_href:'#first-steps/bag',unlocked:true,new:true,active_session_id:null}]});
    if(request?.method==='GET')return response(model.state);
    const body=JSON.parse(request?.body as string);
    if(url.endsWith('/hint'))model.state.round={...model.state.round!,hint:'Use под for under. It takes the instrumental case here.',hint_ru:'Предлог под здесь требует творительного падежа.'};
    if(url.endsWith('/answer')){
      if(model.failAnswer){model.failAnswer=false;return response({error:{code:'unavailable',message:'Please try saving again.'}},false);}
      model.state.phase='feedback';model.state.result={answer:body.answer,correct:false,expected_answer:['preposition:under','noun:instrumental'],feedback:'The place is right. Check the ending.',slot_results:[{id:'preposition',correct:true,expected:'preposition:under',text:'под',explanation:'Under is right.',explanation_ru:'Предлог выбран правильно.'},{id:'noun',correct:false,expected:'noun:instrumental',text:'столом',explanation:'Use столом for a position under the table.',explanation_ru:'Для положения под столом нужна форма столом.'}]};
    }
    if(url.endsWith('/continue')){model.state.round={...round,id:'next',scene_builder:{...round.scene_builder!,scene:'cat-on-table',scenario:'Barsik is on the table.'}};model.state.phase='play';model.state.round_index=1;model.state.result=null;}
    return response(model.state);
  });vi.stubGlobal('fetch',fetch);return {model,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};
}
const click=async(name:string)=>fireEvent.click(await screen.findByRole('button',{name,exact:true}));
beforeEach(()=>{vi.stubGlobal('scrollTo',vi.fn());});afterEach(()=>vi.unstubAllGlobals());

describe('Describe the scene',()=>{
  it('starts with grammar topics and a game length without vocabulary restrictions',async()=>{
    const api=service();render(<JourneyGame gameId="scene-builder"/>);
    await screen.findByRole('button',{name:'Location'});
    expect(screen.queryByLabelText('Word source')).toBeNull();expect(screen.queryByText('Choose words')).toBeNull();
    expect(screen.queryByRole('group',{name:'Motion level'})).toBeNull();
    await click('Verbs of motion');
    expect(screen.getByRole('button',{name:'A1 Everyday journeys'}).getAttribute('aria-pressed')).toBe('true');
    await click('10 rounds');await click('Let’s play');
    const request=JSON.parse(api.posts()[0][1]!.body as string);expect(request.options).toEqual({grammar_focus:'motion',rounds:10,motion_level:'A1'});
  });
  it.each([['Verbs of motion','motion'],['Mixed practice','mixed']])('sends the chosen motion level for %s',async(topic,focus)=>{
    const api=service();render(<JourneyGame gameId="scene-builder"/>);
    await click(topic);await click('B1 Complex journeys');
    expect(screen.getByRole('button',{name:'B1 Complex journeys'}).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('Combine movements in longer routes and situations with more than one action.')).toBeTruthy();
    await click('Let’s play');
    expect(JSON.parse(api.posts()[0][1]!.body as string).options).toEqual({grammar_focus:focus,rounds:5,motion_level:'B1'});
  });
  it('keeps the chosen motion level when changing topics and omits it from other practice',async()=>{
    const api=service();render(<JourneyGame gameId="scene-builder"/>);
    await click('Verbs of motion');await click('A2 Arriving, leaving and carrying');await click('Location');
    expect(screen.queryByRole('group',{name:'Motion level'})).toBeNull();
    await click('Mixed practice');expect(screen.getByRole('button',{name:'A2 Arriving, leaving and carrying'}).getAttribute('aria-pressed')).toBe('true');
    await click('Agreement');await click('Let’s play');
    expect(JSON.parse(api.posts()[0][1]!.body as string).options).toEqual({grammar_focus:'agreement',rounds:5});
  });
  it.each(['Build the sentence to match the scene.','Complete the Russian sentence to describe the scene.'])('omits the repeated saved-round instruction: %s',async(prompt)=>{
    const api=service();api.model.state.round!.prompt=prompt;
    render(<JourneyGame sessionId="scene-test"/>);
    expect(await screen.findByRole('heading',{name:'Describe the scene',level:1})).toBeTruthy();
    expect(screen.getByText('Round 1 of 5')).toBeTruthy();
    expect(screen.getByText('Barsik is sitting under the table.')).toBeTruthy();
    expect(screen.queryByRole('heading',{level:2})).toBeNull();
    expect(screen.queryByText(prompt)).toBeNull();expect(screen.queryByText('Complete the sentence.')).toBeNull();
    expect(screen.getByRole('button',{name:'Show a hint'})).toBeTruthy();
  });
  it('shows a compact motion level and requires both B1 clauses before checking',async()=>{
    const api=service();const motionRound=api.model.state.round!;
    motionRound.scene_builder={family:'motion',level:'B1',skill:'motion_prefix_route_connections',scenario:'Anna walked past the shop, then went around the roadworks.',scenario_ru:'Анна миновала магазин, а затем обошла ремонт дороги.',scene:'motion-route',motion_visual:{mode:'foot',stage:'detour',setting:'shop',destination:'Магазин'},segments:['Анна ',' мимо магазина, потом ',' ремонт дороги.'],slots:[{id:'first',label:'First part',label_ru:'Первая часть',choices:['прошла','пришла','ушла','вышла','вошла','подошла'].map(text=>({id:`first:${text}`,text}))},{id:'second',label:'Next part',label_ru:'Вторая часть',choices:['обошла','вернулась','перешла','дошла','отошла','зашла'].map(text=>({id:`second:${text}`,text}))}]};
    render(<JourneyGame sessionId="scene-test"/>);
    const check=await screen.findByRole('button',{name:'Check the sentence'});
    const level=screen.getByLabelText('Level B1');expect(level.closest('.journey-game-round-count')).toBeTruthy();
    expect(screen.queryByText('motion_prefix_route_connections')).toBeNull();
    expect(within(screen.getByRole('group',{name:'First part'})).getAllByRole('button')).toHaveLength(6);
    expect(within(screen.getByRole('group',{name:'Next part'})).getAllByRole('button')).toHaveLength(6);
    await click('прошла');expect((check as HTMLButtonElement).disabled).toBe(true);
    await click('обошла');expect((check as HTMLButtonElement).disabled).toBe(false);
  });
  it('keeps the choice banks in place and requires every slot before checking',async()=>{
    const api=service();render(<JourneyGame sessionId="scene-test"/>);
    const check=await screen.findByRole('button',{name:'Check the sentence'});
    expect((check as HTMLButtonElement).disabled).toBe(true);
    await click('стол');expect((check as HTMLButtonElement).disabled).toBe(true);
    await click('под');expect((check as HTMLButtonElement).disabled).toBe(false);
    await click('на');expect(screen.getByRole('button',{name:'под'}).getAttribute('aria-pressed')).toBe('false');
    await click('под');expect(screen.getByRole('button',{name:'под'}).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getAllByRole('button',{name:/^(на|под|за|стол|столе|столом)$/})).toHaveLength(6);
    expect(api.posts()).toHaveLength(0);
    await click('Check the sentence');await screen.findByText('Under is right.');
    expect(JSON.parse(api.posts()[0][1]!.body as string).answer).toEqual(['preposition:under','noun:nominative']);
    expect(screen.getByText('Use столом for a position under the table.')).toBeTruthy();
    expect(screen.getByText('Барсик сидит под столом.')).toBeTruthy();
    expect((screen.getByRole('button',{name:'столом'}).closest('fieldset') as HTMLFieldSetElement).disabled).toBe(true);
    await click('Next round');await screen.findByRole('button',{name:'Check the sentence'});
    expect((screen.getByRole('button',{name:'Check the sentence'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('preserves both selections through optional hints and retries the exact failed answer',async()=>{
    const api=service();render(<JourneyGame sessionId="scene-test"/>);
    await click('под');await click('стол');await click('Show a hint');await screen.findByText('Use под for under. It takes the instrumental case here.');
    expect(screen.getByRole('button',{name:'под'}).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button',{name:'стол'}).getAttribute('aria-pressed')).toBe('true');
    api.model.failAnswer=true;await click('Check the sentence');await screen.findByRole('alert');
    expect((screen.getByRole('button',{name:'на'}).closest('fieldset') as HTMLFieldSetElement).disabled).toBe(true);
    await click('Try again');await screen.findByText('Under is right.');
    const answers=api.posts().filter(([url])=>url.endsWith('/answer'));expect(answers).toHaveLength(2);expect(answers[1][1]?.body).toBe(answers[0][1]?.body);
  });
  it('uses the selected interface language for the situation, labels and hints',async()=>{
    service();render(<GameLanguage.Provider value="ru"><JourneyGame sessionId="scene-test"/></GameLanguage.Provider>);
    await screen.findByText('Барсик прячется внизу, под столом.');
    expect(screen.queryByText('Barsik is sitting under the table.')).toBeNull();
    expect(screen.getByRole('group',{name:'Выберите предлог'})).toBeTruthy();
    await click('Показать подсказку');await screen.findByText('Предлог под здесь требует творительного падежа.');
  });
  it('localizes the motion level controls',async()=>{
    service();render(<GameLanguage.Provider value="ru"><JourneyGame gameId="scene-builder"/></GameLanguage.Provider>);
    await click('Глаголы движения');expect(screen.getByRole('group',{name:'Уровень глаголов движения'})).toBeTruthy();
    await click('A2 Приходить, уходить, нести');
    expect(screen.getByText('Приходить или прийти, уходить или уйти. Входить, пересекать улицу, нести вещи и вести людей.')).toBeTruthy();
    expect(screen.queryByText('Arriving, leaving and carrying')).toBeNull();
  });
  it('does not put the completed Russian answer or dictionary links on the unchecked scene',()=>{
    render(<SceneBuilder round={round} selected={[]} disabled={false} onChange={()=>{}}/>);
    expect(screen.queryByText('Барсик сидит под столом.')).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe('Barsik is sitting under the table.');
  });
  it.each<MotionVisual>([
    {mode:'foot',stage:'journey',setting:'park',destination:'Парк'},
    {mode:'transport',stage:'habit',setting:'station',transport:'train',destination:'Вокзал'},
    {mode:'transport',stage:'arrival',setting:'airport',transport:'bus',destination:'Аэропорт'},
    {mode:'transport',stage:'departure',setting:'home',transport:'car',destination:'Дом'},
    {mode:'foot',stage:'enter',setting:'courtyard',destination:'Двор'},
    {mode:'foot',stage:'exit',setting:'shop',destination:'Магазин'},
    {mode:'foot',stage:'cross',setting:'bridge',destination:'Мост'},
    {mode:'transport',stage:'approach',setting:'station',transport:'taxi',destination:'Вокзал'},
    {mode:'carrying',stage:'past',setting:'shop',destination:'Магазин'},
    {mode:'transport',stage:'detour',setting:'street',transport:'car',obstacle:'roadworks',destination:'Улица'},
    {mode:'foot',stage:'detour',setting:'park',obstacle:'puddle',destination:'Парк'},
    {mode:'leading',stage:'journey',setting:'park',destination:'Парк'},
    {mode:'foot',stage:'return',setting:'home',destination:'Дом'},
  ])('renders a contextual route illustration for $mode / $stage / $setting',visual=>{
    const contextualRound={...round,scene_builder:{...round.scene_builder!,scene:'motion-route',motion_visual:visual}};
    const {container}=render(<SceneBuilder round={contextualRound} selected={[]} disabled={false} onChange={()=>{}}/>);
    const illustration=screen.getByRole('img');
    expect(illustration.getAttribute('aria-label')).toBe(round.scene_builder!.scenario);
    expect(within(illustration).getByText(visual.destination)).toBeTruthy();
    expect(illustration.querySelector('svg')).toBeTruthy();
    expect(container.querySelector('img')).toBeNull();
  });
  it('still renders saved motion scenes with their original artwork',()=>{
    const savedRound={...round,scene_builder:{...round.scene_builder!,scene:'walking'}};
    const {container}=render(<SceneBuilder round={savedRound} selected={[]} disabled={false} onChange={()=>{}}/>);
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/static/images/scene-builder/walking-v1.webp');
  });
});

describe('Completed motion scene geometry',()=>{
  function illustration(mode:'foot'|'transport',stage:MotionVisual['stage'],setting:MotionVisual['setting']) {
    const visual:MotionVisual={mode,stage,setting,destination:'Место',...(mode==='transport'?{transport:'car' as const}:{})};
    const {container}=render(<SceneBuilder round={{...round,scene_builder:{...round.scene_builder!,scene:'motion-route',motion_visual:visual}}} selected={[]} onChange={()=>{}} disabled={false}/>);
    const actor=container.querySelector(mode==='foot'?'.scene-motion-person':'.scene-motion-vehicle')!;
    const [x,y,sx,sy]=actor.getAttribute('transform')!.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
    // Conservative bounds include the complete glyph, feet/wheels and shadow.
    const extent=mode==='foot'?{left:-35,right:38,top:-58,bottom:80}:{left:-78,right:88,top:-58,bottom:57};
    const bounds={left:x+Math.min(extent.left*sx,extent.right*sx),right:x+Math.max(extent.left*sx,extent.right*sx),top:y+extent.top*sy,bottom:y+extent.bottom*sy};
    expect(bounds.left).toBeGreaterThanOrEqual(0);expect(bounds.right).toBeLessThanOrEqual(500);
    expect(bounds.top).toBeGreaterThanOrEqual(0);expect(bounds.bottom).toBeLessThanOrEqual(410);
    return {container,bounds};
  }
  it.each(['foot','transport'] as const)('places the entire %s traveler inside the courtyard after entering',mode=>{
    const {container,bounds}=illustration(mode,'enter','courtyard');
    const interior=container.querySelector('.scene-motion-courtyard-interior')!;
    const x=Number(interior.getAttribute('x')),y=Number(interior.getAttribute('y'));
    expect(bounds.left).toBeGreaterThan(x);expect(bounds.right).toBeLessThan(x+Number(interior.getAttribute('width')));
    expect(bounds.top).toBeGreaterThan(y);expect(bounds.bottom).toBeLessThan(y+Number(interior.getAttribute('height')));
  });
  it('places the person fully within the open pharmacy doorway after entering',()=>{
    const {container,bounds}=illustration('foot','enter','shop');
    const door=container.querySelector('.scene-motion-doorway')!;
    expect(bounds.left).toBeGreaterThan(Number(door.getAttribute('x'))+25);
    expect(bounds.right).toBeLessThan(Number(door.getAttribute('x'))+Number(door.getAttribute('width')));
    expect(bounds.top).toBeGreaterThan(Number(door.getAttribute('y')));
    expect(bounds.bottom).toBeLessThan(Number(door.getAttribute('y'))+Number(door.getAttribute('height')));
  });
  it.each(['foot','transport'] as const)('places the entire %s traveler outside after leaving the courtyard',mode=>{
    const {container,bounds}=illustration(mode,'exit','courtyard');
    expect(bounds.right).toBeLessThan(Number(container.querySelector('.scene-motion-courtyard-interior')!.getAttribute('x')));
    expect(bounds.bottom).toBeGreaterThan(285);
  });
  it.each(['foot','transport'] as const)('places the entire %s traveler on the far bank after crossing the bridge',mode=>{
    const {container,bounds}=illustration(mode,'cross','bridge');
    const bridge=container.querySelector('.scene-motion-bridge')!;
    expect(bounds.left).toBeGreaterThan(Number(bridge.getAttribute('x'))+Number(bridge.getAttribute('width'))+6);
  });
  it('places the pedestrian beyond the whole road after crossing',()=>{
    const {bounds}=illustration('foot','cross','street');
    expect(bounds.left).toBeGreaterThan(333);
  });
  it.each(['arrival','approach'] as const)('stops at the destination entrance after %s',stage=>{
    const {bounds}=illustration('transport',stage,'station');
    expect(bounds.left).toBeGreaterThan(280);expect(bounds.right).toBeGreaterThan(400);
    expect(bounds.bottom).toBeGreaterThan(291);
  });
  it.each(['foot','transport'] as const)('clears the entrance when the %s traveler moves away',mode=>{
    const {bounds}=illustration(mode,'departure','courtyard');
    expect(bounds.right).toBeLessThan(297);
  });
});
