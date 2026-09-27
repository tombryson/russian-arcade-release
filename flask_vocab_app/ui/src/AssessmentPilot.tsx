import { useEffect, useRef, useState } from 'preact/hooks';
import { api, ApiError } from './learning-api';
import { pilotPath, sendPilot, type AssessmentDomain, type PilotCommand, type PilotComponent, type PilotOverview, type PilotResponse, type PilotSession } from './assessment-api';
import { PilotRecording } from './PilotRecording';
import type { Language } from './review-types';
import './styles/assessment-pilot.css';

const domains: AssessmentDomain[] = ['language_use', 'reading', 'listening', 'writing', 'speaking'];
const labels = {
  language_use: ['Words & grammar', 'Лексика и грамматика'], reading: ['Reading', 'Чтение'],
  listening: ['Listening', 'Аудирование'], writing: ['Writing', 'Письмо'], speaking: ['Speaking', 'Говорение'],
};
const blockedCodes = ['profile_changed', 'account_changed', 'locked', 'access_required', 'learner_required', 'csrf_failed', 'not_found'];
const reviewing = (component?: PilotComponent) => component?.state === 'reviewing' || ['pending', 'running', 'reviewing'].includes(component?.attempt?.review_status ?? '');

export function AssessmentPilot({ sessionId, profileId, language = 'en' }: { sessionId?: string; profileId: string; language?: Language }) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const label = (domain: AssessmentDomain) => labels[domain][language === 'ru' ? 1 : 0];
  const [overview, setOverview] = useState<PilotOverview>();
  const [saved, setSaved] = useState<PilotSession>();
  const [active, setActive] = useState<AssessmentDomain>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [recordingLocked, setRecordingLocked] = useState(false);
  const [stale, setStale] = useState(false);
  const [reload, setReload] = useState(0);
  const pending = useRef<PilotCommand>();
  const sending = useRef(false);
  const controller = useRef<AbortController>();
  const epoch = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const visible = useRef<{ session?: string; profile: string }>({ profile: profileId });
  const drafts = useRef<Record<string, PilotResponse>>({});
  const nextDomain = useRef<AssessmentDomain>();
  visible.current = { session: saved?.id, profile: profileId };

  function accept(value: PilotSession) {
    if (value.profile_id !== profileId || sessionId && value.id !== sessionId) throw new ApiError(t('The profile changed. Reopen this skills check.', 'Профиль изменился. Откройте проверку заново.'), 'profile_changed');
    setSaved(value);
    setActive(current => current && value.components.some(row => row.domain === current) ? current : value.components.find(row => !row.attempt)?.domain ?? value.components[0]?.domain);
  }
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    const generation = ++epoch.current;
    pending.current = undefined; sending.current = false; drafts.current = {}; nextDomain.current = undefined;
    setBusy(false); setBlocked(false); setStale(false); setRecordingLocked(false); setError(''); setSaved(undefined); setOverview(undefined); setActive(undefined);
    void api<PilotOverview>(pilotPath, undefined, request.signal).then(async value => {
      if (request.signal.aborted || epoch.current !== generation || visible.current.profile !== profileId) return;
      if (value.profile_id !== profileId) throw new ApiError('Choose the profile that started this skills check.', 'profile_changed');
      setOverview(value);
      if (sessionId) {
        const snapshot = await api<PilotSession>(`${pilotPath}/sessions/${sessionId}`, undefined, request.signal);
        if (!request.signal.aborted && epoch.current === generation && visible.current.profile === profileId) accept(snapshot);
      }
    }).catch(reason => {
      if (!request.signal.aborted && epoch.current === generation) {
        setError(reason instanceof Error ? reason.message : t('Your skills check could not open.', 'Не удалось открыть проверку.'));
        if (reason instanceof ApiError && blockedCodes.includes(reason.code)) setBlocked(true);
      }
    });
    return () => request.abort();
  }, [sessionId, profileId, reload]);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [active, saved?.id]);

  // Reloading saved review state never starts or retries a paid assessment.
  const awaitingReview = saved?.components.some(reviewing);
  useEffect(() => {
    if (!saved || !awaitingReview || busy || blocked) return;
    const request = new AbortController();
    const id = saved.id; const generation = epoch.current;
    const timer = setTimeout(() => {
      void api<PilotSession>(`${pilotPath}/sessions/${id}`, undefined, request.signal).then(value => {
        if (!request.signal.aborted && generation === epoch.current && value.profile_id === profileId && value.id === id) setSaved(value);
      }).catch(() => { /* The saved reply remains visible; Refresh below is always available. */ });
    }, 2000);
    return () => { clearTimeout(timer); request.abort(); };
  }, [saved, awaitingReview, busy, blocked, profileId]);

  async function run(command: PilotCommand) {
    if (sending.current || blocked || pending.current && pending.current !== command) return;
    const generation = epoch.current; const signal = controller.current?.signal;
    if (!signal) return;
    pending.current = command; sending.current = true; setBusy(true); setError('');
    try {
      const result = await sendPilot(command, signal);
      if (signal.aborted || generation !== epoch.current || visible.current.profile !== profileId) return;
      accept(result); pending.current = undefined;
      if (command.action === 'draft' && !(command.body instanceof FormData)) {
        const identity = (command.body as { component_id?: string }).component_id;
        if (identity) delete drafts.current[identity];
      }
      if (nextDomain.current) { setActive(nextDomain.current); nextDomain.current = undefined; }
      if (!sessionId) window.location.hash = `assessment/${result.id}`;
    } catch (reason) {
      if (signal.aborted || generation !== epoch.current) return;
      if (reason instanceof ApiError && blockedCodes.includes(reason.code)) {
        pending.current = undefined; setBlocked(true); setSaved(undefined); setOverview(undefined);
      } else if (reason instanceof ApiError && ['invalid_audio', 'invalid_input', 'component_busy'].includes(reason.code)) {
        // A rejected command was not saved. Keep local work and allow a reload
        // instead of repeatedly sending a known rejected request.
        pending.current = undefined; nextDomain.current = undefined;
      } else if (reason instanceof ApiError && reason.code === 'audio_unavailable' && command.action === 'support') {
        pending.current = undefined;
        setSaved(current => current ? { ...current, components: current.components.map(row => row.domain === 'listening' ? { ...row, audio_available: false } : row) } : current);
      } else if (reason instanceof ApiError && ['stale_revision', 'stale_component', 'pilot_changed', 'component_changed', 'already_submitted', 'invalid_saved_task'].includes(reason.code)) {
        pending.current = undefined; setStale(true);
        setError(t('This check changed in another tab. Reload the saved version before continuing.', 'Проверка изменилась в другой вкладке. Загрузите сохранённую версию.'));
        return;
      }
      setError(reason instanceof Error ? reason.message : t('The save could not be confirmed. Try again.', 'Не удалось подтвердить сохранение. Попробуйте ещё раз.'));
    } finally {
      if (!signal.aborted && generation === epoch.current) { sending.current = false; setBusy(false); }
    }
  }
  function componentCommand(component: PilotComponent, operation: string, extra: object = {}) {
    if (!saved) return;
    return run({ url: `${pilotPath}/sessions/${saved.id}/components/${component.domain}/${operation}`,
      action: operation, body: { submission_id: crypto.randomUUID(), component_id: component.id, ...(operation === 'review' ? {} : { expected_revision: component.revision }), ...extra } });
  }
  const component = saved?.components.find(row => row.domain === active);
  const frozen = busy || !!pending.current || blocked || stale;
  const completed = saved?.components.filter(row => row.attempt && !reviewing(row)).length ?? 0;
  return <section class="page assessment-pilot">
    <div class="pilot-topline"><a class="text-link" href="/curriculum">← {t('Curriculum', 'Учебная программа')}</a><span class="quiet">{t('A1 skills check · Pilot', 'Проверка навыков A1 · Пробная версия')}</span></div>
    {error && <div class="pilot-error" role="alert"><p>{error}</p><div class="action-row">
      {!blocked && pending.current && <button class="cta" disabled={busy} onClick={() => void run(pending.current!)}>{t('Try saving again', 'Повторить сохранение')}</button>}
      {!blocked && !pending.current && <button class="text-link" onClick={() => setReload(value => value + 1)}>{t('Reload saved check', 'Загрузить сохранённую проверку')}</button>}
      {blocked && <a href="/post/profiles">{t('Choose a profile', 'Выбрать профиль')}</a>}
    </div></div>}
    {(!overview || sessionId && !saved) && !error && <p role="status">{t('Opening your skills check…', 'Открываем проверку…')}</p>}
    {overview && !saved && !sessionId && <>
      <h1 ref={heading} tabIndex={-1}>{t('Check your A1 skills', 'Проверьте свои навыки A1')}</h1>
      <p class="pilot-intro">{t('Five short tasks show what to practise next. You can stop and return to your saved work.', 'Пять коротких заданий помогут выбрать дальнейшую практику. Можно остановиться и продолжить позже.')}</p>
      <ol class="pilot-overview">{domains.map(domain => <li key={domain}><strong>{label(domain)}</strong></li>)}</ol>
      <p class="quiet">{t('This pilot gives feedback. It does not award a level or change access to activities.', 'Это пробная проверка с обратной связью. Она не присваивает уровень и не меняет доступ к занятиям.')}</p>
      {overview.enabled && overview.recordings_ready === false && <p class="quiet">{t('Listening is unavailable. You can check the other skills now.', 'Аудирование пока недоступно. Можно проверить остальные навыки.')}</p>}
      {overview.active_session ? <a class="cta" href={`#assessment/${overview.active_session.id}`}>{t('Continue your check', 'Продолжить проверку')} →</a>
        : !overview.enabled ? <p>{t('This skills check is not available yet.', 'Эта проверка пока недоступна.')}</p>
        : <button class="cta" disabled={frozen} onClick={() => void run({ url: `${pilotPath}/sessions`, action: 'start', body: { submission_id: crypto.randomUUID() } })}>{busy ? t('Opening…', 'Открываем…') : t('Start the skills check', 'Начать проверку')} →</button>}
      {overview.sessions.length > 0 && <details class="pilot-history"><summary>{t('Previous checks', 'Предыдущие проверки')}</summary><ul>{overview.sessions.map(row => <li key={row.id}><a href={`#assessment/${row.id}`}>{t('Open saved check', 'Открыть проверку')} · {new Date(row.created_at * 1000).toLocaleDateString(language === 'ru' ? 'ru' : 'en')}</a></li>)}</ul></details>}
    </>}
    {saved && <>
      <div class="pilot-heading"><h1 ref={heading} tabIndex={-1}>{t('Your A1 skills check', 'Ваша проверка навыков A1')}</h1><span>{completed}/5 {t('saved', 'сохранено')}</span></div>
      <nav class="pilot-domains" aria-label={t('Skills', 'Навыки')}>{saved.components.map(row => <button type="button" key={row.domain} disabled={frozen || recordingLocked} aria-current={active === row.domain ? 'step' : undefined} onClick={() => {
        if (component && !component.attempt && drafts.current[component.id]) {
          nextDomain.current = row.domain; void componentCommand(component, 'draft', { response: drafts.current[component.id] });
        } else setActive(row.domain);
      }}>{label(row.domain)}{row.attempt && !reviewing(row) && <><span aria-hidden="true"> ✓</span><span class="sr-only"> · {t('saved', 'сохранено')}</span></>}</button>)}</nav>
      {component && <PilotTask key={`${profileId}:${saved.id}:${component.id}:${component.attempt?.submission_id ?? 'draft'}`} component={component} language={language} disabled={frozen} busy={busy}
        onDraft={response => { drafts.current[component.id] = response; }}
        onRecordingLock={setRecordingLocked}
        configured={component.domain === 'writing' || component.domain === 'speaking' ? overview?.configured[component.domain] !== false : true}
        onSave={(response, operation) => void componentCommand(component, operation, { response })}
        onSupport={kind => void componentCommand(component, 'support', { kind })}
        onReview={() => void componentCommand(component, 'review')}
        onRetry={() => void run({ url: `${pilotPath}/sessions/${saved.id}/retry`, action: 'retry', body: { submission_id: crypto.randomUUID(), components: [{ domain: component.domain, component_id: component.id }] } })}
        onAudio={(clip, filename) => {
          const form = new FormData(); form.append('audio', clip, filename); form.append('submission_id', crypto.randomUUID()); form.append('component_id', component.id); form.append('expected_revision', String(component.revision));
          void run({ url: `${pilotPath}/sessions/${saved.id}/components/speaking/attempts`, action: 'attempts', body: form });
        }}
        onRefresh={() => setReload(value => value + 1)} />}
      {completed === saved.components.length && <p class="pilot-summary">{t('All five tasks are saved. Review each skill above, or return to the curriculum to practise.', 'Все пять заданий сохранены. Посмотрите обратную связь по каждому навыку или вернитесь к учебной программе.')}</p>}
    </>}
  </section>;
}

function PilotTask({ component, language, disabled, busy, configured, onDraft, onRecordingLock, onSave, onSupport, onAudio, onReview, onRetry, onRefresh }: {
  component: PilotComponent; language: Language; disabled: boolean; busy: boolean; configured: boolean;
  onSave: (response: PilotResponse, operation: 'draft' | 'attempts') => void; onSupport: (kind: string) => void;
  onDraft: (response: PilotResponse) => void;
  onRecordingLock: (locked: boolean) => void;
  onAudio: (clip: Blob, filename: string) => void; onReview: () => void; onRetry: () => void; onRefresh: () => void;
}) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const [answers, setAnswers] = useState<Record<string, string>>(component.draft && 'answers' in component.draft ? component.draft.answers : {});
  const [text, setText] = useState(component.draft && 'text' in component.draft ? component.draft.text : '');
  const [clip, setClip] = useState<{ blob: Blob; filename: string }>();
  const [audioFailed, setAudioFailed] = useState(false);
  const [audioEnded, setAudioEnded] = useState(false);
  const player = useRef<HTMLAudioElement>(null);
  const playback = useRef(true);
  useEffect(() => { playback.current = true; return () => { playback.current = false; player.current?.pause(); }; }, []);
  const listening = component.domain === 'listening';
  const ready = !listening || component.listened || component.transcript_visible;
  const response: PilotResponse = component.domain === 'writing' ? { text } : { answers };
  const complete = component.domain === 'writing' ? !!text.trim() : !!component.questions?.length && component.questions.every(question => !!answers[question.id]);
  const attempt = component.attempt;
  const unavailable = attempt?.response && 'unavailable' in attempt.response && attempt.response.unavailable === true;
  const reviewUnavailable = attempt && (['failed', 'review_unavailable', 'expired'].includes(attempt.review_status) || attempt.outcome === 'review_unavailable' || component.state === 'review_unavailable');
  const notes = attempt?.production_feedback;
  const support = attempt?.support ?? component.support ?? [];
  useEffect(() => {
    if (audioEnded && !disabled && !component.listened && !attempt) { setAudioEnded(false); onSupport('listened'); }
  }, [audioEnded, disabled, component.listened, attempt]);
  return <div class="pilot-task">
    <h2>{language === 'ru' ? component.title_ru ?? component.title : component.title}</h2>
    {!unavailable && <p class="pilot-instruction">{language === 'ru' ? component.prompt_ru ?? component.prompt : component.prompt}</p>}
    {attempt ? <div class="pilot-result">
      {reviewing(component) ? <><p role="status">{t('Your reply is saved. Preparing feedback…', 'Ответ сохранён. Готовим обратную связь…')}</p><button class="text-link" disabled={disabled} onClick={onRefresh}>{t('Refresh feedback', 'Обновить обратную связь')}</button></>
        : <><h3>{unavailable ? listening ? t('Listening was not measured.', 'Аудирование не оценивалось.') : t('Speaking was not measured.', 'Говорение не оценивалось.') : attempt.outcome === 'demonstrated_in_task' ? t('You handled this task well.', 'Вы справились с этим заданием.') : attempt.outcome === 'more_evidence_needed' ? t('A little more is needed to give useful feedback.', 'Нужно больше информации для обратной связи.') : reviewUnavailable ? t('Your reply is saved. Feedback is not ready.', 'Ответ сохранён. Обратная связь пока недоступна.') : t('Here is what to practise next.', 'Вот что можно потренировать.')}</h3>
          {attempt.feedback && <p>{attempt.feedback}</p>}
          {!unavailable && attempt.criteria?.map((criterion, index) => <p key={index}>{criterion.label && <strong>{language === 'ru' ? criterion.label_ru ?? criterion.label : criterion.label}: </strong>}{criterion.feedback}</p>)}
          {reviewUnavailable && <button class="cta" disabled={disabled} onClick={onReview}>{busy ? t('Checking…', 'Проверяем…') : t('Try feedback again', 'Запросить обратную связь ещё раз')}</button>}
          <button class="text-link" disabled={disabled} onClick={onRetry}>{t('Try this skill again', 'Повторить задание')}</button></>}
      {support.length > 0 && <p class="quiet">{support.includes('transcript') ? t('You used the transcript for this reply.', 'Вы использовали текст записи.') : t('You used help with this reply.', 'Вы использовали подсказку.')}</p>}
      {notes && <details class="pilot-detail-feedback"><summary>{component.domain === 'speaking' ? t('Speaking feedback', 'Обратная связь по речи') : t('Writing feedback', 'Обратная связь по письму')}</summary>
        {notes.grammar?.reason && <p><strong>{t('Grammar: ', 'Грамматика: ')}</strong>{notes.grammar.reason}</p>}
        {notes.fluency?.reason && <p><strong>{t('Fluency: ', 'Беглость: ')}</strong>{notes.fluency.reason}</p>}
        {notes.corrections?.length ? <ul>{notes.corrections.map((correction, index) => <li key={index}><span lang="ru">{correction.original}</span> → <strong lang="ru">{correction.replacement}</strong><p>{correction.explanation}</p></li>)}</ul> : null}
        {notes.example && <p class="pilot-passage" lang="ru">{notes.example}</p>}
        {notes.uncertainty && <p class="quiet">{Array.isArray(notes.uncertainty) ? notes.uncertainty.join(' ') : notes.uncertainty}</p>}
        {notes.transcript && <details><summary>{t('Transcript', 'Расшифровка')}</summary><p class="quiet">{t('The transcript may contain recognition errors.', 'В расшифровке могут быть ошибки распознавания.')}</p><p class="pilot-passage" lang="ru">{notes.transcript}</p></details>}
      </details>}
      {attempt.recording_url && <audio controls preload="none" src={attempt.recording_url} aria-label={t('Your saved recording', 'Ваша сохранённая запись')} />}
      {attempt.response && 'text' in attempt.response && <details><summary>{t('Your reply', 'Ваш ответ')}</summary><p lang="ru" class="pilot-passage">{attempt.response.text}</p></details>}
    </div> : <>
      {component.passage && <div class="pilot-passage" lang="ru">{component.passage}</div>}
      {listening && <div class="pilot-listening">
        {component.audio_url && <audio ref={player} controls preload="none" src={component.audio_url} aria-label={t('Listen to the message', 'Прослушать сообщение')} onEnded={() => { if (playback.current && !component.listened) setAudioEnded(true); }} onError={() => { if (playback.current) setAudioFailed(true); }} />}
        {(audioFailed || component.audio_available === false) && <p role="alert">{t('The recording is unavailable. You can read the transcript or continue without a listening result.', 'Запись недоступна. Можно прочитать текст или продолжить без результата по аудированию.')} {component.audio_url && <button class="text-link" disabled={disabled} onClick={() => { setAudioFailed(false); player.current?.load(); }}>{t('Retry audio', 'Повторить аудио')}</button>}</p>}
        {(audioFailed || component.audio_available === false) && <button class="text-link" disabled={disabled} onClick={() => onSave({ unavailable: true }, 'attempts')}>{t('Continue without listening', 'Продолжить без аудирования')}</button>}
        {!component.transcript_visible && <button class="text-link" disabled={disabled} onClick={() => onSupport('transcript')}>{t('Show transcript', 'Показать текст записи')}</button>}
        {component.transcript_visible && <p class="quiet">{t('Transcript used', 'Текст записи открыт')}</p>}
      </div>}
      {component.domain === 'speaking' ? <>
        <PilotRecording disabled={disabled} language={language} onLockChange={onRecordingLock} limit={component.max_duration_seconds ?? 60} onReady={(blob, filename) => setClip(blob ? { blob, filename: filename ?? 'reply.webm' } : undefined)} />
        <button class="cta" disabled={disabled || !clip} onClick={() => { if (clip) onAudio(clip.blob, clip.filename); }}>{busy ? t('Saving your reply…', 'Сохраняем ответ…') : t('Send your reply', 'Отправить ответ')}</button>
        {!clip && <button class="text-link" disabled={disabled} onClick={() => onSave({ unavailable: true }, 'attempts')}>{t('Continue without a recording', 'Продолжить без записи')}</button>}
      </> : <form onSubmit={event => { event.preventDefault(); if (complete && ready && !disabled) { player.current?.pause(); onSave(response, 'attempts'); } }}>
        {component.domain === 'writing' ? <label class="pilot-writing"><span>{t('Your message in Russian', 'Ваше сообщение по-русски')}</span><textarea lang="ru" maxLength={12000} value={text} disabled={disabled} onInput={event => { setText(event.currentTarget.value); onDraft({ text: event.currentTarget.value }); }} rows={7} /></label>
          : <div class="pilot-questions">{component.questions?.map(question => <fieldset key={question.id} disabled={disabled || !ready}><legend lang="ru">{question.prompt}</legend>{question.choices.map(choice => <label key={choice.id} class="pilot-choice"><input type="radio" name={question.id} value={choice.id} checked={answers[question.id] === choice.id} onChange={() => { const next = { ...answers, [question.id]: choice.id }; setAnswers(next); onDraft({ answers: next }); }} /><span lang="ru">{choice.text}</span></label>)}</fieldset>)}</div>}
        {!ready && component.audio_available !== false && <p class="quiet">{t('Listen to the recording before choosing your answers.', 'Прослушайте запись, затем выберите ответы.')}</p>}
        <div class="action-row"><button class="cta" type="submit" disabled={disabled || !complete || !ready}>{busy ? t('Saving your reply…', 'Сохраняем ответ…') : configured ? t('Check my reply', 'Проверить ответ') : t('Save my reply', 'Сохранить ответ')}</button><button class="text-link" type="button" disabled={disabled} onClick={() => onSave(response, 'draft')}>{t('Save for later', 'Сохранить на потом')}</button></div>
      </form>}
      {!configured && <p class="quiet">{t('Feedback is currently unavailable. You can save your reply and request feedback later.', 'Обратная связь сейчас недоступна. Сохраните ответ и запросите её позже.')}</p>}
      {!component.hint && <button class="text-link" disabled={disabled} onClick={() => onSupport('hint')}>{t('Show a hint', 'Показать подсказку')}</button>}
      {component.hint && <p class="pilot-hint">{component.hint}</p>}
    </>}
  </div>;
}
