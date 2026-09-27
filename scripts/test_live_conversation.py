#!/usr/bin/env python3
"""Opt-in, paid WebRTC smoke test using audio files instead of a real microphone.

Optional test dependencies: aiortc (not required by the application).
Sends real-time paced PCM, receives real audio, and exercises the app's ordinary
signalling, sideband recording, background MAI notes and graceful close routes.
Synthetic speech is a transport fixture, never evidence of human ASR accuracy.
Use --wait-for-natural-end 45 --require-natural-end to verify that the agent
ends after the supplied conversation, without a manual finish masking failure.
"""
import argparse
import asyncio
from array import array
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import time
import uuid
import wave

import requests


async def run(args):
    from aiortc import AudioStreamTrack, RTCPeerConnection, RTCSessionDescription
    from av import AudioFrame, AudioResampler
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    # Decode before starting the real-time clock. Running ffmpeg inside feed()
    # blocks the event loop and can make short fixtures miss their audio slots.
    fixtures={}
    for path in args.audio:
        decoded=await asyncio.to_thread(subprocess.run,
            ['ffmpeg','-nostdin','-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','48000','pipe:1'],
            capture_output=True,check=True,timeout=30)
        fixtures[str(path)]=decoded.stdout
    http=requests.Session()
    response=http.get(args.url+'/api/v1/household',timeout=10);response.raise_for_status()
    http.headers['X-CSRF-Token']=response.json()['csrf_token']
    def post(path,body=None):
        response=http.post(args.url+'/api/v1/live-conversations'+path,json=body or {},timeout=55)
        if not response.ok: raise RuntimeError(f'App returned HTTP {response.status_code}: '+response.json().get('error',{}).get('message',''))
        return response.json()
    body={'submission_id':'webrtc-smoke-'+uuid.uuid4().hex,'language':'en','scenario_id':args.scenario}
    if args.seed:body['scenario_seed']=args.seed
    session=await asyncio.to_thread(post,'',body)
    sid=session['id'];print('Test session',sid,flush=True)
    opening=(session.get('scenario') or {}).get('opening')
    if not isinstance(opening,str) or not opening.strip():
        raise RuntimeError('The saved scenario has no opening; refusing to substitute a different scenario.')
    def read():
        response=http.get(args.url+'/api/v1/live-conversations/'+sid,timeout=10)
        response.raise_for_status()
        return response.json()
    started=time.monotonic();events=[];samples_received=0;audible_frames=0
    natural_close_observed=False;natural_wait_timed_out=False;cleanup_requested=False;failure=None
    ready=asyncio.Event();closed=asyncio.Event();stop=asyncio.Event();first_reply=asyncio.Event();tasks=[]
    heard=wave.open(str(output/'agent.wav'),'wb')
    heard.setnchannels(1);heard.setsampwidth(2);heard.setframerate(24000)
    class FixtureTrack(AudioStreamTrack):
        def __init__(self):
            super().__init__();self.pending=bytearray();self.samples=0;self.clock=None
        async def recv(self):
            if self.clock is None:self.clock=time.monotonic()
            delay=self.clock+self.samples/48000-time.monotonic()
            if delay>0:await asyncio.sleep(delay)
            data=bytes(self.pending[:1920]);del self.pending[:1920]
            frame=AudioFrame(format='s16',layout='mono',samples=960)
            frame.planes[0].update(data.ljust(1920,b'\0'))
            frame.sample_rate=48000;frame.pts=self.samples;frame.time_base=Fraction(1,48000);self.samples+=960
            return frame
        def feed(self,path):
            data=fixtures[str(path)]
            self.pending.extend(data)
            return len(data)/96000
    track=FixtureTrack();peer=RTCPeerConnection();peer.addTrack(track);channel=peer.createDataChannel('oai-events')
    @channel.on('message')
    def message(raw):
        event=json.loads(raw);event['test_received_ms']=round((time.monotonic()-started)*1000);events.append(event)
        if event['type']=='session.started':
            ready.set();channel.send(json.dumps({'type':'session.instructions.append','delegation_id':None,'event_id':'smoke-greeting','content':
                'Весь разговор веди только по-русски, даже если собеседник говорит по-английски. '
                'Произнеси приветствие сохранённого сценария: '+opening+' Затем слушай. Сохраняй роль и все инструкции выбранной ситуации.'},ensure_ascii=False))
        if event['type']=='session.closed':closed.set()
        if event['type']=='session.output_transcript.delta':first_reply.set()
        if 'transcript.delta' in event['type']:print(event['type'],event.get('delta'),flush=True)
        if event['type']=='error':print('Provider event error',event.get('error',{}).get('code'),flush=True)
    @peer.on('track')
    def incoming(remote):
        async def receive():
            nonlocal samples_received,audible_frames
            resampler=AudioResampler(format='s16',layout='mono',rate=24000)
            try:
                while not stop.is_set():
                    frame=await remote.recv();samples_received+=frame.samples
                    values=array('h',bytes(frame.planes[0]))
                    if values and max(abs(v) for v in values)>100:audible_frames+=1
                    for mono in resampler.resample(frame):
                        heard.writeframes(bytes(mono.planes[0])[:mono.samples*2])
            except Exception:pass
        tasks.append(asyncio.create_task(receive()))
    async def heartbeat():
        while not stop.is_set():
            await asyncio.to_thread(post,'/'+sid+'/heartbeat')
            await asyncio.sleep(8)
    tasks.append(asyncio.create_task(heartbeat()))
    try:
        await peer.setLocalDescription(await peer.createOffer())
        answer=await asyncio.to_thread(post,'/'+sid+'/connect',{'sdp':peer.localDescription.sdp})
        await peer.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'],type='answer'))
        await asyncio.wait_for(ready.wait(),25)
        for index,path in enumerate(args.audio):
            if closed.is_set():
                break
            if index==0 and args.interrupt:
                await asyncio.wait_for(first_reply.wait(),15)
                await asyncio.sleep(.25)
            else:
                await asyncio.sleep(5 if index==0 else 6)
            if closed.is_set():
                break
            duration=track.feed(path)
            events.append({'type':'test.fixture','filename':Path(path).name,'duration_seconds':duration,'test_received_ms':round((time.monotonic()-started)*1000)})
            await asyncio.sleep(duration)
        if args.wait_for_natural_end:
            try:
                await asyncio.wait_for(closed.wait(),args.wait_for_natural_end)
                natural_close_observed=True
            except asyncio.TimeoutError:
                natural_wait_timed_out=True
                print('Natural-ending wait timed out; closing the test session for cleanup.',flush=True)
        else:
            await asyncio.sleep(8)
            natural_close_observed=closed.is_set()
            if not closed.is_set():
                cleanup_requested=True
                await asyncio.to_thread(post,'/'+sid+'/finish')
                await asyncio.wait_for(closed.wait(),16)
    except Exception as error:
        failure=f'{type(error).__name__}: {error}'
    finally:
        try:
            if not closed.is_set():
                cleanup_requested=True
                await asyncio.to_thread(post,'/'+sid+'/finish')
                # Keep the data channel and audio alive while final events drain.
                try:await asyncio.wait_for(closed.wait(),16)
                except asyncio.TimeoutError:pass
        except Exception as error:
            failure=failure or f'Cleanup {type(error).__name__}: {error}'
        finally:
            stop.set();await peer.close()
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            heard.close()
            (output/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
    result=await asyncio.to_thread(read)
    review_deadline=time.monotonic()+80
    while time.monotonic()<review_deadline:
        review=result.get('review') or {}
        notes_done=all(r['state'] in ('ready','failed','silent') for r in result['recordings'])
        review_done=not review or review.get('state') in ('ready','failed')
        if result['recordings'] and notes_done and review_done:break
        await asyncio.sleep(min(2,max(0,review_deadline-time.monotonic())))
        if time.monotonic()>=review_deadline:break
        result=await asyncio.to_thread(read)
    (output/'session.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    metrics={'session_id':sid,'webrtc_state':peer.connectionState,'received_samples':samples_received,'audible_frames':audible_frames,
             'gracefully_closed':closed.is_set(),'recordings':len(result['recordings']),'notes_states':[r['state'] for r in result['recordings']],
             'scenario_id':session.get('scenario_id'),'scenario_seed':(session.get('scenario') or {}).get('seed'),
             'end_reason':result.get('end_reason'),'final_state':result.get('state'),
             'review_state':(result.get('review') or {}).get('state','not_requested'),
             'review_error':(result.get('review') or {}).get('error'),
             'natural_close_observed':natural_close_observed,'natural_wait_timed_out':natural_wait_timed_out,
             'cleanup_requested':cleanup_requested,'failure':failure,
             'source':'audio file fixtures, no human microphone','asr_accuracy_verified':False}
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics),flush=True)
    if failure:raise RuntimeError(failure)
    if not audible_frames or not closed.is_set() or not result['recordings']:raise RuntimeError('The full audio path did not pass.')
    if args.require_natural_end and (not natural_close_observed or cleanup_requested
            or result.get('end_reason') not in ('task_complete','learner_finished')):
        raise RuntimeError('The agent did not end naturally. Cleanup is not a natural-ending pass; inspect metrics.json and events.json.')
    if args.russian_only:
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'flask_vocab_app'))
        from services.conversation_policy import russian_speech
        spoken=''.join(e.get('delta','') for e in events if e['type']=='session.output_transcript.delta')
        if not russian_speech(spoken):raise RuntimeError('Agent captions contained non-Russian speech; inspect events.json and agent.wav.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Authorize this paid provider test')
    parser.add_argument('--url',default='http://127.0.0.1:5052')
    parser.add_argument('--scenario',default='cafe',help='Speaking scenario id from the app catalogue')
    parser.add_argument('--seed',help='Optional exact situation seed within that scenario')
    parser.add_argument('--audio',action='append',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--interrupt',action='store_true',help='Start the first fixture during the greeting')
    parser.add_argument('--russian-only',action='store_true',help='Fail if agent captions contain non-Russian letters; listen to agent.wav separately')
    parser.add_argument('--wait-for-natural-end',type=float,default=0,metavar='SECONDS',
                        help='Wait up to 120 seconds after the fixtures for agent closure before cleanup (default: manual close)')
    parser.add_argument('--require-natural-end',action='store_true',
                        help='Fail unless the server ends for task_complete or learner_finished before any cleanup request')
    args=parser.parse_args()
    if not args.run:parser.error('Use --run to make paid provider calls.')
    if not 0<=args.wait_for_natural_end<=120:parser.error('--wait-for-natural-end must be between 0 and 120 seconds.')
    if args.require_natural_end and not args.wait_for_natural_end:parser.error('--require-natural-end needs --wait-for-natural-end SECONDS.')
    asyncio.run(run(args))
