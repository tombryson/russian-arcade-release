import { useState } from 'preact/hooks';
import type { PassageWord } from './learning-api';

export type WordSelection = {word: string; offset: number};

/** Context stays in the frozen task; only the selected occurrence is sent. */
export function PassageWords({text, selection, entry, disabled, language, onLookup, onSave, onClose}: {
  text: string; selection?: WordSelection; entry?: PassageWord; disabled: boolean; language: 'en'|'ru';
  onLookup: (selection: WordSelection) => void; onSave: (lemma: string, pos: string) => void; onClose: () => void;
}) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  let paragraphStart = 0;
  return <div class="passage-words">
    <small class="passage-word-note" lang={language}>{t('Select a word for help or to save it.', 'Выберите слово для подсказки или сохранения.')}</small>
    {text.split(/(\n\s*\n)/).map((paragraph, index) => {
      const start = paragraphStart; paragraphStart += paragraph.length;
      if (index % 2) return null;
      let cursor = 0;
      const parts = [];
      for (const token of paragraph.matchAll(/[А-Яа-яЁё][А-Яа-яЁё\u0300-\u036f]*(?:-[А-Яа-яЁё][А-Яа-яЁё\u0300-\u036f]*)*/gu)) {
        parts.push(paragraph.slice(cursor, token.index));
        const offset = [...text.slice(0, start + token.index)].length;
        parts.push(<button key={offset} type="button" class="passage-word" disabled={disabled} aria-pressed={selection?.offset === offset}
          onClick={() => onLookup({word: token[0], offset})}>{token[0]}</button>);
        cursor = token.index + token[0].length;
      }
      parts.push(paragraph.slice(cursor));
      return <p key={index} lang="ru">{parts}</p>;
    })}
    {selection && <PassageWordDetails key={selection.offset} selection={selection} entry={entry} disabled={disabled} language={language} onSave={onSave} onClose={onClose} />}
  </div>;
}

function PassageWordDetails({selection, entry, disabled, language, onSave, onClose}: {
  selection: WordSelection; entry?: PassageWord; disabled: boolean; language: 'en'|'ru';
  onSave: (lemma: string, pos: string) => void; onClose: () => void;
}) {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const [choice, setChoice] = useState('');
  const reading = entry?.choices.length ? entry.choices.find(value => `${value.lemma}|${value.pos}` === choice) : entry;
  return <aside class="passage-word-detail" lang={language} aria-label={t('Word help', 'Подсказка к слову')}>
    <div class="passage-word-head"><strong lang="ru">{selection.word}{reading?.lemma && reading.lemma !== selection.word && <> → {reading.lemma}</>}</strong>
      <button class="text-link" disabled={disabled} onClick={onClose}>{t('Close', 'Закрыть')}</button></div>
    {!entry && disabled && <p role="status">{t('Looking up…', 'Загружаем…')}</p>}
    {entry && <>
      <blockquote lang="ru">{entry.context}</blockquote>
      {entry.meaning && <p>{entry.meaning}</p>}{entry.translation && <p>{entry.translation}</p>}
      {entry.message && <p>{entry.message}</p>}
      {!!entry.choices.length && <label>{t('Which word is used here?', 'Какое слово использовано здесь?')}
        <select value={choice} disabled={disabled} onChange={event => setChoice(event.currentTarget.value)}>
          <option value="">{t('Choose a reading', 'Выберите значение')}</option>
          {entry.choices.map(value => <option key={`${value.lemma}|${value.pos}`} value={`${value.lemma}|${value.pos}`}>{value.label}</option>)}
        </select></label>}
      {reading?.mnemonic && <p><strong>{t('Memory hint: ', 'Как запомнить: ')}</strong>{reading.mnemonic}</p>}
      <div class="action-row">
        {reading?.in_vocabulary && !reading.enrichment_pending && <span role="status">{entry.added ? t('Added to your vocabulary.', 'Добавлено в словарь.') : t('Already in your vocabulary.', 'Уже в вашем словаре.')}</span>}
        {reading?.lemma && reading.pos && (reading.can_add || reading.enrichment_pending) && <button class="text-link" disabled={disabled} onClick={() => onSave(reading.lemma!, reading.pos!)}>
          {reading.enrichment_pending ? t('Finish word details', 'Дополнить сведения о слове') : t('Add to my words', 'Добавить в словарь')}</button>}
        {reading?.dictionary_url && <a class="text-link" href={reading.dictionary_url} target="_blank" rel="noopener noreferrer">{t('Open dictionary', 'Открыть словарь')} ↗</a>}
      </div>
    </>}
  </aside>;
}
