import { useLayoutEffect, useRef, useState } from 'preact/hooks';
import type { Language } from './review-types';
import type { ProgressionData, ProgressionState } from './Progression';
import '../../static/css/skill_progress.css';

export type SkillRating={id:string;label:string;label_ru:string;status:string;rating:number|null;stage:number;stage_start:number;stage_end:number;progress:number;observations:number;last_updated:number|null;points_to_next:number};
export type SkillProgressData={status:string;policy_version?:string;active_skill?:string;skills?:SkillRating[]};
export function activeRating(data?:ProgressionData):SkillRating|undefined {
  const item=data?.skill.skills?.find(skill=>skill.id===data.skill.active_skill);
  return item && Number.isFinite(item.rating) && item.observations>0 ? item : undefined;
}
export const boundedProgress=(value?:number)=>Number.isFinite(value) ? Math.min(1,Math.max(0,value!)) : 0;

export function SkillProgress({progression,language='en',introductory=false}:{progression:ProgressionState;language?:Language;introductory?:boolean;profileHref?:string}) {
  const t=(en:string,ru:string)=>language==='ru' ? ru : en;
  const previous=useRef<{key:string;progress:number}>();
  const [moving,setMoving]=useState(false);
  const data=introductory ? undefined : progression.data;
  const course=data?.course;
  const chapter=course?.chapters.find(item=>item.id===course.current_chapter_id) ?? (course?.completed ? course.chapters.at(-1) : undefined);
  // A visual-only preview: the actual progression data stays untouched.
  const preview=new URLSearchParams(window.location.search).get('progress-preview')==='50';
  const progress=preview ? .5 : boundedProgress(chapter?.progress);
  const unavailable=!data && !introductory && !!progression.error;
  const chapterLabel=chapter ? t(`Chapter ${chapter.number} of ${course!.chapters.length} · ${chapter.title}`,`Глава ${chapter.number} из ${course!.chapters.length} · ${chapter.title_ru}`) : '';
  const label=preview ? t('50% layout preview; saved progress unchanged','Предпросмотр 50%; сохранённый прогресс не изменён') : chapter ? `${chapterLabel} · ${chapter.status==='passed' ? t('Milestone passed','Этап пройден') : t(`${Math.round(progress*100)}% prepared for checkpoint`,`${Math.round(progress*100)}% подготовки к проверке`)}` : unavailable ? t('Chapter progress unavailable','Прогресс главы недоступен') : !data && !introductory ? t('Loading chapter progress…','Загружаем прогресс главы…') : '';
  const linkLabel=[label,t('Open your journey','Открыть путешествие')].filter(Boolean).join('. ');
  useLayoutEffect(()=>{
    const key=data && course && chapter ? `${data.profile_id}:${course.release_id ?? course.version}:${chapter.id}` : '';
    const last=previous.current;
    const shouldMove=!!(!preview && chapter && last && last.key===key && progress>last.progress);
    previous.current=chapter ? {key,progress} : undefined;
    setMoving(shouldMove);
    if (shouldMove) {const timer=setTimeout(()=>setMoving(false),800);return ()=>clearTimeout(timer);}
  },[preview,data?.profile_id,course?.version,course?.release_id,chapter?.id,progress]);
  return <div class={`skill-rail${moving ? ' is-moving' : ''}${!data && !preview && !introductory ? ' is-unavailable' : ''}`} style={{'--skill-progress':progress}}>
    <a class="skill-rail-link" href="/#journey" aria-label={linkLabel}>
      <span class="skill-rail-track" aria-hidden="true"><span class="skill-rail-fill" /></span>
      {(data || preview || introductory) && <span class="skill-rail-runner" aria-hidden="true"><img src="/static/images/barsik-progress-run-v1.webp" alt="" width="56" height="40" /></span>}
      {(chapter || preview) && <span class="sr-only" role="progressbar" aria-label={t('Checkpoint preparation','Подготовка к проверке')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress*100)} aria-valuetext={preview ? t('50% layout preview; saved progress unchanged','Предпросмотр 50%; сохранённый прогресс не изменён') : label} />}
    </a>
  </div>;
}
