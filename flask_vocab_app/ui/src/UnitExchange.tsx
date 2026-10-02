import {useEffect, useRef, useState} from 'preact/hooks';
import {api, ApiError, upload} from './learning-api';
import {appUrl} from './app-url';
import {PilotRecording} from './PilotRecording';
import {Sheet} from './components';
import type {Language} from './review-types';

type Exchange = {
  id:string; profile_id:string; revision:number; title:string; title_ru?:string; prompt:string;
  current_turn:{id:string;audio_url?:string;audio_available:boolean;listened:boolean;playbacks?:number;plays_remaining?:number}|null;
  turns:{id:string;saved:boolean;recording_url?:string}[];
  work_state:string; availability:string; condition:'unverified'; support?:string[]; closing?:string; closing_audio_url?:string;
  scene?:{places?:{id:string;ru:string;en:string}[];instruction?:string;instruction_ru?:string};
  feedback?:{summary?:string;feedback?:string;next_step?:string;corrections?:{original:string;replacement:string;explanation:string}[];criterion_report?:{judgements:{criterion_id:string;feedback:string}[]}}|null;
  study_actions?:{kind:'phrasebook'|'flashcards';href:string;label:string;label_ru:string}[];
  origin:{href:string;title:string};
};
type Command = {kind:'listened'|'recording'|'review';url:string;body:Record<string,unknown>|FormData};

/** The authored exchange is a bounded task in the ordinary Speaking workspace. */
export function UnitExchange({id,profileId,language='en'}:{id:string;profileId?:string;language?:Language}) {
  const t=(en:string,ru:string)=>language==='ru'?ru:en;
  const [saved,setSaved]=useState<Exchange>();
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [blocked,setBlocked]=useState(false);
  const [clip,setClip]=useState<{blob:Blob;filename:string}>();
  const [locked,setLocked]=useState(false);
  const [audioFailed,setAudioFailed]=useState(false);
  const [reload,setReload]=useState(0);
  const controller=useRef<AbortController>();
  const epoch=useRef(0);
  const inFlight=useRef(false);
  const pending=useRef<Command>();
  const player=useRef<HTMLAudioElement>(null);
  const closingPlayer=useRef<HTMLAudioElement>(null);
  const heading=useRef<HTMLHeadingElement>(null);
  const unsent=useRef(false);unsent.current=locked;
  const path=`/api/v1/unit-exchanges/${encodeURIComponent(id)}`;

  useEffect(()=>{
    const request=new AbortController();controller.current=request;const version=++epoch.current;
    setError('');setBlocked(false);setBusy(false);inFlight.current=false;pending.current=undefined;
    setSaved(undefined);setClip(undefined);setLocked(false);unsent.current=false;
    void api<Exchange>(path,undefined,request.signal).then(value=>{
      if(request.signal.aborted||version!==epoch.current)return;
      if(profileId&&value.profile_id!==profileId)throw new Error(t('Open the profile that started this task.','Откройте профиль, в котором начато задание.'));
      setSaved(value);
    }).catch(reason=>{if(!request.signal.aborted)setError(reason instanceof Error?reason.message:t('The task could not open.','Не удалось открыть задание.'));});
    return()=>{request.abort();player.current?.pause();closingPlayer.current?.pause();};
  },[id,profileId,reload]);
  useEffect(()=>{setAudioFailed(false);heading.current?.focus({preventScroll:true});},[saved?.current_turn?.id]);
  useEffect(()=>{
    const turn=saved?.current_turn;
    if(turn?.audio_available&&!turn.listened&&(turn.plays_remaining??2)>0) void player.current?.play()?.catch(()=>{});
  },[saved?.current_turn?.id,saved?.current_turn?.audio_url]);
  useEffect(()=>{if(saved?.closing_audio_url) void closingPlayer.current?.play()?.catch(()=>{});},[saved?.closing_audio_url]);
  useEffect(()=>{
    let previous=window.location.href;
    const leave=t('This recording has not been sent. Leave and discard it?','Запись ещё не отправлена. Выйти и удалить её?');
    const unload=(event:BeforeUnloadEvent)=>{if(unsent.current){event.preventDefault();event.returnValue='';}};
    const click=(event:MouseEvent)=>{
      const link=event.target instanceof Element?event.target.closest<HTMLAnchorElement>('a[href]'):null;
      if(!link||link.target||event.button||event.metaKey||event.ctrlKey||!unsent.current)return;
      if(!window.confirm(leave)){event.preventDefault();event.stopImmediatePropagation();}else{unsent.current=false;player.current?.pause();}
    };
    const hash=(event:HashChangeEvent)=>{
      if(unsent.current&&!window.confirm(leave)){event.stopImmediatePropagation();history.replaceState(history.state,'',previous);return;}
      unsent.current=false;previous=window.location.href;
    };
    window.addEventListener('beforeunload',unload);window.addEventListener('hashchange',hash,true);document.addEventListener('click',click,true);
    return()=>{window.removeEventListener('beforeunload',unload);window.removeEventListener('hashchange',hash,true);document.removeEventListener('click',click,true);};
  },[language]);

  async function command(value:Command) {
    if(inFlight.current||blocked)return;
    pending.current??=value;const action=pending.current;const version=epoch.current;
    inFlight.current=true;setBusy(true);setError('');
    try {
      const result=action.body instanceof FormData?await upload<Exchange>(action.url,action.body,controller.current?.signal):await api<Exchange>(action.url,action.body,controller.current?.signal);
      if(version!==epoch.current||controller.current?.signal.aborted)return;
      if(profileId&&result.profile_id!==profileId)throw new ApiError(t('Your profile changed.','Профиль изменился.'),'profile_changed');
      pending.current=undefined;
      if(action.kind==='recording'){unsent.current=false;setLocked(false);setClip(undefined);}
      setSaved(result);
    } catch(reason) {
      if(version!==epoch.current||controller.current?.signal.aborted)return;
      if(reason instanceof ApiError&&['profile_changed','account_changed','locked','access_required','csrf_failed','stale_revision'].includes(reason.code)){setBlocked(true);pending.current=undefined;}
      setError(reason instanceof Error?reason.message:t('The save could not be confirmed. Your recording is still here.','Сохранение не подтверждено. Запись осталась на странице.'));
    } finally {if(version===epoch.current){inFlight.current=false;setBusy(false);}}
  }
  function listened() {
    const turn=saved?.current_turn;
    if(!saved||!turn||(turn.plays_remaining??(turn.listened?1:2))<=0||!turn.audio_available||unsent.current||busy||pending.current)return;
    void command({kind:'listened',url:`${path}/turns/${encodeURIComponent(turn.id)}/listened`,body:{submission_id:crypto.randomUUID(),expected_revision:saved.revision}});
  }
  function send() {
    const turn=saved?.current_turn;if(!saved||!turn?.listened||!clip)return;
    const body=new FormData();body.set('audio',clip.blob,clip.filename);body.set('submission_id',crypto.randomUUID());body.set('expected_revision',String(saved.revision));
    void command({kind:'recording',url:`${path}/turns/${encodeURIComponent(turn.id)}/recording`,body});
  }
  function reloadSaved() {
    if(unsent.current&&!window.confirm(t('Reload the saved task and discard this unsent recording?','Загрузить сохранённое задание и удалить неотправленную запись?')))return;
    setReload(value=>value+1);
  }
  function recordingLock(value:boolean) {
    unsent.current=value;
    if(value) player.current?.pause();
    setLocked(value);
  }
  const turn=saved?.current_turn;
  const allSaved=!!saved&&!turn&&saved.turns.length===2&&saved.turns.every(item=>item.saved);
  const finished=saved?.work_state==='reviewed';
  const sceneInstruction=language==='ru'?saved?.scene?.instruction_ru??saved?.scene?.instruction:saved?.scene?.instruction;
  return <section class="page practice-page unit-exchange">
    <div class="lesson-head"><a class="text-link" href={appUrl(saved?.origin.href??'/#speaking')}>{saved?.origin.title??t('Speaking','Говорение')}</a><span class="quiet">{busy?t('Saving…','Сохраняем…'):t('Speaking','Говорение')}</span></div>
    <h1 ref={heading} tabIndex={-1}>{saved?(language==='ru'?saved.title_ru??saved.title:saved.title):t('Opening your speaking task…','Открываем разговорное задание…')}</h1>
    {saved&&<Sheet>
      <p>{saved.prompt}</p>
      {sceneInstruction&&<p class="conversation-correction"><strong>{t('Your situation: ','Ваша ситуация: ')}</strong>{sceneInstruction}</p>}
      {!!saved.scene?.places?.length&&<p class="quiet"><span>{t('Places: ','Места: ')}</span><span lang="ru">{saved.scene.places.map(place=>place.ru).join(' · ')}</span></p>}
      {turn&&<>
        {turn.audio_url&&(turn.plays_remaining??(turn.listened?1:2))>0&&<audio key={turn.id} ref={player} controls={!locked&&!busy&&!pending.current} preload="none" src={appUrl(turn.audio_url)} aria-label={t('Listen to Nina','Послушать Нину')} onPlay={()=>{if(unsent.current||busy||pending.current)player.current?.pause();}} onEnded={listened} onError={()=>setAudioFailed(true)}/>}
        {turn.plays_remaining===0&&<p class="quiet">{t('You have listened twice. Record your reply when you are ready.','Вы прослушали вопрос дважды. Запишите ответ, когда будете готовы.')}</p>}
        {(!turn.audio_available||audioFailed)&&<p role="alert">{t('The recording is unavailable. Try again or return to the lesson.','Аудио недоступно. Повторите попытку или вернитесь к уроку.')} {turn.audio_url&&<button class="text-link" onClick={()=>{setAudioFailed(false);player.current?.load();}}>{t('Retry audio','Повторить аудио')}</button>}</p>}
        {!turn.listened&&<p class="quiet">{t('Listen to the question, then record your reply.','Послушайте вопрос, затем запишите ответ.')}</p>}
        <PilotRecording key={turn.id} language={language} limit={60} disabled={busy||blocked||!!pending.current||!turn.audio_available||!turn.listened} onLockChange={recordingLock} onReady={(blob,filename)=>setClip(blob?{blob,filename:filename??'reply.webm'}:undefined)}/>
        {clip&&<button class="cta" disabled={busy||blocked||!!pending.current} onClick={send}>{t('Send reply','Отправить ответ')}</button>}
      </>}
      {allSaved&&<>
        {saved.closing&&<p lang="ru"><strong>Нина:</strong> {saved.closing}</p>}
        {saved.closing_audio_url&&<audio ref={closingPlayer} controls preload="none" src={appUrl(saved.closing_audio_url)} aria-label={t('Nina’s reply','Ответ Нины')}/>}
        <p>{t('Both replies are saved.','Оба ответа сохранены.')}</p>
        {finished?<><h2>{t('Your speaking feedback','Отзыв о вашем ответе')}</h2>{saved.feedback?.summary&&<p>{saved.feedback.summary}</p>}{saved.feedback?.feedback&&<p>{saved.feedback.feedback}</p>}{saved.feedback?.corrections?.slice(0,1).map((correction,index)=><div class="conversation-correction" key={index}><span lang="ru">{correction.original}</span> → <strong lang="ru">{correction.replacement}</strong><p>{correction.explanation}</p></div>)}{saved.feedback?.next_step&&<p>{saved.feedback.next_step}</p>}{!!saved.feedback?.criterion_report?.judgements.length&&<details class="answer-history"><summary>{t('What this recording shows','Что показывает эта запись')}</summary>{saved.feedback.criterion_report.judgements.map(item=><p key={item.criterion_id}>{item.feedback}</p>)}</details>}{!!saved.study_actions?.length&&<p class="quiet">{saved.study_actions.map((action,index)=><span key={action.kind}>{index>0&&' · '}<a class="text-link" href={appUrl(action.href)}>{language==='ru'?action.label_ru:action.label}</a></span>)}</p>}<a class="cta" href={appUrl(saved.origin.href)}>{t('Continue lesson','Продолжить урок')} →</a></>
          :saved.work_state==='reviewing'?<p role="status">{t('Preparing feedback…','Готовим отзыв…')} <button class="text-link" onClick={()=>setReload(value=>value+1)}>{t('Refresh feedback','Обновить отзыв')}</button></p>
            :<><p>{saved.work_state==='review_unavailable'?t('Your replies are saved. Feedback is unavailable.','Ответы сохранены. Отзыв недоступен.'):t('Review your replies when you are ready.','Когда будете готовы, запросите проверку ответов.')}</p><button class="cta" disabled={busy||blocked||!!pending.current} onClick={()=>void command({kind:'review',url:`${path}/review`,body:{}})}>{saved.work_state==='review_unavailable'?t('Retry feedback','Повторить проверку'):t('Get feedback','Получить отзыв')}</button></>}
      </>}
      {saved.turns.some(item=>item.recording_url)&&<details class="answer-history"><summary>{t('Your saved replies','Ваши сохранённые ответы')}</summary>{saved.turns.filter(item=>item.recording_url).map((item,index)=><audio key={item.id} controls preload="none" src={appUrl(item.recording_url!)} aria-label={`${t('Saved reply','Сохранённый ответ')} ${index+1}`}/>)}</details>}
      <details class="answer-history"><summary>{t('About this practice','Об этой практике')}</summary><p>{t('This short exchange practises location and destination. The original recordings are saved.','Этот короткий разговор помогает описывать место и направление. Исходные записи сохраняются.')}</p>{!!saved.support?.length&&<p>{t('With help: an example or earlier feedback was available for this task.','С помощью: для задания уже был доступен пример или предыдущий отзыв.')}</p>}<p>{t('Independent conditions were not checked.','Самостоятельность выполнения не проверялась.')}</p></details>
    </Sheet>}
    {error&&<div class="error-note" role="alert"><p>{error}</p>{pending.current&&!blocked&&<button class="text-link" disabled={busy} onClick={()=>void command(pending.current!)}>{t('Try saving again','Повторить сохранение')}</button>}{(!saved||blocked)&&<button class="text-link" onClick={reloadSaved}>{t('Reload saved task','Загрузить сохранённое задание')}</button>}</div>}
  </section>;
}
