import { useEffect, useRef, useState } from 'preact/hooks';
import { api } from './learning-api';
import { cardLabel } from './CardDetails';
import { CardLibrary } from './CardLibrary';
import { Sheet } from './components';
import { ActivityHeader } from './ActivityHeader';
import { nextTime, words, type CardOverview, type CardScope, type CardHistory, type Language, type LibraryCard, type ReviewSession } from './review-types';

export function Flashcards({ profileId, language = 'en', personal = false, wordId, lessonId, topic }: { profileId: string; language?: Language; personal?: boolean; wordId?: number; lessonId?: string; topic?: string }) {
  const t = words(language);
  const [data, setData] = useState<CardOverview>();
  const [scope, setScope] = useState<CardScope>({...wordId ? {word_id:String(wordId)} : {}, ...lessonId ? {lesson_id:lessonId} : {}, ...topic ? {topic} : {}});
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [mediaCard,setMediaCard] = useState('');
  const [mediaProgress,setMediaProgress] = useState('');
  const [size, setSize] = useState(10);
  const [history, setHistory] = useState<CardHistory>();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const pending = useRef<object>();
  const working = useRef(false);
  const controller = useRef<AbortController>();
  const heading = useRef<HTMLHeadingElement>(null);
  const library = useRef<HTMLElement>(null);
  const returnToCard = useRef<{ id: string; index: number; profileId: string; query: string }>();
  const query = new URLSearchParams(Object.entries(scope).filter(([,value]) => !!value)).toString();
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    setError(''); setData(undefined); setHistory(undefined);
    void api<CardOverview>(`/api/v1/flashcards${query ? `?${query}` : ''}`, undefined, request.signal).then(value => {
      if (request.signal.aborted) return;
      if (value.profile_id !== profileId) throw new Error(t('The study profile changed. Reload this page.', 'Профиль изменился. Обновите страницу.'));
      setData(value);
    }).catch(reason => { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : t('Cards could not open.', 'Не удалось открыть карточки.')); });
    return () => request.abort();
  }, [profileId, query, revision]);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const target = returnToCard.current;
    if (!target) return;
    if (target.profileId !== profileId || target.query !== query) {
      returnToCard.current = undefined;
      return;
    }
    if (!data || !library.current) return;
    returnToCard.current = undefined;
    const rows = Array.from(library.current.querySelectorAll<HTMLButtonElement>('button[data-card-id]'));
    const row = rows.find(button => button.dataset.cardId === target.id) ?? rows[Math.min(target.index, rows.length - 1)];
    (row ?? library.current.querySelector<HTMLElement>('h2'))?.focus({ preventScroll: true });
  }, [data, profileId, query]);

  function refreshAfterCardChange(card: LibraryCard) {
    returnToCard.current = { id: card.id, index: Math.max(0, data?.cards.findIndex(value => value.id === card.id) ?? 0), profileId, query };
    setRevision(value => value + 1);
  }

  async function start() {
    if (!data || working.current) return;
    if (data.active_session_id && !pending.current) { window.location.hash = `review/${data.active_session_id}`; return; }
    if (!pending.current) pending.current = { profile_id: profileId, scope, size, submission_id: crypto.randomUUID() };
    const request = controller.current;
    working.current = true; setBusy(true); setError('');
    try {
      const saved = await api<ReviewSession>('/api/v1/review-sessions', pending.current, request?.signal);
      if (request?.signal.aborted) return;
      if (saved.profile_id !== profileId) throw new Error(t('The study profile changed. Reload this page.', 'Профиль изменился. Обновите страницу.'));
      pending.current = undefined; window.location.hash = `review/${saved.id}`;
    } catch (reason) {
      if (!request?.signal.aborted) setError(reason instanceof Error ? reason.message : t('We could not confirm the start. Try again.', 'Не удалось подтвердить начало. Попробуйте ещё раз.'));
    } finally { working.current = false; if (!request?.signal.aborted) setBusy(false); }
  }
  async function suspend(card: LibraryCard) {
    if (working.current || pending.current) return;
    const request = controller.current;
    working.current = true; setBusy(true); setError('');
    try {
      await api(`/api/v1/flashcards/${card.id}/suspension`, { profile_id: profileId, suspended: card.status !== 'suspended', expected_revision: card.revision }, request?.signal);
      if (!request?.signal.aborted) refreshAfterCardChange(card);
    } catch (reason) { if (!request?.signal.aborted) setError(reason instanceof Error ? reason.message : t('Reload the library to check this card.', 'Обновите коллекцию и проверьте карточку.')); }
    finally { working.current = false; if (!request?.signal.aborted) setBusy(false); }
  }
  async function deleteCard(card: LibraryCard) {
    if (working.current || pending.current) return;
    const request = controller.current;
    working.current=true;setBusy(true);setError('');
    try {
      await api(`/api/v1/cards/${card.id}/delete`,{},request?.signal);
      if (!request?.signal.aborted) refreshAfterCardChange(card);
    } catch (reason) { if (!request?.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not delete the card.'); }
    finally { working.current=false; if (!request?.signal.aborted) setBusy(false); }
  }
  async function addMedia(card: LibraryCard) {
    if (working.current) return;
    const request=controller.current;
    working.current=true;setBusy(true);setError('');setMediaCard(card.id);setMediaProgress(t('Creating media…','Создаём файлы…'));
    try {
      let retry=true;
      while (!request?.signal.aborted) {
        const result=await api<{ complete: boolean; saved: number; failed: number }>(`/api/v1/flashcards/${card.id}/media`,retry ? {retry:true} : {},request?.signal);
        retry=false;
        if (request?.signal.aborted) return;
        setMediaProgress(`${result.saved} / 3 ${t('saved','сохранено')}`);
        if (result.complete) {
          if (result.failed) setError(t('The card is saved, but some media could not be created. Use Retry media to try again.','Карточка сохранена, но часть файлов не создана. Нажмите «Повторить создание файлов».'));
          const value=await api<CardOverview>(`/api/v1/flashcards${query ? `?${query}` : ''}`,undefined,request?.signal);
          if (!request?.signal.aborted && value.profile_id===profileId) setData(value);
          break;
        }
        await new Promise(resolve => window.setTimeout(resolve,1000));
      }
    } catch (reason) { if (!request?.signal.aborted) setError(reason instanceof Error ? reason.message : 'Media creation paused.'); }
    finally { working.current=false;setBusy(false);setMediaCard('');setMediaProgress(''); }
  }
  async function inspectHistory(card: LibraryCard) {
    const request = controller.current;
    try {
      const value = await api<CardHistory>(`/api/v1/flashcards/${card.id}/history`, undefined, request?.signal);
      if (value.profile_id !== profileId) throw new Error(t('The study profile changed. Reload this page.', 'Профиль изменился. Обновите страницу.'));
      if (!request?.signal.aborted) setHistory(value);
    } catch (reason) { if (!request?.signal.aborted) setError(reason instanceof Error ? reason.message : t('History could not open.', 'Не удалось открыть историю.')); }
  }
  const label = (value: string) => ({ new: t('New', 'Новая'), learning: t('Learning', 'Изучаю'), reviewing: t('Reviewing', 'Повторяю'), suspended: t('Set aside', 'Отложена') })[value] ?? value;
  const decks = data?.facets?.decks ?? Array.from(new Map(data?.cards.flatMap(c => c.decks).map(d => [d.content_id, d])).values());
  return <section class="page flashcards-page activity-entry"><div class="activity-entry-content">
    <ActivityHeader title={t('Flashcards', 'Карточки')} headingRef={heading} headingTabIndex={-1}
      actions={personal && <a class="cta activity-header-action" href={data?.lesson?.url ?? (scope.word_id ? `#generate?word_id=${scope.word_id}` : '#generate')}>{t('Generate cards','Создать карточки')} <span aria-hidden="true">＋</span></a>} />
    {data?.lesson && <div class="letter lesson-card-context"><strong>{data.lesson.title}</strong><div class="action-row"><a class="text-link" href={data.lesson.url}>{t("Back to lesson", "К уроку")} →</a><a class="text-link" href="#flashcards">{t("All flashcards", "Все карточки")}</a></div></div>}
    {scope.word_id && <p class="intro">{t('Showing cards for this vocabulary word.', 'Карточки выбранного слова.')} <button class="text-link" disabled={busy || !!pending.current} onClick={() => setScope(lessonId ? {lesson_id:lessonId} : {})}>{t('Show all cards', 'Показать все карточки')}</button></p>}
    {error && <div class="error-note" role="alert"><p>{error}</p><div class="action-row"><button class="text-link" onClick={() => { pending.current = undefined; setRevision(v => v + 1); }}>{t('Reload cards', 'Обновить карточки')}</button>{!personal && <a href="/post/household">{t('Choose a learner', 'Выбрать ученика')}</a>}</div></div>}
    {!data ? !error && <p role="status">{t('Opening your cards…', 'Открываем карточки…')}</p> : <>
      <div class="flashcard-study-bar">
        <dl class="flashcard-study-counts" aria-label={t('Study today', 'Сегодня')}>
          <div><dt>{t('Due', 'К повторению')}</dt><dd>{data.counts.due}</dd></div>
          <div><dt>{t('New', 'Новые')}</dt><dd>{Math.min(data.counts.new, data.counts.new_allowance)}</dd></div>
          <div><dt>{t('Reviewed today', 'Повторено сегодня')}</dt><dd>{data.counts.practised_today}</dd></div>
        </dl>
        {(data.active_session_id || data.counts.ready > 0) && <div class="flashcard-study-actions">
          {!data.active_session_id && <label class="flashcard-session-size"><span class="sr-only">{t('Session size', 'Размер занятия')}</span><select value={size} disabled={busy || !!pending.current} onChange={e => setSize(Number(e.currentTarget.value))}>{[5,10,20].map(n => <option value={n} key={n}>{n} {t('cards', 'карточек')}</option>)}</select></label>}
          <button class="cta" disabled={busy} onClick={() => void start()}>{busy ? t('Opening…', 'Открываем…') : pending.current ? t('Try starting again', 'Попробовать начать снова') : data.active_session_id ? t('Continue practice', 'Продолжить') : t('Start practice', 'Начать практику')} <span aria-hidden="true">→</span></button>
        </div>}
      </div>
      {!data.active_session_id && !data.counts.ready && data.counts.cards > 0 && <p class="flashcard-study-note">{data.counts.media_pending
        ? t('Some cards still need pictures and audio. Open a card to add them.', 'Некоторым карточкам нужны картинка и аудио. Откройте карточку, чтобы добавить их.')
        : data.counts.next_due_at ? `${t('Next review', 'Следующее повторение')}: ${nextTime(data.counts.next_due_at, data.server_now, language)}.`
        : data.counts.suspended ? t('Open a card to return it to practice.', 'Откройте карточку, чтобы вернуть её в практику.')
        : t('No cards due. New cards will be available tomorrow.', 'Пока нечего повторять. Новые карточки будут доступны завтра.')}</p>}
      <section ref={library} class="native-library" aria-labelledby="card-library-heading">
        <div class="flashcard-library-toolbar">
          <h2 id="card-library-heading" tabIndex={-1}>{t('Your cards', 'Ваши карточки')} <span>{data.counts.cards}</span></h2>
          <form key={query} class="flashcard-search" role="search" onSubmit={event => {
            event.preventDefault(); if (pending.current || busy) return;
            const form = new FormData(event.currentTarget);
            setScope({...scope, q: String(form.get('q') ?? '').trim()});
          }}>
            <label class="sr-only" for="card-search">{t('Search cards', 'Найти карточки')}</label>
            <input id="card-search" name="q" type="search" value={scope.q ?? ''} placeholder={t('Search cards', 'Найти карточки')} maxLength={120} />
            <button type="submit" class="flashcard-search-submit" aria-label={t('Search', 'Найти')} disabled={busy || !!pending.current}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg></button>
          </form>
          <button type="button" class="flashcard-filter-toggle" aria-expanded={filtersOpen} aria-controls="card-library-filters" onClick={() => setFiltersOpen(value => !value)}>{t('Filters', 'Фильтры')} <span aria-hidden="true">{filtersOpen ? '−' : '+'}</span></button>
        </div>
        <div id="card-library-filters" hidden={!filtersOpen}>
          <form key={query} class="review-filters" onSubmit={event => { event.preventDefault(); if (pending.current || busy) return; const form = new FormData(event.currentTarget); setScope(Object.fromEntries([...form.entries()].map(([k,v]) => [k,String(v)]))); }}>
            {scope.lesson_id && <input type="hidden" name="lesson_id" value={scope.lesson_id} />}{scope.word_id && <input type="hidden" name="word_id" value={scope.word_id} />}
            {scope.q && <input type="hidden" name="q" value={scope.q} />}
        <label>{t('Collection', 'Коллекция')}<select name="deck" value={scope.deck ?? ''}><option value="">{t('All cards', 'Все карточки')}</option>{decks.map(d => <option key={d.content_id} value={d.content_id}>{language==='ru' && d.title_ru ? d.title_ru : d.title}</option>)}{scope.deck && !decks.some(d => d.content_id===scope.deck) && <option value={scope.deck}>{t('Selected collection', 'Выбранная коллекция')}</option>}</select></label>
        {!!data.facets?.topics.length && <label>{t('Topic', 'Тема')}<select name="topic" value={scope.topic ?? ''}><option value="">{t('All topics', 'Все темы')}</option>{data.facets.topics.map(topic => <option key={topic} value={topic}>{cardLabel(topic,language)}</option>)}</select></label>}
        <label>{t('Practise', 'Что практикуем')}<select name="direction" value={scope.direction ?? ''}><option value="">{t('All types', 'Все виды')}</option><option value="ru-en">{t('Russian → English', 'Русский → Английский')}</option><option value="en-ru">{t('English → Russian', 'Английский → Русский')}</option><option value="ru-cloze">{t('Missing word', 'Пропущенное слово')}</option></select></label>
        <label>{t('Word type','Часть речи')}<select name="pos" value={scope.pos ?? ''}><option value="">{t('All word types','Все части речи')}</option>{data.facets?.pos?.map(value => <option value={value}>{cardLabel(value,language)}</option>)}</select></label>
        <label>{t('Case','Падеж')}<select name="case" value={scope.case ?? ''}><option value="">{t('All cases','Все падежи')}</option>{data.facets?.cases?.map(value => <option value={value}>{cardLabel(value,language)}</option>)}</select></label>
        <label>{t('Difficulty','Сложность')}<select name="difficulty" value={scope.difficulty ?? ''}><option value="">{t('Any difficulty','Любая сложность')}</option>{[1,2,3,4,5,6,7,8].map(value => <option value={value}>{value}/8</option>)}</select></label>
        <label>{t('Sort collection','Порядок карточек')}<select name="sort" value={scope.sort ?? 'due'}><option value="due">{t('Due first','Сначала к повторению')}</option><option value="alphabetical">{t('Russian A–Я','По алфавиту')}</option><option value="difficulty">{t('Easiest first','Сначала простые')}</option></select></label>
        <label>{t('Show', 'Показать')}<select name="state" value={scope.state ?? ''}><option value="">{t('All states', 'Все состояния')}</option><option value="due">{t('Ready now', 'Пора повторить')}</option>{['new','learning','reviewing','suspended'].map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label>
        <div class="action-row"><button class="cta" disabled={busy || !!pending.current}>{t('Apply selection', 'Применить')}</button><button type="button" class="text-link" disabled={busy || !!pending.current} onClick={() => setScope(lessonId ? {lesson_id:lessonId} : {})}>{t('Reset selection', 'Сбросить выбор')}</button></div></form>
        </div>
        <CardLibrary cards={data.cards} language={language} personal={personal} busy={busy}
          suspensionDisabled={busy || !!pending.current} history={history} mediaCard={mediaCard} mediaProgress={mediaProgress} error={error}
          onSuspend={card => void suspend(card)} onDelete={card => void deleteCard(card)}
          onMedia={card => void addMedia(card)} onHistory={card => void inspectHistory(card)} />
        {!data.cards.length && <p>{query ? t('No cards match this selection.', 'Нет карточек с такими условиями.') : t('No flashcards yet.', 'Пока нет карточек.')}
          {!personal && !query && <> <a class="text-link" href="/post/household">{t('Choose cards', 'Выбрать карточки')}</a></>}
        </p>}
      </section>
    </>}
  </div></section>;
}

export function FlashcardsSetup({ adult, language='en' }: { adult: boolean; language?: Language }) {
  const t=words(language);
  return <section class="page flashcards-page activity-entry"><div class="activity-entry-content">
    <ActivityHeader title={t('Flashcards', 'Карточки')} description={t('Review your Russian vocabulary with flashcards.', 'Повторяйте русские слова с помощью карточек.')} />
    <Sheet><h2>{t('One learner. Their own practice.', 'У каждого своя практика.')}</h2><p>{t('Choose a learner to save their cards and review schedule. A grown-up can prepare cards, explain tricky meanings and approve them before practice.', 'Выберите ученика, чтобы сохранять его карточки и расписание. Взрослый может подготовить карточки, объяснить сложные значения и одобрить материал.')}</p><div class="action-row"><a class="cta" href="/post/household">{t('Choose a learner', 'Выбрать ученика')}</a>{adult && <a class="text-link" href="/post/flashcards/manage">{t('Prepare & review cards', 'Подготовить и проверить карточки')}</a>}</div></Sheet>
  </div></section>;
}
