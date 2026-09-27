import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/preact';
import { PilotRecording } from './PilotRecording';

class Recorder {
  static isTypeSupported() { return true; }
  static instances: Recorder[] = [];
  mimeType = 'audio/webm;codecs=opus'; state = 'inactive';
  ondataavailable?: (event: { data: Blob }) => void; onstop?: () => void; onerror?: () => void;
  constructor() { Recorder.instances.push(this); }
  start() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['original audio'], { type: this.mimeType }) }); this.onstop?.(); }
}
const stop = vi.fn();
const media = { getTracks: () => [{ stop }] };
beforeEach(() => {
  Recorder.instances = []; stop.mockClear(); vi.stubGlobal('MediaRecorder', Recorder);
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue(media) } });
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  URL.createObjectURL = vi.fn(() => 'blob:pilot-recording'); URL.revokeObjectURL = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Pilot original recording', () => {
  it('opens the microphone only on request and returns original bytes after stopping', async () => {
    const ready = vi.fn(); render(<PilotRecording disabled={false} onReady={ready} />);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Record your reply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Stop recording' }));
    expect(await screen.findByLabelText('Listen to your recording')).toBeTruthy();
    const [clip, filename] = ready.mock.calls.at(-1)!;
    expect(clip).toBeInstanceOf(Blob); expect(clip.size).toBe(14); expect(filename).toBe('reply.webm'); expect(stop).toHaveBeenCalled();
  });
  it('releases a microphone whose permission resolves after leaving the component', async () => {
    let resolve!: (value: typeof media) => void;
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(() => new Promise(done => { resolve = done as unknown as typeof resolve; }));
    const ready = vi.fn(); const { unmount } = render(<PilotRecording disabled={false} onReady={ready} />);
    fireEvent.click(screen.getByRole('button', { name: 'Record your reply' })); unmount();
    await act(async () => resolve(media));
    expect(stop).toHaveBeenCalledOnce(); expect(ready).not.toHaveBeenCalled(); expect(Recorder.instances).toHaveLength(0);
  });
  it('stops active recording and ignores late data after profile or component unmount', async () => {
    const ready = vi.fn(); const { unmount } = render(<PilotRecording disabled={false} onReady={ready} />);
    fireEvent.click(screen.getByRole('button', { name: 'Record your reply' })); await screen.findByRole('button', { name: 'Stop recording' });
    ready.mockClear(); unmount();
    expect(Recorder.instances[0].state).toBe('inactive'); expect(stop).toHaveBeenCalled(); expect(ready).not.toHaveBeenCalled();
  });
  it('shows a recoverable message when microphone permission is denied', async () => {
    vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValue(new Error('permission'));
    render(<PilotRecording disabled={false} onReady={vi.fn()} />); fireEvent.click(screen.getByRole('button', { name: 'Record your reply' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Allow microphone access');
    expect(screen.getByRole('button', { name: 'Record your reply' }).hasAttribute('disabled')).toBe(false);
  });
  it('keeps skill navigation locked until an unsent preview is submitted or discarded', async () => {
    const lock = vi.fn(); const ready = vi.fn();
    render(<PilotRecording disabled={false} onReady={ready} onLockChange={lock} />);
    expect(lock).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByRole('button', { name: 'Record your reply' }));
    await screen.findByRole('button', { name: 'Stop recording' });
    expect(lock).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard recording' }));
    await vi.waitFor(() => expect(lock).toHaveBeenLastCalledWith(false));
    expect(ready).toHaveBeenLastCalledWith(undefined);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:pilot-recording');
    expect(screen.queryByLabelText('Listen to your recording')).toBeNull();
    expect(screen.getByText('Submit your reply to save the recording.')).toBeTruthy();
  });

});
