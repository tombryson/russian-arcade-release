import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/preact';
import {LessonAudio} from './LessonAudio';

beforeEach(()=>{
  vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});
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
