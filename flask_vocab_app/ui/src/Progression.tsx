import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { api, ApiError } from './learning-api';
import type { Language } from './review-types';
import type { SkillProgressData } from './SkillProgress';
import type { CourseData } from './CourseJourney';
import {GameCatalogue} from './JourneyGames';
import './styles/progression.css';

export type PracticeLevel='A1'|'A2'|'B1'|'B2';
type World={id:string;title:string;title_ru:string;threshold:number;unlocked:boolean;visited:boolean;completed:boolean;scene_id:string};
export type ProgressionData={profile_id:string;balance:number;earned_total:number;legacy_balance:number;preferred_level:PracticeLevel;
  levels:{id:PracticeLevel;label:string;label_ru:string}[];policy:{activity_coins:number;activity_daily_cap:number;review_coins:number;review_daily_cap:number};
  recent_rewards:{id:string;amount:number;activity:string;title:string;created_at:number}[];
  journey:{worlds:World[];next_world:World|null};skill:SkillProgressData;course?:CourseData};
export type ProgressionState={data?:ProgressionData;error:string;loading:boolean;refresh:()=>void};
type Scene={world:World;scene:{title:string;title_ru:string;intro:string;intro_ru:string;prompt:string;prompt_ru:string;choices:{id:string;text:string;text_ru:string}[];
  feedback?:{correct:boolean;text:string;text_ru:string};completed:boolean};progression:ProgressionData;coins_earned?:number};

export function useProgression(enabled=true,profileKey?:string):ProgressionState {
  const [data,setData]=useState<ProgressionData>();
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const [revision,setRevision]=useState(0);
  const refresh=()=>setRevision(value=>value+1);
  useEffect(()=>{setData(undefined);setError('');},[enabled,profileKey]);
  useEffect(()=>{
    if (!enabled) { setData(undefined);return; }
    const abort=new AbortController();setLoading(true);
    void api<ProgressionData>('/api/v1/progression',undefined,abort.signal).then(value=>{
      if (abort.signal.aborted) return;
      if (profileKey && value.profile_id!==profileKey) throw new ApiError('The learner changed. Reload to view their progress.','profile_changed');
      if (!Number.isFinite(value.balance)) throw new Error('Your coin balance could not load.');
      setData(value);setError('');
    }).catch(e=>{
      if (abort.signal.aborted) return;
      if (e instanceof ApiError && ['locked','profile_changed','profile_required','adult_required','unauthorized'].includes(e.code)) setData(undefined);
      setError(e instanceof Error ? e.message : 'Your progress could not load.');
    })
      .finally(()=>{if (!abort.signal.aborted) setLoading(false);});
    return ()=>abort.abort();
  },[enabled,profileKey,revision]);
  useEffect(()=>{
    if (!enabled) return;
    let pending:ReturnType<typeof setTimeout>;
    const changed=()=>{clearTimeout(pending);pending=setTimeout(refresh,300);};
    const visible=()=>{if (document.visibilityState==='visible') changed();};
    window.addEventListener('lingo:progression',changed);
    document.addEventListener('visibilitychange',visible);
    // A speaking review can finish on the server without a browser write.
    // Refreshing only this small badge leaves the active call untouched.
    const timer=setInterval(()=>{if (document.visibilityState==='visible') refresh();},30000);
    return ()=>{clearTimeout(pending);clearInterval(timer);window.removeEventListener('lingo:progression',changed);document.removeEventListener('visibilitychange',visible);};
  },[enabled,profileKey]);
  return {data,error,loading,refresh};
}

export function ProgressionBadge({progression,language='en',introductory=false}:{progression:ProgressionState;language?:Language;introductory?:boolean}) {
  const label=language==='ru' ? 'Лингокоины' : 'Lingo coins';
  const balance=introductory ? 0 : progression.data?.balance;
  const previous=useRef<{profile:string;balance:number}>();
  const [gaining,setGaining]=useState(false);
  useLayoutEffect(()=>{
    const current=progression.data;
    const last=previous.current;
    const increased=!!(!introductory && current && last?.profile===current.profile_id && current.balance>last.balance);
    previous.current=!introductory && current ? {profile:current.profile_id,balance:current.balance} : undefined;
    setGaining(increased);
    if (increased) {const timer=setTimeout(()=>setGaining(false),900);return()=>clearTimeout(timer);}
  },[introductory,progression.data?.profile_id,balance]);
  return <a class={`progression-badge${gaining ? ' is-gaining' : ''}`} href="#shop" aria-label={`${label}: ${balance ?? (progression.error ? language==='ru' ? 'недоступно' : 'unavailable' : language==='ru' ? 'загружаем' : 'loading')}`} title={language==='ru' ? 'Магазин' : 'Shop'}>
    <span class="progression-coin" aria-hidden="true">Л</span><strong>{balance ?? '—'}</strong>
  </a>;
}

export function Journey({worldId,language='en',progression}:{worldId?:string;language?:Language;progression:ProgressionState}) {
  const t=(en:string,ru:string)=>language==='ru' ? ru : en;
  const [scene,setScene]=useState<Scene>();
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const [answering,setAnswering]=useState(false);
  const [retry,setRetry]=useState(0);
  const pending=useRef<{answer:string;submission_id:string}>();
  useEffect(()=>{
    if (!worldId) {setScene(undefined);setError('');return;}
    if (worldId==='post-office') {
      setScene(undefined);setError('');pending.current=undefined;
      window.location.replace('#first-steps');
      return;
    }
    const abort=new AbortController();setLoading(true);setScene(undefined);setError('');pending.current=undefined;
    void api<Scene>(`/api/v1/journey/${encodeURIComponent(worldId)}`,undefined,abort.signal).then(value=>{if (!abort.signal.aborted) setScene(value);})
      .catch(e=>{if (!abort.signal.aborted) setError(e.message);}).finally(()=>{if (!abort.signal.aborted) setLoading(false);});
    return ()=>abort.abort();
  },[worldId,retry]);
  async function answer(choice:string) {
    if (!worldId || worldId==='post-office' || answering) return;
    if (pending.current?.answer!==choice) pending.current={answer:choice,submission_id:crypto.randomUUID()};
    setAnswering(true);setError('');
    try {setScene(await api<Scene>(`/api/v1/journey/${encodeURIComponent(worldId)}/answer`,pending.current));pending.current=undefined;progression.refresh();}
    catch(e) {setError(e instanceof Error ? e.message : t('Your answer could not be saved. Try again.','Не удалось сохранить ответ. Попробуйте ещё раз.'));}
    finally {setAnswering(false);}
  }
  const data=scene?.progression ?? progression.data;
  if (worldId==='post-office') return <section class="page journey-page"><a class="cta" href="#first-steps">{t('First steps','Первые шаги')} →</a></section>;
  return <section class="page journey-page">
    <a class="text-link" href={worldId ? '#journey' : '#activities'}>← {worldId ? t('Your journey','Ваше путешествие') : t('Activities','Занятия')}</a>
    <p class="kicker">{t('One letter. A journey ahead.','Одно письмо. Путешествие впереди.')}</p>
    <h1>{worldId && scene ? t(scene.scene.title,scene.scene.title_ru) : t('Barsik’s journey','Путешествие Барсика')}</h1>
    {worldId ? <>
      {loading && <p role="status">{t('Opening this stop…','Открываем остановку…')}</p>}
      {scene && <section class="journey-scene"><p class="journey-scene-intro">{t(scene.scene.intro,scene.scene.intro_ru)}</p>
        <h2>{t(scene.scene.prompt,scene.scene.prompt_ru)}</h2>
        {scene.scene.completed ? <p class="journey-complete">✓ {t('This part of the journey is complete.','Эта часть путешествия завершена.')}</p> : <div class="journey-choices">{scene.scene.choices.map(choice=><button class="word" key={choice.id} disabled={answering} onClick={()=>void answer(choice.id)}>{t(choice.text,choice.text_ru)}</button>)}</div>}
        {scene.scene.feedback && <p class={`journey-feedback${scene.scene.feedback.correct ? ' correct' : ''}`} role="status">{t(scene.scene.feedback.text,scene.scene.feedback.text_ru)}</p>}
        {!!scene.coins_earned && <p class="quiet">+{scene.coins_earned} {t('Lingo coins earned','лингокоинов')}</p>}
        {scene.scene.completed && <a class="cta" href="#journey">{t('Continue the journey','Продолжить путешествие')} →</a>}
      </section>}
      {error && <div><p class="error-note" role="alert">{error}</p>{!scene && <button class="live-mute" onClick={()=>setRetry(value=>value+1)}>{t('Try again','Попробовать ещё раз')}</button>}</div>}
    </> : <>
      <p class="intro">{t('Help Barsik carry your letter from one place to the next. Practice earns the coins that open new stops along the way.','Помогите Барсику доставить ваше письмо. За практику вы получаете монеты, которые открывают новые остановки на пути.')}</p>
      {data ? <>
        <div class="journey-balance"><span class="progression-coin" aria-hidden="true">Л</span><div><strong>{data.balance}</strong><span>{t('Lingo coins','Лингокоины')}</span></div><p>{data.earned_total} {t('earned through practice','заработано за практику')}</p></div>
        {data.legacy_balance>0 && <p class="quiet">{t(`Your earlier ${data.legacy_balance.toLocaleString('en-AU')} coins are saved. This new journey counts coins earned from here.`,`Ваши прежние ${data.legacy_balance.toLocaleString('ru-RU')} монет сохранены. Для нового путешествия учитываются монеты, заработанные теперь.`)}</p>}
        <ol class="journey-worlds">{data.journey.worlds.map((world,index)=>{
          const remaining=Math.max(0,world.threshold-data.earned_total);
          return <li class={world.unlocked ? 'journey-world available' : 'journey-world upcoming'} key={world.id}>
            <span class="journey-stop-number" aria-hidden="true">{world.completed ? '✓' : index+1}</span><div><p class="kicker">{world.completed ? t('Visited','Пройдено') : world.unlocked ? t('Ready to explore','Можно отправляться') : t('Further along the way','Дальше по пути')}</p>
              <h2>{t(world.title,world.title_ru)}</h2>
              {world.unlocked ? <a class="text-link" href={world.id==='post-office' ? '#first-steps' : `#journey/${world.id}`}>{world.completed ? t('Visit again','Вернуться') : world.visited ? t('Continue','Продолжить') : t('Start','Начать')} →</a> : <p class="quiet">{remaining>0 ? t(`Earn ${remaining} more Lingo coins and finish the previous stop to reach here.`,`Заработайте ещё ${remaining} лингокоинов и завершите предыдущую остановку.`) : t('Finish the previous stop to continue here.','Завершите предыдущую остановку, чтобы продолжить.')}</p>}
            </div>
          </li>;
        })}</ol>
        <GameCatalogue key={data.profile_id} context="journey"/>
        <p class="quiet">{t('The main practice activities are always available. Games you buy from Barsik stay in Activities. Spending coins does not change your journey progress.','Основные занятия всегда доступны. Купленные у Барсика игры остаются в разделе занятий. Покупки не меняют прогресс путешествия.')}</p>
        <details class="journey-rules"><summary>{t('How coins work','Как начисляются монеты')}</summary><p>{t(`Complete a practice activity to earn ${data.policy.activity_coins} coins, up to ${data.policy.activity_daily_cap} a day. Review a flashcard to earn ${data.policy.review_coins} coin, up to ${data.policy.review_daily_cap} a day. Repeating the same activity or card that day does not earn extra coins.`,`За завершённое занятие вы получаете ${data.policy.activity_coins} монеты, до ${data.policy.activity_daily_cap} в день. За повторение карточки — ${data.policy.review_coins} монету, до ${data.policy.review_daily_cap} в день. Повтор того же занятия или карточки в этот день не добавляет монеты.`)}</p><p>{t('Coins recognise practice, not your Russian level. Hints and corrections are part of learning.','Монеты отмечают практику, а не уровень владения русским. Подсказки и исправления — часть обучения.')}</p></details>
      </> : progression.loading ? <p role="status">{t('Loading your progress…','Загружаем ваш прогресс…')}</p> : <div><p role="alert">{progression.error || t('Your progress could not load.','Не удалось загрузить прогресс.')}</p><button class="live-mute" onClick={progression.refresh}>{t('Try again','Попробовать ещё раз')}</button></div>}
    </>}
  </section>;
}
