import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {CourseJourney,type CourseData,type CourseAttempt} from './CourseJourney';
import type {ProgressionData} from './Progression';
const course=(patch:Partial<CourseData>={}):CourseData=>({version:1,release_id:'a1-v1',chapter_count:4,completed_milestones:0,profile_id:'learner',band:'A1',unlocked_levels:['A1'],current_chapter_id:'first',progress:.2,completed:false,chapters:Array.from({length:4},(_,index)=>({id:index===0 ? 'first' : `chapter-${index+1}`,number:index+1,title:['A small message','The market','A new address','Your original letter'][index],title_ru:'Короткое сообщение',intro:index===0 ? 'Meet Barsik’s helpers. Your original letter stays sealed.' : 'The next part of your journey.',intro_ru:'Познакомьтесь с помощниками Барсика.',status:index===0 ? 'practice' : 'locked',progress:index===0 ? .2 : 0,activity_count:0,required_activity_count:2,last_attempt_id:null,objectives:[{en:'Understand a short greeting.',ru:'Понять короткое приветствие.'}],preparation:[{topic_id:'greetings',title:'Say hello',title_ru:'Приветствия',explanation:'Use this phrase to introduce yourself.',explanation_ru:'Так можно представиться.',examples:[{ru:'Меня зовут Анна.',en:'My name is Anna.'}]}],topics:[{id:'greetings',title:'Greetings',title_ru:'Приветствия',completed:false,successful_tasks:1,required_tasks:2,links:[{activity:'reading',label:'Read a greeting',label_ru:'Читать приветствие',href:'/reading?topic=greetings&difficulty=A1'}]}]})),...patch});
const attempt=(patch:Partial<CourseAttempt>={}):CourseAttempt=>({release_id:'a1-v1',band:'A1',chapter_count:4,id:'attempt-1',chapter_id:'first',chapter_number:1,title:'A small message',title_ru:'Короткое сообщение',letter:'Привет, Барсик! Меня зовут Анна.',letter_title:'A note for Barsik',letter_title_ru:'Записка для Барсика',glossary:[{ru:'привет',en:'hello'}],listening:{audio_url:'/static/audio/course/first.mp3'},questions:[{id:'read',kind:'reading',prompt:'Who wrote this message?',prompt_ru:'Кто написал сообщение?',choices:[{id:'anna',text:'Анна'},{id:'misha',text:'Миша'}]},{id:'listen',kind:'listening',prompt:'When is the meeting?',prompt_ru:'Когда встреча?',choices:[{id:'three',text:'В три часа'},{id:'four',text:'В четыре часа'}]},{id:'reply',kind:'response',prompt:'Choose your reply.',prompt_ru:'Выберите ответ.',choices:[{id:'yes',text:'Хорошо, спасибо!'},{id:'no',text:'До свидания!'}]}],status:'active',support_used:false,listened:false,course:course(),...patch});
const progression=(profile='learner')=>({data:{profile_id:profile,course:course({profile_id:profile})} as ProgressionData,error:'',loading:false,refresh:vi.fn()});
const result=(passed=true):CourseAttempt=>attempt({status:passed ? 'passed' : 'retry',listened:true,result:{score:passed ? 3 : 2,total:3,passed,feedback:[{question_id:'read',correct:true,answer:'anna',explanation:'Anna signs the message.',explanation_ru:'Анна подписала сообщение.'},{question_id:'listen',correct:passed,answer:'four',explanation:'The recording changes the meeting to four.',explanation_ru:'В записи встреча перенесена на четыре.'},{question_id:'reply',correct:true,answer:'yes',explanation:'Thank the helper.',explanation_ru:'Поблагодарите помощника.'}]}});
function respond(value:unknown,ok=true) {return {ok,json:async()=>value};}
function mockServer(handler:(url:string,body:Record<string,unknown>|undefined)=>unknown=()=>course()) {
  const fetch=vi.fn(async(input:RequestInfo|URL,options?:RequestInit)=>{
    const value=await handler(String(input),options?.body ? JSON.parse(String(options.body)) : undefined);
    return respond(value);
  });vi.stubGlobal('fetch',fetch);return fetch;
}
async function selectAnswers() {
  fireEvent.click(await screen.findByRole('radio',{name:'Анна'}));fireEvent.click(screen.getByRole('radio',{name:'В четыре часа'}));fireEvent.click(screen.getByRole('radio',{name:'Хорошо, спасибо!'}));
}
beforeEach(()=>{sessionStorage.clear();window.location.hash='';});afterEach(()=>vi.unstubAllGlobals());
describe('Guided chapter journey',()=>{
  it.each([['practice','In practice','Continue milestone →'],['ready','Checkpoint ready','Open checkpoint →']] as const)('shows one %s milestone card and keeps future chapters hidden',async(status,state,action)=>{
    const current=course();current.chapters[0].status=status;
    mockServer(()=>current);render(<CourseJourney progression={progression()}/>);
    await screen.findByRole('heading',{name:'Your journey'});
    expect(screen.queryByText('Your A1 journey')).toBeNull();
    expect(screen.getAllByText(`Milestone 1 of 4 · ${state}`)).toHaveLength(1);
    expect(screen.getAllByRole('heading',{name:'A small message'})).toHaveLength(1);
    expect(screen.queryByRole('link',{name:'A small message'})).toBeNull();
    const continueLink=screen.getByRole('link',{name:action});
    const activeCard=continueLink.closest('li')!;
    expect(activeCard).toBeTruthy();
    expect(activeCard.querySelectorAll('a')).toHaveLength(1);
    expect(continueLink.getAttribute('href')).toBe('#journey/release/a1-v1/chapter/first');
    for (const number of [2,3,4]) {
      const future=screen.getByRole('listitem',{name:`Milestone ${number}, locked`});
      expect(future.textContent).toBe(String(number));
      expect(future.querySelector('a,button,summary,input')).toBeNull();
    }
    expect(screen.queryByText('The market')).toBeNull();
    expect(screen.queryByText('A new address')).toBeNull();
    expect(screen.queryByText('Your original letter')).toBeNull();
    expect(screen.queryByText('The next part of your journey.')).toBeNull();
    expect(screen.getByRole('link',{name:'Curriculum'}).getAttribute('href')).toBe('/curriculum');
    expect(screen.getByRole('link',{name:'Browse all practice activities →'})).toBeTruthy();
    expect(screen.queryByText('Привет, Барсик! Меня зовут Анна.')).toBeNull();
  });
  it('teaches the topic and offers explicit early test-out with a stable request ID on retry',async()=>{
    let fail=true;const fetch=mockServer((url)=>{if (url.endsWith('/checkpoint')) {if(fail) throw new Error('Connection lost');return attempt();}if(url==='/api/v1/course/checkpoints/attempt-1') return attempt();return course();});
    render(<CourseJourney chapterId="first" progression={progression()}/>);
    expect(await screen.findByText('Меня зовут Анна.')).toBeTruthy();
    expect(screen.queryByText('Use this phrase to introduce yourself.')).toBeNull();
    expect(screen.getByText('Меня зовут Анна.')).toBeTruthy();expect(screen.getByRole('link',{name:'Read a greeting →'}).getAttribute('href')).toContain('topic=greetings');
    fireEvent.click(screen.getByRole('button',{name:'Test out of this milestone →'}));await screen.findByRole('alert');
    fail=false;fireEvent.click(screen.getByRole('button',{name:'Test out of this milestone →'}));
    await waitFor(()=>expect(window.location.hash).toBe('#journey/checkpoint/attempt-1'));
    const writes=fetch.mock.calls.filter(([,options])=>options?.method==='POST');expect(writes).toHaveLength(2);
    const first=JSON.parse(String(writes[0][1]?.body));expect(first.challenge).toBe(true);expect(first.release_id).toBe('a1-v1');expect(JSON.parse(String(writes[1][1]?.body))).toEqual(first);
    expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/course/checkpoints/attempt-1')).toHaveLength(1);
  });
  it('reveals the next milestone after a pass while keeping later destinations hidden',async()=>{
    const current=course({current_chapter_id:'chapter-2',completed_milestones:1});
    current.chapters[0].status='passed';current.chapters[1].status='practice';
    mockServer(()=>current);render(<CourseJourney progression={progression()}/>);
    await screen.findByRole('heading',{name:'Your journey'});
    expect(screen.getAllByRole('heading',{name:'The market'})).toHaveLength(1);
    const continueLink=screen.getByRole('link',{name:'Continue milestone →'});
    expect(continueLink.getAttribute('href')).toBe('#journey/release/a1-v1/chapter/chapter-2');
    expect(continueLink.closest('li')?.querySelectorAll('a')).toHaveLength(1);
    const passedLink=screen.getByRole('link',{name:'A small message'});
    expect(passedLink.getAttribute('href')).toBe('#journey/release/a1-v1/chapter/first');
    expect(passedLink.closest('li')?.querySelectorAll('a')).toHaveLength(1);
    expect(screen.getByText('Milestone 1 of 4 · Passed')).toBeTruthy();
    for(const number of [3,4]) expect(screen.getByRole('listitem',{name:`Milestone ${number}, locked`}).textContent).toBe(String(number));
    expect(screen.queryByText('A new address')).toBeNull();
  });
  it('reads the current enrolment after replaying a start receipt from an equally stale page',async()=>{
    const receipt=attempt();
    const canonical=attempt({course:course({release_id:'a1-journey-v2'})});
    let saved=false;
    const fetch=mockServer(url=>{
      if(url.endsWith('/checkpoint')) {if(!saved){saved=true;throw new Error('Connection lost after saving');}return receipt;}
      if(url==='/api/v1/course/checkpoints/attempt-1') return canonical;
      return course();
    });
    render(<CourseJourney chapterId="first" progression={progression()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Test out of this milestone →'}));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button',{name:'Test out of this milestone →'}));
    await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/course/checkpoints/attempt-1')).toHaveLength(1));
    await waitFor(()=>expect(window.location.hash).toBe('#journey/checkpoint/attempt-1'));
    const writes=fetch.mock.calls.filter(([,options])=>options?.method==='POST');
    expect(writes).toHaveLength(2);expect(writes[0][1]?.body).toBe(writes[1][1]?.body);
    expect(JSON.parse(String(writes[1][1]?.body)).release_id).toBe('a1-v1');
  });
  it('offers a normal checkpoint once ready and stops checkpoint entry for a locked chapter',async()=>{
    const ready=course();ready.chapters[0].status='ready';mockServer(()=>ready);
    const {rerender}=render(<CourseJourney chapterId="first" progression={progression()}/>);
    expect(await screen.findByRole('button',{name:'Start checkpoint →'})).toBeTruthy();expect(screen.queryByRole('button',{name:/Test out/})).toBeNull();
    rerender(<CourseJourney chapterId="chapter-2" progression={progression()}/>);
    await screen.findByText('Pass the previous milestone to continue. You can practise any time.');expect(screen.queryByRole('button',{name:'Start checkpoint →'})).toBeNull();
    expect(screen.queryByRole('heading',{name:'The market'})).toBeNull();
    expect(screen.queryByText('The next part of your journey.')).toBeNull();
    expect(screen.queryByText('Use this phrase to introduce yourself.')).toBeNull();
    expect(screen.queryByRole('link',{name:'Read a greeting →'})).toBeNull();
  });

  it('explains when completed topic work still needs a second activity',async()=>{
    const current=course();current.chapters[0].activity_count=1;current.chapters[0].topics[0].completed=true;
    mockServer(()=>current);render(<CourseJourney chapterId="first" progression={progression()}/>);
    expect(await screen.findByText(/Complete two successful tasks for each topic, using at least two activities/)).toBeTruthy();
    expect(screen.getByText(/1\/2 activities used/)).toBeTruthy();
    expect(screen.getByText(/Try another activity, such as Writing or Speaking/)).toBeTruthy();
  });
  it('keeps focused practice optional and separate from activity preparation',async()=>{
    const current=course({release_id:'a1-journey-v2'});
    current.chapters[0].target_coverage={required_count:1,prepared_count:0,ready:false,targets:[{id:'name',title:'Introduce yourself',title_ru:'Представиться',topic_id:'greetings',required:true,introduced:false,practised:false,demonstrated:false,needs_practice:true}]};
    mockServer(()=>current);render(<CourseJourney chapterId="first" progression={progression()}/>);
    expect(await screen.findByRole('link',{name:'Practise these skills →'})).toBeTruthy();
    expect(screen.queryByText('Understand a short greeting.')).toBeNull();
    const examples=screen.getByText('Notes and examples').closest('details');
    expect(examples?.open).toBe(false);
    const readiness=screen.getByText('Focused practice · 0/1').closest('details');
    expect(readiness?.open).toBe(false);
    expect(readiness?.textContent).toContain('Prepare through activities or these focused exercises.');
    expect(screen.getByRole('heading',{name:'More practice by topic'})).toBeTruthy();
  });
  it.each([['en','Greetings','Formal','Informal'],['ru','Приветствия','Официально','Неформально']] as const)('groups reference examples by function and register in %s',async(language,title,formal,informal)=>{
    const current=course({release_id:'a1-journey-v2'});
    current.chapters[0].preparation![0].groups=[{id:'greetings',title:'Greetings',title_ru:'Приветствия',items:[
      {label:'Formal',label_ru:'Официально',ru:'Здравствуйте!',en:'Hello!'},
      {label:'Informal',label_ru:'Неформально',ru:'Привет!',en:'Hi!'},
    ]}];
    mockServer(()=>current);render(<CourseJourney chapterId="first" language={language} progression={progression()}/>);
    await screen.findByRole('heading',{name:language==='ru' ? 'Короткое сообщение' : 'A small message'});
    const summary=screen.getByText(language==='ru' ? 'Пояснения и примеры' : 'Notes and examples');
    const reference=summary.closest('details')!;
    expect(reference.open).toBe(false);
    fireEvent.click(summary);
    const category=reference.querySelector('h4')!;
    expect(category.textContent).toBe(title);
    const rows=reference.querySelectorAll('dl>div');
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector('dt')?.textContent).toBe(formal);
    expect(rows[0].querySelector('[lang="ru"]')?.textContent).toBe('Здравствуйте!');
    expect(rows[1].querySelector('dt')?.textContent).toBe(informal);
    expect(rows[1].querySelector('[lang="ru"]')?.textContent).toBe('Привет!');
    expect(reference.textContent).not.toContain('Use this phrase to introduce yourself.');
    expect(reference.textContent).not.toContain('Меня зовут Анна.');
  });
  it('shows honest A1 completion and available A2 practice',async()=>{
    mockServer(()=>course({completed:true,completed_milestones:4,unlocked_levels:['A1','A2']}));render(<CourseJourney progression={progression()}/>);
    await screen.findByRole('heading',{name:'A1 course complete'});expect(screen.getByText('A1 · 4 of 4 milestones complete')).toBeTruthy();expect(screen.queryByText(/A2 journey/)).toBeNull();expect(screen.getByRole('link',{name:'Explore A2 practice →'}).getAttribute('href')).toBe('/curriculum#level-A2');
  });
});
describe('Chapter checkpoints',()=>{
  it('allows explicit transcript support to finish practice when audio is inaccessible',async()=>{
    let supported=false;let submitted=false;
    const assisted=()=>attempt({support_used:true,listened:false,listening:{audio_url:'/static/audio/course/first.mp3',transcript:'Встреча в четыре.'}});
    const fetch=mockServer(url=>{if(url.endsWith('/support')){supported=true;return assisted();}if(url.endsWith('/answer')){submitted=true;return {...result(false),support_used:true,listened:false};}return submitted ? {...result(false),support_used:true,listened:false} : supported ? assisted() : attempt();});
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();expect(screen.getByRole('button',{name:'Check my answers'}).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Read transcript · practice only'}));
    await screen.findByText('Transcript support is on. You can finish this as practice.');
    expect(screen.getByRole('button',{name:'Check my answers'}).hasAttribute('disabled')).toBe(false);
    fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await screen.findByRole('heading',{name:'A little more practice'});
    expect(fetch.mock.calls.some(([url])=>String(url).endsWith('/listened'))).toBe(false);
  });
  it('refreshes an answer receipt when both the page and receipt still show the previous enrolment',async()=>{
    const receipt=result();
    const canonical={...result(),course:course({release_id:'a1-journey-v2'})};
    let checked=false;
    const fetch=mockServer(url=>{
      if(url.endsWith('/answer')) {checked=true;return receipt;}
      return checked ? canonical : attempt({listened:true});
    });
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();
    expect(screen.queryByText(/This saved assessment belongs to an earlier course/)).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await screen.findByRole('heading',{name:'Milestone passed'});
    expect(screen.getByText(/This saved assessment belongs to an earlier course/)).toBeTruthy();
    expect(screen.queryByRole('link',{name:'Practise this milestone'})).toBeNull();
    expect(screen.getByRole('link',{name:'← Your journey'}).getAttribute('href')).toBe('#journey');
    expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/course/checkpoints/attempt-1')).toHaveLength(2);
  });
  it('refreshes older completion state even when the receipt and current course share a release',async()=>{
    const completed=course({completed:true,completed_milestones:4,current_chapter_id:null,unlocked_levels:['A1','A2']});
    completed.chapters=completed.chapters.map(chapter=>({...chapter,status:'passed',progress:1}));
    let checked=false;
    const fetch=mockServer(url=>{
      if(url.endsWith('/answer')) {checked=true;return result();}
      return checked ? {...result(),course:completed} : attempt({listened:true});
    });
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await screen.findByRole('heading',{name:'Milestone passed'});
    expect(screen.getByRole('link',{name:'Explore A2 practice →'}).getAttribute('href')).toBe('/curriculum#level-A2');
    expect(screen.queryByRole('link',{name:'Continue the journey →'})).toBeNull();
    expect(screen.queryByText(/This saved assessment belongs to an earlier course/)).toBeNull();
    expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/course/checkpoints/attempt-1')).toHaveLength(2);
  });
  it('rejects another learner returned by the canonical read after a valid answer receipt',async()=>{
    let checked=false;
    mockServer(url=>{
      if(url.endsWith('/answer')) {checked=true;return result();}
      return checked ? {...result(),course:course({profile_id:'another'})} : attempt({listened:true});
    });
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    expect((await screen.findByRole('alert')).textContent).toBe('The learner changed. Reload your journey.');
    expect(screen.queryByText('Привет, Барсик! Меня зовут Анна.')).toBeNull();
    expect(screen.queryByRole('heading',{name:'Milestone passed'})).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });
  it.each(['legacy','versioned'])('rehydrates a %s answer receipt instead of restoring an earlier journey',async receiptType=>{
    const currentCourse=course({release_id:'a1-journey-v2'});
    const historical={...result(),course:currentCourse};
    const receipt={...result()};
    if(receiptType==='legacy'){delete receipt.release_id;delete receipt.course.release_id;}
    let checked=false;
    const fetch=mockServer(url=>{
      if (url.endsWith('/answer')) {checked=true;return receipt;}
      return checked ? historical : attempt({listened:true,course:currentCourse});
    });
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await screen.findByRole('heading',{name:'Milestone passed'});
    expect(screen.getByText(/This saved assessment belongs to an earlier course/)).toBeTruthy();
    expect(screen.queryByRole('link',{name:'Practise this milestone'})).toBeNull();
    expect(fetch.mock.calls.filter(([url])=>url==='/api/v1/course/checkpoints/attempt-1')).toHaveLength(2);
  });
  it('keeps a saved assessment tied to its own milestone count after the learner changes edition',async()=>{
    const saved={...result(false),chapter_number:4,course:course({release_id:'a1-journey-v2',chapter_count:6})};
    mockServer(()=>saved);render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    expect(await screen.findByText('A1 · Milestone 4 of 4 · Checkpoint')).toBeTruthy();
    expect(screen.getByText(/This saved assessment belongs to an earlier course/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Try a different checkpoint →'})).toBeNull();
    expect(screen.queryByRole('link',{name:'Practise this milestone'})).toBeNull();
    expect(screen.getByRole('link',{name:'← Your journey'}).getAttribute('href')).toBe('#journey');
  });

  it('shows the passage before questions, accessible choices and bundled audio without listening credit on load',async()=>{
    let current=attempt();const fetch=mockServer((url)=>{if(url.endsWith('/listened')) current={...current,listened:true};return current;});
    const {container}=render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    const text=await screen.findByText('Привет, Барсик! Меня зовут Анна.');const question=screen.getByRole('group',{name:'1. Who wrote this message?'});
    expect(text.compareDocumentPosition(question)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('Useful words')).toBeTruthy();expect(fetch.mock.calls.every(([,options])=>options?.method==='GET')).toBe(true);
    const audio=screen.getByLabelText('Checkpoint recording');expect(audio.getAttribute('preload')).toBe('none');expect(audio.hasAttribute('autoplay')).toBe(false);
    expect(container.querySelector('.course-correction')).toBeNull();expect(screen.queryByText('The recording changes the meeting to four.')).toBeNull();
    await selectAnswers();expect((screen.getByRole('button',{name:'Check my answers'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent(audio,new Event('ended'));await screen.findByText('✓ Recording heard. You can replay it.');
    expect((screen.getByRole('button',{name:'Check my answers'}) as HTMLButtonElement).disabled).toBe(false);
    expect(fetch.mock.calls.filter(([url])=>String(url).endsWith('/listened'))).toHaveLength(1);
  });

  it('saves listening completion when the audio ends while a hint is loading',async()=>{
    let release:((value:CourseAttempt)=>void)|undefined;
    const fetch=mockServer((url)=>url.endsWith('/support') ? new Promise<CourseAttempt>(resolve=>{release=resolve;}) : attempt({listened:url.endsWith('/listened'),support_used:url.endsWith('/listened')}));
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    fireEvent.click((await screen.findAllByRole('button',{name:'Get a hint · practice only'}))[0]);
    fireEvent(screen.getByLabelText('Checkpoint recording'),new Event('ended'));
    release!(attempt({support_used:true}));
    await screen.findByText('✓ Recording heard. You can replay it.');
    expect(fetch.mock.calls.filter(([url])=>String(url).endsWith('/listened'))).toHaveLength(1);
  });
  it('offers audio recovery without granting listening credit on failure or retry',async()=>{
    const fetch=mockServer(()=>attempt());
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();
    const audio=screen.getByLabelText('Checkpoint recording') as HTMLAudioElement;
    const load=vi.spyOn(audio,'load').mockImplementation(()=>{});
    const play=vi.spyOn(audio,'play').mockResolvedValue();
    fireEvent(audio,new Event('error'));
    expect(await screen.findByText('The recording couldn’t play. Try again, or read the transcript for a practice attempt.')).toBeTruthy();
    expect(screen.queryByText('Listen to the full recording before submitting.')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Retry audio'}));
    expect(load).toHaveBeenCalledTimes(1);expect(play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button',{name:'Check my answers'}).hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button',{name:'Read transcript · practice only'}).hasAttribute('disabled')).toBe(false);
    expect(fetch.mock.calls.some(([url])=>String(url).endsWith('/listened'))).toBe(false);
  });
  it('retries saving a completed recording without replaying it',async()=>{
    let fail=true;let current=attempt();
    const fetch=mockServer(url=>{if(url.endsWith('/listened')){if(fail)throw new Error('Connection lost');current={...current,listened:true};}return current;});
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await selectAnswers();
    const audio=screen.getByLabelText('Checkpoint recording') as HTMLAudioElement;
    const play=vi.spyOn(audio,'play').mockResolvedValue();
    fireEvent(audio,new Event('ended'));
    await screen.findByRole('alert');
    expect(screen.getByText('You’ve heard the recording. Retry saving to continue.')).toBeTruthy();
    expect(screen.getByRole('button',{name:'Check my answers'}).hasAttribute('disabled')).toBe(true);
    fail=false;fireEvent.click(screen.getByRole('button',{name:'Retry saving listening'}));
    await screen.findByText('✓ Recording heard. You can replay it.');
    expect(screen.queryByRole('button',{name:'Retry saving listening'})).toBeNull();
    expect(screen.getByRole('button',{name:'Check my answers'}).hasAttribute('disabled')).toBe(false);
    expect(play).not.toHaveBeenCalled();
    expect(fetch.mock.calls.filter(([url])=>String(url).endsWith('/listened'))).toHaveLength(2);
  });
  it('reveals hints and the transcript only through server support and explains the practice-only consequence',async()=>{
    let current=attempt();const fetch=mockServer((url,body)=>{if(url.endsWith('/support')) {current={...current,support_used:true};if(body?.kind==='hint') current={...current,questions:current.questions.map(q=>q.id===body.question_id ? {...q,hint:'Look at the signature.',hint_ru:'Посмотрите подпись.'} : q)};else current={...current,listening:{...current.listening,transcript:'Встреча в четыре часа.'}};}return current;});
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    fireEvent.click((await screen.findAllByRole('button',{name:'Get a hint · practice only'}))[0]);await screen.findByText('Look at the signature.');
    expect(screen.getByText(/Support used: this is a practice attempt/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Read transcript · practice only'}));await screen.findByText('Встреча в четыре часа.');
    const bodies=fetch.mock.calls.filter(([url])=>String(url).endsWith('/support')).map(([,options])=>JSON.parse(String(options?.body)));
    expect(bodies).toEqual([{kind:'hint',question_id:'read'},{kind:'transcript'}]);
  });
  it('submits all choices once and freezes the saved response with useful corrections and retry',async()=>{
    let current=attempt({listened:true});const fetch=mockServer(url=>{if(url.endsWith('/answer')) current=result(false);return current;});
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);await selectAnswers();
    const submit=screen.getByRole('button',{name:'Check my answers'});fireEvent.click(submit);fireEvent.click(submit);
    await screen.findByRole('heading',{name:'A little more practice'});expect(screen.getByText('The recording changes the meeting to four.')).toBeTruthy();
    expect((screen.getByRole('radio',{name:'Анна'}) as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
    expect(screen.getByRole('button',{name:'Try a different checkpoint →'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Check my answers'})).toBeNull();
    const writes=fetch.mock.calls.filter(([url])=>String(url).endsWith('/answer'));expect(writes).toHaveLength(1);expect(JSON.parse(String(writes[0][1]?.body)).answers).toEqual({read:'anna',listen:'four',reply:'yes'});
    expect(sessionStorage.length).toBe(0);
  });


  it('shows corrections without repeated hints and focuses only a newly saved result',async()=>{
    const saved=result(false);saved.questions=saved.questions.map(question=>({...question,hint:'Read this again before answering.',hint_ru:'Прочитайте ещё раз.'}));
    let completed=false;mockServer(url=>{if (url.endsWith('/answer')) completed=true;return completed ? saved : attempt({listened:true});});
    const previousScroll=HTMLElement.prototype.scrollIntoView;const scroll=vi.fn();HTMLElement.prototype.scrollIntoView=scroll;
    try {
      const first=render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);await selectAnswers();
      fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
      const summary=await screen.findByRole('region',{name:'Checkpoint result'});
      await waitFor(()=>expect(document.activeElement).toBe(summary));expect(scroll).toHaveBeenCalledOnce();
      expect(screen.queryByText('Read this again before answering.')).toBeNull();
      expect(screen.getByText('The recording changes the meeting to four.')).toBeTruthy();first.unmount();
      render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
      const reopened=await screen.findByRole('region',{name:'Checkpoint result'});
      expect(document.activeElement).not.toBe(reopened);expect(scroll).toHaveBeenCalledOnce();
    } finally {HTMLElement.prototype.scrollIntoView=previousScroll;}
  });
  it('restores submitted choices on a saved result and explains an essential detail miss',async()=>{
    const saved=result(false);saved.result!.score=3;saved.result!.essential_passed=false;
    saved.result!.feedback=saved.result!.feedback.map(item=>({...item,selected_answer:item.question_id==='listen' ? 'three' : item.answer}));
    mockServer(()=>saved);render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    expect((await screen.findByRole('radio',{name:'В три часа'}) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole('radio',{name:'В четыре часа'}) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText('One key detail needs another look. Review the corrections and try again.')).toBeTruthy();
    expect(screen.getByText('The recording changes the meeting to four.')).toBeTruthy();
  });
  it('holds submitted answers after an uncertain save and retries the identical submission',async()=>{
    let fail=true;let current=attempt({listened:true});const fetch=mockServer(url=>{if(url.endsWith('/answer')) {current=result();if(fail) throw new Error('Offline');}return current;});
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);await selectAnswers();fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await screen.findByRole('alert');expect((screen.getByRole('radio',{name:'Миша'}) as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
    fail=false;fireEvent.click(screen.getByRole('button',{name:'Retry saving answers'}));await screen.findByRole('heading',{name:'Milestone passed'});
    const writes=fetch.mock.calls.filter(([url])=>String(url).endsWith('/answer'));expect(writes).toHaveLength(2);expect(writes[0][1]?.body).toBe(writes[1][1]?.body);
  });
  it('restores the learner’s draft on return and removes it when another learner takes over',async()=>{
    let profile='learner';mockServer(()=>attempt({course:course({profile_id:profile})}));
    const first=render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);fireEvent.click(await screen.findByRole('radio',{name:'Анна'}));first.unmount();
    const second=render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);expect((await screen.findByRole('radio',{name:'Анна'}) as HTMLInputElement).checked).toBe(true);
    profile='another';second.rerender(<CourseJourney attemptId="attempt-1" progression={progression('another')}/>);
    await waitFor(()=>expect((screen.getByRole('radio',{name:'Анна'}) as HTMLInputElement).checked).toBe(false));expect(sessionStorage.length).toBe(0);
  });
  it('does not show another profile’s course and offers retry after a load error',async()=>{
    mockServer(()=>course({profile_id:'another'}));render(<CourseJourney progression={progression()}/>);
    expect(await screen.findByRole('alert')).toBeTruthy();expect(screen.queryByRole('heading',{name:'Your journey'})).toBeNull();expect(screen.getByRole('button',{name:'Try again'})).toBeTruthy();
  });
});

describe('Received-letter milestone course',()=>{
  const received=(patch:Partial<CourseAttempt>={})=>attempt({release_id:'a1-journey-v2',sender:'Anna',sender_ru:'Анна',letter_purpose:'Anna has left a message to help Barsik get ready.',letter_purpose_ru:'Анна оставила записку Барсику.',course:course({release_id:'a1-journey-v2'}),...patch});
  it('opens a received letter and groups the assessment without leaking later answer sets',async()=>{
    const current=received({questions:[...attempt().questions,{id:'form',kind:'language',prompt:'Choose the ending.',prompt_ru:'Выберите окончание.',choices:[{id:'a',text:'моя сестра'},{id:'b',text:'мой сестра'}]}]});
    mockServer(()=>current);render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    await screen.findByText('Anna');expect(screen.queryByText(current.letter)).toBeNull();expect(screen.queryByRole('radio')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Read the letter →'}));expect(screen.getByText(current.letter)).toBeTruthy();
    expect(screen.getByRole('radio',{name:'Анна'})).toBeTruthy();expect(screen.queryByRole('radio',{name:'В четыре часа'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Choose the form 0/1'}));expect(screen.getByRole('radio',{name:'моя сестра'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Check my answers'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Reply to the letter 0/1'}));expect(screen.getByRole('button',{name:'Check my answers'})).toBeTruthy();
  });
  it('shows component minima and next useful practice without claiming a pass',async()=>{
    const current=received({...result(),release_id:'a1-journey-v2',chapter_number:4,chapter_count:4,consequence:'Barsik is ready to leave town. Your letter stays sealed in his bag.',result:{...result().result!,passed:false,component_results:[{kind:'reading',score:7,total:8,required:6,passed:true},{kind:'language',score:1,total:3,required:2,passed:false}],next_practice:[{label:'Choosing a location',label_ru:'Местоположение',href:'/sentences?topic=home&level=A1'}]},course:course({release_id:'a1-journey-v2',completed:true,completed_milestones:4})});
    mockServer(()=>current);render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    expect(await screen.findByRole('heading',{name:'A little more practice'})).toBeTruthy();expect(screen.queryByText(current.consequence!)).toBeNull();expect(screen.getByText('Needs 2')).toBeTruthy();expect(screen.getByRole('link',{name:'Choosing a location →'}).getAttribute('href')).toBe('/sentences?topic=home&level=A1');
  });
  it('completes A1 with an onward consequence while preserving the original letter',async()=>{
    const current=received({...result(),release_id:'a1-journey-v2',chapter_number:4,chapter_count:4,consequence:'Barsik is ready to leave town. Your letter stays sealed in his bag.',course:course({release_id:'a1-journey-v2',completed:true,completed_milestones:4})});
    mockServer(()=>current);render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    expect(await screen.findByRole('heading',{name:'A1 course complete'})).toBeTruthy();expect(screen.getByText(current.consequence!)).toBeTruthy();expect(screen.getByText('A1 · 4 of 4 milestones complete')).toBeTruthy();
  });
  it('switches only on explicit request, keeps the same command after failure and retains old letters',async()=>{
    const old=course({release_upgrade:{release_id:'a1-journey-v2',title:'Home to the next village',title_ru:'От дома до следующей деревни',retained_access:['A1','A2'],active_attempts:[{id:'saved-old',title:'An unfinished letter',title_ru:'Незаконченное письмо'}],retained_milestones:4,starting_chapter:'Home'}});
    const updated=course({release_id:'a1-journey-v2',previous_courses:[{release_id:'a1-v1',title:'Earlier A1 journey',title_ru:'Прежнее путешествие A1',attempts:[{id:'saved-old',title:'An unfinished letter',title_ru:'Незаконченное письмо',status:'active'}]}]});
    let fail=true;const fetch=mockServer(url=>{if(url.endsWith('/switch')){if(fail)throw new Error('Offline');return updated;}return old;});
    render(<CourseJourney progression={progression()}/>);await screen.findByText('Updated journey available');
    expect(fetch.mock.calls.every(([,options])=>options?.method==='GET')).toBe(true);expect(screen.getByRole('link',{name:'An unfinished letter'}).getAttribute('href')).toBe('#journey/checkpoint/saved-old');
    fireEvent.click(screen.getByRole('button',{name:'Move to the updated journey →'}));await screen.findByRole('alert');fail=false;fireEvent.click(screen.getByRole('button',{name:'Move to the updated journey →'}));
    await screen.findByText('Earlier journeys and saved letters');expect(screen.getByRole('link',{name:'An unfinished letter · Continue'}).getAttribute('href')).toBe('#journey/checkpoint/saved-old');
    const writes=fetch.mock.calls.filter(([,options])=>options?.method==='POST');expect(writes).toHaveLength(2);expect(writes[0][1]?.body).toBe(writes[1][1]?.body);expect(JSON.parse(String(writes[0][1]?.body)).from_release_id).toBe('a1-v1');
  });
  it('saves vocabulary only after submission and asks for ambiguous lemma selection',async()=>{
    const saved=received({...result(),release_id:'a1-journey-v2',result:{...result().result!,vocabulary:[{word:'стали',context:'Они стали читать.'}]}});
    const fetch=mockServer((url,body)=>url.endsWith('/vocabulary') ? body?.lemma ? {word_id:7,href:'/vocab?word_id=7',flashcards_href:'#generate?word_id=7',enrichment_pending:true} : {needs_choice:true,choices:[{lemma:'стать',pos:'VERB',label:'стать · verb'},{lemma:'сталь',pos:'NOUN',label:'сталь · noun'}]} : saved);
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);await screen.findByText('Keep words from this letter');
    fireEvent.click(screen.getByRole('button',{name:'Add word'}));fireEvent.click(await screen.findByRole('button',{name:'стать · verb'}));
    expect(await screen.findByRole('link',{name:'Saved in My words'})).toBeTruthy();expect(screen.getByText('Word saved. Details could not be prepared.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Retry details'}));await waitFor(()=>expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST')).toHaveLength(3));
    const writes=fetch.mock.calls.filter(([,options])=>options?.method==='POST');expect(JSON.parse(String(writes[1][1]?.body))).toMatchObject({word:'стали',lemma:'стать',pos:'VERB'});expect(JSON.parse(String(writes[1][1]?.body))).not.toHaveProperty('context');expect(JSON.parse(String(writes[2][1]?.body))).toMatchObject({word:'стали',lemma:'стать',pos:'VERB'});expect(JSON.parse(String(writes[2][1]?.body)).request_id).not.toBe(JSON.parse(String(writes[1][1]?.body)).request_id);
  });
  it('loads saved account answers and saves later changes with the server revision',async()=>{
    const current=attempt({draft_answers:{read:'anna'},draft_revision:4});
    const fetch=mockServer((url,body)=>url.endsWith('/draft')?{...current,draft_answers:body!.answers,draft_revision:5}:current);
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    expect((await screen.findByRole('radio',{name:'Анна'}) as HTMLInputElement).checked).toBe(true);fireEvent.click(screen.getByRole('radio',{name:'Миша'}));
    await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>String(url).endsWith('/draft'))).toHaveLength(1));
    const saved=fetch.mock.calls.find(([url])=>String(url).endsWith('/draft'))!;expect(JSON.parse(String(saved[1]?.body))).toEqual({answers:{read:'misha'},revision:4});
  });
});

describe('Saved answer draft conflicts',()=>{
  it('does not overwrite a newer account draft with an older browser draft',async()=>{
    sessionStorage.setItem('word-post:checkpoint:learner:attempt-1',JSON.stringify({answers:{read:'misha'},revision:2}));
    const fetch=mockServer(()=>attempt({draft_answers:{read:'anna'},draft_revision:3,listened:true}));
    render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    expect(await screen.findByText(/These answers changed in another tab or device/)).toBeTruthy();expect((screen.getByRole('radio',{name:'Миша'}) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Use saved answers'}));expect((screen.getByRole('radio',{name:'Анна'}) as HTMLInputElement).checked).toBe(true);
    await new Promise(resolve=>setTimeout(resolve,500));expect(fetch.mock.calls.every(([,options])=>options?.method==='GET')).toBe(true);
  });
  it('fetches a conflicting draft and waits for an explicit choice',async()=>{
    let conflicting=false;
    const fetch=vi.fn(async(url:string,_options?:RequestInit)=>{
      if(url.endsWith('/draft')){conflicting=true;return respond({error:{code:'draft_conflict',message:'A newer draft is saved.'}},false);}
      return respond(attempt({draft_answers:{read:conflicting?'misha':'anna'},draft_revision:conflicting?3:2}));
    });vi.stubGlobal('fetch',fetch);render(<CourseJourney attemptId="attempt-1" progression={progression()}/>);
    fireEvent.click(await screen.findByRole('radio',{name:'В четыре часа'}));
    await screen.findByText(/These answers changed in another tab or device/);
    expect((screen.getByRole('radio',{name:'Анна'}) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Use saved answers'}));expect((screen.getByRole('radio',{name:'Миша'}) as HTMLInputElement).checked).toBe(true);
    await new Promise(resolve=>setTimeout(resolve,500));expect(fetch.mock.calls.filter(([url])=>url.endsWith('/draft'))).toHaveLength(1);
  });
});

describe('Release-scoped course navigation',()=>{
  it('loads an explicit historical release and resumes its saved attempt without a fresh start',async()=>{
    const historical=course({is_current_release:false,current_release_id:'a1-journey-v2'});
    historical.chapters[0].active_attempt_id='saved-old';
    const fetch=mockServer(()=>historical);
    render(<CourseJourney releaseId="a1-v1" chapterId="first" progression={progression()}/>);
    const resume=await screen.findByRole('link',{name:'Continue saved checkpoint →'});
    expect(resume.getAttribute('href')).toBe('#journey/checkpoint/saved-old');
    expect(screen.queryByRole('button',{name:/Start checkpoint|Test out/})).toBeNull();
    expect(fetch.mock.calls.map(([url])=>String(url))).toEqual(['/api/v1/course?release_id=a1-v1']);
    expect(fetch.mock.calls.every(([,options])=>options?.method==='GET')).toBe(true);
  });
  it('discards a delayed same-chapter response after changing releases',async()=>{
    let resolveOld!:(value:CourseData)=>void;
    const old=course();old.chapters[0].title='A stale message';
    const current=course({release_id:'a1-journey-v2'});current.chapters[0].title='A new message';
    const fetch=mockServer(url=>url.endsWith('=a1-v1') ? new Promise<CourseData>(resolve=>{resolveOld=resolve;}) : current);
    const view=render(<CourseJourney releaseId="a1-v1" chapterId="first" progression={progression()}/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledOnce());
    view.rerender(<CourseJourney releaseId="a1-journey-v2" chapterId="first" progression={progression()}/>);
    await screen.findByRole('heading',{name:'A new message'});
    resolveOld(old);
    await waitFor(()=>expect(screen.queryByRole('heading',{name:'A stale message'})).toBeNull());
    expect(screen.getByRole('heading',{name:'A new message'})).toBeTruthy();
    expect(fetch.mock.calls.map(([url])=>String(url))).toEqual(['/api/v1/course?release_id=a1-v1','/api/v1/course?release_id=a1-journey-v2']);
  });
  it('shows an unavailable explicit release without falling back to another route',async()=>{
    const fetch=vi.fn(async(_url:RequestInfo|URL,_options?:RequestInit)=>respond({error:{code:'course_release_unavailable',message:'That course release is not available.'}},false));
    vi.stubGlobal('fetch',fetch);
    render(<CourseJourney releaseId="unknown-release" chapterId="home" progression={progression()}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('That course release is not available.');
    expect(screen.queryByRole('button',{name:/Test out|Start checkpoint/})).toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
    expect(String(fetch.mock.calls[0][0])).toBe('/api/v1/course?release_id=unknown-release');
  });
});
