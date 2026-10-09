import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/preact';
import {CardMedia} from './CardDetails';
import type {CardAsset} from './review-types';

const word:CardAsset={id:'word',role:'prompt',media_type:'audio/mpeg',kind:'word_audio'};
const example:CardAsset={id:'example',role:'answer',media_type:'audio/mpeg',kind:'sentence_audio'};
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(() => {});
});
afterEach(() => { cleanup();vi.restoreAllMocks(); });

describe('Card media',() => {
  it('retains native library audio controls and image rendering',() => {
    const view=render(<CardMedia asset={word} language="en" />);
    const player=screen.getByLabelText('Word: Russian audio') as HTMLAudioElement;
    expect(player.controls).toBe(true);
    expect(player.hidden).toBe(false);
    expect(screen.queryByRole('button',{name:'Play word'})).toBeNull();
    view.rerender(<CardMedia asset={{id:'picture',role:'answer',media_type:'image/png',kind:'image'}} language="en" compact />);
    expect(screen.getByRole('img',{name:'Illustration of the example sentence'}).getAttribute('src')).toBe('/api/v1/assets/picture');
    expect(view.container.querySelector('.card-recording--compact')).toBeNull();
  });

  it('starts compact audio only on request and keeps the selected speed after metadata loads',async() => {
    render(<CardMedia asset={word} language="en" compact />);
    const player=screen.getByLabelText('Word: Russian audio') as HTMLAudioElement;
    expect(player.hidden).toBe(true);
    expect(player.controls).toBe(false);
    expect(player.autoplay).toBe(false);
    expect(player.play).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('combobox',{name:'Word: playback speed'}),{target:{value:'0.75'}});
    expect(player.playbackRate).toBe(.75);
    player.playbackRate=1;
    fireEvent(player,new Event('loadedmetadata'));
    expect(player.playbackRate).toBe(.75);
    fireEvent.click(screen.getByRole('button',{name:'Play word'}));
    await screen.findByRole('button',{name:'Pause word'});
    expect(player.play).toHaveBeenCalledOnce();
    expect(player.playbackRate).toBe(.75);
    fireEvent.click(screen.getByRole('button',{name:'Pause word'}));
    expect(player.pause).toHaveBeenCalledOnce();
    expect(screen.getByRole('button',{name:'Play word'})).toBeTruthy();
  });

  it('tracks play, pause and ended events from the audio element',() => {
    render(<CardMedia asset={example} language="en" compact />);
    const player=screen.getByLabelText('Example: Russian audio');
    fireEvent(player,new Event('play'));
    expect(screen.getByRole('button',{name:'Pause example'})).toBeTruthy();
    fireEvent(player,new Event('pause'));
    expect(screen.getByRole('button',{name:'Play example'})).toBeTruthy();
    fireEvent(player,new Event('play'));
    fireEvent(player,new Event('ended'));
    expect(screen.getByRole('button',{name:'Play example'})).toBeTruthy();
  });

  it('announces rejected playback and lets the same button retry',async() => {
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException('Blocked','NotAllowedError'));
    render(<CardMedia asset={word} language="en" compact />);
    fireEvent.click(screen.getByRole('button',{name:'Play word'}));
    expect((await screen.findByRole('alert')).textContent).toContain('The recording could not play.');
    fireEvent.click(screen.getByRole('button',{name:'Play word'}));
    await screen.findByRole('button',{name:'Pause word'});
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('localizes pronunciation controls and reports media load errors',() => {
    render(<CardMedia asset={{...word,kind:undefined}} language="ru" compact />);
    expect(screen.getByRole('button',{name:'Воспроизвести произношение'})).toBeTruthy();
    expect(screen.getByRole('combobox',{name:'Произношение: скорость воспроизведения'})).toBeTruthy();
    fireEvent(screen.getByLabelText('Произношение: аудио по-русски'),new Event('error'));
    expect(screen.getByRole('alert').textContent).toContain('Не удалось воспроизвести запись.');
  });

  it('stops pending audio when the card changes and ignores its late rejection',async() => {
    let reject!:(reason:Error) => void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(() => new Promise<void>((_resolve,fail) => { reject=fail; }));
    const view=render(<CardMedia asset={word} language="en" compact />);
    const oldPlayer=screen.getByLabelText('Word: Russian audio');
    fireEvent.click(screen.getByRole('button',{name:'Play word'}));
    view.rerender(<CardMedia asset={example} language="en" compact />);
    expect(vi.mocked(HTMLMediaElement.prototype.pause).mock.contexts).toContain(oldPlayer);
    await act(async() => reject(new Error('Old recording failed')));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('button',{name:'Play example'})).toBeTruthy();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledOnce();
  });
});
