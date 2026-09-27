import { useEffect, useRef, useState } from 'preact/hooks';
import { CardMedia, CardTags } from './CardDetails';
import { ratingLabel, words, type CardHistory, type Language, type LibraryCard } from './review-types';

type Props = {
  cards: LibraryCard[]; language: Language; personal: boolean; busy: boolean;
  suspensionDisabled: boolean; history?: CardHistory; mediaCard: string; mediaProgress: string; error?: string;
  onSuspend: (card: LibraryCard) => void; onDelete: (card: LibraryCard) => void;
  onMedia: (card: LibraryCard) => void; onHistory: (card: LibraryCard) => void;
};

const targetWord = (card: LibraryCard) => card.direction === 'ru-en' ? card.lemma || card.prompt : card.answer;

export function CardLibrary({ cards, language, personal, busy, suspensionDisabled, history,
  mediaCard, mediaProgress, error, onSuspend, onDelete, onMedia, onHistory }: Props) {
  const t = words(language);
  const [selectedId, setSelectedId] = useState<string>();
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>();
  const selected = cards.find(card => card.id === selectedId);
  const status = (card: LibraryCard) => card.status === 'suspended' ? t('Set aside', 'Отложена')
    : card.media_ready === false ? t('Media needed', 'Нужны файлы')
    : card.buried ? t('Spaced for later', 'На потом')
    : card.due ? t('Ready now', 'Пора повторить')
    : ({ new: t('New', 'Новая'), learning: t('Learning', 'Изучаю'), reviewing: t('Reviewing', 'Повторяю') })[card.status] ?? card.status;
  const type = (card: LibraryCard) => card.direction === 'ru-cloze' ? t('Missing word', 'Пропуск')
    : card.direction === 'en-ru' ? t('Russian recall', 'По-русски') : t('Meaning', 'Значение');

  function finishClose() {
    setSelectedId(undefined);
    if (opener.current?.isConnected) opener.current.focus({ preventScroll: true });
  }
  function close() {
    dialog.current?.close();
    finishClose();
  }
  useEffect(() => {
    if (selected && !dialog.current?.open) dialog.current?.showModal();
    if (!selected && dialog.current?.open) close();
  }, [selected?.id]);
  // Native dialog supplies focus containment and Escape handling. Remove it
  // from the top layer if a filter or profile change unmounts this collection.
  useEffect(() => () => { if (dialog.current?.open) dialog.current.close(); }, []);

  return <>
    {!!cards.length && <div class="card-library-list">
      <div class="card-library-columns" aria-hidden="true">
        <span>{t('Word', 'Слово')}</span><span>{t('Sentence', 'Предложение')}</span>
        <span class="card-library-type">{t('Type', 'Тип')}</span><span>{t('Status', 'Статус')}</span><span />
      </div>
      <ul aria-label={t('Your cards', 'Ваши карточки')}>
        {cards.map(card => <li key={card.id}><button type="button" class="card-library-row" data-card-id={card.id}
          aria-label={`${t('Open card', 'Открыть карточку')}: ${targetWord(card)}`} aria-haspopup="dialog"
          aria-describedby={`card-sentence-${card.id} card-type-${card.id} card-status-${card.id}`}
          onClick={event => { opener.current = event.currentTarget; setSelectedId(card.id); }}>
          <strong class="card-library-word" lang="ru" title={targetWord(card)}>{targetWord(card)}</strong>
          <span id={`card-sentence-${card.id}`} class="card-library-sentence" lang={card.direction === 'en-ru' ? 'en' : 'ru'} title={card.prompt.replace('[[blank]]', '[...]')}>{card.prompt.replace('[[blank]]', '[...]')}</span>
          <span id={`card-type-${card.id}`} class="card-library-type">{type(card)}</span>
          <span id={`card-status-${card.id}`} class="card-library-status">{status(card)}</span><span class="card-library-chevron" aria-hidden="true">›</span>
        </button></li>)}
      </ul>
    </div>}
    <dialog ref={dialog} class="card-library-dialog" aria-labelledby="card-library-detail-title"
      onCancel={event => { event.preventDefault(); close(); }} onClose={finishClose}>
      {selected && <>
        <header class="card-library-detail-header">
          <h2 id="card-library-detail-title">{t('Card details', 'Карточка')}</h2>
          <button type="button" class="card-library-close" aria-label={t('Close card details', 'Закрыть карточку')} onClick={close} autoFocus>×</button>
        </header>
        <div class="card-library-detail-body">
          {error && <p class="error-note" role="alert">{error}</p>}
          <div class="card-type-line"><span>{type(selected)}</span><span>{status(selected)}</span></div>
          <p class="card-library-detail-situation">{language === 'ru' && selected.title_ru ? selected.title_ru : selected.title}</p>
          <p class="library-prompt" lang={selected.direction === 'en-ru' ? 'en' : 'ru'}>{selected.prompt.replace('[[blank]]', '[...]')}</p>
          {selected.direction === 'ru-cloze' && selected.cue_en && <p lang="en">{selected.cue_en}</p>}
          <div class="card-library-answer">
            <h3>{t('Answer', 'Ответ')}</h3>
            <p class="prepared-answer">{selected.dictionary_url && selected.direction !== 'ru-en'
              ? <a href={selected.dictionary_url} target="_blank" rel="noopener noreferrer">{selected.answer}</a> : selected.answer}</p>
            {selected.context !== selected.prompt && <p lang="ru">{selected.context}</p>}
            {selected.context_meaning && <p>{selected.context_meaning}</p>}
            {(selected.explanation || selected.explanation_ru) && <p>{language === 'ru' && selected.explanation_ru ? selected.explanation_ru : selected.explanation}</p>}
          </div>
          {!!selected.assets?.length && <div class="card-library-media">{selected.assets.map(asset => <CardMedia key={`${asset.kind ?? 'asset'}:${asset.id}`} asset={asset} language={language} />)}</div>}
          {selected.sources?.map(source => <a class="text-link" href={source.url} key={`${source.url}:${source.page}`}>
            {source.origin === 'example' ? t('New example · ', 'Новый пример · ') : ''}{source.title}{source.page ? ` · ${t('Page', 'Страница')} ${source.page}` : ''}
          </a>)}
          <CardTags metadata={selected.metadata} language={language} />
          <div class="library-actions">
            {personal && <a class="text-link" href={`/post/flashcards/manage?edit=${selected.version_id}`}>{t('Edit card', 'Изменить')}</a>}
            <button class="text-link" disabled={suspensionDisabled} onClick={() => onSuspend(selected)}>{selected.status === 'suspended' ? t('Return to practice', 'Вернуть в практику') : t('Set aside', 'Отложить')}</button>
            <button class="text-link" onClick={() => onHistory(selected)}>{t('History', 'История')}</button>
            {personal && <button class="text-link" disabled={busy} onClick={() => onDelete(selected)}>{t('Delete card', 'Удалить')}</button>}
          </div>
          {personal && selected.media_supported !== false && !['image', 'word_audio', 'sentence_audio'].every(kind => selected.assets?.some(asset => asset.kind === kind)) &&
            <button class="text-link" disabled={busy} onClick={() => onMedia(selected)}>{mediaCard === selected.id ? mediaProgress
              : selected.media_jobs?.some(job => job.status === 'failed') ? t('Retry media', 'Повторить создание файлов')
              : selected.media_jobs?.length ? t('Resume media', 'Продолжить создание файлов') : t('Add audio & picture', 'Добавить аудио и картинку')}</button>}
          {history?.card_id === selected.id && <div class="card-history" aria-live="polite">{history.events.length
            ? <ol>{history.events.map((event, index) => <li key={index}><time>{new Date(event.at * 1000).toLocaleString(language)}</time> · {ratingLabel(event.rating, language)}{event.assisted ? t(' · with help', ' · с помощью') : ''}{event.undone ? t(' · undone', ' · отменено') : ''}</li>)}</ol>
            : <p>{t('No reviews yet.', 'Повторений пока нет.')}</p>}</div>}
        </div>
      </>}
    </dialog>
  </>;
}
