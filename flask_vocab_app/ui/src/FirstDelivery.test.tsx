import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {FirstDelivery} from './FirstDelivery';
import type {FirstDeliveryState,FirstDeliveryAttempt} from './first-delivery-api';

const next={href:'#activities',label:'Choose an activity',description:'Choose something to practise.'};
const endpoint='/api/v1/onboarding/practice';
const version='first-delivery-v2';
const words=[
  {id:'word-hello',word:'Привет!',meaning:'Hello',title:'Say hello to Barsik.',prompt:'Say hello to Barsik.',explanation:'Use this greeting with a friend.',correct:'hello'},
  {id:'word-letter',word:'письмо',meaning:'a letter',title:'A letter for you.',prompt:'Choose the Russian word for “a letter”.',explanation:'This is what Barsik is carrying.',correct:'letter'},
  {id:'word-thanks',word:'Спасибо!',meaning:'Thank you',title:'Say thank you.',prompt:'Say thank you.',explanation:'Use this when someone helps you.',correct:'thanks'},
];
const choices=[{id:'letter',text:'письмо'},{id:'hello',text:'Привет!'},{id:'thanks',text:'Спасибо!'}];
const question=(index=0,learn=false)=>({...words[index],choices:learn ? [] : choices,...(learn ? {lesson:words[index]} : {})});
const attempt=(patch:Partial<FirstDeliveryAttempt>={}):FirstDeliveryAttempt=>({id:'delivery-1',version,phase:'question',question_index:0,total_questions:3,question:question(),answers:[],completed_at:null,...patch});
const empty=():FirstDeliveryState=>({profile_id:'tom',attempt:null,pending_reward:0,reward:null});
const answer=(index:number,patch={})=>({question_id:words[index].id,answer:words[index].correct,answer_text:words[index].word,correct:true,correct_answer:words[index].word,feedback:`${words[index].word} means ${words[index].meaning.toLowerCase()}.`,hint_used:false,acknowledged:false,...patch});
const ready=():FirstDeliveryState=>({...empty(),attempt:attempt({phase:'ready',question_index:3,question:null,answers:words.map((_,index)=>answer(index,{acknowledged:true}))})});
const completed=(reward:FirstDeliveryState['reward']={amount:3,status:'credited',awarded_now:false}):FirstDeliveryState=>({...ready(),attempt:{...ready().attempt!,phase:'completed',completed_at:100},reward});
const response=(value:unknown,ok=true)=>({ok,json:async()=>structuredClone(value)});
function server(initial=empty()) {
  const state={value:initial,failNext:'',holdNext:'',release:undefined as undefined|(()=>void)};
  const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
    if(url!==endpoint && !url.startsWith(endpoint+'/')) throw new Error(`Unexpected request: ${url}`);
    if(request?.method==='GET') return response(state.value);
    const action=url.split('/').at(-1)!;
    if(state.holdNext===action) {state.holdNext='';await new Promise<void>(resolve=>{state.release=resolve;});}
    if(state.failNext===action) {state.failNext='';return response({error:{code:'offline',message:'Please try saving again.'}},false);}
    const body=JSON.parse(request?.body as string);
    if(action==='start' && (!state.value.attempt || body.restart)) state.value={...state.value,attempt:attempt({phase:'learn',question:question(0,true)})};
    const current=state.value.attempt;if(!current) throw new Error('No activity');
    if(action==='learn') {
      if(current.question_index<2) {current.question_index++;current.question=question(current.question_index,true);}
      else {current.question_index=0;current.phase='question';current.question=question();}
    }
    if(action==='hint') current.question={...current.question!,hint:'Привет is the greeting you learned.'};
    if(action==='answer') {
      const choice=current.question!.choices.find(item=>item.id===body.answer)!;
      current.answers.push(answer(current.question_index,{answer:choice.id,answer_text:choice.text,correct:choice.id===words[current.question_index].correct,hint_used:!!current.question!.hint}));
      current.phase='feedback';
    }
    if(action==='continue') {
      current.answers.at(-1)!.acknowledged=true;current.question_index++;
      current.question=current.question_index<3 ? question(current.question_index) : null;
      current.phase=current.question ? 'question' : 'ready';
    }
    if(action==='complete') {const fresh=current.phase!=='completed';current.phase='completed';current.completed_at=100;state.value.reward={amount:3,status:state.value.profile_id ? 'credited' : 'pending',awarded_now:fresh && !!state.value.profile_id};state.value.pending_reward=state.value.profile_id ? 0 : 3;}
    return response(state.value);
  });
  vi.stubGlobal('fetch',fetch);
  return {state,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};
}
async function start() {
  fireEvent.click(screen.getByRole('button',{name:'Continue',exact:true}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Learn your first words'}).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Learn your first words'}));
  await screen.findByText('Hello',{exact:true});
}
async function learnWords() {
  fireEvent.click(screen.getByRole('button',{name:'Next word'}));await screen.findByText('a letter',{exact:true});
  fireEvent.click(screen.getByRole('button',{name:'Next word'}));await screen.findByText('Thank you',{exact:true});
  fireEvent.click(screen.getByRole('button',{name:'Try these words'}));await screen.findByRole('button',{name:'Привет!'});
}
beforeEach(()=>vi.stubGlobal('scrollTo',vi.fn()));
afterEach(()=>vi.unstubAllGlobals());

describe('Your first words',()=>{
  it('introduces coins then progress without a dummy quiz or an early reward',async()=>{
    const api=server();const onIntroduce=vi.fn();render(<FirstDelivery next={next} onIntroduce={onIntroduce} courseJourney />);
    expect(screen.getByRole('link',{name:'First steps'}).getAttribute('href')).toBe('#first-steps');
    expect(screen.queryByText('Lesson 1 of 5')).toBeNull();
    expect(screen.queryByRole('list',{name:'Tutorial progress'})).toBeNull();
    expect(screen.queryByText('Before the journey')).toBeNull();
    expect(onIntroduce.mock.calls).toEqual([['coins']]);
    fireEvent.click(screen.getByRole('button',{name:'Continue',exact:true}));
    expect(onIntroduce.mock.calls).toEqual([['coins'],['progress']]);
    expect(document.activeElement).toBe(screen.getByRole('heading',{name:'Help Barsik reach the next stop.'}));
    expect(screen.queryByText('Which word means “hello”?')).toBeNull();
    await waitFor(()=>expect(api.fetch).toHaveBeenCalledOnce());expect(api.posts()).toHaveLength(0);
  });
  it('teaches all three words before Russian-only choices and continues without changing activities',async()=>{
    const api=server();render(<FirstDelivery next={next} />);await start();
    const heading=screen.getByRole('heading',{name:words[0].title,level:1});
    await waitFor(()=>expect(document.activeElement).toBe(heading));
    expect(screen.getByText('Привет!',{exact:true}).getAttribute('lang')).toBe('ru');
    expect(screen.queryByRole('button',{name:'Привет!'})).toBeNull();
    await learnWords();
    expect(screen.getByRole('heading',{name:words[0].prompt,level:1})).toBe(heading);
    expect(screen.queryByText('Use this greeting with a friend.')).toBeNull();
    expect(document.querySelector('.tutorial-word-card')).toBeNull();
    for(const choice of choices) expect(screen.getByRole('button',{name:choice.text}).getAttribute('lang')).toBe('ru');
    expect(screen.queryByRole('button',{name:'Hello'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Привет!'}));
    await screen.findByText('That’s right.');
    fireEvent.click(screen.getByRole('button',{name:'Next word'}));
    await screen.findByRole('heading',{name:words[1].prompt});
    expect(screen.queryByText(/Continue your activity|Carry on from/)).toBeNull();
    expect(api.posts().map(([url])=>url.split('/').at(-1))).toEqual(['start','learn','learn','learn','answer','continue']);
    expect(screen.queryByText('+3 Lingocoins')).toBeNull();
  });
  it('restores a teaching card on reload and never shows its answer beside the recall choices',async()=>{
    server({...empty(),attempt:attempt({phase:'learn',question_index:1,question:question(1,true)})});render(<FirstDelivery next={next} />);
    await screen.findByText('a letter',{exact:true});
    expect(screen.queryByRole('button',{name:'письмо'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Next word'}));await screen.findByText('Thank you',{exact:true});
    fireEvent.click(screen.getByRole('button',{name:'Try these words'}));await screen.findByRole('button',{name:'Привет!'});
    expect(screen.queryByText('Thank you',{exact:true})).toBeNull();
  });
  it('requests hints on click and keeps saved feedback until Next word',async()=>{
    const api=server({...empty(),attempt:attempt()});render(<FirstDelivery next={next} />);
    await screen.findByRole('button',{name:'Привет!'});
    expect(screen.queryByText(/greeting you learned/)).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Show a hint'}));await screen.findByText('Привет is the greeting you learned.');
    fireEvent.click(screen.getByRole('button',{name:'Спасибо!'}));await screen.findByText('Here’s the word you need.');
    expect(screen.getByText('Привет!',{selector:'.answer-text'}).getAttribute('lang')).toBe('ru');
    expect(screen.queryByRole('button',{name:'Привет!'})).toBeNull();
    expect(api.state.value.attempt?.answers[0].hint_used).toBe(true);
  });
  it('retries the same failed answer without advancing or celebrating',async()=>{
    const api=server({...empty(),attempt:attempt()});api.state.holdNext='answer';api.state.failNext='answer';
    render(<FirstDelivery next={next} />);fireEvent.click(await screen.findByRole('button',{name:'Привет!'}));
    expect(screen.getByRole('button',{name:'письмо'}).hasAttribute('disabled')).toBe(true);
    await act(async()=>api.state.release!());await screen.findByRole('alert');
    expect(screen.queryByText('That’s right.')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));await screen.findByText('That’s right.');
    const saves=api.posts().filter(([url])=>url.endsWith('/answer'));expect(saves).toHaveLength(2);expect(saves[0][1]?.body).toBe(saves[1][1]?.body);
  });
  it('resumes frozen feedback without letting the first answer be changed',async()=>{
    const api=server({...empty(),attempt:attempt({phase:'feedback',question_index:1,question:question(1),answers:[answer(0,{acknowledged:true}),answer(1)]})});render(<FirstDelivery next={next} />);
    await screen.findByText('письмо means a letter.');expect(screen.queryByRole('button',{name:'письмо'})).toBeNull();
    expect(api.posts()).toHaveLength(0);fireEvent.click(screen.getByRole('button',{name:'Next word'}));await screen.findByRole('heading',{name:words[2].prompt});
  });
  it('explicitly replaces the old English-answer activity when the learner starts the new lesson',async()=>{
    const api=server({...empty(),attempt:attempt({version:'first-delivery-v1',question:{id:'old',prompt:'What are they doing?',choices:[{id:'old',text:'Saying hello'}]}})});
    render(<FirstDelivery next={next} />);await waitFor(()=>expect(api.fetch).toHaveBeenCalledOnce());
    expect(screen.queryByText('Saying hello')).toBeNull();expect(api.posts()).toHaveLength(0);
    await start();expect(JSON.parse(api.posts()[0][1]?.body as string)).toEqual({restart:true});
    expect(screen.getByRole('heading',{name:words[0].title,level:1})).toBeTruthy();
  });
  it('shows the completion reward only after saving and does not award again when revisiting',async()=>{
    const api=server({...empty(),attempt:attempt({phase:'feedback',question_index:2,question:question(2),answers:[answer(0,{acknowledged:true}),answer(1,{acknowledged:true}),answer(2)]})});api.state.failNext='complete';
    render(<FirstDelivery next={next} />);fireEvent.click(await screen.findByRole('button',{name:'Finish activity'}));await screen.findByRole('alert');
    expect(screen.queryByText('+3 Lingocoins')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));await screen.findByText('+3 Lingocoins');
    const count=api.posts().length;fireEvent.click(screen.getByRole('button',{name:'Revisit the introduction'}));fireEvent.click(screen.getByRole('button',{name:'Continue',exact:true}));fireEvent.click(screen.getByRole('button',{name:'Learn your first words'}));
    expect(screen.queryByText('+3 Lingocoins')).toBeNull();expect(api.posts()).toHaveLength(count);
  });
  it('resumes the actual credited amount without another completion request',async()=>{
    const api=server(completed({amount:2,status:'credited',awarded_now:false}));render(<FirstDelivery next={next} />);
    await screen.findByText('2 Lingocoins earned');expect(api.posts()).toHaveLength(0);
  });
  it('keeps pending guest coins distinct from saved profile coins',async()=>{
    server({...completed({amount:3,status:'pending',awarded_now:false}),profile_id:null,pending_reward:3});render(<FirstDelivery next={next} />);
    await screen.findByText('Create a profile to save your coins and first activity.');
    expect(screen.queryByText('Your first activity bonus is saved.')).toBeNull();
  });
  it('avoids a duplicate household action and preserves its destination',async()=>{
    server({...completed({amount:3,status:'pending',awarded_now:false}),profile_id:null,pending_reward:3});render(<FirstDelivery next={{...next,href:'/post/household',label:'Choose a learner'}} profileHref="/post/household" />);
    await screen.findByRole('heading',{name:'Your first lesson is complete.'});expect(screen.getAllByRole('link',{name:'Choose a learner'})).toHaveLength(1);
  });
  it('can skip to activities without starting the lesson',async()=>{
    const api=server();const onIntroduce=vi.fn();render(<FirstDelivery next={next} onIntroduce={onIntroduce} />);
    expect(screen.getByRole('link',{name:'Go straight to activities'}).getAttribute('href')).toBe('#activities');
    await waitFor(()=>expect(api.fetch).toHaveBeenCalledOnce());expect(api.posts()).toHaveLength(0);expect(onIntroduce.mock.calls).toEqual([['coins']]);
  });
});
