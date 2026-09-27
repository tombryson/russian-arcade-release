import { h, useState } from './preact_deps.js';
import { uiText, uiLanguage } from './ui_text.js?v=2';

const parts = {
    en: { NOUN: 'Noun', ADJF: 'Adjective', ADJS: 'Short adjective', COMP: 'Comparative', VERB: 'Verb', INFN: 'Verb', PRTF: 'Participle', PRTS: 'Short participle', GRND: 'Verbal adverb', NUMR: 'Numeral', ADVB: 'Adverb', NPRO: 'Pronoun', PRED: 'Predicative', PREP: 'Preposition', CONJ: 'Conjunction', PRCL: 'Particle', INTJ: 'Interjection' },
    ru: { NOUN: 'Существительное', ADJF: 'Прилагательное', ADJS: 'Краткое прилагательное', COMP: 'Сравнительная степень', VERB: 'Глагол', INFN: 'Глагол', PRTF: 'Причастие', PRTS: 'Краткое причастие', GRND: 'Деепричастие', NUMR: 'Числительное', ADVB: 'Наречие', NPRO: 'Местоимение', PRED: 'Предикатив', PREP: 'Предлог', CONJ: 'Союз', PRCL: 'Частица', INTJ: 'Междометие' },
};
const partName = pos => parts[uiLanguage()][pos] || '';

export function WordModal({ word, position, source, onClose, onSaved }) {
    const [selected, setSelected] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [pending, setPending] = useState(false);
    const choices = word.choices || [];
    const reading = choices.length ? choices.find(choice => `${choice.lemma}:${choice.pos}` === selected) : word;

    const save = async () => {
        if (saving || !reading) return;
        setSaving(true);
        setError('');
        try {
            const response = await fetch(`/add-vocab/${encodeURIComponent(reading.lemma)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ ...source, word: word.word, pos: reading.pos }),
            });
            const result = await response.json().catch(() => null);
            if (!response.ok || !result?.word) {
                setPending(Boolean(result?.error?.enrichment_pending));
                throw new Error(result?.error?.message || uiText('error_load_word'));
            }
            setPending(false);
            onSaved(result);
        } catch (failure) {
            setError(failure instanceof TypeError ? uiText('error_add_word') : failure.message || uiText('error_add_word'));
        } finally {
            setSaving(false);
        }
    };

    return h('div', {
        className: 'word-modal', role: 'dialog', 'aria-label': word.word,
        style: { left: `${position.x}px`, top: `${position.y}px` },
        onKeyDown: event => { if (event.key === 'Escape') onClose(); },
    },
        h('div', { className: 'word-modal-header' },
            h('strong', { lang: 'ru' }, word.word),
            h('button', { type: 'button', className: 'btn btn-sm btn-secondary', onClick: onClose, 'aria-label': uiText('close_word_card') }, '×')),
        word.loading ? h('p', { role: 'status' }, uiText('loading_words')) : null,
        word.error ? h('p', { role: 'alert' }, word.error) : null,
        choices.length ? h('label', { className: 'word-modal-row' }, uiText('choose_word_reading'),
            h('select', { className: 'form-select', value: selected, onChange: event => { setSelected(event.target.value); setError(''); setPending(false); } },
                h('option', { value: '' }, uiText('choose_word')),
                choices.map(choice => h('option', { value: `${choice.lemma}:${choice.pos}` }, `${choice.lemma} · ${partName(choice.pos)}`)))) : null,
        reading?.lemma && reading.lemma !== word.word.toLowerCase() ? h('p', { className: 'word-modal-row' }, h('strong', null, `${uiText('lemma')}: `), h('span', { lang: 'ru' }, reading.lemma)) : null,
        reading?.pos ? h('p', { className: 'word-modal-row' }, partName(reading.pos)) : null,
        reading?.mnemonic ? h('p', { className: 'word-modal-row' }, h('strong', null, `${uiText('mnemonic')}: `), reading.mnemonic) : null,
        reading?.dictionary_url ? h('p', { className: 'word-modal-row' }, h('a', { href: reading.dictionary_url, target: '_blank', rel: 'noopener noreferrer' }, uiText('open_dictionary'))) : null,
        word.message ? h('p', null, word.message) : null,
        reading?.in_vocabulary && !pending ? h('p', { className: 'word-modal-row', role: 'status' }, uiText('word_exists')) : null,
        error ? h('p', { role: 'alert' }, error) : null,
        reading && (reading.can_add || pending || (reading.in_vocabulary && reading.enrichment_pending)) ? h('button', {
            type: 'button', className: 'btn btn-sm btn-primary btn-full', disabled: saving, onClick: save,
        }, saving ? uiText('saving_word') : pending || reading.in_vocabulary ? uiText('retry_word_details') : uiText('add_to_list')) : null,
    );
}
