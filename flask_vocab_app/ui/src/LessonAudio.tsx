import {useLayoutEffect,useRef,useState} from 'preact/hooks';
import {appUrl} from './app-url';
import './styles/lesson-audio.css';

let activePlayback:{player:HTMLAudioElement;stop:()=>void}|undefined;

/** Recorded pronunciation only; replay and slower playback never submit an answer. */
export function LessonAudio({src,label='the recording',compact=false,inline=false,autoPlay=false}:{src?:string;label?:string;compact?:boolean;inline?:boolean;autoPlay?:boolean}) {
  const audio=useRef<HTMLAudioElement>(null);
  const generation=useRef(0);
  const rate=useRef(1);
  const [playing,setPlaying]=useState(false);
  const [failed,setFailed]=useState(false);
  const [blocked,setBlocked]=useState(false);
  useLayoutEffect(()=>{
    const player=audio.current;generation.current++;setPlaying(false);setFailed(false);setBlocked(false);
    if(autoPlay && src)void replay(1,true);
    return()=>{
      generation.current++;
      const ownsPlayback=activePlayback?.player===player;
      if(ownsPlayback)activePlayback=undefined;
      if(player && (ownsPlayback || !player.paused))player.pause();
    };
  },[src,autoPlay]);
  if(!src)return null;
  async function replay(speed:number,automatic=false) {
    const player=audio.current;if(!player)return;
    if(activePlayback && activePlayback.player!==player)activePlayback.stop();
    activePlayback={player,stop:pause};
    const current=++generation.current;rate.current=speed;setFailed(false);setBlocked(false);
    try {
      if(failed && !automatic)player.load();
      player.currentTime=0;player.playbackRate=speed;player.preservesPitch=true;
      await player.play();
      if(current===generation.current)setPlaying(true);
      // A pending play can finish after leaving the question or starting another clip.
      // Do not stop a newer replay that still owns this same element.
      else if(activePlayback?.player!==player)player.pause();
    } catch(cause) {
      if(current!==generation.current)return;
      setPlaying(false);if(activePlayback?.player===player)activePlayback=undefined;
      if(typeof cause==='object' && cause!==null && 'name' in cause && cause.name==='NotAllowedError')setBlocked(true);
      else setFailed(true);
    }
  }
  function pause() {generation.current++;audio.current?.pause();setPlaying(false);if(activePlayback?.player===audio.current)activePlayback=undefined;}
  function finished() {generation.current++;setPlaying(false);if(activePlayback?.player===audio.current)activePlayback=undefined;}
  return <div class={`lesson-audio${compact?' is-compact':''}${inline?' is-inline':''}`}>
    <audio ref={audio} key={src} src={appUrl(src)} preload="none" onPause={event=>{if(event.currentTarget===audio.current)setPlaying(false);}} onEnded={event=>{if(event.currentTarget===audio.current)finished();}} onError={event=>{if(event.currentTarget===audio.current){finished();setBlocked(false);setFailed(true);}}}/>
    <div class="lesson-audio-controls" role="group" aria-label={`Audio for ${label}`}>
      <button type="button" class="lesson-audio-button" onClick={()=>playing?pause():void replay(1)} title={`${playing?'Pause':'Listen to'} ${label}`} aria-label={`${playing?'Pause':'Listen to'} ${label}`}><span aria-hidden="true">{playing?'Ⅱ':'▶'}</span>{!compact && <span>{playing?'Pause':'Listen'}</span>}</button>
      {!compact && <button type="button" class="lesson-audio-button" onClick={()=>void replay(.75)} title="Slow replay" aria-label={`Slow replay of ${label}`}>{inline ? '0.75×' : 'Slow replay'}</button>}
    </div>
    {blocked && <p class="lesson-audio-error" role="status">Press Listen to hear the recording.</p>}
    {failed && <p class="lesson-audio-error" role="alert">The recording couldn’t play. <button type="button" class="text-link" onClick={()=>void replay(rate.current)}>Retry audio</button></p>}
  </div>;
}
