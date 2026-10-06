import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {LessonAudio} from './LessonAudio';

beforeEach(()=>{
  vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
describe('Recorded lesson audio',()=>{
  it('starts only on request and replays slowly without changing pitch or saving answers',async()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
    const view=render(<LessonAudio src="/static/audio/hello.mp3" label="Привет!"/>);
    const player=view.container.querySelector('audio')!;
    expect(player.preload).toBe('none');expect(player.play).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Listen to Привет!'}));
    await screen.findByRole('button',{name:'Pause Привет!'});expect(player.playbackRate).toBe(1);
    player.currentTime=2;
    fireEvent.click(screen.getByRole('button',{name:'Slow replay of Привет!'}));
    await waitFor(()=>expect(player.play).toHaveBeenCalledTimes(2));
    expect(player.currentTime).toBe(0);expect(player.playbackRate).toBe(.75);expect(player.preservesPitch).toBe(true);
    fireEvent(player,new Event('ended'));expect(screen.getByRole('button',{name:'Listen to Привет!'})).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();vi.unstubAllGlobals();
  });
  it('shows a clear replay action after a playback failure',async()=>{
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error('Unavailable'));
    const view=render(<LessonAudio src="/static/audio/hello.mp3"/>);
    fireEvent.click(screen.getByRole('button',{name:'Slow replay of the recording'}));
    expect((await screen.findByRole('alert')).textContent).toContain('The recording couldn’t play.');
    fireEvent.click(screen.getByRole('button',{name:'Retry audio'}));
    await screen.findByRole('button',{name:'Pause the recording'});
    expect(view.container.querySelector('audio')!.playbackRate).toBe(.75);
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalledOnce();expect(screen.queryByRole('alert')).toBeNull();
  });
  it('autoplays once at normal speed on entry and leaves normal and slow replay available',async()=>{
    const view=render(<LessonAudio src="/static/audio/question.mp3" autoPlay/>);
    const player=view.container.querySelector('audio')!;
    await screen.findByRole('button',{name:'Pause the recording'});
    expect(player.play).toHaveBeenCalledOnce();expect(player.playbackRate).toBe(1);
    view.rerender(<LessonAudio src="/static/audio/question.mp3" label="the question" autoPlay inline/>);
    expect(player.play).toHaveBeenCalledOnce();
    fireEvent(player,new Event('ended'));
    fireEvent.click(screen.getByRole('button',{name:'Listen to the question'}));
    await screen.findByRole('button',{name:'Pause the question'});
    fireEvent.click(screen.getByRole('button',{name:'Slow replay of the question'}));
    await waitFor(()=>expect(player.play).toHaveBeenCalledTimes(3));expect(player.playbackRate).toBe(.75);
    view.rerender(<LessonAudio src="/static/audio/next-question.mp3" label="the question" autoPlay/>);
    await waitFor(()=>expect(player.play).toHaveBeenCalledTimes(4));
    expect(view.container.querySelector('audio')!.playbackRate).toBe(1);
    expect(vi.mocked(player.pause).mock.contexts).toContain(player);
  });
  it('offers Listen when the browser blocks autoplay, without reporting a broken recording',async()=>{
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException('User gesture required','NotAllowedError'));
    const view=render(<LessonAudio src="/static/audio/question.mp3" autoPlay/>);
    expect((await screen.findByRole('status')).textContent).toBe('Press Listen to hear the recording.');
    expect(screen.queryByRole('alert')).toBeNull();expect(screen.queryByRole('button',{name:'Retry audio'})).toBeNull();
    view.rerender(<LessonAudio src="/static/audio/question.mp3" autoPlay inline/>);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button',{name:'Listen to the recording'}));
    await screen.findByRole('button',{name:'Pause the recording'});
    expect(screen.queryByRole('status')).toBeNull();expect(HTMLMediaElement.prototype.load).not.toHaveBeenCalled();
  });
  it('keeps genuine autoplay failures retryable',async()=>{
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error('Unavailable'));
    render(<LessonAudio src="/static/audio/question.mp3" autoPlay/>);
    expect((await screen.findByRole('alert')).textContent).toContain('The recording couldn’t play.');
    expect(screen.queryByRole('status')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Retry audio'}));
    await screen.findByRole('button',{name:'Pause the recording'});
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalledOnce();
  });
  it('stops when autoplay is disabled and plays again only on another entry',async()=>{
    const view=render(<LessonAudio src="/static/audio/question.mp3" autoPlay/>);
    await screen.findByRole('button',{name:'Pause the recording'});
    view.rerender(<LessonAudio src="/static/audio/question.mp3" autoPlay={false}/>);
    expect(screen.getByRole('button',{name:'Listen to the recording'})).toBeTruthy();
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledOnce();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledOnce();
    view.rerender(<LessonAudio src="/static/audio/question.mp3" autoPlay/>);
    await screen.findByRole('button',{name:'Pause the recording'});
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    view.unmount();expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(2);
  });
  it.each(['leave','change','stop'] as const)('stops pending playback that resolves after %s',async transition=>{
    let resolve!:()=>void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(()=>new Promise<void>(done=>{resolve=done;}));
    const view=render(<LessonAudio src="/static/audio/question.mp3" label="question" autoPlay/>);
    const player=view.container.querySelector('audio')!;
    if(transition==='leave')view.unmount();
    else if(transition==='change')view.rerender(<LessonAudio src="/static/audio/next-question.mp3" label="next question" autoPlay/>);
    else view.rerender(<LessonAudio src="/static/audio/question.mp3" label="question" autoPlay={false}/>);
    const pauses=vi.mocked(player.pause).mock.contexts.filter(context=>context===player).length;
    await act(async()=>resolve());
    expect(vi.mocked(player.pause).mock.contexts.filter(context=>context===player)).toHaveLength(pauses+1);
    expect(screen.queryByRole('button',{name:'Pause question'})).toBeNull();
    if(transition==='change')expect(screen.getByRole('button',{name:'Pause next question'})).toBeTruthy();
  });
  it('does not let a stale play completion interrupt a newer replay on the same player',async()=>{
    let resolve!:()=>void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(()=>new Promise<void>(done=>{resolve=done;}));
    const view=render(<LessonAudio src="/static/audio/question.mp3" autoPlay/>);
    fireEvent.click(screen.getByRole('button',{name:'Slow replay of the recording'}));
    await screen.findByRole('button',{name:'Pause the recording'});
    await act(async()=>resolve());
    expect(screen.getByRole('button',{name:'Pause the recording'})).toBeTruthy();
    expect(view.container.querySelector('audio')!.playbackRate).toBe(.75);
    expect(HTMLMediaElement.prototype.pause).not.toHaveBeenCalled();
  });
  it('pauses the previous recording when another word starts',async()=>{
    const view=render(<><LessonAudio src="/static/audio/hello.mp3" label="hello"/><LessonAudio src="/static/audio/letter.mp3" label="letter"/></>);
    const [hello,letter]=view.container.querySelectorAll('audio');
    fireEvent.click(screen.getByRole('button',{name:'Listen to hello'}));await screen.findByRole('button',{name:'Pause hello'});
    fireEvent.click(screen.getByRole('button',{name:'Listen to letter'}));await screen.findByRole('button',{name:'Pause letter'});
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledOnce();
    expect(vi.mocked(HTMLMediaElement.prototype.pause).mock.instances[0]).toBe(hello);
    expect(screen.getByRole('button',{name:'Listen to hello'})).toBeTruthy();
    fireEvent(letter,new Event('pause'));expect(screen.getByRole('button',{name:'Listen to letter'})).toBeTruthy();
  });
  it('ignores a late failure after the teaching recording changes',async()=>{
    let reject!:(reason:Error)=>void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(()=>new Promise<void>((_resolve,fail)=>{reject=fail;}));
    const view=render(<LessonAudio src="/static/audio/hello.mp3" label="hello"/>);
    fireEvent.click(screen.getByRole('button',{name:'Listen to hello'}));
    view.rerender(<LessonAudio src="/static/audio/letter.mp3" label="letter"/>);
    await act(async()=>reject(new Error('Old recording failed')));
    expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByRole('button',{name:'Listen to letter'})).toBeTruthy();
  });
});
