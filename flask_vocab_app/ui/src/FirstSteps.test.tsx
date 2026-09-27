import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {FirstSteps} from './FirstSteps';
import type {FirstStepsAttempt,FirstStepsChapter,FirstStepsLesson,FirstStepsSummary,FirstStepsTeaching} from './first-steps-api';

const root='/api/v1/first-steps';
const summaries:FirstStepsSummary[]=[
  {id:'hello',position:1,title:'Hello, Barsik!',description:'Meet Barsik and your first three words.',status:'completed',href:'#first-delivery'},
  {id:'bag',position:2,title:'In the bag',description:'Help Barsik pack his letter bag.',status:'available',href:'#first-steps/bag'},
  {id:'directions',position:3,title:'Which way?',description:'Read a sign and choose a direction.',status:'locked',href:'#first-steps/directions'},
  {id:'help',position:4,title:'A little help',description:'Ask for help along the way.',status:'locked',href:'#first-steps/help'},
  {id:'set-off',position:5,title:'Ready to go',description:'Find the post office.',status:'locked',href:'#first-steps/set-off'},
];
const cards:FirstStepsTeaching[]=[
  {id:'bag-word',title:'Barsik’s bag',word:'сумка',meaning:'a bag',explanation:'Barsik keeps the letter in his bag.',example:'Это сумка.',translation:'This is a bag.',visual:'bag'},
  {id:'letter-word',title:'Your letter',word:'письмо',meaning:'a letter',explanation:'The letter is for you.',visual:'envelope'},
];
const questions=[
  {id:'bag-q',prompt:'Which word means a bag?',choices:[{id:'bag',text:'сумка'},{id:'letter',text:'письмо'}]},
  {id:'letter-q',prompt:'Which word means a letter?',choices:[{id:'letter',text:'письмо'},{id:'bag',text:'сумка'}]},
];
const attempt=(patch:Partial<FirstStepsAttempt>={}):FirstStepsAttempt=>({id:'bag-1',version:'first-steps-v1',phase:'learn',teaching_index:0,total_teaching:2,question_index:0,total_questions:2,teaching:cards[0],question:null,answers:[],completed_at:null,...patch});
const chapter=():FirstStepsChapter=>({profile_id:'tom',lessons:structuredClone(summaries),next_lesson:structuredClone(summaries[1]),completed_count:1,complete:false,pending_reward:0});
const lesson=(patch:Partial<FirstStepsLesson>={}):FirstStepsLesson=>({profile_id:'tom',lesson:{...summaries[1],total_lessons:5},attempt:null,teaching_cards:[],reward:null,pending_reward:0,next_lesson:{...summaries[2],status:'available'},chapter_complete:false,...patch});
const answer=(index=0)=>({question_id:questions[index].id,answer:questions[index].choices[0].id,answer_text:questions[index].choices[0].text,correct:true,correct_answer:questions[index].choices[0].text,feedback:index===0 ? 'Сумка means a bag.' : 'Письмо means a letter.',hint_used:false,acknowledged:false});
const done=(patch:Partial<FirstStepsLesson>={})=>lesson({attempt:attempt({phase:'completed',teaching_index:2,teaching:null,question_index:2,question:null,completed_at:123,answers:[answer(0),answer(1)]}),teaching_cards:cards,resolution:'Barsik has packed his bag. Time to find the post office.',reward:{amount:3,status:'credited',awarded_now:false},...patch});
const response=(value:unknown,ok=true)=>({ok,json:async()=>structuredClone(value)});
function server(initial=lesson(),overview=chapter()) {
  const state={lesson:structuredClone(initial),chapter:structuredClone(overview),failNext:'',locked:false,holdNext:'',release:undefined as undefined|(()=>void)};
  const fetch=vi.fn(async(url:string,request?:RequestInit)=>{
    if(url==='/api/v1/games')return response({profile_id:state.lesson.profile_id,games:[]});
    const action=request?.method==='GET' ? 'load' : url.split('/').at(-1)!;
    if(state.holdNext===action){state.holdNext='';await new Promise<void>(resolve=>{state.release=resolve;});}
    if(state.failNext===action){state.failNext='';return response({error:{code:'unavailable',message:'Please try saving again.'}},false);}
    if(url===root)return response(state.chapter);
    if(state.locked)return response({error:{code:'lesson_locked',message:'Finish Hello, Barsik! before opening this lesson.'}},false);
    if(request?.method==='GET')return response(state.lesson);
    if(url.endsWith('/flashcards'))return response({id:'cards-from-bag'});
    if(url.endsWith('/word-jumble'))return response({url:'/word_jumble/load/known-words'});
    const body=JSON.parse(request?.body as string);
    if(action==='start')state.lesson.attempt=state.lesson.attempt ?? attempt();
    const current=state.lesson.attempt!;
    if(action==='learn'){
      if(body.teaching_id!==current.teaching!.id)throw new Error('Wrong teaching card');
      current.teaching_index++;current.teaching=cards[current.teaching_index] ?? null;
      if(!current.teaching){current.phase='question';current.question=questions[0];}
    }
    if(action==='hint')current.question={...current.question!,hint:'The word for a bag starts with су.'};
    if(action==='answer'){
      const choice=current.question!.choices.find(item=>item.id===body.answer)!;
      current.answers.push({...answer(current.question_index),answer:choice.id,answer_text:choice.text,correct:choice.id===current.question!.choices[0].id,hint_used:!!current.question!.hint});current.phase='feedback';
    }
    if(action==='continue'){
      current.answers.at(-1)!.acknowledged=true;current.question_index++;current.question=questions[current.question_index] ?? null;
      if(!current.question)current.phase='ready';else current.phase='question';
    }
    if(action==='complete'){
      current.phase='completed';current.completed_at=123;state.lesson.teaching_cards=cards;state.lesson.resolution='Barsik has packed his bag. Time to find the post office.';
      state.lesson.reward={amount:3,status:state.lesson.profile_id ? 'credited' : 'pending',awarded_now:!!state.lesson.profile_id};
      state.lesson.pending_reward=state.lesson.profile_id ? 0 : 6;
    }
    return response(state.lesson);
  });
  vi.stubGlobal('fetch',fetch);
  return {state,fetch,posts:()=>fetch.mock.calls.filter(([,request])=>request?.method==='POST')};
}
async function click(name:string){fireEvent.click(await screen.findByRole('button',{name}));}
beforeEach(()=>vi.stubGlobal('scrollTo',vi.fn()));
afterEach(()=>vi.unstubAllGlobals());

describe('First steps chapter',()=>{
  it('shows the five actual lessons and links the real next step without pretending locked lessons are available',async()=>{
    const api=server();render(<FirstSteps/>);
    expect(await screen.findByText('1 of 5 lessons complete')).toBeTruthy();
    expect(screen.getByRole('list',{name:'First steps lessons'}).children).toHaveLength(5);
    expect(screen.getByRole('link',{name:'Start lesson 2'}).getAttribute('href')).toBe('#first-steps/bag');
    expect(screen.getByRole('link',{name:/Hello, Barsik!.*Completed/}).getAttribute('href')).toBe('#first-delivery');
    expect(screen.queryByRole('link',{name:/Which way/})).toBeNull();
    expect(screen.getByRole('link',{name:'Choose an activity'}).getAttribute('href')).toBe('#activities');
    expect(api.posts()).toHaveLength(0);
    expect(api.fetch.mock.calls.some(([url])=>url==='/api/v1/games')).toBe(false);
  });

  it('uses Continue for an active lesson and offers main activities when the chapter is finished',async()=>{
    const overview=chapter();overview.lessons[1].status='active';overview.next_lesson=overview.lessons[1];server(lesson(),overview);
    const view=render(<FirstSteps/>);
    expect(await screen.findByRole('link',{name:'Continue lesson 2'})).toBeTruthy();view.unmount();
    const finished=chapter();finished.lessons.forEach(item=>item.status='completed');finished.completed_count=5;finished.complete=true;finished.next_lesson=null;
    server(done(),finished);render(<FirstSteps/>);
    await screen.findByText('5 of 5 lessons complete');
    expect(document.querySelector('.action-row .cta')?.getAttribute('href')).toBe('#activities');
    expect(screen.getByText('5 of 5 lessons complete')).toBeTruthy();
  });

  it('recovers a failed overview read without creating an activity',async()=>{
    const api=server();api.state.failNext='load';render(<FirstSteps/>);
    await screen.findByRole('alert');await click('Try again');
    expect(await screen.findByText('1 of 5 lessons complete')).toBeTruthy();expect(api.posts()).toHaveLength(0);
  });
});

describe('First steps lesson player',()=>{
  it('sends a completed introduction to main practice without requesting or announcing game unlocks',async()=>{
    const api=server(done());render(<FirstSteps lessonId="bag"/>);
    const activity=await screen.findByRole('link',{name:'Choose an activity'});
    expect(activity.getAttribute('href')).toBe('#activities');
    expect(activity.classList.contains('cta')).toBe(true);
    expect(screen.getByRole('link',{name:'Next: Which way?'}).classList.contains('cta')).toBe(false);
    expect(screen.queryByText('New game unlocked')).toBeNull();
    expect(screen.queryByRole('heading',{name:'Pack the bag'})).toBeNull();
    expect(api.fetch.mock.calls.some(([url])=>url==='/api/v1/games')).toBe(false);
    expect(screen.getByRole('button',{name:'Make flashcards'})).toBeTruthy();
  });

  it('teaches every word before asking Russian-choice questions, with context and a light illustration',async()=>{
    const api=server();render(<FirstSteps lessonId="bag"/>);
    expect(await screen.findByText('a bag')).toBeTruthy();expect(screen.getByText('Это сумка.').getAttribute('lang')).toBe('ru');
    const teachingHeading=screen.getByRole('heading',{level:1,name:cards[0].title});
    expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
    await waitFor(()=>expect(document.activeElement).toBe(teachingHeading));
    expect(screen.getByText('This is a bag.')).toBeTruthy();expect(screen.queryByRole('button',{name:'сумка'})).toBeNull();
    expect(document.querySelector('.first-steps-art svg')).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Let’s begin'})).toBeNull();
    expect(screen.queryByText('A few useful words, then your turn.')).toBeNull();
    await click('Continue');expect(await screen.findByText('a letter')).toBeTruthy();
    expect(screen.queryByRole('button',{name:'письмо'})).toBeNull();await click('Try what you’ve learned');
    const questionHeading=await screen.findByRole('heading',{level:1,name:questions[0].prompt});
    expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
    await waitFor(()=>expect(document.activeElement).toBe(questionHeading));
    expect(screen.queryByText('The letter is for you.')).toBeNull();expect(screen.queryByText('a bag')).toBeNull();
    expect(screen.getByRole('button',{name:'сумка'}).getAttribute('lang')).toBe('ru');
    expect(api.posts().map(([url,request])=>[url,JSON.parse(request?.body as string)])).toEqual([[root+'/bag/start',{}],[root+'/bag/learn',{teaching_id:'bag-word'}],[root+'/bag/learn',{teaching_id:'letter-word'}]]);
  });

  it('shows optional hints only on click and saves wrong answers before moving on',async()=>{
    const api=server(lesson({attempt:attempt({phase:'question',teaching_index:2,teaching:null,question:questions[0]})}));render(<FirstSteps lessonId="bag"/>);
    const heading=await screen.findByRole('heading',{level:1,name:questions[0].prompt});expect(screen.queryByText(/starts with су/)).toBeNull();
    await click('Show a hint');expect(await screen.findByText('The word for a bag starts with су.')).toBeTruthy();
    await click('письмо');expect(await screen.findByText('Here’s the answer.')).toBeTruthy();expect(screen.getByText('Сумка means a bag.')).toBeTruthy();
    expect(screen.getByRole('heading',{level:1,name:questions[0].prompt})).toBe(heading);
    await waitFor(()=>expect(document.activeElement).toBe(heading));
    expect(screen.queryByRole('button',{name:'сумка'})).toBeNull();expect(screen.queryByRole('heading',{name:questions[1].prompt})).toBeNull();
    await click('Continue');expect(await screen.findByRole('heading',{name:questions[1].prompt})).toBeTruthy();
    expect(api.state.lesson.attempt?.answers[0]).toMatchObject({correct:false,hint_used:true,acknowledged:true});
  });

  it('preserves the question during a failed answer and retries the exact submission',async()=>{
    const api=server(lesson({attempt:attempt({phase:'question',teaching:null,question:questions[0]})}));api.state.holdNext='answer';api.state.failNext='answer';
    render(<FirstSteps lessonId="bag"/>);await click('сумка');
    expect(screen.getByRole('button',{name:'письмо'}).hasAttribute('disabled')).toBe(true);expect(screen.getByRole('button',{name:'Show a hint'}).hasAttribute('disabled')).toBe(true);
    await act(async()=>api.state.release!());await screen.findByRole('alert');
    expect(screen.queryByText('Сумка means a bag.')).toBeNull();await click('Try again');await screen.findByText('Сумка means a bag.');
    const posts=api.posts().filter(([url])=>url.endsWith('/answer'));expect(posts).toHaveLength(2);expect(posts[0][1]?.body).toBe(posts[1][1]?.body);
  });

  it('resumes the saved teaching position and then exact feedback after a reload',async()=>{
    server(lesson({attempt:attempt({teaching_index:1,teaching:cards[1]})}));const first=render(<FirstSteps lessonId="bag"/>);
    expect(await screen.findByText('Learn · 2 of 2')).toBeTruthy();expect(screen.queryByText('a bag')).toBeNull();first.unmount();
    const api=server(lesson({attempt:attempt({phase:'feedback',teaching:null,teaching_index:2,question:questions[0],answers:[answer(0)]})}));render(<FirstSteps lessonId="bag"/>);
    expect(await screen.findByText('Сумка means a bag.')).toBeTruthy();expect(screen.queryByRole('button',{name:'сумка'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });

  it('does not celebrate a failed completion and retries completion without acknowledging twice',async()=>{
    const api=server(lesson({attempt:attempt({phase:'feedback',teaching:null,question_index:1,question:questions[1],answers:[{...answer(0),acknowledged:true},answer(1)]})}));api.state.failNext='complete';render(<FirstSteps lessonId="bag"/>);
    await click('Finish lesson');await screen.findByRole('alert');expect(screen.queryByText('+3 Lingocoins')).toBeNull();expect(screen.queryByText('First steps · Lesson complete')).toBeNull();
    await click('Try again');expect(await screen.findByText('+3 Lingocoins')).toBeTruthy();
    expect(screen.getByRole('link',{name:'Next: Which way?'}).getAttribute('href')).toBe('#first-steps/directions');
    expect(api.posts().filter(([url])=>url.endsWith('/continue'))).toHaveLength(1);expect(api.posts().filter(([url])=>url.endsWith('/complete'))).toHaveLength(2);
  });

  it('revisits completed content and saved answers without creating a replay or awarding again',async()=>{
    const api=server(done());render(<FirstSteps lessonId="bag"/>);
    expect(await screen.findByText('3 Lingocoins earned')).toBeTruthy();expect(screen.queryByText('+3 Lingocoins')).toBeNull();
    expect(screen.getByText('Revisit what you learned')).toBeTruthy();expect(screen.getByText('Your saved answers')).toBeTruthy();
    expect(screen.getByText('Barsik keeps the letter in his bag.')).toBeTruthy();expect(screen.queryByRole('button',{name:'Start again'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });

  it('reports zero actual reward honestly without substituting a fixed bonus',async()=>{
    server(done({reward:{amount:0,status:'credited',awarded_now:false}}));render(<FirstSteps lessonId="bag"/>);
    expect(await screen.findByText('Your lesson is complete. No coins were added.')).toBeTruthy();expect(screen.queryByText(/3 Lingocoins/)).toBeNull();
  });

  it('keeps guest progress optional and points to creating a new profile to save it',async()=>{
    const api=server(done({profile_id:null,reward:{amount:3,status:'pending',awarded_now:false},pending_reward:6}));render(<FirstSteps lessonId="bag"/>);
    expect(await screen.findByText('Create a profile to save your lessons and coins.',{exact:false})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Create a profile'}).getAttribute('href')).toBe('/post/profiles');
    expect(screen.getByRole('link',{name:'Next: Which way?'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Make flashcards'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });

  it('links an unavailable lesson back to the real sequence',async()=>{
    const api=server();api.state.locked=true;render(<FirstSteps lessonId="directions"/>);
    expect(await screen.findByText('Finish Hello, Barsik! before opening this lesson.')).toBeTruthy();
    expect(screen.getByRole('link',{name:'See your next lesson'}).getAttribute('href')).toBe('#first-steps');expect(screen.queryByRole('button',{name:'Let’s begin'})).toBeNull();expect(api.posts()).toHaveLength(0);
  });

  it('creates flashcards only when requested and opens the existing generator',async()=>{
    const api=server(done());render(<FirstSteps lessonId="bag"/>);await screen.findByRole('button',{name:'Make flashcards'});expect(api.posts()).toHaveLength(0);
    await click('Make flashcards');await waitFor(()=>expect(window.location.hash).toBe('#generate/cards-from-bag'));
    expect(api.posts().map(([url,request])=>[url,request?.body])).toEqual([[root+'/bag/flashcards','{}']]);
  });

  it('offers chapter practice after the last lesson and retries a failed card request',async()=>{
    const api=server(done({chapter_complete:true,next_lesson:null}));api.state.failNext='flashcards';render(<FirstSteps lessonId="set-off"/>);
    expect(await screen.findByRole('link',{name:'Choose an activity',exact:true})).toBeTruthy();expect(screen.getByRole('button',{name:'Write with these words'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Try a conversation'}).getAttribute('href')).toBe('#speaking/scenario/directions');
    await click('Make chapter flashcards');await screen.findByRole('alert');expect(window.location.hash).not.toContain('generate');
    await click('Try again');await waitFor(()=>expect(window.location.hash).toBe('#generate/cards-from-bag'));
    expect(api.posts().filter(([url])=>url===root+'/chapter/flashcards')).toHaveLength(2);
  });

  it('describes a direction illustration without revealing a Russian answer in its accessible label',async()=>{
    server(lesson({attempt:attempt({phase:'question',teaching:null,question:{...questions[0],visual:'straight'}})}));render(<FirstSteps lessonId="directions"/>);
    expect(await screen.findByRole('img',{name:'An arrow pointing straight ahead'})).toBeTruthy();
    expect(screen.queryByRole('img',{name:'Прямо'})).toBeNull();
  });

  it('retries a failed start directly without another handoff or a duplicate read',async()=>{
    const api=server();api.state.failNext='start';render(<FirstSteps lessonId="bag"/>);
    await screen.findByRole('alert');expect(screen.queryByText('a bag')).toBeNull();
    expect(screen.queryByRole('button',{name:'Let’s begin'})).toBeNull();
    await click('Try again');expect(await screen.findByText('a bag')).toBeTruthy();
    expect(api.fetch.mock.calls.filter(([,request])=>request?.method==='GET')).toHaveLength(1);
    expect(api.posts().map(([url,request])=>[url,request?.body])).toEqual([[root+'/bag/start','{}'],[root+'/bag/start','{}']]);
  });

  it('does not start a lesson if its availability read finishes after leaving the page',async()=>{
    const api=server();api.state.holdNext='load';const view=render(<FirstSteps lessonId="bag"/>);
    await waitFor(()=>expect(api.state.release).toBeTypeOf('function'));
    view.unmount();await act(async()=>api.state.release!());
    expect(api.posts()).toHaveLength(0);
  });
});
