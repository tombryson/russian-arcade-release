import { useEffect, useState } from 'preact/hooks';
import { api } from './learning-api';
import type { Language } from './review-types';

type SavedConversation = { id: string; created_at: number; mode?: string; title?:string; title_ru?:string; scenario?:{title:string;title_ru?:string} };
type HistoryItem = SavedConversation & { kind: 'live' | 'recorded' | 'step' };

/** Read saved modes without moving records or starting generation. */
export function SpeakingHistory({ language }: { language: Language }) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    setLoading(true); setFailed(false);
    void Promise.allSettled([
      api<{ sessions: SavedConversation[] }>('/api/v1/live-conversations/options', undefined, abort.signal),
      api<{ sessions: SavedConversation[] }>('/api/v1/conversations/options', undefined, abort.signal),
      api<{ sessions: SavedConversation[] }>('/api/v1/step-conversations/history', undefined, abort.signal),
    ]).then(results => {
      if (abort.signal.aborted) return;
      const next: HistoryItem[] = [];
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          next.push(...result.value.sessions.filter(session => index !== 1 || session.mode === 'conversation')
            .map(session => ({ ...session, kind: index === 0 ? 'live' as const : index === 1 ? 'recorded' as const : 'step' as const })));
        }
      });
      setItems(next.sort((a, b) => b.created_at - a.created_at));
      setFailed(results.some(result => result.status === 'rejected'));
      setLoading(false);
    });
    return () => abort.abort();
  }, [open, retry]);

  return <details class="conversation-history" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{t('Previous conversations', 'Предыдущие разговоры')}</summary>
    {open && <>
      {loading ? <p class="quiet" role="status">{t('Loading conversations…', 'Загружаем разговоры…')}</p> : <>
        {failed && <p class="quiet" role="status">{t('Some conversations could not load.', 'Не все разговоры удалось загрузить.')} <button class="text-link" onClick={() => setRetry(value => value + 1)}>{t('Try again', 'Попробовать ещё раз')}</button></p>}
        {!!items.length && <ul>{items.map(item => <li key={`${item.kind}:${item.id}`}>
          <a href={item.kind === 'live' ? `#speaking/${item.id}` : item.kind==='step' ? `#speaking/step/${item.id}` : `#speaking/recorded/${item.id}`}>
            {(language==='ru' ? item.title_ru ?? item.scenario?.title_ru : item.title ?? item.scenario?.title) ?? t('At the café', 'В кафе')} · {new Date(item.created_at * 1000).toLocaleString(language === 'ru' ? 'ru-RU' : 'en-AU')}
          </a>{item.kind === 'recorded' && <span class="quiet"> · {t('Recorded practice', 'Практика с записью')}</span>}
          {item.kind === 'step' && <span class="quiet"> · {t('Step-through', 'Пошаговый разговор')}</span>}
        </li>)}</ul>}
        {!failed && !items.length && <p class="quiet">{t('Your conversations will appear here.', 'Здесь появятся ваши разговоры.')}</p>}
      </>}
    </>}
  </details>;
}
