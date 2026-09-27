import { useEffect, useRef, useState } from 'preact/hooks';
import { api } from './learning-api';
import { words, type Language, type MediaJob, type LessonSource } from './review-types';

type Options = { audio: boolean; image: boolean; kind: string; quantity: number; max_cards: number; difficulty?: number; pos?: string; case?: string; topic?: string; word_id?: number };
type Batch = { first_steps?:{lesson_id?:string;title:string;url:string;study_url:string;reused:number}; id: string; complete: boolean; saved: number; total: number; household: boolean; source?: (LessonSource & {first_page:number; last_page:number; report: {added?:number; reused?:number; requested?:number; surface?:string; reason?:string; page?:number}[]}) | null;
  items: { id: string; word: string; status: string; origin?: string; english?: string; sentence?: string; notes?: string; error?: string; card_version_id?: string; media_jobs?: MediaJob[] }[] };
type Settings = { topics: string[]; word?: { id: number; lemma: string }; configured: boolean; household: boolean; max_quantity: number };

export function GenerateCards({ batchId, wordId, language='en' }: { batchId?: string; wordId?: number; language?: Language }) {
  const t=words(language);
  const [settings,setSettings]=useState<Settings>();
  const [options,setOptions]=useState<Options>({audio:true,image:true,kind:'ru-cloze',quantity:wordId ? 1 : 5,max_cards:1,...(wordId ? {word_id:wordId} : {})});
  const [matches,setMatches]=useState<{word_id:number;form:string}[]>();
  const [batch,setBatch]=useState<Batch>();
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [running,setRunning]=useState(false);
  const requestKey=useRef<string>();
  const heading=useRef<HTMLHeadingElement>(null);
  const alive=useRef(true);
  useEffect(() => { heading.current?.focus(); return () => { alive.current=false; }; },[]);
  useEffect(() => {
    const controller=new AbortController();
    void api<Settings>(`/api/v1/card-generation/options${wordId ? `?word_id=${wordId}` : ''}`,undefined,controller.signal)
      .then(value => { if (!controller.signal.aborted) setSettings(value); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  },[wordId]);
  useEffect(() => {
    if (batchId) return;
    const controller=new AbortController();setMatches(undefined);requestKey.current=undefined;
    const timer=window.setTimeout(() => {
      void api<{words:{word_id:number;form:string}[]}>('/api/v1/card-generation/preview',options,controller.signal)
        .then(value => { if (!controller.signal.aborted) setMatches(value.words); })
        .catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    },200);
    return () => { clearTimeout(timer);controller.abort(); };
  },[JSON.stringify(options),batchId]);
  useEffect(() => {
    if (!batchId) return;
    const controller=new AbortController();
    void api<Batch>(`/api/v1/card-generation/batches/${batchId}`,undefined,controller.signal)
      .then(value => { if (!controller.signal.aborted) { setBatch(value);setRunning(!value.complete); } })
      .catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  },[batchId]);
  useEffect(() => {
    if (!running || !batchId) return;
    const controller=new AbortController();let timer:number;
    const advance=async () => {
      try {
        const value=await api<Batch>(`/api/v1/card-generation/batches/${batchId}/next`,{},controller.signal);
        if (controller.signal.aborted) return;
        setBatch(value);
        if (value.complete) setRunning(false);
        else timer=window.setTimeout(() => void advance(),1000);
      } catch (reason) {
        if (!controller.signal.aborted) { setRunning(false);setError(reason instanceof Error ? reason.message : t('Generation paused. Your saved cards are kept.', 'Создание приостановлено. Готовые карточки сохранены.')); }
      }
    };
    void advance();
    return () => { controller.abort();clearTimeout(timer); };
  },[batchId,running]);

  async function generate() {
    if (busy || !matches?.length) return;
    requestKey.current ??= crypto.randomUUID();setBusy(true);setError('');
    try {
      const value=await api<Batch>('/api/v1/card-generation/batches',{submission_id:requestKey.current,options});
      if (alive.current) window.location.hash=`generate/${value.id}`;
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : t('Could not start generation.', 'Не удалось начать создание.')); }
    finally { if (alive.current) setBusy(false); }
  }
  async function retryMedia() {
    setBusy(true);setError('');
    try {
      const value=await api<Batch>(`/api/v1/card-generation/batches/${batchId}/retry-media`,{});
      if (alive.current) { setBatch(value);setRunning(!value.complete); }
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : 'Could not retry media.'); }
    finally { if (alive.current) setBusy(false); }
  }
  async function retryCards(source = false) {
    setBusy(true);setError('');
    try {
      const value=await api<Batch>(`/api/v1/card-generation/batches/${batchId}/${source ? "recheck-source" : "retry-cards"}`,{});
      if (alive.current) {setBatch(value);setRunning(!value.complete);}
    } catch(reason) {if(alive.current)setError(reason instanceof Error ? reason.message : 'Could not retry cards.');}
    finally {if(alive.current)setBusy(false);}
  }
  const mediaJobs=batch?.items.flatMap(item => item.media_jobs ?? []) ?? [];
  const lessonCardsUrl=batch?.first_steps?.study_url ?? (batch?.source ? `#flashcards?lesson_id=${encodeURIComponent(batch.source.lesson_id)}` : '#flashcards');
  const reused=batch?.first_steps?.reused ?? batch?.source?.report[0]?.reused ?? 0;
  const fromGame=batch?.first_steps?.lesson_id?.startsWith('game:') ?? false;
  const mediaFailed=mediaJobs.some(job => job.status==='failed');
  function choose(name:keyof Options,value:string) {
    setError('');setOptions(previous => ({...previous,[name]:['quantity','max_cards','difficulty'].includes(name) ? value ? Number(value) : undefined : value}));
  }
  return <section class="page generate-page">
    <a class="text-link" href={batch?.first_steps?.url ?? batch?.source?.url ?? "#flashcards"}>← {fromGame ? t('Back to game','К игре') : batch?.source || batch?.first_steps ? t('Back to lesson','К уроку') : t('Flashcards','Карточки')}</a>
    <h1 ref={heading} tabIndex={-1}>{t('Generate flashcards','Создать карточки')}</h1>
    {batch?.first_steps ? <p class="intro">{batch.first_steps.title} · {t("Pictures and audio for the words you practised.","Картинки и записи изученных слов.")}</p> : batch?.source ? <p class="intro">{batch.source.title} · {t('Pages','Страницы')} {batch.source.first_page}–{batch.source.last_page}</p> : !batchId && <p class="intro">{t('Choose the cards you want. We’ll make them from your vocabulary.','Выберите нужные карточки. Мы создадим их из вашего словаря.')}</p>}
    {error && <div class="error-note" role="alert">{error}</div>}
    {!batchId ? <form class="letter generator-form" onSubmit={event => { event.preventDefault();void generate(); }}>
      <div class="generator-main-options">
        <label>{t('Card type','Тип карточек')}<select name="kind" value={options.kind} onChange={e => choose('kind',e.currentTarget.value)} disabled={busy}>
          <option value="ru-cloze">{t('Missing word in a sentence','Пропущенное слово')}</option>
          <option value="ru-en">{t('Russian → English','Русский → Английский')}</option>
          <option value="en-ru">{t('English → Russian','Английский → Русский')}</option>
        </select></label>
        <label>{t('Number of cards','Количество карточек')}<input type="number" min="1" max={settings?.max_quantity ?? 5} value={options.quantity} onInput={e => choose('quantity',e.currentTarget.value)} disabled={busy || !settings} required /></label>
      </div>
      {settings && settings.max_quantity < 20 && <p class="quiet">{t(`Up to ${settings.max_quantity} cards per demo batch.`, `В демоверсии — до ${settings.max_quantity} карточек за раз.`)}</p>}
      {settings?.word && options.word_id && <p class="selected-vocab"><strong lang="ru">{settings.word.lemma}</strong><button class="text-link" type="button" onClick={() => setOptions(({word_id,...rest}) => rest)}>{t('Use all vocabulary','Весь словарь')}</button></p>}
      <div class="generator-filters">
        <label>{t('Difficulty','Сложность')}<select value={options.difficulty ?? ''} onChange={e => choose('difficulty',e.currentTarget.value)} disabled={busy}><option value="">{t('Any','Любая')}</option>{[1,2,3,4,5,6,7,8].map(n => <option value={n}>{n}{n===1 ? t(' · easiest',' · простая') : ''}</option>)}</select></label>
        <label>{t('Word type','Часть речи')}<select value={options.pos ?? ''} onChange={e => choose('pos',e.currentTarget.value)} disabled={busy}><option value="">{t('Any','Любая')}</option>{[['NOUN','Nouns','Существительные'],['VERB','Verbs','Глаголы'],['ADJ','Adjectives','Прилагательные'],['ADVB','Adverbs','Наречия'],['NPRO','Pronouns','Местоимения'],['PREP','Prepositions','Предлоги'],['NUMR','Numbers','Числительные'],['CONJ','Conjunctions','Союзы'],['PRCL','Particles','Частицы']].map(([value,en,ru]) => <option value={value}>{t(en,ru)}</option>)}</select></label>
        <label>{t('Case','Падеж')}<select value={options.case ?? ''} onChange={e => choose('case',e.currentTarget.value)} disabled={busy}><option value="">{t('Any','Любой')}</option>{[['nomn','Nominative','Именительный'],['gent','Genitive','Родительный'],['datv','Dative','Дательный'],['accs','Accusative','Винительный'],['ablt','Instrumental','Творительный'],['loct','Prepositional','Предложный']].map(([value,en,ru]) => <option value={value}>{t(en,ru)}</option>)}</select></label>
        <label>{t('Topic','Тема')}<select value={options.topic ?? ''} onChange={e => choose('topic',e.currentTarget.value)} disabled={busy}><option value="">{t('Any','Любая')}</option>{settings?.topics.map(topic => <option value={topic}>{topic.replaceAll('_',' ').replace(/^./,letter => letter.toUpperCase())}</option>)}</select></label>
      </div>
      <fieldset class="generator-media-options"><legend>{t('Include with each card','Добавить к каждой карточке')}</legend><label><input type="checkbox" checked={options.image} disabled={busy} onChange={e => setOptions(previous => ({...previous,image:e.currentTarget.checked}))} />{t('Picture','Картинку')}</label><label><input type="checkbox" checked={options.audio} disabled={busy} onChange={e => setOptions(previous => ({...previous,audio:e.currentTarget.checked}))} />{t('Russian audio · word & example','Аудио по-русски · слово и пример')}</label></fieldset>
      <details><summary>{t('More options','Дополнительно')}</summary><label>{t('Maximum cards per word','Максимум карточек на слово')}<input type="number" min="1" max="20" value={options.max_cards} onInput={e => choose('max_cards',e.currentTarget.value)} disabled={busy} required /></label></details>
      <div class="generation-selection" aria-live="polite"><p>{matches === undefined ? t('Finding words…','Ищем слова…') : matches.length ? t('Selected words','Выбранные слова') : t('No matching words. Try different filters or allow more cards per word.','Слов не найдено. Измените фильтры или увеличьте число карточек на слово.')}</p>{matches && matches.length>0 && matches.length<options.quantity && <p class="quiet">{t(`Only ${matches.length} matching words are available. We’ll make ${matches.length} cards.`, `Найдено слов: ${matches.length}. Создадим столько же карточек.`)}</p>}<div class="word-results">{matches?.map(word => <span class="word" lang="ru" key={word.word_id}>{word.form}</span>)}</div></div>
      {settings && !settings.configured && <p role="status">{t('Generation needs the app’s OpenAI API key. Existing cards are still available to study.','Для создания нужен ключ OpenAI в настройках приложения. Готовые карточки доступны для занятий.')}</p>}
      <div class="action-row"><button class="cta" disabled={busy || !matches?.length || !settings?.configured}>{busy ? t('Starting…','Начинаем…') : t('Generate cards','Создать карточки')} <span aria-hidden="true">→</span></button><a class="text-link" href="#flashcards">{t('My flashcards','Мои карточки')}</a></div>
      <p class="quiet">{settings?.household ? t('Household mode is on. Generated cards go to the shared review list.','Включён семейный режим. Карточки попадут в список для проверки.') : t('Cards are saved automatically. You can edit or delete any of them.','Карточки сохраняются автоматически. Их можно изменить или удалить.')}</p>
    </form> : <>
      <div class="generation-status" aria-live="polite"><h2>{batch?.complete ? reused && !batch.total ? t('These cards are already in your collection','Эти карточки уже в вашей коллекции') : batch.saved ? batch.items.some(i => i.status==='failed') ? t('Cards saved · some need a retry','Карточки сохранены · некоторые нужно создать повторно') : mediaFailed ? t('Cards saved · some media needs a retry','Карточки сохранены · некоторые файлы нужно создать повторно') : t('Your cards are ready','Карточки готовы') : batch.items.some(i => i.status==='removed') ? t('No cards left in this batch','В этом наборе не осталось карточек') : t('No cards were generated','Карточки не созданы') : running ? t('Generating your cards…','Создаём карточки…') : t('Generation paused','Создание приостановлено')}</h2><p>{batch ? `${batch.saved} / ${batch.total} ${t('cards saved','карточек сохранено')}` : t('Opening your batch…','Открываем карточки…')}</p>{batch && <progress value={batch.items.filter(i => ['saved','failed','removed'].includes(i.status)).length + mediaJobs.filter(j => ['saved','failed'].includes(j.status)).length} max={Math.max(1,batch.total + mediaJobs.length)} aria-label={t('Generation progress','Ход создания')} />}
        {!!mediaJobs.length && <p class="quiet">{mediaJobs.filter(j => j.status==='saved').length} / {mediaJobs.length} {t('pictures and recordings saved','картинок и записей сохранено')}</p>}
        <div class="action-row">{!running && batch?.items.some(item => item.status==='failed') && <button class="text-link" disabled={busy} onClick={() => void retryCards()}>{t("Retry unfinished cards","Повторить создание карточек")}</button>}{mediaFailed && !running && <button class="text-link" disabled={busy} onClick={() => void retryMedia()}>{t('Retry missing media','Создать недостающие файлы')}</button>}{batch && (batch.saved || (!batch.first_steps && reused)) ? <a class="cta" href={batch.household ? '/post/flashcards/manage?review=1' : lessonCardsUrl}>{batch.household ? t('Review cards','Проверить карточки') : t('Study flashcards','Учить карточки')}</a> : null}{batch && !batch.complete && !running && <button class="cta" onClick={() => {setError('');setRunning(true);}}>{t('Resume generation','Продолжить создание')}</button>}<a class="text-link" href={fromGame ? '#activities' : batch?.first_steps?.url ?? batch?.source?.url ?? '#generate'}>{fromGame ? t('Choose another game','Выбрать другую игру') : t('Generate more','Создать ещё')}</a></div>
      </div>
      {batch?.first_steps && reused>0 && <p class="quiet">{reused} {fromGame ? reused===1 ? t("existing card is included. Its review date is unchanged.","готовая карточка включена. Дата повторения сохранена.") : t("existing cards are included. Their review dates are unchanged.","готовых карточек включено. Даты повторения сохранены.") : t("cards from earlier lessons are included. Their review dates are unchanged.","карточек из предыдущих уроков включено. Даты повторения сохранены.")}</p>}
      {batch?.source && <div class="lesson-generation-report">{batch.source.report.length>1 && <button class="text-link" disabled={busy || running} onClick={() => void retryCards(true)}>{t("Recheck skipped words","Проверить пропущенные слова")}</button>}{reused>0 && <p>{reused} {t('existing cards reused. Their review dates are unchanged.','готовых карточек уже есть. Даты повторения сохранены.')}</p>}{batch.source.report.slice(1).map((entry,index) => <p key={index} class="quiet"><span lang="ru">{entry.surface}</span> · {t('Page','Страница')} {entry.page}: {entry.reason}</p>)}{batch.source.report[0] && (batch.source.report[0].added ?? 0) + reused < (batch.source.report[0].requested ?? 0) && <p>{t('This section produced fewer suitable cards than requested. You can choose more pages from the lesson.','В этом разделе найдено меньше подходящих примеров. Можно выбрать другие страницы урока.')}</p>}</div>}
      <div class="generated-cards">{batch?.items.map(item => <article class="letter generated-card" key={item.id}><h3 lang="ru">{item.word}</h3>{item.status==='saved' ? <>{item.origin==='example' && <p class="quiet">{t('New example based on your selection','Новый пример по выбранному слову')}</p>}<p class="generated-meaning">{item.english}</p><p lang="ru">{item.sentence}</p>{item.notes && <p class="quiet">{item.notes}</p>}{!!item.media_jobs?.length && <ul class="media-job-list">{item.media_jobs.map(job => <li key={job.kind}>{job.kind==='image' ? t('Picture','Картинка') : job.kind==='word_audio' ? t('Word audio','Запись слова') : t('Example audio','Запись примера')} <span>{job.status==='saved' ? t('Ready','Готово') : job.status==='failed' ? t('Retry needed','Нужно повторить') : job.status==='running' ? t('Creating…','Создаём…') : t('Waiting','В очереди')}</span></li>)}</ul>}<a class="text-link" href={`/post/flashcards/manage?edit=${item.card_version_id}`}>{t('Edit card','Изменить карточку')}</a></> : <p>{item.error || (item.status==='removed' ? t('Removed or replaced. Other cards will continue generating.','Удалена или заменена. Остальные карточки будут созданы.') : item.status==='running' || item.status==='generated' ? t('Generating…','Создаём…') : t('Waiting','В очереди'))}</p>}</article>)}</div>
    </>}
  </section>;
}
