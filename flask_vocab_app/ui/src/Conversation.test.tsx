import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/preact';
import { Conversation } from './Conversation';

const scenario={title:'A stop at the café',title_ru:'В кафе',description:'Order a drink.',description_ru:'Закажите напиток.',opening:'Что будете пить?',opening_english:'What would you like to drink?'};
const options={scenario,cases:[{id:'genitive',category:'case',text:'Я хочу чай без сахар.',corrected:'Я хочу чай без сахара.',note:'Genitive.'}],configured:true,audio_configured:true,sessions:[]};
const session={id:'one',mode:'conversation',state:'active',scenario,turns:[],greeting_audio_url:null};
const response=(value:unknown)=>Promise.resolve({ok:true,json:async()=>value});
function setup(saved:unknown=session) {
  const fetch=vi.fn((url:string)=>response(url.endsWith('/household')?{csrf_token:'csrf'}:url.endsWith('/options')?options:saved));
  vi.stubGlobal('fetch',fetch);
  return fetch;
}
afterEach(()=>vi.unstubAllGlobals());

describe('Recorded conversation archive and speech lab',()=>{
  it('omits English recognition text while retaining the original recording',async()=>{
    setup({...session,turns:[{id:'turn',ordinal:1,state:'ready',recording_url:'/private-original',
      transcript:{text:"I'd like some coffee and some tea",model:'MAI',style:'verbatim',latency_ms:1000},
      reply:null,assessment:null,comparisons:[],working:false,retryable:false}]});
    render(<Conversation sessionId="one" />);
    expect(await screen.findByText('No Russian transcript to show.')).toBeTruthy();
    expect(screen.queryByText(/I'd like some coffee/)).toBeNull();
    expect(screen.getByLabelText('Your recording 1').getAttribute('src')).toBe('/private-original');
  });
  it('keeps old conversations available without offering a new recording or requesting microphone access',async()=>{
    setup();const getUserMedia=vi.fn();vi.stubGlobal('navigator',{mediaDevices:{getUserMedia}});
    render(<Conversation sessionId="one" />);
    expect(await screen.findByRole('link',{name:/Start speaking/})).toBeTruthy();
    expect(screen.queryByRole('button',{name:/Step into the café|Tap to speak|Finish practice/})).toBeNull();
    expect(screen.queryByLabelText('Audio file')).toBeNull();
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(screen.queryByText(/PIN|grown-up/)).toBeNull();
  });
  it('starts diagnostic tests with an idempotency key and saves under Speaking',async()=>{
    const fetch=setup({...session,mode:'lab'});render(<Conversation lab />);
    fireEvent.click(await screen.findByRole('button',{name:/Start a speech test/}));
    await vi.waitFor(()=>expect(fetch.mock.calls.some(([url])=>url==='/api/v1/conversations')).toBe(true));
    const call=fetch.mock.calls.find(([url])=>url==='/api/v1/conversations') as unknown as [string,RequestInit];
    expect(JSON.parse(call[1].body as string)).toMatchObject({mode:'lab',language:'en',submission_id:expect.any(String)});
    await vi.waitFor(()=>expect(window.location.hash).toBe('#speaking/recorded/one'));
  });
  it('keeps English translations optional and never displays a made-up grade',async()=>{
    setup();render(<Conversation sessionId="one" />);
    await screen.findByText('Что будете пить?');
    expect(screen.queryByText('What would you like to drink?')).toBeNull();
    fireEvent.click(screen.getByLabelText('Show English translations'));
    expect(screen.getByText('What would you like to drink?')).toBeTruthy();
    expect(screen.queryByText(/Elo|Grammar score|Fluency score/)).toBeNull();
  });
  it('handles unavailable microphone permission with a file alternative',async()=>{
    setup({...session,mode:'lab'});vi.stubGlobal('MediaRecorder',class {});
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn().mockRejectedValue(new Error('denied'))}});
    render(<Conversation sessionId="one" />);
    fireEvent.click(await screen.findByRole('button',{name:/Tap to speak/}));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByLabelText('Audio file')).toBeTruthy();
  });
  it('releases a microphone granted after navigation away',async()=>{
    setup({...session,mode:'lab'});let grant:(value:unknown)=>void=()=>{};const stop=vi.fn();
    vi.stubGlobal('MediaRecorder',class {});
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn(()=>new Promise(resolve=>{grant=resolve;}))}});
    const view=render(<Conversation sessionId="one" />);
    fireEvent.click(await screen.findByRole('button',{name:/Tap to speak/}));view.unmount();
    grant({getTracks:()=>[{stop}]});await vi.waitFor(()=>expect(stop).toHaveBeenCalled());
  });
  it('stops tracks and keeps a recorded clip ready for preview and sending',async()=>{
    setup({...session,mode:'lab'});const stopTrack=vi.fn();
    class Recorder {
      static isTypeSupported() {return true;}
      state='inactive';mimeType='audio/webm';
      ondataavailable=(_event:{data:Blob})=>{};
      onstop=()=>{};
      start(){this.state='recording';}
      stop(){this.state='inactive';this.ondataavailable({data:new Blob(['recorded speech'],{type:'audio/webm'})});this.onstop();}
    }
    vi.stubGlobal('MediaRecorder',Recorder);
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn().mockResolvedValue({getTracks:()=>[{stop:stopTrack}]})}});
    vi.stubGlobal('URL',{createObjectURL:()=> 'blob:test-recording',revokeObjectURL:vi.fn()});
    render(<Conversation sessionId="one" />);
    fireEvent.click(await screen.findByRole('button',{name:/Tap to speak/}));
    fireEvent.click(await screen.findByRole('button',{name:/Stop recording/}));
    expect(await screen.findByRole('button',{name:/Compare transcriptions/})).toBeTruthy();
    expect(stopTrack).toHaveBeenCalled();
    expect(screen.getByLabelText('Listen before sending').getAttribute('src')).toBe('blob:test-recording');
  });
  it('keeps recognised text separate from suggested corrections and original audio',async()=>{
    setup({...session,turns:[{id:'turn',ordinal:1,state:'ready',duration_seconds:3,recording_url:'/private-original',reply_audio_url:'/private-reply',
      transcript:{text:'Она читаю книгу.',model:'MAI',style:'verbatim',latency_ms:1000},reply:{russian:'А что читаете вы?',english:'And what are you reading?'},
      assessment:{basis:'unverified_transcript',communication:'Meaning is clear.',uncertainty:'',corrections:[{original:'читаю',replacement:'читает',explanation:'Third person singular.'}]},
      comparisons:[],audio_state:'ready',assessment_state:'ready',working:false,retryable:false}]});
    render(<Conversation sessionId="one" />);
    expect(await screen.findByText('Она читаю книгу.')).toBeTruthy();
    expect(screen.getByText('читает')).toBeTruthy();
    expect(screen.getByText(/Based on the transcript/)).toBeTruthy();
    expect(screen.getByLabelText('Your recording 1').getAttribute('src')).toBe('/private-original');
    expect(screen.getByLabelText('Listen to reply 1').getAttribute('src')).toBe('/private-reply');
    expect(screen.getByRole('link',{name:/Speaking/}).getAttribute('href')).toBe('#speaking');
  });
  it('lets the learner record deliberately incorrect sentences in the lab',async()=>{
    setup({...session,mode:'lab'});render(<Conversation sessionId="one" />);
    expect(await screen.findByLabelText('Test sentence')).toBeTruthy();
    expect(screen.getByText(/It is not sent to the recogniser/)).toBeTruthy();
    expect(screen.queryByText('Что будете пить?')).toBeNull();
  });
});
