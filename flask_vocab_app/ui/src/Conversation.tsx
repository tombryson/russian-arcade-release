import { useEffect, useRef, useState } from 'preact/hooks';
import { api, upload } from './learning-api';
import type { Language } from './review-types';
import './styles/conversation.css';
import { russianTranscript } from './conversation-transcript';

type Transcript = { text: string; model: string; style: string; latency_ms: number };
type Correction = { original: string; replacement: string; explanation: string };
type Turn = { id: string; ordinal: number; state: string; duration_seconds: number; case_id: string | null;
  transcript: Transcript | null; reply: { russian: string; english: string } | null;
  assessment: { communication: string; uncertainty: string; corrections: Correction[]; basis: string } | null;
  comparisons: { provider: string; transcription?: Transcript; error?: string }[] | null;
  recording_url: string; reply_audio_url: string | null; assessment_state: string; audio_state: string;
  error: string | null; assessment_error: string | null; audio_error: string | null; retryable: boolean; working: boolean };
type Scenario = { title: string; title_ru: string; description: string; description_ru: string; opening: string; opening_english: string };
type Session = { id: string; mode: 'conversation' | 'lab'; state: string; scenario: Scenario; turns: Turn[]; greeting_audio_url: string | null };
type Case = { id: string; category: string; text: string; corrected: string; note: string };
type Options = { scenario: Scenario; cases: Case[]; configured: boolean; audio_configured: boolean; transcription_model: string;
  comparison_model: string; conversation_model: string; sessions: { id: string; mode: string; state: string; created_at: number }[] };

function Player({ src, label, autoPlay = false }: { src: string; label: string; autoPlay?: boolean }) {
  return <audio controls preload="metadata" autoPlay={autoPlay} src={src} aria-label={label} />;
}

export function Conversation({ sessionId, lab = false, language = 'en' }: { sessionId?: string; lab?: boolean; language?: Language }) {
  const ru = language === 'ru';
  const t = (en: string, russian: string) => ru ? russian : en;
  const [options, setOptions] = useState<Options>();
  const [session, setSession] = useState<Session>();
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [autoPlayTurn, setAutoPlayTurn] = useState('');
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [requestingMic, setRequestingMic] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [clip, setClip] = useState<Blob>();
  const [clipUrl, setClipUrl] = useState('');
  const [filename, setFilename] = useState('recording.webm');
  const [caseId, setCaseId] = useState('genitive');
  const [showTranslations, setShowTranslations] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const recorder = useRef<MediaRecorder>();
  const stream = useRef<MediaStream>();
  const timer = useRef<ReturnType<typeof setInterval>>();
  const alive = useRef(true);
  const startKey = useRef(crypto.randomUUID());
  const submission = useRef(crypto.randomUUID());
  const polling = useRef<AbortController>();
  const pageAbort = useRef(new AbortController());
  const latestReply = useRef<HTMLParagraphElement>(null);
  const followTurn = useRef('');

  useEffect(() => {
    alive.current = true;
    const controller = pageAbort.current;
    void (async () => {
      try {
        await api('/api/v1/household', undefined, controller.signal);
        const next = await api<Options>('/api/v1/conversations/options', undefined, controller.signal);
        if (!controller.signal.aborted) setOptions(next);
        if (sessionId) {
          const saved = await api<Session>(`/api/v1/conversations/${sessionId}`, undefined, controller.signal);
          if (!controller.signal.aborted) setSession(saved);
        }
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Unable to open the conversation.'); }
    })();
    return () => {
      alive.current = false; controller.abort(); polling.current?.abort();
      if (recorder.current?.state === 'recording') recorder.current.stop();
      stream.current?.getTracks().forEach(track => track.stop());
      clearInterval(timer.current);
    };
  }, [sessionId]);

  useEffect(() => {
    if (!clip) { setClipUrl(''); return; }
    const url = URL.createObjectURL(clip); setClipUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [clip]);

  const working = session?.turns.some(turn => turn.working) ?? false;
  useEffect(() => {
    if (!sessionId || !working) return;
    let stopped = false;
    let timeout: ReturnType<typeof setTimeout>;
    const controller = new AbortController(); polling.current = controller;
    const poll = async () => {
      try {
        const saved = await api<Session>(`/api/v1/conversations/${sessionId}`, undefined, controller.signal);
        if (!stopped) { setSession(previous => previous && previous.turns.length>saved.turns.length ? previous : saved); setPollError(''); }
      } catch (e) { if (!stopped) setPollError(t('Connection interrupted. Your recording is saved; reconnecting…', 'Связь прервалась. Запись сохранена. Подключаемся…')); }
      if (!stopped) timeout = setTimeout(() => void poll(), 1500);
    };
    timeout = setTimeout(() => void poll(), 1200);
    return () => { stopped = true; clearTimeout(timeout); controller.abort(); };
  }, [sessionId, working]);

  const newest = session?.turns.at(-1);
  useEffect(() => {
    if (newest?.reply && newest.id===followTurn.current) {
      latestReply.current?.focus({preventScroll:true});
      latestReply.current?.scrollIntoView?.({block:'center'});
      followTurn.current='';
    }
  }, [newest?.id, newest?.reply?.russian]);

  async function action<T>(run: () => Promise<T>, done: (result: T) => void) {
    if (busy) return;
    setBusy(true); setError('');
    try { const result = await run(); if (alive.current) done(result); }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : t('Please try again.', 'Попробуйте ещё раз.')); }
    finally { if (alive.current) setBusy(false); }
  }

  async function record() {
    if (requestingMic || recording) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError(t('This browser cannot record audio. Upload a recording below, or open this page in Chrome or Safari.', 'В этом браузере запись недоступна. Загрузите аудиофайл или откройте страницу в Chrome или Safari.')); return;
    }
    setError(''); setRequestingMic(true);
    setAutoPlayTurn('');
    document.querySelectorAll('audio').forEach(audio => audio.pause());
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const mime = ['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const rec = new MediaRecorder(media, mime ? {mimeType:mime} : undefined);
      recorder.current = rec;
      const chunks: Blob[] = [];
      rec.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      rec.onstop = () => {
        media.getTracks().forEach(track => track.stop()); clearInterval(timer.current);
        if (!alive.current) return;
        setRecording(false);
        const blob = new Blob(chunks, {type:rec.mimeType});
        if (blob.size) {
          setClip(blob); setFilename(`recording.${rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'}`);
          submission.current = crypto.randomUUID();
        }
      };
      rec.onerror = () => { media.getTracks().forEach(track => track.stop()); clearInterval(timer.current); if (alive.current) { setRecording(false); setError(t('Recording stopped unexpectedly. Please try again.', 'Запись прервалась. Попробуйте ещё раз.')); } };
      setClip(undefined); setElapsed(0); setRecording(true); rec.start();
      const started = Date.now();
      timer.current = setInterval(() => { const seconds = Math.floor((Date.now()-started)/1000); setElapsed(seconds); if (seconds>=60 && rec.state==='recording') rec.stop(); }, 250);
    } catch {
      stream.current?.getTracks().forEach(track => track.stop());
      if (alive.current) setError(t('Microphone access was not available. Allow it in your browser, or upload an audio file.', 'Нет доступа к микрофону. Разрешите доступ в браузере или загрузите аудиофайл.'));
    } finally { if (alive.current) setRequestingMic(false); }
  }

  function send() {
    if (!clip || !session) return;
    const form = new FormData(); form.append('audio',clip,filename); form.append('submission_id',submission.current);
    if (session.mode==='lab') form.append('case_id',caseId);
    void action(() => upload<Session>(`/api/v1/conversations/${session.id}/turns`,form,pageAbort.current.signal), saved => {
      const id=saved.turns.at(-1)?.id ?? '';followTurn.current=id;setAutoPlayTurn(id);setSession(saved);setClip(undefined);
    });
  }

  const isLab = session ? session.mode==='lab' : lab;
  const selected = options?.cases.find(c => c.id===caseId);
  const pending = session?.turns.some(turn => turn.state!=='ready');
  const title = isLab ? t('Speech lab', 'Проверка распознавания') : t('Saved conversation', 'Сохранённый разговор');

  return <section class="page conversation-page">
    <a class="text-link" href="#speaking">← {t('Speaking', 'Разговорная практика')}</a>
    <div class="conversation-heading"><div><p class="kicker">{t('Speaking practice', 'Разговорная практика')}</p><h1>{title}</h1></div><span class="conversation-sign" aria-hidden="true">{isLab ? 'А → а' : 'кафе'}</span></div>
    <p class="intro">{isLab ? t('Can the transcriber keep a grammatical mistake exactly as spoken?', 'Сохранит ли модель грамматическую ошибку так, как она прозвучала?') : t('Listen back to your conversation and revisit the language notes.', 'Прослушайте разговор и вернитесь к замечаниям по языку.')}</p>
    {error && <p class="error-note" role="alert">{error}</p>}
    {pollError && <p class="quiet" role="status">{pollError}</p>}
    {!options && !error && <p role="status">{t('Opening…', 'Открываем…')}</p>}
    {options && !session && !sessionId && isLab && <>
      <div class="conversation-start"><p>{t('Read a test sentence, including its deliberate mistake. Compare MAI verbatim, MAI clean and OpenAI on the same recording.', 'Прочитайте предложение с намеренной ошибкой. Сравните три варианта распознавания одной записи.')}</p>
        <button class="cta" disabled={busy || !options.configured} onClick={() => void action(() => api<Session>('/api/v1/conversations',{submission_id:startKey.current,mode:'lab',language},pageAbort.current.signal), saved => {window.location.hash=`speaking/recorded/${saved.id}`;})}>{busy ? t('Opening…','Открываем…') : t('Start a speech test','Начать проверку')} <span aria-hidden="true">→</span></button>
        {!options.configured && <p class="error-note">{t('Add the OpenRouter and OpenAI keys to your existing .env file to begin.', 'Для начала нужны ключи OpenRouter и OpenAI в файле .env.')}</p>}
        <p class="quiet">{t('Recordings are saved with this test and sent to speech providers for processing. You can delete them when you finish.', 'Записи сохраняются с этой проверкой и отправляются сервисам распознавания. После проверки их можно удалить.')}</p>
      </div>
      {!!options.sessions.filter(s => s.mode === 'lab').length && <details class="conversation-history"><summary>{t('Previous speech tests','Предыдущие проверки речи')}</summary><ul>{options.sessions.filter(s => s.mode === 'lab').map(s => <li key={s.id}><a href={`#speaking/recorded/${s.id}`}>{t('Speech test','Проверка речи')} · {new Date(s.created_at*1000).toLocaleString(ru?'ru':'en')}</a></li>)}</ul></details>}
    </>}
    {session && <>
      {!isLab && <a class="cta" href="#speaking">{t('Start speaking', 'Начать разговор')} ↗</a>}
      {!isLab && <>
        <label class="conversation-translation"><input type="checkbox" checked={showTranslations} onChange={e => setShowTranslations(e.currentTarget.checked)} /> {t('Show English translations', 'Показать перевод на английский')}</label>
        <div class="conversation-bubble"><span class="conversation-speaker">{t('Café worker', 'Сотрудник кафе')}</span><p lang="ru">{session.scenario.opening}</p>{showTranslations && <p class="conversation-english" lang="en">{session.scenario.opening_english}</p>}
          {session.greeting_audio_url && <Player src={session.greeting_audio_url} label={t('Listen to the greeting','Послушать приветствие')} />}
        </div>
      </>}
      <div class="conversation-thread">{session.turns.map(turn => <article key={turn.id} class="conversation-turn">
        <div class="conversation-you"><span class="conversation-speaker">{t('Your reply','Ваш ответ')} {turn.ordinal}</span>
          <Player src={turn.recording_url} label={`${t('Your recording','Ваша запись')} ${turn.ordinal}`} />
          {turn.transcript && <details open={isLab}><summary>{t('What the app heard','Что распознало приложение')}</summary>{isLab || russianTranscript(turn.transcript.text) !== null ? <p lang="ru">{turn.transcript.text}</p> : <p class="quiet">{t('No Russian transcript to show.','Нет русского текста для показа.')}</p>}<span class="quiet">{turn.transcript.model} · {turn.transcript.style} · {(turn.transcript.latency_ms/1000).toFixed(1)}s</span></details>}
        </div>
        {turn.reply && <div class="conversation-bubble"><span class="conversation-speaker">{t('Café worker','Сотрудник кафе')}</span><p lang="ru" tabIndex={-1} ref={turn.id===newest?.id ? latestReply : undefined}>{turn.reply.russian}</p>{showTranslations && <p class="conversation-english" lang="en">{turn.reply.english}</p>}{turn.reply_audio_url ? <Player src={turn.reply_audio_url} autoPlay={turn.id===autoPlayTurn} label={`${t('Listen to reply','Послушать ответ')} ${turn.ordinal}`} /> : turn.audio_state==='pending' && <p class="quiet" role="status">{t('Preparing the voice…','Готовим голос…')}</p>}{turn.audio_error && <p class="quiet">{turn.audio_error}</p>}</div>}
        {isLab && turn.comparisons?.map(result => <div class="speech-comparison" key={result.provider}>{result.transcription ? <><strong>{result.transcription.model} · {result.transcription.style}</strong><p lang="ru">{result.transcription.text}</p><span class="quiet">{(result.transcription.latency_ms/1000).toFixed(1)}s</span></> : <p class="error-note">{result.error}</p>}</div>)}
        {isLab && <p class="quiet">{t('Script to compare with:', 'Исходный текст:')} <span lang="ru">{options?.cases.find(c=>c.id===turn.case_id)?.text}</span></p>}
        {turn.assessment && <details class="conversation-coaching" open={session.state==='completed'}><summary>{t('Language notes','Замечания по языку')}</summary><p class="quiet">{t('Based on the transcript. Listen to your recording before treating a suggestion as a spoken mistake.', 'На основе распознанного текста. Прослушайте запись, прежде чем считать замечание ошибкой в речи.')}</p><p>{turn.assessment.communication}</p>{turn.assessment.corrections.map((c,i) => <div class="conversation-correction" key={i}><span lang="ru">{c.original}</span> <span aria-hidden="true">→</span> <strong lang="ru">{c.replacement}</strong><p>{c.explanation}</p></div>)}{turn.assessment.uncertainty && <p>{turn.assessment.uncertainty}</p>}</details>}
        {turn.error && <p class="error-note">{turn.error}</p>}{turn.assessment_error && <p class="quiet">{turn.assessment_error}</p>}
        {turn.working && <p class="quiet" role="status">{turn.state!=='ready' ? t('Listening and preparing your reply…','Распознаём речь и готовим ответ…') : t('Finishing audio and language notes…','Завершаем аудио и замечания…')}</p>}
        {turn.retryable && <button class="text-link" disabled={busy} onClick={() => void action(() => api<Session>(`/api/v1/conversations/${session.id}/turns/${turn.id}/retry`,{},pageAbort.current.signal),setSession)}>{t('Retry unfinished steps','Повторить незавершённые шаги')}</button>}
      </article>)}</div>
      {isLab && session.state==='active' && session.turns.length<8 && !pending && <div class="conversation-recorder">
        {isLab && <div class="speech-script"><label for="speech-case">{t('Test sentence','Тестовое предложение')}</label><select id="speech-case" value={caseId} disabled={recording || busy || !!clip} onChange={e=>setCaseId(e.currentTarget.value)}>{options?.cases.map(c=><option key={c.id} value={c.id}>{c.text}</option>)}</select><p lang="ru">{selected?.text}</p><p class="quiet">{t('Read the sentence as written, including any mistake. It is not sent to the recogniser.', 'Прочитайте текст как написано, включая ошибку. Текст не отправляется распознавателю.')}</p></div>}
        <div class="conversation-mic-row"><button class={`conversation-mic ${recording?'is-recording':''}`} disabled={busy || requestingMic} onClick={() => recording ? recorder.current?.stop() : void record()}>{recording ? <><span aria-hidden="true">■</span> {t('Stop recording','Остановить запись')} · {elapsed}s</> : <><span aria-hidden="true">●</span> {requestingMic ? t('Opening microphone…','Открываем микрофон…') : clip ? t('Record again','Записать заново') : t('Tap to speak','Нажмите и говорите')}</>}</button><span class="quiet">{recording ? t('Recording · up to 60 seconds','Идёт запись · до 60 секунд') : t('Speak naturally. Short answers are welcome.','Говорите естественно. Короткие ответы тоже подходят.')}</span></div>
        {clipUrl && <div class="conversation-preview"><Player src={clipUrl} label={t('Listen before sending','Прослушать перед отправкой')} /><button class="cta" disabled={busy || recording} onClick={send}>{busy ? t('Sending…','Отправляем…') : isLab ? t('Compare transcriptions','Сравнить распознавание') : t('Send reply','Отправить ответ')} <span aria-hidden="true">→</span></button><button class="text-link" disabled={busy} onClick={()=>setClip(undefined)}>{t('Discard recording','Удалить запись')}</button></div>}
        <details class="conversation-upload"><summary>{t('Use an audio file instead','Загрузить аудиофайл')}</summary><input aria-label={t('Audio file','Аудиофайл')} type="file" accept="audio/*,.webm,.mp4,.m4a" disabled={recording || busy} onChange={e=>{const file=e.currentTarget.files?.[0];if(file){if(file.size>8*1024*1024){setError(t('Choose a file smaller than 8 MB.','Выберите файл меньше 8 МБ.'));return;}setClip(file);setFilename(file.name);submission.current=crypto.randomUUID();}}} /></details>
      </div>}
      {session.state==='completed' && <div class="conversation-finished"><h2>{t('Conversation finished','Разговор завершён')}</h2><p>{t('Listen back and try any useful corrections aloud. Your recordings and notes are saved here.','Прослушайте записи и повторите полезные исправления вслух. Записи и замечания сохранены здесь.')}</p>{isLab && <a class="cta" href="#speaking/lab">{t('Start another','Начать заново')} →</a>}</div>}
      <div class="conversation-controls">{isLab && session.state==='active' && <button class="text-link" disabled={busy || recording || !!pending} onClick={()=>void action(()=>api<Session>(`/api/v1/conversations/${session.id}/finish`,{},pageAbort.current.signal),setSession)}>{t('Finish practice','Завершить занятие')}</button>}
        <button class="text-link" disabled={busy || recording || working} onClick={()=>setDeleteConfirm(!deleteConfirm)}>{t('Delete this session and its recordings','Удалить занятие и его записи')}</button>
      </div>
      {deleteConfirm && <div class="conversation-delete"><p>{t('Delete this session, recordings and feedback?','Удалить занятие, записи и замечания?')}</p><button disabled={busy} onClick={()=>void action(()=>api(`/api/v1/conversations/${session.id}/delete`,{},pageAbort.current.signal),()=>{window.location.hash=isLab?'speaking/lab':'speaking';})}>{t('Delete','Удалить')}</button> <button onClick={()=>setDeleteConfirm(false)}>{t('Keep it','Оставить')}</button></div>}
      {isLab && <p class="quiet">{t('Agreement between models is not proof of what was said. Listen to the original recording. These tests do not change your ranking.','Совпадение результатов не доказывает, что именно прозвучало. Прослушайте исходную запись. Проверки не меняют рейтинг.')}</p>}
    </>}
  </section>;
}
