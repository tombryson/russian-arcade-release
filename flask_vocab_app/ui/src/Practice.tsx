import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { api, ApiError, type PracticeSession } from './learning-api';
import { Feedback, Sheet } from './components';

type Operation = 'attempts' | 'help' | 'listened' | 'transcript';
type Command = {url: string; body: object; operation: Operation};

export function Practice({ sessionId, profileId, onFinish }: { sessionId: string; profileId: string; onFinish: () => void }) {
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
    }).catch(reason => { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : 'This activity could not open.'); });
    return () => request.abort();
  }, [sessionId, profileId, reload]);
  useEffect(() => { heading.current?.focus(); }, [saved?.completed_items, feedback]);

  async function submit(operation: Operation, answer?: {choice_id: string} | {text: string}) {
    if (!saved?.item || sending.current || blocked || saved.id !== sessionId || saved.profile_id !== profileId) return;
    if (pending.current && pending.current.operation !== operation) return;
    if (operation === 'attempts' && saved.item.type === 'listening_choice' && !saved.item.listened && !saved.item.transcript) return;
    if (operation === 'attempts') audio.current?.pause();
    const epoch = requestEpoch.current;
    const signal = controller.current?.signal;
    if (!pending.current) pending.current = { operation, url: `/api/v1/learning-sessions/${sessionId}/${operation}`, body: {
      submission_id: crypto.randomUUID(), expected_revision: saved.revision, item_id: saved.item.id,
      ...(operation === 'attempts' ? { answer } : {}),
    } };
    sending.current = true; setBusy(true); setError('');
    try {
      const result = await api<PracticeSession>(pending.current.url, pending.current.body, signal);
      if (signal?.aborted || requestEpoch.current !== epoch) return;
      if (result.profile_id !== profileId) throw new Error('The learner changed. Open this activity again.');
      pending.current = undefined; setSaved(result); setFeedback(operation === 'attempts');
      if (operation === 'attempts') setAnswerText('');
    } catch (reason) {
      if (signal?.aborted || requestEpoch.current !== epoch) return;
      if (reason instanceof ApiError && reason.code === 'stale_revision' && reason.currentSession?.profile_id === profileId) {
        pending.current = undefined; setSaved(reason.currentSession); setFeedback(true); setAnswerText('');
        setError('Practice changed in another tab. The latest saved answer is shown here.');
      } else if (reason instanceof ApiError && reason.code === 'audio_unavailable' && operation === 'listened') {
        pending.current = undefined; setCompletedAudio(null); setAudioFailed(playbackKey); setError('');
      } else if (reason instanceof ApiError && ['locked', 'profile_changed', 'account_changed', 'access_required', 'adult_required', 'learner_required', 'content_unavailable', 'not_found', 'csrf_failed'].includes(reason.code)) {
        pending.current = undefined; setBlocked(true); setSaved(undefined); setError(reason.message);
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
  return <section class="page practice-page"><div class="lesson-head"><a class="text-link" href={saved?.origin?.href ?? "#activities"}>{saved?.origin ? saved.origin.title : "Back to activities"}</a><span class="quiet">{busy ? 'Saving…' : pending.current ? 'Save not confirmed' : saved?.origin ? `${Math.min(saved.completed_items + (showResult || saved.status === 'completed' ? 0 : 1), saved.total_items)} of ${saved.total_items}` : saved ? 'Progress saved' : ''}</span></div>
    {!saved ? <><h1 ref={heading} tabIndex={-1}>{error ? 'This activity could not open.' : 'Opening your practice…'}</h1>{error ? <><p role="alert">{error}</p><div class="action-row">{!blocked && <button class="cta" onClick={() => { pending.current = undefined; setReload(value => value + 1); }}>Try again</button>}<a href="/post/profiles">Choose a profile</a></div></> : <p role="status">Loading your saved answers.</p>}</>
      : <>{!saved.origin && <p class="kicker">{saved.title}</p>}{(!saved.origin || showResult || saved.status === 'completed') && <h1 ref={heading} tabIndex={-1}>{showResult ? last.outcome === 'correct' ? 'That’s right.' : 'Let’s look at the answer.' : saved.status === 'completed' ? 'Practice complete.' : `Question ${saved.completed_items + 1} of ${saved.total_items}`}</h1>}
        {showResult ? <Sheet>{saved.attempts.at(-1)?.prompt && <p class="practice-prompt">{saved.attempts.at(-1)?.prompt}</p>}{last.response_text !== undefined && <><p class="answer-label">Your answer</p><p class="answer-text" lang="ru">{last.response_text}</p></>}{(last.response_text === undefined || last.outcome !== 'correct') && <><p class="answer-label">{last.outcome === 'correct' ? 'Your answer' : 'The correct answer'}</p><p class="answer-text" lang="ru">{last.answer}</p></>}{last.transcript && <div class="practice-transcript"><p class="answer-label">Transcript</p><p lang="ru">{last.transcript}</p></div>}{last.explanation && <p>{last.explanation}</p>}<p>{last.support?.includes('transcript') ? 'Transcript used' : last.assisted ? 'You used a hint for this question.' : 'Your answer has been saved.'}</p><button class="cta" onClick={() => setFeedback(false)}>{saved.status === 'completed' ? 'Finish practice' : 'Next question'} <span aria-hidden="true">→</span></button></Sheet>
          : saved.status === 'completed' ? <Sheet><h2>You answered {saved.total_items} {saved.total_items === 1 ? 'question' : 'questions'}.</h2><p>Your answers are saved. Choose another activity when you’re ready.</p><details class="answer-history"><summary>Review your answers</summary><ol>{saved.attempts.map(attempt => <li key={attempt.id}>{attempt.feedback.answer} — {attempt.feedback.outcome === 'correct' ? 'answered correctly' : 'answer shown'}{attempt.feedback.support?.includes('transcript') ? ' · Transcript used' : attempt.feedback.assisted ? ' with a hint' : ''}</li>)}</ol></details>{saved.origin ? <a class="cta" href={saved.origin.href}>Continue learning →</a> : <button class="cta" onClick={onFinish}>Back to activities</button>}</Sheet>
            : saved.item && <Sheet>{saved.origin ? <h1 class="practice-prompt" ref={heading} tabIndex={-1} lang="ru">{saved.item.prompt}</h1> : <h2 class="practice-prompt">{saved.item.prompt}</h2>}
              {isListening && <div class="practice-listening">
                {saved.item.audio && <audio key={playbackKey} ref={audio} controls preload="none" aria-label="Listen to the message" src={saved.item.audio.url}
                  onEnded={() => { if (playbackKey && activePlayback.current === playbackKey) setCompletedAudio(playbackKey); }}
                  onError={() => { if (playbackKey && activePlayback.current === playbackKey) setAudioFailed(playbackKey); }} />}
                {audioFailed === playbackKey && playbackKey && <div class="practice-audio-error" role="alert"><span>The audio is unavailable.</span><button class="text-link" disabled={busy || !!pending.current} onClick={() => void retryAudio()}>Retry audio</button></div>}
                {!saved.item.audio && <p>The audio is unavailable. You can read the transcript.</p>}
                {saved.item.has_transcript && !saved.item.transcript && <button class="text-link" disabled={busy || !!pending.current} onClick={() => void submit('transcript')}>Show transcript</button>}
                {saved.item.transcript && <div class="practice-transcript"><p class="answer-label">Transcript</p><p lang="ru">{saved.item.transcript}</p></div>}
              </div>}
              {saved.item.type === 'controlled_text' ? <form class="practice-answer-form" onSubmit={event => {event.preventDefault(); if(answerText.trim()) void submit('attempts', {text: answerText});}}>
                <label class="answer-label" htmlFor="practice-form-answer">Your answer in Russian</label>
                <input id="practice-form-answer" type="text" lang="ru" autoComplete="off" autoCapitalize="off" spellcheck={false} maxLength={200} value={answerText} disabled={busy || !!pending.current} onInput={event => setAnswerText(event.currentTarget.value)} />
                <button class="cta" type="submit" disabled={busy || !!pending.current || !answerText.trim()}>Check answer</button>
              </form> : <><p>{listeningReady ? 'Choose one answer.' : 'Listen, then choose an answer.'}</p><div class="options">{saved.item.choices?.map(choice => <button key={choice.id} class="word" disabled={busy || !!pending.current || !listeningReady} onClick={() => void submit('attempts', {choice_id: choice.id})}>{choice.text}</button>)}</div></>}
              {saved.item.has_hint && !saved.item.hint && <button class="text-link" disabled={busy || !!pending.current} onClick={() => void submit('help')}>Show a hint</button>}
              {saved.item.hint && <Feedback>{saved.item.hint}</Feedback>}
              {!!saved.item.asset_ids?.length && <div class="activity-media">{saved.item.asset_ids.map((id, index) => <a key={id} class="text-link" href={`/api/v1/assets/${id}`} target="_blank" rel="noopener">Open supporting picture or audio {index + 1}</a>)}</div>}
            </Sheet>}
        {error && <div role="alert" class="error-note"><p>{error}</p>{pending.current && <button class="cta" disabled={busy} onClick={() => void submit(pending.current!.operation)}>Try saving again</button>}</div>}
      </>}
  </section>;
}
