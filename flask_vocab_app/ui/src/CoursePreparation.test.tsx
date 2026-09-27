import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {CoursePreparation,type CoursePractice} from './CoursePreparation';
import type {ProgressionState} from './Progression';
const progression={data:{profile_id:'p',course:{release_id:'a1-journey-v2'}},refresh:vi.fn(),loading:false,error:''} as unknown as ProgressionState;
const practice=():CoursePractice=>({id:'practice-1',release_id:'a1-journey-v2',target_catalogue_version:'a1-targets-v1',content_version:'a1-target-practice-v1',profile_id:'p',section_id:'home',status:'active',completed_count:0,total_count:1,current_item:{id:'item-1',target_id:'target-1',title:'A family member',title_ru:'Член семьи',stage:'learn',teaching:{explanation:'Use моя before сестра.',explanation_ru:'Перед словом «сестра» употребляем «моя».',example_ru:'Это моя сестра.',example_en:'This is my sister.'},question:{prompt:'Which phrase fits?',prompt_ru:'Какой вариант подходит?',choices:[{id:'right',text:'Моя сестра'},{id:'wrong',text:'Мой сестра'}]},hint:null,feedback:null,listened:false,transcript:null},coverage:{required_count:1,prepared_count:0,ready:false,targets:[]}});
function serve(handler:(url:string,body:any)=>unknown){const fetch=vi.fn(async(url:string,options?:RequestInit)=>({ok:true,json:async()=>handler(url,options?.body?JSON.parse(String(options.body)):undefined)}));vi.stubGlobal('fetch',fetch);return fetch;}
beforeEach(()=>{window.location.hash='';});afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('Milestone target practice',()=>{
  it('teaches before recall, checks a real choice and returns to the same milestone',async()=>{
    let value=practice();const fetch=serve(url=>{
      if(url.endsWith('/learn'))value={...value,current_item:{...value.current_item!,stage:'question'}};
      if(url.endsWith('/answer'))value={...value,current_item:{...value.current_item!,stage:'feedback',feedback:{correct:true,answer:'right',explanation:'Сестра takes моя.',explanation_ru:'Перед словом «сестра» стоит «моя».'}}};
      if(url.endsWith('/next'))value={...value,status:'completed',current_item:null,completed_count:1};return value;
    });render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    await screen.findByText('Use моя before сестра.');expect(screen.queryByRole('radio')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Try it →'}));fireEvent.click(await screen.findByRole('radio',{name:'Моя сестра'}));fireEvent.click(screen.getByRole('button',{name:'Check answer'}));
    expect(await screen.findByText('That’s right.')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Finish practice →'}));
    await screen.findByRole('heading',{name:'Practice saved'});expect(screen.getByRole('link',{name:'Continue the milestone →'}).getAttribute('href')).toBe('#journey/release/a1-journey-v2/chapter/home');
    const commands=fetch.mock.calls.filter(([,options])=>options?.method==='POST');expect(commands.map(([url])=>url.split('/').at(-1))).toEqual(['learn','answer','next']);
    expect(JSON.parse(String(commands[1][1]?.body))).toMatchObject({item_id:'item-1',choice_id:'right'});
  });
  it('starts or resumes section practice with a stable request across an uncertain start',async()=>{
    let fail=true;const fetch=vi.fn(async(_url:string,_options?:RequestInit)=>{if(fail)throw new Error('Offline');return{ok:true,json:async()=>practice()};});vi.stubGlobal('fetch',fetch);
    render(<CoursePreparation sectionId="home" progression={progression}/>);await screen.findByRole('alert');fail=false;fireEvent.click(screen.getByRole('button',{name:'Try again'}));
    await waitFor(()=>expect(window.location.hash).toBe('#journey/practice/practice-1'));
    expect(fetch.mock.calls[0][1]?.body).toBe(fetch.mock.calls[1][1]?.body);expect(JSON.parse(String(fetch.mock.calls[0][1]?.body)).release_id).toBe('a1-journey-v2');
  });
  it('does not expose another learner’s saved practice',async()=>{
    serve(()=>({...practice(),profile_id:'other'}));render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    await screen.findByRole('alert');expect(screen.queryByText('Use моя before сестра.')).toBeNull();
  });
  it('requires the listening clip or optional transcript before checking',async()=>{
    let value=practice();value.current_item={...value.current_item!,stage:'question',question:{...value.current_item!.question!,audio_url:'/static/audio/example.mp3'}};
    serve(url=>{if(url.endsWith('/listened'))value={...value,current_item:{...value.current_item!,listened:true}};return value;});
    render(<CoursePreparation practiceId="practice-1" progression={progression}/>);fireEvent.click(await screen.findByRole('radio',{name:'Моя сестра'}));expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent(screen.getByLabelText('Practice recording'),new Event('ended'));await waitFor(()=>expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(false));
  });
});

const listeningPractice=():CoursePractice=>{
  const value=practice();
  return {...value,current_item:{...value.current_item!,stage:'question',question:{...value.current_item!.question!,audio_url:'/static/audio/example.mp3'}}};
};
describe('Preparation audio recovery',()=>{
  it('retries failed media without counting playback or failure as listening',async()=>{
    const load=vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
    const play=vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
    const fetch=serve(()=>listeningPractice());
    render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    fireEvent.click(await screen.findByRole('radio',{name:'Моя сестра'}));
    const recording=screen.getByLabelText('Practice recording');
    fireEvent(recording,new Event('play'));fireEvent(recording,new Event('error'));
    expect(screen.getByRole('alert').textContent).toContain('The recording could not play.');
    expect(screen.getByRole('button',{name:'Show transcript'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Retry audio'}));
    expect(load).toHaveBeenCalledOnce();expect(play).toHaveBeenCalledOnce();
    expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(true);
    expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST')).toHaveLength(0);
    expect(screen.queryByRole('button',{name:'Retry audio'})).toBeNull();
  });
  it('keeps transcript support available after a playback rejection without inventing a listening receipt',async()=>{
    vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
    vi.spyOn(HTMLMediaElement.prototype,'play').mockRejectedValue(new Error('Playback unavailable'));
    let value=listeningPractice();
    const fetch=serve(url=>{if(url.endsWith('/transcript'))value={...value,current_item:{...value.current_item!,transcript:'Это моя сестра.'}};return value;});
    render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    fireEvent.click(await screen.findByRole('radio',{name:'Моя сестра'}));
    fireEvent(screen.getByLabelText('Practice recording'),new Event('error'));
    fireEvent.click(screen.getByRole('button',{name:'Retry audio'}));
    await screen.findByRole('button',{name:'Retry audio'});
    fireEvent.click(screen.getByRole('button',{name:'Show transcript'}));
    await screen.findByText('Это моя сестра.');
    expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(false);
    expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST').map(([url])=>url.split('/').at(-1))).toEqual(['transcript']);
  });
  it('retries a failed listening receipt without replay and reuses the command id',async()=>{
    const play=vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
    let value=listeningPractice();let failed=false;
    const fetch=serve(url=>{if(url.endsWith('/listened')){if(!failed){failed=true;throw new Error('Offline');}value={...value,current_item:{...value.current_item!,listened:true}};}return value;});
    render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    fireEvent.click(await screen.findByRole('radio',{name:'Моя сестра'}));
    fireEvent(screen.getByLabelText('Practice recording'),new Event('ended'));
    await screen.findByText('We couldn’t save that you listened. You can retry saving without playing the recording again.');
    expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Retry saving listening'}));
    await waitFor(()=>expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(false));
    const writes=fetch.mock.calls.filter(([,options])=>options?.method==='POST');
    expect(writes).toHaveLength(2);expect(writes[0][1]?.body).toBe(writes[1][1]?.body);expect(play).not.toHaveBeenCalled();
  });
  it('does not apply a late listening receipt to another learner',async()=>{
    let resolveReceipt!:(value:CoursePractice)=>void;
    const current=listeningPractice();
    const next={...listeningPractice(),id:'practice-2',profile_id:'p2',current_item:{...listeningPractice().current_item!,id:'item-2',title:'New listening task'}};
    serve(url=>url.endsWith('/listened')?new Promise<CoursePractice>(resolve=>{resolveReceipt=resolve;}):url.includes('/practice-2')?next:current);
    const {rerender}=render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    fireEvent(await screen.findByLabelText('Practice recording'),new Event('ended'));
    rerender(<CoursePreparation practiceId="practice-2" progression={{...progression,data:{...progression.data!,profile_id:'p2'}}}/>);
    await screen.findByRole('heading',{name:'New listening task'});
    resolveReceipt({...current,current_item:{...current.current_item!,listened:true}});
    fireEvent.click(screen.getByRole('radio',{name:'Моя сестра'}));
    await waitFor(()=>expect((screen.getByRole('button',{name:'Check answer'}) as HTMLButtonElement).disabled).toBe(true));
    expect(screen.getByRole('heading',{name:'New listening task'})).toBeTruthy();
  });
  it('ignores late media events and playback rejection after a learner changes',async()=>{
    let rejectPlayback!:(reason:Error)=>void;
    vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
    vi.spyOn(HTMLMediaElement.prototype,'play').mockImplementation(()=>new Promise<void>((_resolve,reject)=>{rejectPlayback=reject;}));
    const current=listeningPractice();const next={...listeningPractice(),id:'practice-2',profile_id:'p2',current_item:{...listeningPractice().current_item!,id:'item-2',title:'New listening task'}};
    const fetch=serve(url=>url.includes('/practice-2')?next:current);
    const {rerender}=render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    const oldRecording=await screen.findByLabelText('Practice recording');
    fireEvent(oldRecording,new Event('error'));fireEvent.click(screen.getByRole('button',{name:'Retry audio'}));
    rerender(<CoursePreparation practiceId="practice-2" progression={{...progression,data:{...progression.data!,profile_id:'p2'}}}/>);
    await screen.findByRole('heading',{name:'New listening task'});
    fireEvent(oldRecording,new Event('ended'));fireEvent(oldRecording,new Event('error'));rejectPlayback(new Error('Old player failed'));
    await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
    expect(fetch.mock.calls.filter(([,options])=>options?.method==='POST')).toHaveLength(0);
  });
});

describe('Release-scoped preparation navigation',()=>{
  it('retains known release identity through an exact legacy action receipt',async()=>{
    const current=practice();
    const receipt={...current,release_id:undefined,target_catalogue_version:undefined,content_version:undefined,status:'completed',current_item:null,completed_count:1} as CoursePractice;
    const fetch=serve(url=>url.endsWith('/learn')?receipt:current);
    const changed={...progression,data:{...progression.data!,course:{...progression.data!.course!,release_id:'a1-v1'}}};
    render(<CoursePreparation practiceId="practice-1" progression={changed}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Try it →'}));
    expect((await screen.findByRole('link',{name:'Continue the milestone →'})).getAttribute('href')).toBe('#journey/release/a1-journey-v2/chapter/home');
    expect(screen.getByRole('link',{name:'← Milestone practice'}).getAttribute('href')).toBe('#journey/release/a1-journey-v2/chapter/home');
    expect(fetch.mock.calls.map(([url])=>url)).toEqual(['/api/v1/course/practice/practice-1','/api/v1/course/practice/practice-1/learn']);
    expect(receipt.release_id).toBeUndefined();
  });
  it.each(['id','profile_id','section_id','release_id','target_catalogue_version','content_version'] as const)('rejects an action receipt with a different %s',async(field)=>{
    const current=practice();
    const receipt={...current,[field]:'different',status:'completed',current_item:null,completed_count:1};
    serve(url=>url.endsWith('/learn')?receipt:current);
    render(<CoursePreparation practiceId="practice-1" progression={progression}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Try it →'}));
    await screen.findByRole('alert');
    expect(screen.queryByRole('heading',{name:'Practice saved'})).toBeNull();
    expect(screen.queryByRole('link',{name:'Continue the milestone →'})).toBeNull();
  });
  it('returns saved practice to its own release despite a changed current journey',async()=>{
    const fetch=serve(()=>({...practice(),status:'completed',current_item:null,completed_count:1}));
    const changed={...progression,data:{...progression.data!,course:{...progression.data!.course!,release_id:'a1-v1'}}};
    render(<CoursePreparation practiceId="practice-1" progression={changed}/>);
    const link=await screen.findByRole('link',{name:'Continue the milestone →'});
    expect(link.getAttribute('href')).toBe('#journey/release/a1-journey-v2/chapter/home');
    expect(fetch.mock.calls.map(([url])=>url)).toEqual(['/api/v1/course/practice/practice-1']);
    expect(fetch.mock.calls.every(([,options])=>options?.method==='GET')).toBe(true);
  });
  it('binds new requests to their explicit release and ignores a stale same-section response',async()=>{
    let resolveOld!:(value:CoursePractice)=>void;
    const next={...practice(),id:'practice-2',release_id:'a1-v1',current_item:{...practice().current_item!,title:'Current practice'}};
    const fetch=serve((_url,body)=>body?.release_id==='a1-journey-v2' ? new Promise<CoursePractice>(resolve=>{resolveOld=resolve;}) : next);
    const view=render(<CoursePreparation releaseId="a1-journey-v2" sectionId="home" progression={progression}/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledOnce());
    view.rerender(<CoursePreparation releaseId="a1-v1" sectionId="home" progression={progression}/>);
    await screen.findByRole('heading',{name:'Current practice'});
    resolveOld(practice());
    await waitFor(()=>expect(screen.queryByRole('heading',{name:'A family member'})).toBeNull());
    const bodies=fetch.mock.calls.map(([,options])=>JSON.parse(String(options?.body)));
    expect(bodies.map(body=>body.release_id)).toEqual(['a1-journey-v2','a1-v1']);
    expect(bodies[0].request_id).not.toBe(bodies[1].request_id);
    expect(window.location.hash).toBe('#journey/practice/practice-2');
  });
  it('keeps unknown saved content unavailable without restarting against the current release',async()=>{
    const fetch=vi.fn(async(_url:string,_options?:RequestInit)=>({ok:false,json:async()=>({error:{code:'practice_content_unavailable',message:'This saved preparation version is unavailable.'}})}));
    vi.stubGlobal('fetch',fetch);
    render(<CoursePreparation practiceId="saved-unknown" progression={progression}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('This saved preparation version is unavailable.');
    expect(screen.queryByRole('button',{name:'Try it →'})).toBeNull();
    expect(fetch.mock.calls.map(([url])=>url)).toEqual(['/api/v1/course/practice/saved-unknown']);
  });
});
