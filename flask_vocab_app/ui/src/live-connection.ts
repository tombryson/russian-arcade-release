import { api, endOnLeave } from './learning-api';
import { russianTranscript } from './conversation-transcript';

export type Caption = { type: 'session.input_transcript.delta' | 'session.output_transcript.delta'; event_id?: string; delta: string; start_ms: number; end_ms: number };
export type VoiceState = 'connecting' | 'listening' | 'ending' | 'ended';
type Callbacks = { status: (state: VoiceState) => void; caption: (event: Caption) => void;
  error: (message: string) => void; playbackBlocked: () => void };

/** Owns one peer and microphone. No response is synthesized through the old game. */
export class LiveConnection {
  private peer?: RTCPeerConnection;
  private events?: RTCDataChannel;
  private microphone?: MediaStream;
  private speaker = new Audio();
  private disposed = false;
  private closing = false;
  private ready = false;
  private serverControlled = false;
  private closeTimer?: ReturnType<typeof setTimeout>;
  private startTimer?: ReturnType<typeof setTimeout>;
  private connectionTimer?: ReturnType<typeof setTimeout>;
  private abort = new AbortController();
  private seen = new Set<string>();
  constructor(private sid: string, private callbacks: Callbacks,
    private opening = 'Здравствуйте! Что будете пить: чай или кофе?') {
    this.speaker.autoplay = true;
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia || typeof RTCPeerConnection === 'undefined') {
      throw new Error('Speaking needs a browser with microphone support on HTTPS or localhost.');
    }
    this.callbacks.status('connecting');
    try {
      const microphone = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
      if (this.disposed) { microphone.getTracks().forEach(track => track.stop()); return; }
      this.microphone = microphone;
      const peer = new RTCPeerConnection();
      this.peer = peer;
      microphone.getTracks().forEach(track => peer.addTrack(track,microphone));
      peer.ontrack = event => {
        if (this.disposed) return;
        this.speaker.srcObject = event.streams[0] ?? new MediaStream([event.track]);
        void this.speaker.play().catch(() => { if (!this.disposed) this.callbacks.playbackBlocked(); });
      };
      peer.onconnectionstatechange = () => {
        clearTimeout(this.connectionTimer);
        if (this.disposed) return;
        if (peer.connectionState === 'failed') this.fail('The connection dropped. Your saved recordings are kept.');
        if (peer.connectionState === 'disconnected') {
          this.connectionTimer = setTimeout(() => this.fail('The connection dropped. Start a new conversation when you are ready.'),8000);
        }
      };
      const events = peer.createDataChannel('oai-events');
      this.events = events;
      events.onmessage = message => {
        if (this.disposed) return;
        try { this.receive(JSON.parse(message.data)); }
        catch { this.fail('The voice connection sent an unreadable update. Please start a new conversation.'); }
      };
      events.onclose = () => { if (!this.disposed) this.fail('The live connection ended. Your saved recordings are kept.'); };
      const offer = await peer.createOffer();
      if (this.disposed) return;
      await peer.setLocalDescription(offer);
      await this.gather(peer);
      if (this.disposed) return;
      const answer = await api<{sdp:string;server_controlled?:boolean}>(`/api/v1/live-conversations/${this.sid}/connect`,{sdp:peer.localDescription?.sdp},this.abort.signal);
      if (this.disposed) return;
      this.serverControlled = Boolean(answer.server_controlled);
      await peer.setRemoteDescription({type:'answer',sdp:answer.sdp});
      if (!this.ready && !this.disposed) this.startTimer = setTimeout(() => this.fail('The voice connection did not become ready. Please start a new conversation.'),20000);
    } catch (error) {
      if (!this.disposed) {
        this.dispose();
        throw error;
      }
    }
  }

  private gather(peer: RTCPeerConnection) {
    if (peer.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise<void>((resolve,reject) => {
      const cleanup = () => { clearTimeout(timer); peer.removeEventListener('icegatheringstatechange',check); this.abort.signal.removeEventListener('abort',cancel); };
      const check = () => { if (peer.iceGatheringState === 'complete') { cleanup(); resolve(); } };
      const cancel = () => { cleanup(); reject(new Error('Connection cancelled.')); };
      const timer = setTimeout(() => { cleanup(); reject(new Error('The browser could not establish an audio connection.')); },12000);
      peer.addEventListener('icegatheringstatechange',check);
      this.abort.signal.addEventListener('abort',cancel,{once:true});
      check();
    });
  }

  private receive(event: Record<string, unknown>) {
    if (typeof event.event_id === 'string') {
      if (this.seen.has(event.event_id)) return;
      this.seen.add(event.event_id);
    }
    if (event.type === 'session.started') {
      this.ready = true;
      clearTimeout(this.startTimer);
      this.callbacks.status('listening');
      if (!this.serverControlled) this.send({type:'session.instructions.append',event_id:crypto.randomUUID(),delegation_id:null,
        content:`Весь разговор веди только по-русски, даже если собеседник говорит по-английски. Поприветствуй его сейчас: «${this.opening}» Затем слушай. Сохраняй роль и все инструкции выбранной ситуации.`});
    } else if (event.type === 'session.closed') {
      this.callbacks.status('ended');
      this.dispose();
    } else if (event.type === 'session.input_transcript.delta' || event.type === 'session.output_transcript.delta') {
      if (typeof event.delta === 'string' && typeof event.start_ms === 'number' && typeof event.end_ms === 'number') this.callbacks.caption(event as Caption);
    } else if (event.type === 'error' && !this.closing) {
      this.callbacks.error('The voice connection reported a problem. You can end the call and start again.');
    }
  }

  private send(value: unknown) { if (this.events?.readyState === 'open') this.events.send(JSON.stringify(value)); }
  mute(value: boolean) { this.microphone?.getAudioTracks().forEach(track => { track.enabled = !value; }); }
  async play() { await this.speaker.play(); }

  end() {
    if (this.closing || this.disposed) return;
    this.closing = true;
    this.callbacks.status('ending');
    this.mute(true);
    this.speaker.pause();
    endOnLeave(`/api/v1/live-conversations/${this.sid}/finish`);
    if (this.ready && this.events?.readyState === 'open') {
      this.closeTimer = setTimeout(() => { this.callbacks.status('ended'); this.dispose(); },13000);
    } else {
      this.callbacks.status('ended');
      this.dispose();
    }
  }

  private fail(message: string) {
    if (this.disposed) return;
    this.callbacks.error(message);
    this.callbacks.status('ended');
    this.dispose();
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    endOnLeave(`/api/v1/live-conversations/${this.sid}/finish`);
    this.abort.abort();
    clearTimeout(this.closeTimer); clearTimeout(this.startTimer); clearTimeout(this.connectionTimer);
    this.microphone?.getTracks().forEach(track => track.stop());
    this.speaker.pause(); this.speaker.srcObject = null;
    this.events?.close(); this.peer?.close();
  }
}

/** Captions are revisable display groups, never completed turns or grading input. */
export function captionRows(fragments: Caption[]) {
  const rows: {id:string;role:'you'|'server';text:string;start:number;end:number}[] = [];
  const sorted = fragments.map((event,index) => ({event,index})).sort((a,b) => a.event.start_ms-b.event.start_ms || a.index-b.index);
  for (const {event,index} of sorted) {
    const role = event.type === 'session.input_transcript.delta' ? 'you' : 'server';
    const previous = rows.slice().reverse().find(row => row.role === role && event.start_ms-row.end <= 1800 && event.start_ms >= row.start
      && !rows.some(other => other.role !== role && other.start >= row.end && other.start < event.start_ms));
    if (previous) { previous.text += event.delta; previous.end = Math.max(previous.end,event.end_ms); }
    else rows.push({id:event.event_id ?? `${role}:${index}`,role,text:event.delta,start:event.start_ms,end:event.end_ms});
  }
  // Filter after grouping: dropping isolated English deltas could leave a
  // misleading Russian fragment of a mixed utterance. Do not alter raw events.
  return rows.filter(row => russianTranscript(row.text) !== null);
}
