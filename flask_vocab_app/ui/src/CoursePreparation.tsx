import {useEffect,useRef,useState} from 'preact/hooks';
import {api,ApiError} from './learning-api';
import {courseHref} from './course-routes';
import type {Language} from './review-types';
import type {ProgressionState} from './Progression';
import './styles/course-journey.css';

export type TargetCoverage={required_count:number;prepared_count:number;ready:boolean;targets:{id:string;title:string;title_ru:string;topic_id:string;introduced:boolean;practised:boolean;demonstrated:boolean;prepared?:boolean;needs_practice:boolean;required:boolean}[]};
type PracticeItem={id:string;target_id:string;title:string;title_ru:string;stage:'learn'|'question'|'feedback';selected_choice?:string|null;teaching:{explanation:string;explanation_ru:string;example_ru:string;example_en:string};question:{prompt:string;prompt_ru:string;passage?:string;audio_url?:string;choices:{id:string;text:string}[]}|null;hint:{en:string;ru:string}|null;feedback:{correct:boolean;answer:string;explanation:string;explanation_ru:string}|null;listened:boolean;transcript:string|null};
export type CoursePractice={release_id?:string;target_catalogue_version?:string;content_version?:string;id:string;profile_id:string;section_id:string;status:'active'|'completed';completed_count:number;total_count:number;current_item:PracticeItem|null;coverage:TargetCoverage};
export function CoursePreparation({practiceId,sectionId,releaseId,language='en',progression}:{releaseId?:string;practiceId?:string;sectionId?:string;language?:Language;progression:ProgressionState}) {
  const t=(en:string,ru:string)=>language==='ru'?ru:en;
  const selectedRelease=releaseId ?? (practiceId ? undefined : progression.data?.course?.release_id);
  const identity=`${progression.data?.profile_id ?? ''}:${selectedRelease ?? ''}:${practiceId ?? ''}:${sectionId ?? ''}`;
  const owner=useRef(identity);owner.current=identity;
  const [practice,setPractice]=useState<CoursePractice>();
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [revision,setRevision]=useState(0);
  const [choice,setChoice]=useState('');
  const [uncertainAnswer,setUncertainAnswer]=useState(false);
  const [audioError,setAudioError]=useState('');
  const recording=useRef<HTMLAudioElement>(null);
  const mediaOwner=useRef('');
  const mediaStage=useRef('');
  const playbackAttempt=useRef(0);
  const requestEpoch=useRef(0);
  const listeningPending=useRef(false);
  const inFlight=useRef(false);
  const command=useRef<{key:string;request_id:string}>();
  const failedAction=useRef<'learn'|'answer'|'next'|'hint'|'listened'|'transcript'>();
  const heading=useRef<HTMLHeadingElement>(null);
  const startRequest=useRef<{identity:string;request_id:string}>();
  useEffect(()=>{
    const abort=new AbortController();const epoch=++requestEpoch.current;owner.current=identity;setAudioError('');playbackAttempt.current++;failedAction.current=undefined;setPractice(undefined);setError('');setChoice('');setUncertainAnswer(false);listeningPending.current=false;setBusy(true);inFlight.current=false;command.current=undefined;
    if(startRequest.current?.identity!==identity) startRequest.current={identity,request_id:crypto.randomUUID()};
    const promise=practiceId ? api<CoursePractice>(`/api/v1/course/practice/${encodeURIComponent(practiceId)}`,undefined,abort.signal) : api<CoursePractice>(`/api/v1/course/chapters/${encodeURIComponent(sectionId ?? '')}/practice`,{release_id:selectedRelease,request_id:startRequest.current.request_id},abort.signal);
    void promise.then(value=>{
      if(abort.signal.aborted || owner.current!==identity || requestEpoch.current!==epoch)return;
      if(progression.data?.profile_id && value.profile_id!==progression.data.profile_id) throw new ApiError(t('The learner changed. Reload your practice.','Профиль изменился. Загрузите практику заново.'),'profile_changed');
      setPractice(value);setChoice(value.current_item?.selected_choice ?? '');if(!practiceId) window.location.replace(`#journey/practice/${encodeURIComponent(value.id)}`);
    }).catch(reason=>{if(!abort.signal.aborted && owner.current===identity && requestEpoch.current===epoch)setError(reason instanceof Error?reason.message:t('Practice could not open.','Не удалось открыть практику.'));}).finally(()=>{if(!abort.signal.aborted && owner.current===identity && requestEpoch.current===epoch)setBusy(false);});
    return()=>{abort.abort();if(requestEpoch.current===epoch)requestEpoch.current++;if(owner.current===identity)owner.current='';};
  },[identity,revision]);
  async function save(action:'learn'|'answer'|'next'|'hint'|'listened'|'transcript') {
    if(!practice?.current_item || inFlight.current)return;
    const actor=identity;const epoch=requestEpoch.current;failedAction.current=action;inFlight.current=true;setBusy(true);setError('');if(action==='listened')listeningPending.current=false;if(action==='answer')setUncertainAnswer(true);
    const key=`${practice.id}:${practice.current_item.id}:${action}:${action==='answer'?choice:''}`;
    if(command.current?.key!==key)command.current={key,request_id:crypto.randomUUID()};
    try {
      const value=await api<CoursePractice>(`/api/v1/course/practice/${encodeURIComponent(practice.id)}/${action}`,{item_id:practice.current_item.id,request_id:command.current.request_id,...(action==='answer'?{choice_id:choice}:{})});
      if(owner.current!==actor || requestEpoch.current!==epoch)return;
      if(value.profile_id!==practice.profile_id)throw new ApiError(t('The learner changed. Reload your practice.','Профиль изменился. Загрузите практику заново.'),'profile_changed');
      if(value.id!==practice.id || value.section_id!==practice.section_id || (['release_id','target_catalogue_version','content_version'] as const).some(field=>value[field]!==undefined && practice[field]!==undefined && value[field]!==practice[field]))throw new ApiError(t('The saved practice changed. Reload it to continue.','Сохранённая практика изменилась. Загрузите её заново.'),'practice_changed');
      // Receipts issued before release-scoped practice retain their original
      // payload. Keep only the identity already verified by the current GET.
      setPractice({...value,release_id:value.release_id ?? practice.release_id,target_catalogue_version:value.target_catalogue_version ?? practice.target_catalogue_version,content_version:value.content_version ?? practice.content_version});command.current=undefined;failedAction.current=undefined;if(action==='answer')setUncertainAnswer(false);
      if(action==='next'||action==='learn')setChoice('');else if(value.current_item?.selected_choice)setChoice(value.current_item.selected_choice);
      if(value.status==='completed')progression.refresh();
      if(action==='next'||action==='learn'||action==='answer') requestAnimationFrame(()=>heading.current?.focus({preventScroll:true}));
    }catch(reason){if(owner.current===actor && requestEpoch.current===epoch){if(reason instanceof ApiError && reason.code==='stale_practice'){setRevision(value=>value+1);return;}if(reason instanceof ApiError && ['profile_changed','practice_changed','locked','unauthorized'].includes(reason.code))setPractice(undefined);setError(action==='listened' ? t('We couldn’t save that you listened. You can retry saving without playing the recording again.','Не удалось сохранить прослушивание. Можно повторить сохранение, не включая запись заново.') : reason instanceof Error?reason.message:t('Your answer could not be saved.','Не удалось сохранить ответ.'));}}
    finally{if(owner.current===actor && requestEpoch.current===epoch){inFlight.current=false;setBusy(false);if(action==='answer'||action==='next')listeningPending.current=false;else if(action!=='listened' && listeningPending.current)void save('listened');}}
  }
  const item=practice?.current_item;
  const mediaKey=`${identity}:${item?.id ?? ''}:${item?.question?.audio_url ?? ''}`;
  mediaOwner.current=mediaKey;mediaStage.current=item?.stage ?? '';
  function isCurrentMedia() {return owner.current===identity && mediaOwner.current===mediaKey;}
  function retryAudio() {
    const player=recording.current;
    if(!player || !isCurrentMedia())return;
    const playback=++playbackAttempt.current;
    setAudioError('');
    try {
      player.load();
      void player.play().catch(()=>{if(isCurrentMedia() && playbackAttempt.current===playback)setAudioError(mediaKey);});
    } catch {if(isCurrentMedia() && playbackAttempt.current===playback)setAudioError(mediaKey);}
  }
  return <section class="page course-page course-preparation-player">
    <nav class="course-navigation"><a class="text-link" href={courseHref(practice?.release_id ?? selectedRelease,practice?.section_id ?? sectionId ?? 'home')}>← {t('Milestone practice','Практика этапа')}</a>{practice && <span>{practice.completed_count}/{practice.total_count}</span>}</nav>
    {error && <div role="alert" class="course-error"><p>{error}</p><button class="live-mute" disabled={busy} onClick={()=>practice && failedAction.current ? void save(failedAction.current) : setRevision(value=>value+1)}>{failedAction.current==='listened' ? t('Retry saving listening','Повторить сохранение прослушивания') : t('Try again','Попробовать ещё раз')}</button></div>}
    {!practice && !error && <p role="status">{t('Opening practice…','Открываем практику…')}</p>}
    {practice?.status==='completed' ? <><header class="course-heading"><h1 ref={heading} tabIndex={-1}>{t('Practice saved','Практика сохранена')}</h1><p>{t('Your answers help show what to practise next.','Ваши ответы помогут выбрать следующую практику.')}</p></header><a class="cta" href={courseHref(practice.release_id ?? selectedRelease,practice.section_id)}>{t('Continue the milestone','Продолжить этап')} →</a></> : item && <>
      <header class="course-heading"><p class="kicker">{item.stage==='learn' ? t('Learn','Разберём пример') : item.stage==='feedback'?t('Your answer','Ваш ответ'):t('Try it','Попробуйте')}</p><h1 ref={heading} tabIndex={-1}>{t(item.title,item.title_ru)}</h1></header>
      {item.stage==='learn' ? <article class="course-teaching-card"><p>{t(item.teaching.explanation,item.teaching.explanation_ru)}</p><p class="course-teaching-example" lang="ru">{item.teaching.example_ru}</p>{language==='en' && <p class="quiet">{item.teaching.example_en}</p>}<button class="cta" disabled={busy} onClick={()=>void save('learn')}>{t('Try it','Попробовать')} →</button></article> : item.question && <form onSubmit={event=>{event.preventDefault();void save('answer');}} class="course-preparation-question">
        {item.question.passage && <p class="course-teaching-example" lang="ru">{item.question.passage}</p>}
        {item.question.audio_url && <section class="course-listening"><audio key={mediaKey} ref={recording} controls preload="none" aria-label={t('Practice recording','Запись для практики')} src={item.question.audio_url} onError={()=>{if(isCurrentMedia())setAudioError(mediaKey);}} onCanPlay={()=>{if(isCurrentMedia())setAudioError('');}} onEnded={()=>{if(isCurrentMedia() && mediaStage.current==='question' && !item.listened && item.stage==='question' && !uncertainAnswer){listeningPending.current=true;void save('listened');}}}/>{audioError===mediaKey && <div role="alert" class="course-error"><p>{t('The recording could not play. Try again, or read the transcript to keep practising.','Не удалось воспроизвести запись. Попробуйте ещё раз или откройте текст, чтобы продолжить практику.')}</p><button type="button" class="text-button" onClick={retryAudio}>{t('Retry audio','Повторить воспроизведение')}</button></div>}{item.transcript ? <p lang="ru">{item.transcript}</p> : <button type="button" class="text-button" disabled={busy||uncertainAnswer} onClick={()=>void save('transcript')}>{t('Show transcript','Показать текст записи')}</button>}</section>}
        <fieldset disabled={busy||uncertainAnswer||item.stage==='feedback'}><legend>{t(item.question.prompt,item.question.prompt_ru)}</legend><div class="course-choices">{item.question.choices.map(answer=><label class={`course-choice${choice===answer.id?' is-selected':''}`} key={answer.id}><input type="radio" name={`practice-${item.id}`} checked={choice===answer.id} value={answer.id} onChange={()=>setChoice(answer.id)}/><span lang="ru">{answer.text}</span></label>)}</div></fieldset>
        {item.stage==='feedback' && item.feedback ? <><div class="course-correction" role="status"><strong>{item.feedback.correct?t('That’s right.','Верно.'):t('Here’s the answer.','Вот правильный ответ.')}</strong>{!item.feedback.correct && <p lang="ru">{item.question.choices.find(answer=>answer.id===item.feedback!.answer)?.text ?? item.feedback.answer}</p>}<p>{t(item.feedback.explanation,item.feedback.explanation_ru)}</p></div><button type="button" class="cta" disabled={busy} onClick={()=>void save('next')}>{practice.completed_count+1>=practice.total_count?t('Finish practice','Завершить практику'):t('Next','Дальше')} →</button></> : <><div class="course-practice-hint">{item.hint ? <p class="course-support">{t(item.hint.en,item.hint.ru)}</p> : <button type="button" class="text-button" disabled={busy||uncertainAnswer} onClick={()=>void save('hint')}>{t('Show a hint','Подсказка')}</button>}</div><button class="cta" type="submit" disabled={busy||!choice||!!(item.question.audio_url&&!item.listened&&!item.transcript)}>{busy?t('Saving…','Сохраняем…'):uncertainAnswer?t('Retry saving answer','Повторить сохранение ответа'):t('Check answer','Проверить ответ')}</button></>}
      </form>}
    </>}
  </section>;
}
