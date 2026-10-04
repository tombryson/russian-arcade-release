import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { api, ApiError, type PracticeSession, type PassageWord } from './learning-api';
import { Feedback, Sheet } from './components';
import {appUrl} from './app-url';
import {usePracticeDraft} from './usePracticeDraft';
import {PassageWords, type WordSelection} from './PassageWords';

type Operation = 'attempts' | 'help' | 'listened' | 'transcript' | 'words/lookup' | 'words';
type Command = {url: string; body: object; operation: Operation};

export function Practice({ sessionId, profileId, onFinish, language = 'en' }: { sessionId: string; profileId: string; onFinish: () => void; language?: 'en'|'ru' }) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const [saved, setSaved] = useState<PracticeSession>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(true);
  const [reload, setReload] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const [answerText, setAnswerText] = useState('');
  const [completedAudio, setCompletedAudio] = useState<string | null>(null);
  const [audioFailed, setAudioFailed] = useState<string | null>(null);
  const pending = useRef<Command>();
  const sending = useRef(false);
  const audio = useRef<HTMLAudioElement>(null);
  const activePlayback = useRef<string | null>(null);
  const controller = useRef<AbortController>();
  const requestEpoch = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const draft = usePracticeDraft(saved, answerText, setAnswerText, language);
  const [conflictedText, setConflictedText] = useState('');
  const [wordSelection, setWordSelection] = useState<WordSelection>();
  const [wordEntry, setWordEntry] = useState<PassageWord>();
  useLayoutEffect(() => { setWordSelection(undefined); setWordEntry(undefined); }, [sessionId, profileId, saved?.item?.id]);

  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    const epoch = ++requestEpoch.current;
    pending.current = undefined; sending.current = false; setBusy(false);
    setCompletedAudio(null); setAudioFailed(null);
    setSaved(undefined); setError(''); setBlocked(false); setAnswerText('');
    void api<PracticeSession>(`/api/v1/learning-sessions/${sessionId}`, undefined, request.signal).then(value => {
      if (request.signal.aborted || requestEpoch.current !== epoch) return;
      if (value.profile_id !== profileId) throw new Error('Choose the learner who started this activity.');
      setSaved(value); setFeedback(true);
    }).catch(reason => { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : t('This activity could not open.','Не удалось открыть задание.')); });
    return () => request.abort();
  }, [sessionId, profileId, reload]);
  useEffect(() => { heading.current?.focus(); }, [saved?.completed_items, feedback]);

  async function submit(operation: Operation, answer?: {choice_id: string} | {text: string}, word?: WordSelection & {lemma?: string; pos?: string}) {
    if (!saved?.item || sending.current || blocked || saved.id !== sessionId || saved.profile_id !== profileId) return;
    if (pending.current && pending.current.operation !== operation) return;
    if (operation === 'attempts' && saved.item.type === 'listening_choice' && !saved.item.listened && !saved.item.transcript) return;
    if (draft.active && !await draft.flush()) return;
    if (sending.current || blocked) return;
    if (operation === 'attempts') audio.current?.pause();
    const epoch = requestEpoch.current;
    const signal = controller.current?.signal;
    if (!pending.current) pending.current = { operation, url: `/api/v1/learning-sessions/${sessionId}/${operation}`, body: {
      submission_id: crypto.randomUUID(), expected_revision: saved.revision, item_id: saved.item.id,
      ...(operation === 'attempts' ? { answer } : {}),
      ...(word ?? {}),
    } };
    sending.current = true; setBusy(true); setError('');
    try {
      const result = await api<PracticeSession & {word?: PassageWord}>(pending.current.url, pending.current.body, signal);
      if (signal?.aborted || requestEpoch.current !== epoch) return;
      if (result.profile_id !== profileId) throw new Error('The learner changed. Open this activity again.');
      pending.current = undefined; setSaved(result); setFeedback(operation === 'attempts');
      if (result.word) setWordEntry(result.word);
      if (operation === 'attempts') setAnswerText('');
    } catch (reason) {
      if (signal?.aborted || requestEpoch.current !== epoch) return;
      if (reason instanceof ApiError && reason.code === 'stale_revision' && reason.currentSession?.profile_id === profileId) {
        if (answerText) setConflictedText(answerText);
        pending.current = undefined; setSaved(reason.currentSession); setFeedback(true); setAnswerText('');
        setError('Practice changed in another tab. The latest saved answer is shown here.');
      } else if (reason instanceof ApiError && reason.code === 'audio_unavailable' && operation === 'listened') {
        pending.current = undefined; setCompletedAudio(null); setAudioFailed(playbackKey); setError('');
      } else if (reason instanceof ApiError && reason.code === 'vocabulary_enrichment_pending' && reason.currentSession?.profile_id === profileId) {
        const current = reason.currentSession as PracticeSession & {word?: PassageWord};
        pending.current = undefined; setSaved(current); setWordEntry(current.word); setError(reason.message);
      } else if (reason instanceof ApiError && ['locked', 'profile_changed', 'account_changed', 'access_required', 'adult_required', 'learner_required', 'content_unavailable', 'not_found', 'csrf_failed'].includes(reason.code)) {
        if (answerText) setConflictedText(answerText);
        pending.current = undefined; setBlocked(true); setSaved(undefined); setError(reason.message);
      } else if (operation === 'words' || operation === 'words/lookup') {
        setError(reason instanceof ApiError ? reason.message : t('Word help could not be confirmed. Try again.', 'Не удалось подтвердить подсказку. Повторите попытку.'));
      } else setError(operation === 'listened'
        ? 'We could not save your listening progress. Try saving again; you do not need to replay the audio.'
        : operation === 'transcript' ? 'The transcript could not open. Try again.'
        : 'We could not confirm the save. Your answer is still here. Try saving again.');
    } finally { if (!signal?.aborted && requestEpoch.current === epoch) { sending.current = false; setBusy(false); } }
  }

  const last = saved?.attempts.at(-1)?.feedback;
  const showResult = feedback && last;
  const isListening = saved?.item?.type === 'listening_choice';
  const listeningReady = !isListening || saved?.item?.listened || !!saved?.item?.transcript;
  const playbackKey = isListening && !showResult && saved?.status === 'active' && saved.id === sessionId && saved.profile_id === profileId
    ? `${profileId}:${sessionId}:${saved.item!.id}` : null;
  activePlayback.current = playbackKey;

  useLayoutEffect(() => {
    const player = audio.current;
    return () => { player?.pause(); };
  }, [playbackKey]);
  useEffect(() => {
    if (!completedAudio) return;
    if (completedAudio !== playbackKey) { setCompletedAudio(null); return; }
    // Wait for an in-flight hint request; the receipt must use its saved revision.
    if (busy || pending.current || blocked) return;
    setCompletedAudio(null);
    if (!saved?.item?.listened) void submit('listened');
  }, [completedAudio, playbackKey, busy, saved, blocked]);

  async function retryAudio() {
    const player = audio.current;
    const key = playbackKey;
    if (!player || !key) return;
    setAudioFailed(null);
    player.load();
    try { await player.play(); }
    catch { if (activePlayback.current === key) setAudioFailed(playbackKey); }
  }
  const passageWords = (text: string) => <PassageWords text={text} selection={wordSelection} entry={wordEntry}
    disabled={busy || !!pending.current} language={language} onClose={() => {if (!sending.current && !pending.current) {setWordSelection(undefined); setWordEntry(undefined); setError('');}}}
    onLookup={selection => {if (sending.current || pending.current || blocked) return; setWordSelection(selection); setWordEntry(undefined); void submit('words/lookup', undefined, selection);}}
    onSave={(lemma, pos) => {if (wordSelection) void submit('words', undefined, {...wordSelection, lemma, pos});}} />;
  return <section class={`page practice-page${saved?.item?.passage ? ' practice-reading-page' : ''}`}><div class="lesson-head"><a class="text-link" href={appUrl(saved?.sequence?.lesson_url ?? saved?.origin?.href ?? "#activities")}>{saved?.origin ? saved.origin.title : saved?.sequence ? t("Back to lesson", "К уроку") : t("Back to activities", "К занятиям")}</a><span class="quiet">{draft.active ? draft.status : busy ? t('Saving…','Сохраняем…') : pending.current ? t('Save not confirmed','Сохранение не подтверждено') : saved?.sequence ? (language === 'ru' ? saved.sequence.step_label_ru : saved.sequence.step_label) : saved?.origin ? `${Math.min(saved.completed_items + (showResult || saved.status === 'completed' ? 0 : 1), saved.total_items)} of ${saved.total_items}` : saved ? t('Progress saved','Прогресс сохранён') : ''}</span></div>
    {!saved ? <><h1 ref={heading} tabIndex={-1}>{error ? t('This activity could not open.','Не удалось открыть задание.') : t('Opening your practice…','Открываем практику…')}</h1>{error ? <><p role="alert">{error}</p><div class="action-row">{!blocked && <button class="cta" onClick={() => { pending.current = undefined; setReload(value => value + 1); }}>{t('Try again','Повторить')}</button>}<a href="/post/profiles">{t('Choose a profile','Выбрать профиль')}</a></div></> : <p role="status">{t('Loading your saved answers.','Загружаем сохранённые ответы.')}</p>}</>
      : <>{!saved.origin && !saved.sequence && <p class="kicker">{saved.title}</p>}{(!saved.origin && !saved.sequence || showResult || saved.status === 'completed') && <h1 ref={heading} tabIndex={-1}>{showResult ? last.deferred ? t('Reply saved.','Ответ сохранён.') : last.outcome === 'correct' ? t('That’s right.','Верно.') : t('Let’s look at the answer.','Посмотрим на ответ.') : saved.status === 'completed' ? t('Practice complete.','Практика завершена.') : t(`Question ${saved.completed_items + 1} of ${saved.total_items}`,`Вопрос ${saved.completed_items + 1} из ${saved.total_items}`)}</h1>}
        {showResult ? <Sheet>{saved.attempts.at(-1)?.prompt && <p class="practice-prompt">{saved.attempts.at(-1)?.prompt}</p>}{last.response_text !== undefined && <><p class="answer-label">{t('Your answer','Ваш ответ')}</p><p class="answer-text" lang="ru">{last.response_text}</p></>}{!last.deferred && (last.response_text === undefined || last.outcome !== 'correct') && <><p class="answer-label">{last.outcome === 'correct' ? t('Your answer','Ваш ответ') : t('The correct answer','Правильный ответ')}</p><p class="answer-text" lang="ru">{last.answer}</p></>}{last.transcript && <div class="practice-transcript"><p class="answer-label">{t('Transcript','Текст записи')}</p><p lang="ru">{last.transcript}</p></div>}{last.explanation && <p>{last.explanation}</p>}{last.deferred && <p>{t('Feedback follows after the questions about this recording.','Обратная связь появится после вопросов к этой записи.')}</p>}<p>{last.support?.includes('transcript') ? t('Transcript used','Использован текст записи') : last.support?.includes('model_answer') ? t('You have seen this answer before.','Вы уже видели этот ответ.') : last.assisted ? t('You used a hint for this question.','Вы использовали подсказку.') : t('Your answer has been saved.','Ваш ответ сохранён.')}</p><button class="cta" onClick={() => setFeedback(false)}>{saved.status === 'completed' ? t('Finish practice','Завершить практику') : t('Next question','Следующий вопрос')} <span aria-hidden="true">→</span></button></Sheet>
          : saved.status === 'completed' ? <Sheet><h2>{t(`You answered ${saved.total_items} ${saved.total_items === 1 ? 'question' : 'questions'}.`, `Вы ответили на вопросы: ${saved.total_items}.`)}</h2><p>{t('Your answers are saved. Choose another activity when you’re ready.','Ответы сохранены. Выберите следующее занятие, когда будете готовы.')}</p><details class="answer-history"><summary>{t('Review your answers','Посмотреть ответы')}</summary><ol>{saved.attempts.map(attempt => <li key={attempt.id}>
                {attempt.prompt && <p><strong lang="ru">{attempt.prompt}</strong></p>}
                <p><span lang="ru">{attempt.feedback.response_text ?? attempt.feedback.answer}</span> — {attempt.feedback.outcome === 'correct' ? t('answered correctly','правильный ответ') : t('try again','попробуйте ещё раз')}{attempt.feedback.support?.includes('transcript') ? t(' · Transcript used',' · Использован текст записи') : attempt.feedback.support?.includes('model_answer') ? t(' · Answer seen before',' · Ответ уже был показан') : attempt.feedback.assisted ? t(' with a hint',' с подсказкой') : ''}</p>
                {attempt.feedback.outcome !== 'correct' && attempt.feedback.response_text !== undefined && <p>{t('Correct answer: ','Правильный ответ: ')}<span lang="ru">{attempt.feedback.answer}</span></p>}
                {attempt.feedback.explanation && <p>{attempt.feedback.explanation}</p>}
              </li>)}</ol></details>{saved.origin || saved.sequence ? <a class="cta" href={appUrl(saved.sequence?.next_action?.url ?? saved.sequence?.lesson_url ?? saved.origin?.href ?? '/curriculum')}>{(language === 'ru' ? saved.sequence?.next_action?.label_ru : saved.sequence?.next_action?.label) ?? t('Continue learning','Продолжить урок')} →</a> : <button class="cta" onClick={onFinish}>{t('Back to activities','К занятиям')}</button>}</Sheet>
            : saved.item && <Sheet><div class={saved.item.passage ? 'practice-reading-layout' : undefined}>
              {saved.item.passage && <section class="practice-passage" lang="ru" aria-label={t('Reading text','Текст для чтения')}>
                {saved.item.word_lookup ? passageWords(saved.item.passage) : saved.item.passage.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}
              </section>}
              <div class={saved.item.passage ? 'practice-reading-question' : undefined}>
              {saved.origin || saved.sequence ? <h1 class="practice-prompt" ref={heading} tabIndex={-1} lang={saved.item.passage ? language : 'ru'}>{saved.item.prompt}</h1> : <h2 class="practice-prompt">{saved.item.prompt}</h2>}
              {isListening && <div class="practice-listening">
                {saved.item.audio && <audio key={playbackKey} ref={audio} controls preload="none" aria-label={t('Listen to the message','Послушать сообщение')} src={appUrl(saved.item.audio.url)}
                  onEnded={() => { if (playbackKey && activePlayback.current === playbackKey) setCompletedAudio(playbackKey); }}
                  onError={() => { if (playbackKey && activePlayback.current === playbackKey) setAudioFailed(playbackKey); }} />}
                {audioFailed === playbackKey && playbackKey && <div class="practice-audio-error" role="alert"><span>{t('The audio is unavailable.','Аудио недоступно.')}</span><button class="text-link" disabled={busy || !!pending.current} onClick={() => void retryAudio()}>{t('Retry audio','Повторить аудио')}</button></div>}
                {!saved.item.audio && <p>{t('The audio is unavailable. You can read the transcript.','Аудио недоступно. Можно прочитать текст.')}</p>}
                {saved.item.has_transcript && !saved.item.transcript && <button class="text-link" disabled={busy || !!pending.current} onClick={() => void submit('transcript')}>{t('Show transcript','Показать текст')}</button>}
                {saved.item.transcript && <div class="practice-transcript"><p class="answer-label">{t('Transcript','Текст записи')}</p>{saved.item.word_lookup ? passageWords(saved.item.transcript) : <p lang="ru">{saved.item.transcript}</p>}</div>}
              </div>}
              {saved.item.type === 'controlled_text' ? <form class="practice-answer-form" onSubmit={event => {event.preventDefault(); if(answerText.trim()) void submit('attempts', {text: answerText});}}>
                <label class="answer-label" htmlFor="practice-form-answer">{t('Your answer in Russian','Ваш ответ по-русски')}</label>
                <input id="practice-form-answer" type="text" lang="ru" autoComplete="off" autoCapitalize="off" spellcheck={false} maxLength={200} value={answerText} disabled={busy || !!pending.current} onInput={event => setAnswerText(event.currentTarget.value)} />
                <button class="cta" type="submit" disabled={busy || !!pending.current || !answerText.trim()}>{t('Check answer','Проверить ответ')}</button>
              </form> : <><p>{listeningReady ? t('Choose one answer.','Выберите ответ.') : t('Listen, then choose an answer.','Послушайте и выберите ответ.')}</p><div class="options">{saved.item.choices?.map(choice => <button key={choice.id} class="word" disabled={busy || !!pending.current || !listeningReady} onClick={() => void submit('attempts', {choice_id: choice.id})}>{choice.text}</button>)}</div></>}
              {saved.item.has_hint && !saved.item.hint && <button class="text-link" disabled={busy || !!pending.current} onClick={() => void submit('help')}>{t('Show a hint','Показать подсказку')}</button>}
              {saved.item.hint && <Feedback>{saved.item.hint}</Feedback>}
              {!!saved.item.asset_ids?.length && <div class="activity-media">{saved.item.asset_ids.map((id, index) => <a key={id} class="text-link" href={appUrl(`/api/v1/assets/${id}`)} target="_blank" rel="noopener">{t('Open supporting picture or audio','Открыть изображение или аудио')} {index + 1}</a>)}</div>}
              </div></div>
            </Sheet>}
        {error && <div role="alert" class="error-note"><p>{error}</p>{pending.current && <button class="cta" disabled={busy} onClick={() => void submit(pending.current!.operation)}>{t('Try saving again','Повторить сохранение')}</button>}</div>}
      </>}
    {draft.message && <div class="error-note" role="alert"><p>{draft.message}</p>{draft.state === 'failed' && <button class="text-link" onClick={() => void draft.flush()}>{t('Retry save','Повторить сохранение')}</button>}{draft.state === 'conflict' && <button class="text-link" onClick={() => {setConflictedText(answerText); setReload(value => value + 1);}}>{t('Load saved version','Загрузить сохранённую версию')}</button>}</div>}
    {draft.leaving && draft.state !== 'saving' && <div class="error-note" role="alert"><p>{t('Save your draft before leaving this activity.','Сохраните черновик перед выходом из задания.')}</p><div class="action-row"><button class="text-link" onClick={draft.cancelLeave}>{t('Stay here','Остаться')}</button><button class="text-link" onClick={draft.discardAndLeave}>{t('Leave without saving','Выйти без сохранения')}</button></div></div>}
    {conflictedText && <details class="answer-history" open><summary>{t('Your unsaved text','Ваш несохранённый текст')}</summary><textarea aria-label={t('Copy your unsaved text','Скопируйте несохранённый текст')} readOnly value={conflictedText} lang="ru" /></details>}
  </section>;
}
