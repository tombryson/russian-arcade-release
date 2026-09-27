import { useEffect, useRef, useState } from 'preact/hooks';
import type { Language } from './review-types';

export function PilotRecording({ disabled, onReady, onLockChange, language = 'en', limit = 60 }: {
  disabled: boolean; onReady: (clip: Blob | undefined, filename?: string) => void; onLockChange?: (locked: boolean) => void; language?: Language; limit?: number;
}) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const [opening, setOpening] = useState(false);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const alive = useRef(true);
  const recorder = useRef<MediaRecorder>();
  const stream = useRef<MediaStream>();
  const clock = useRef<ReturnType<typeof setInterval>>();
  const audio = useRef<HTMLAudioElement>(null);
  const currentUrl = useRef('');
  const requesting = useRef(false);
  useEffect(() => { onLockChange?.(opening || recording || !!preview); }, [opening, recording, preview]);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      clearInterval(clock.current);
      if (recorder.current?.state === 'recording') recorder.current.stop();
      stream.current?.getTracks().forEach(track => track.stop());
      audio.current?.pause();
      if (currentUrl.current) URL.revokeObjectURL(currentUrl.current);
      onLockChange?.(false);
    };
  }, []);
  function clearClip() {
    audio.current?.pause();
    if (currentUrl.current) URL.revokeObjectURL(currentUrl.current);
    currentUrl.current = ''; setPreview(''); onReady(undefined);
  }
  async function start() {
    if (disabled || requesting.current || recording) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError(t('Audio recording is not available in this browser. Try a browser with microphone support.', 'Запись звука недоступна в этом браузере. Откройте страницу в браузере с поддержкой микрофона.')); return;
    }
    requesting.current = true; setOpening(true); setError(''); audio.current?.pause();
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const next = new MediaRecorder(media, mimeType ? { mimeType } : undefined);
      recorder.current = next;
      const chunks: Blob[] = [];
      let failed = false;
      next.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      next.onerror = () => {
        failed = true; clearInterval(clock.current); media.getTracks().forEach(track => track.stop());
        if (alive.current) { setRecording(false); setError(t('The recording stopped. Please try again.', 'Запись прервалась. Попробуйте ещё раз.')); }
      };
      next.onstop = () => {
        clearInterval(clock.current); media.getTracks().forEach(track => track.stop());
        if (!alive.current || failed) return;
        setRecording(false);
        const clip = new Blob(chunks, { type: next.mimeType });
        if (!clip.size) { setError(t('No audio was recorded. Please try again.', 'Звук не записан. Попробуйте ещё раз.')); return; }
        currentUrl.current = URL.createObjectURL(clip); setPreview(currentUrl.current);
        onReady(clip, `reply.${next.mimeType.includes('mp4') ? 'mp4' : next.mimeType.includes('ogg') ? 'ogg' : 'webm'}`);
      };
      clearClip(); setElapsed(0); next.start(); setRecording(true);
      const started = Date.now();
      clock.current = setInterval(() => {
        const seconds = Math.floor((Date.now() - started) / 1000);
        if (alive.current) setElapsed(seconds);
        if (seconds >= limit && next.state === 'recording') next.stop();
      }, 250);
    } catch {
      stream.current?.getTracks().forEach(track => track.stop());
      if (alive.current) setError(t('Allow microphone access in your browser, then try again.', 'Разрешите доступ к микрофону в браузере и попробуйте ещё раз.'));
    } finally {
      requesting.current = false;
      if (alive.current) setOpening(false);
    }
  }
  return <div class="pilot-recording">
    <div class="action-row"><button type="button" class="cta" disabled={disabled || opening}
      onClick={() => recording ? recorder.current?.stop() : void start()}>
      {opening ? t('Opening microphone…', 'Открываем микрофон…') : recording ? t('Stop recording', 'Остановить запись') : preview ? t('Record again', 'Записать ещё раз') : t('Record your reply', 'Записать ответ')}
    </button>{recording && <span role="status">{elapsed}s / {limit}s</span>}</div>
    {preview && <><audio ref={audio} controls preload="none" src={preview} aria-label={t('Listen to your recording', 'Прослушать свою запись')} /><button type="button" class="text-link" disabled={disabled} onClick={clearClip}>{t('Discard recording', 'Удалить запись')}</button></>}
    <p class="quiet">{t('Submit your reply to save the recording.', 'Отправьте ответ, чтобы сохранить запись.')}</p>
    {error && <p role="alert">{error}</p>}
  </div>;
}
