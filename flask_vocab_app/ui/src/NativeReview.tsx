import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { CardMedia } from './CardDetails';
import { api, ApiError } from './learning-api';
import { isReviewSession, ratingLabel, ratings, words, type Language, type ReviewSession } from './review-types';

export function NativeReview({ sessionId, profileId, language='en', personal=false }: { sessionId: string; profileId: string; language?: Language; personal?: boolean }) {
  const t=words(language);
  const [saved,setSaved]=useState<ReviewSession>();
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [blocked,setBlocked]=useState(false);
  const [reload,setReload]=useState(0);
  const [hintOpen,setHintOpen]=useState(false);
  const working=useRef(false);
  const pending=useRef<{url:string;body:object}>();
  const controller=useRef<AbortController>();
  const heading=useRef<HTMLHeadingElement>(null);
  const hintButton=useRef<HTMLButtonElement>(null);
  const cardFace=useRef<HTMLDivElement>(null);
  const cardAnswer=useRef<HTMLDivElement>(null);
  const advancing=useRef<number>();
  useEffect(() => {
    const request=new AbortController();controller.current=request;
    setSaved(undefined);setError('');setBlocked(false);pending.current=undefined;advancing.current=undefined;
    void api<ReviewSession>(`/api/v1/review-sessions/${sessionId}`,undefined,request.signal).then(value => {
      if (request.signal.aborted) return;
      if (request?.signal.aborted) return;
      if (value.profile_id!==profileId) throw new Error(t('Choose the learner who started this practice.', 'Выберите ученика, который начал эту практику.'));
      setSaved(value);
    }).catch(reason => {
      if (request.signal.aborted) return;
      if (reason instanceof ApiError && isReviewSession(reason.currentSession) && reason.currentSession.profile_id===profileId) { setSaved(reason.currentSession);setBlocked(true); }
      setError(reason instanceof Error ? reason.message : t('Your practice could not open.', 'Не удалось открыть практику.'));
    });
    return () => request.abort();
  },[sessionId,profileId,reload]);
  useLayoutEffect(() => {
    heading.current?.focus({preventScroll:true});setHintOpen(false);
    const face=cardFace.current;
    if (!face) return;
    if (saved?.phase==='revealed' && face.hasAttribute('data-review-scroll') && cardAnswer.current) {
      face.scrollTop+=cardAnswer.current.getBoundingClientRect().top-face.getBoundingClientRect().top;
    } else face.scrollTop=0;
  },[saved?.phase,saved?.item?.id,blocked]);
  useEffect(() => {
    // Only advance after the rating is confirmed. This also resumes sessions
    // saved on the old confirmation screen without recording another review.
    if (saved?.phase==='feedback' && saved.feedback && !busy && !pending.current && !blocked && advancing.current!==saved.revision) {
      advancing.current=saved.revision;
      void command('next');
    }
  },[saved,busy,blocked]);

  async function command(operation:string, extra:Record<string,string>={}) {
    if (!saved || working.current || (blocked && operation!=='finish')) return;
    if (!pending.current) pending.current={url:`/api/v1/review-sessions/${sessionId}/${operation}`,body:{submission_id:crypto.randomUUID(),expected_revision:saved.revision,
      ...(['reveal','help','reviews','report'].includes(operation) && saved.item ? {item_id:saved.item.id} : {}),...extra}};
    const request=controller.current;
    working.current=true;setBusy(true);setError('');
    try {
      const value=await api<ReviewSession>(pending.current.url,pending.current.body,request?.signal);
      if (request?.signal.aborted) return;
      if (value.profile_id!==profileId) throw new Error(t('The learner changed. Reopen your practice.', 'Ученик изменился. Откройте практику заново.'));
      pending.current=undefined;setSaved(value);setBlocked(false);
    } catch (reason) {
      if (request?.signal.aborted) return;
      if (reason instanceof ApiError && reason.code==='stale_revision' && isReviewSession(reason.currentSession) && reason.currentSession.profile_id===profileId) {
        pending.current=undefined;setSaved(reason.currentSession);setError(t('Practice changed in another tab. This is the latest saved card.', 'Практика изменилась в другой вкладке. Здесь последнее сохранённое состояние.'));
      } else if (reason instanceof ApiError && ['locked','profile_changed','adult_required','content_unavailable','not_found','csrf_failed','card_changed'].includes(reason.code)) {
        pending.current=undefined;setBlocked(true);setError(reason.message);
        if (isReviewSession(reason.currentSession) && reason.currentSession.profile_id===profileId) setSaved(reason.currentSession);
      } else if (reason instanceof ApiError && ['invalid_input','wrong_item','session_complete','undo_unavailable','undo_conflict','clock_changed'].includes(reason.code)) {
        pending.current=undefined;setError(reason.message);
      } else setError(t('We could not confirm the save. Retry the same action below; your answer will only be recorded once.', 'Не удалось подтвердить сохранение. Повторите действие ниже — ответ запишется только один раз.'));
    } finally { working.current=false;if (!request?.signal.aborted) setBusy(false); }
  }
  const disabled=busy || !!pending.current || blocked;
  const item=saved?.item;
  const cardAssets=item?.assets.filter(asset => asset.role!=='hint') ?? [];
  const hintAssets=item?.assets.filter(asset => asset.role==='hint') ?? [];
  const hintAvailable=!!item?.hint || hintAssets.length>0;
  const longCard=!!item && [item.prompt,item.answer,item.context].some(text => (text?.length ?? 0)>140);
  const explanation=item && (language==='ru' && item.explanation_ru ? item.explanation_ru : item.explanation);
  const promptParts=item?.prompt.split('[[blank]]');
  function reloadCard() {
    // Never discard the submission ID of an action whose save is uncertain.
    if (working.current || pending.current) return;
    setHintOpen(false);setReload(n => n+1);
  }
  async function toggleHint() {
    if (disabled || !item) return;
    if (saved?.phase==='front' && !item.assisted) await command('help');
    setHintOpen(open => !open);
  }
  function closeHint() {
    setHintOpen(false);hintButton.current?.focus({preventScroll:true});
  }
  return <section class="page native-review-page" onKeyDown={event => {
    if (event.key==='Escape' && hintOpen) {closeHint();event.preventDefault();return;}
    if (event.repeat || disabled || event.target===cardFace.current || (event.target instanceof Element && event.target.closest('button,a,input,textarea,select,summary,audio'))) return;
    if (event.key===' ' && saved?.phase==='front') { event.preventDefault();void command('reveal'); }
    else if (saved?.phase==='revealed' && ['1','2','3','4'].includes(event.key)) { event.preventDefault();void command('reviews',{rating:ratings[Number(event.key)-1]}); }
  }}>
    <div class="review-topline"><a class="text-link" href={saved?.lesson ? `#flashcards?lesson_id=${encodeURIComponent(saved.lesson.lesson_id)}` : "#flashcards"}>← {t('Flashcards', 'Карточки')}</a><span class="quiet" role="status">{busy ? t('Saving…', 'Сохраняем…') : pending.current ? t('Save not confirmed', 'Сохранение не подтверждено') : ''}</span></div>
    {saved?.lesson && <a class="text-link" href={saved.lesson.url}>{t("Back to lesson", "К уроку")} →</a>}
    {saved && <div class="review-progress"><span>{saved.practised_cards} / {saved.total_cards}{saved.skipped_cards ? ` · ${t('set aside', 'отложено')}: ${saved.skipped_cards}` : ''}</span><progress value={saved.practised_cards+saved.skipped_cards} max={saved.total_cards || 1} aria-label={t('Progress through selected cards', 'Прогресс по выбранным карточкам')} /></div>}
    {error && <div class="error-note" role="alert"><p>{error}</p>{pending.current && <button class="cta" disabled={busy} onClick={() => void command('retry')}>{t('Retry saving', 'Повторить сохранение')}</button>}{!pending.current && <div class="action-row"><button class="text-link" disabled={busy} onClick={reloadCard}>{t('Reload saved practice', 'Загрузить сохранённую практику')}</button>{!personal && <a href="/post/household">{t('Choose a learner', 'Выбрать ученика')}</a>}</div>}</div>}
    {!saved ? <h1 ref={heading} tabIndex={-1}>{error ? t('Practice could not open.', 'Практика не открылась.') : t('Opening your cards…', 'Открываем карточки…')}</h1>
      : blocked ? <div class="letter"><h1 ref={heading} tabIndex={-1}>{t('Let’s check this practice.', 'Нужно проверить эту практику.')}</h1><p>{t('Your saved reviews are kept. Finish this session, then check the card in your collection.', 'Повторения сохранены. Завершите занятие и проверьте карточку в коллекции.')}</p></div>
      : saved.phase==='completed' ? <div class="review-complete"><h1 ref={heading} tabIndex={-1}>{t('Practice saved.', 'Практика сохранена.')}</h1><p class="intro">{t('Cards practised this session', 'Карточек за это занятие')}: <strong>{saved.practised_cards}</strong>.</p><a class="cta" href={saved?.lesson ? `#flashcards?lesson_id=${encodeURIComponent(saved.lesson.lesson_id)}` : "#flashcards"}>{t('Back to flashcards', 'К карточкам')} <span aria-hidden="true">→</span></a></div>
      : saved.phase==='feedback' ? saved.feedback
        ? <p role="status">{t('Opening the next card…', 'Открываем следующую карточку…')}</p>
        : <div class="review-feedback letter"><h1 ref={heading} tabIndex={-1}>{t('Card set aside.', 'Карточка отложена.')}</h1><p>{t('The card is set aside. You can edit it or return it to practice from your collection. This did not count as a forgotten answer.', 'Карточка отложена. Её можно изменить или вернуть в практику из коллекции. Это не считается забытым ответом.')}</p>
        <button class="cta" disabled={disabled} onClick={() => void command('next')}>{t('Continue', 'Продолжить')} <span aria-hidden="true">→</span></button></div>
      : item && <article class={`recall-card${saved.phase==='revealed' ? ' is-revealed' : ''}${longCard ? ' is-long' : ''}`}>
        <div class="recall-toolbar">
          <div class="recall-hint-control">
            {(saved.phase==='front' && item.has_hint || hintAvailable) && <button ref={hintButton} class="recall-tool" disabled={disabled} aria-expanded={hintOpen && hintAvailable} aria-controls={hintAvailable ? 'recall-hint' : undefined} onClick={() => void toggleHint()}>{t('Hint', 'Подсказка')}</button>}
            {hintOpen && hintAvailable && <aside id="recall-hint" class="recall-hint" aria-label={t('Hint', 'Подсказка')}><div class="recall-hint-content">{item.hint && <p>{item.hint}</p>}{hintAssets.map(asset => <CardMedia key={asset.id} asset={asset} language={language} compact />)}</div><button class="recall-tool" onClick={closeHint} aria-label={t('Close hint','Закрыть подсказку')}>×</button></aside>}
          </div>
          <button class="recall-tool recall-refresh" disabled={disabled} onClick={reloadCard} aria-label={t('Refresh card', 'Обновить карточку')} title={t('Reload this saved card', 'Загрузить сохранённую карточку')}><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 6.1A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.9"/></svg></button>
        </div>
        <div ref={cardFace} class={`recall-face ${cardAssets.some(a => a.media_type.startsWith("image/")) ? "has-picture" : ""}`} tabIndex={longCard ? 0 : undefined} role={longCard ? 'region' : undefined} aria-label={longCard ? t('Card content','Текст карточки') : undefined} data-review-scroll={longCard ? '' : undefined}>{cardAssets.filter(a => a.media_type.startsWith("image/")).map(asset => <CardMedia key={`${asset.kind ?? "asset"}:${asset.id}`} asset={asset} language={language} />)}<div class="recall-text"><h1 ref={heading} tabIndex={-1} class="recall-prompt" lang={item.direction==='en-ru' ? 'en' : 'ru'}>{promptParts?.length===2 ? <>{promptParts[0]}<span class="cloze-slot">{saved.phase==='revealed' ? item.dictionary_url ? <a href={item.dictionary_url} target="_blank" rel="noopener noreferrer" title={t('Look up this word on OpenRussian', 'Открыть слово в OpenRussian')}>{item.answer}</a> : item.answer : '[...]'}</span>{promptParts[1]}</> : item.prompt}</h1>
        {item.context && item.direction==='ru-en' && item.context!==item.prompt && <p class="recall-context" lang="ru">{item.context}</p>}{saved.phase==='front' && item.direction==='ru-cloze' && item.cue_en && <p class="recall-word-meaning" lang="en">{item.cue_en}</p>}
        {saved.phase==='revealed' && <div ref={cardAnswer} class="recall-answer" aria-live="polite">
          {promptParts?.length!==2 && <p class="answer-text" lang={item.direction==='ru-en' ? 'en' : 'ru'}>{item.dictionary_url && item.direction!=='ru-en' ? <a href={item.dictionary_url} target="_blank" rel="noopener noreferrer" title={t('Look up this word on OpenRussian', 'Открыть слово в OpenRussian')}>{item.answer}</a> : item.answer}</p>}
          {item.cue_en && item.direction==='ru-cloze' && <p class="recall-word-meaning" lang="en">{item.cue_en}</p>}
          {item.context_meaning && item.context_meaning!==item.answer && <p class="recall-context-meaning" lang="en">{item.context_meaning}</p>}
          {item.context && item.direction==='en-ru' && <p class="recall-context" lang="ru">{item.context}</p>}
          {(explanation || item.sources?.length) && <details key={item.id} class="recall-explanation"><summary>{t('Explanation', 'Объяснение')}</summary>{explanation && <p class="answer-explanation">{explanation}</p>}{item.sources?.map(source => <a key={source.url} class="text-link" href={source.url}>{source.title} · {t('Page', 'Страница')} {source.page}</a>)}</details>}
        </div>}
        </div></div>
        {!!cardAssets.some(a => a.media_type.startsWith("audio/")) && <div class="recall-media">{cardAssets.filter(a => a.media_type.startsWith("audio/")).sort((a,b) => (a.kind==='word_audio' ? 0 : 1)-(b.kind==='word_audio' ? 0 : 1)).map(asset => <CardMedia key={`${asset.kind ?? "asset"}:${asset.id}`} asset={asset} language={language} compact />)}</div>}
        <div class="recall-actions">{saved.phase==='front'
          ? <button class="cta reveal-button" disabled={disabled} onClick={() => void command('reveal')}>{t('Show answer', 'Показать ответ')}</button>
          : <div class="rating-controls" role="group" aria-label={t('Rate your recall', 'Оцените, как вы вспомнили')}>{ratings.map((rating,index) => <button key={rating} class={`rating-${rating}`} disabled={disabled} onClick={() => void command('reviews',{rating})}><span>{ratingLabel(rating,language)}</span><kbd aria-hidden="true">{index+1}</kbd></button>)}</div>}
        </div>
      </article>}
    {(saved?.status==='active' || saved?.can_undo) && <div class="review-bottomline">
      {saved?.can_undo && saved.phase!=='feedback' && !blocked && <button class="text-link" disabled={disabled} onClick={() => void command('undo')}>{t('Undo last answer', 'Отменить последний ответ')}</button>}
      {saved?.status==='active' && <button class="text-link review-finish" disabled={busy || !!pending.current} onClick={() => void command('finish')}>{t('Finish for now', 'На сегодня хватит')}</button>}
    </div>}
  </section>;
}
