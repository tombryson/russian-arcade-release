import { h, useEffect, useRef, useState } from './preact_deps.js';
import { vocabularyLabel, normaliseRussian } from './vocab_labels.js';

export function VocabTable() {
    const language = document.documentElement.lang === 'ru' ? 'ru' : 'en';
    const t = (en, ru) => language === 'ru' ? ru : en;
    const label = value => vocabularyLabel(value, language);
    const initial = new URLSearchParams(window.location.search);
    const [words, setWords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [query, setQuery] = useState(initial.get('search') || '');
    const [pos, setPos] = useState('');
    const [topic, setTopic] = useState('');
    const [level, setLevel] = useState('');
    const [cards, setCards] = useState('');
    const [sort, setSort] = useState('lemma');
    const [page, setPage] = useState(1);
    const [expanded, setExpanded] = useState(null);
    const [detail, setDetail] = useState(null);
    const [detailError, setDetailError] = useState('');
    const [refresh, setRefresh] = useState(0);
    const list = useRef();
    const pageSize = 25;
    useEffect(() => {
        const controller = new AbortController();
        setLoading(true); setError('');
        fetch('/vocab?source=db&fetch_all=true', {headers:{Accept:'application/json'}, signal:controller.signal})
            .then(async response => {
                if (!response.ok) throw new Error();
                const data = await response.json();
                if (data.error || !Array.isArray(data.words)) throw new Error();
                if (!controller.signal.aborted) setWords(data.words);
            }).catch(() => { if (!controller.signal.aborted) setError(t('Your words could not load. Please try again.', 'Не удалось загрузить слова. Попробуйте ещё раз.')); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [refresh]);
    useEffect(() => {
        const visible = () => { if (document.visibilityState === 'visible') setRefresh(value => value + 1); };
        document.addEventListener('visibilitychange', visible);
        return () => document.removeEventListener('visibilitychange', visible);
    }, []);
    useEffect(() => {
        setDetail(null); setDetailError('');
        if (!expanded) return;
        const controller = new AbortController();
        fetch(`/vocab/words/${expanded}`, {signal:controller.signal})
            .then(async response => { if (!response.ok) throw new Error(); return response.json(); })
            .then(data => { if (!controller.signal.aborted) setDetail(data); })
            .catch(() => { if (!controller.signal.aborted) setDetailError(t('Details could not load. Close and reopen this word to retry.', 'Не удалось загрузить сведения. Закройте и снова откройте слово.')); });
        return () => controller.abort();
    }, [expanded, refresh]);
    useEffect(() => { setPage(1); }, [query, pos, topic, level, cards, sort]);
    const needle = normaliseRussian(query.trim());
    const filtered = words.filter(word => (!needle || normaliseRussian(`${word.lemma} ${word.forms_search}`).includes(needle)) &&
        (!pos || word.pos === pos) && (!topic || word.topic.includes(topic)) &&
        (!level || String(word.lemma_difficulty) === level) && (!cards || (cards === 'with' ? word.native_count > 0 : word.native_count === 0)));
    filtered.sort((a,b) => sort === 'cards' ? b.native_count-a.native_count || a.lemma.localeCompare(b.lemma,'ru') :
        sort === 'recent' ? b.date_added.localeCompare(a.date_added) || b.id-a.id :
        sort === 'level' ? a.lemma_difficulty-b.lemma_difficulty || a.lemma.localeCompare(b.lemma,'ru') : a.lemma.localeCompare(b.lemma,'ru') || a.id-b.id);
    const totalPages = Math.max(1, Math.ceil(filtered.length/pageSize));
    const current = Math.min(page, totalPages);
    const visibleWords = filtered.slice((current-1)*pageSize,current*pageSize);
    const activeFilters = !!(query || pos || topic || level || cards);
    const reset = () => { setQuery(''); setPos(''); setTopic(''); setLevel(''); setCards(''); };
    const changePage = value => { setPage(value); setExpanded(null); list.current?.scrollIntoView({block:'start',behavior:'smooth'}); };
    const number = value => Number(value || 0).toLocaleString(language);
    const counted = (n, one, many, ruOne, ruFew, ruMany) => {
        const mod100=n%100, mod10=n%10;
        const noun = language==='ru' ? mod100>=11 && mod100<=14 ? ruMany : mod10===1 ? ruOne : mod10>=2 && mod10<=4 ? ruFew : ruMany : n===1 ? one : many;
        return `${number(n)} ${noun}`;
    };
    const date = value => { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString(language==='ru' ? 'ru' : 'en-GB',{day:'numeric',month:'short',year:'numeric'}); };
    const select = (name,title,value,setter,options) => h('label',{className:'vocab-filter'},[title,h('select',{name,value,onChange:event=>setter(event.currentTarget.value)},[h('option',{value:''},t('All','Все')),...options.map(option=>h('option',{key:option,value:option},name==='level' ? option : label(option)))])]);
    const stats = [
        [words.length,t('Words','Слов')],
        [words.reduce((n,w)=>n+w.native_count,0),t('In-app cards','Карточек в приложении')],
        [words.filter(w=>w.native_count>0).length,t('Words with cards','Слов с карточками')],
    ];
    return h('section',{className:'vocab-library','aria-label':t('Word library','Словарь')},[
        h('dl',{className:'vocab-stats'},stats.map(([value,title])=>h('div',{key:title},[h('dt',null,title),h('dd',null,loading ? '…' : error ? '—' : number(value))]))),
        h('div',{className:'vocab-paper'},[
            h('div',{className:'vocab-search-row'},[
                h('label',{className:'vocab-search'},[h('span',null,t('Find a word or one of its forms','Найти слово или его форму')),h('input',{type:'search',value:query,placeholder:t('Search Russian words…','Поиск по русским словам…'),onInput:event=>setQuery(event.currentTarget.value)})]),
                h('a',{className:'vocab-flashcard-link',href:'/#flashcards'},t('Open flashcards →','Открыть карточки →')),
            ]),
            h('details',{className:'vocab-filters'},[
                h('summary',null,t('Filter words','Фильтры')),
                h('div',{className:'vocab-filter-grid'},[
                    select('pos',t('Part of speech','Часть речи'),pos,setPos,[...new Set(words.map(w=>w.pos))].sort()),
                    select('topic',t('Topic','Тема'),topic,setTopic,[...new Set(words.flatMap(w=>w.topic))].sort()),
                    select('level',t('Difficulty','Сложность'),level,setLevel,[...new Set(words.map(w=>w.lemma_difficulty))].sort((a,b)=>a-b)),
                    h('label',{className:'vocab-filter'},[t('In-app cards','Карточки в приложении'),h('select',{value:cards,onChange:event=>setCards(event.currentTarget.value)},[
                        h('option',{value:''},t('All words','Все слова')),h('option',{value:'with'},t('With cards','С карточками')),h('option',{value:'without'},t('Without cards','Без карточек'))])]),
                ]),
            ]),
            h('div',{className:'vocab-results-bar'},[
                h('p',{role:'status'},loading ? t('Loading your words…','Загружаем слова…') : counted(filtered.length,'word','words','слово','слова','слов')),
                activeFilters && h('button',{type:'button',className:'vocab-plain-button',onClick:reset},t('Clear filters','Сбросить фильтры')),
                h('label',null,[t('Sort','Порядок'),h('select',{value:sort,onChange:event=>setSort(event.currentTarget.value)},[
                    ['lemma','Russian A–Я','По алфавиту'],['recent','Newest first','Сначала новые'],['cards','Most cards','Больше карточек'],['level','Easiest first','Сначала простые'],
                ].map(([value,en,ru])=>h('option',{value},t(en,ru))))]),
            ]),
            error && h('div',{className:'vocab-error',role:'alert'},[error,' ',h('button',{onClick:()=>setRefresh(v=>v+1)},t('Retry','Повторить'))]),
            !loading && !error && !visibleWords.length && h('div',{className:'vocab-empty'},[
                h('h2',null,activeFilters ? t('No matching words','Ничего не найдено') : t('Your word library is ready to grow','Добавьте первые слова')),
                h('p',null,activeFilters ? t('Try another spelling or clear the filters.','Попробуйте другое написание или сбросьте фильтры.') : t('Add words to Google Drive, then sync them into your library.','Добавьте слова в Google Drive, затем синхронизируйте словарь.')),
            ]),
            !error && visibleWords.length > 0 && h('table',{className:'vocab-table',ref:list},[
                h('thead',null,h('tr',null,[t('Word','Слово'),t('Topics','Темы'),t('Difficulty','Сложность'),t('Cards','Карточки')].map(title=>h('th',{scope:'col'},title)))),
                h('tbody',null,visibleWords.flatMap(word=>[
                    h('tr',{key:word.id,className:expanded===word.id ? 'is-expanded' : ''},[
                        h('td',null,[h('button',{className:'vocab-word',onClick:()=>setExpanded(expanded===word.id ? null : word.id),'aria-expanded':expanded===word.id,'aria-controls':`word-detail-${word.id}`},[h('span',{lang:'ru'},word.lemma),h('span',{'aria-hidden':true},expanded===word.id ? '−' : '+')]),h('span',{className:'vocab-word-meta'},`${label(word.pos)} · ${counted(word.form_count,'form','forms','форма','формы','форм')}`)]),
                        h('td',{className:'vocab-topic-cell','data-label':t('Topics','Темы')},h('div',{className:'vocab-tags'},word.topic.length ? word.topic.slice(0,2).map(topic=>h('span',{key:topic},label(topic))).concat(word.topic.length>2 ? h('span',{title:word.topic.slice(2).map(label).join(', ')},`+${word.topic.length-2}`) : []) : h('span',{className:'vocab-muted'},'—'))),
                        h('td',{'data-label':t('Difficulty','Сложность')},h('span',{className:'vocab-level'},word.lemma_difficulty || '—')),
                        h('td',{'data-label':t('Cards','Карточки')},[
                            word.native_count ? h('a',{className:'vocab-count',href:`/#flashcards?word_id=${word.id}`,'aria-label':`${word.lemma}: ${counted(word.native_count,'in-app card','in-app cards','карточка в приложении','карточки в приложении','карточек в приложении')}`},`${word.native_count} →`) : h('span',{className:'vocab-zero','aria-label':t('0 in-app cards','0 карточек в приложении')},'0'),
                            word.anki_exports>0 && h('span',{className:'vocab-anki'},`${t('Anki exports','Экспорты в Anki')}: ${word.anki_exports}`),
                        ]),
                    ]),
                    expanded===word.id && h('tr',{key:`detail-${word.id}`,className:'vocab-detail-row'},h('td',{colSpan:4},h('section',{id:`word-detail-${word.id}`,className:'vocab-word-detail','aria-label':`${t('Details','Сведения')}: ${word.lemma}`},[
                        h('div',{className:'vocab-detail-top'},[
                            h('div',null,[h('h3',null,t('Memory hint','Подсказка для запоминания')),h('p',{lang:'en'},word.mnemonic || t('No hint saved.','Подсказка пока не сохранена.'))]),
                            h('p',{className:'vocab-muted'},`${t('Added','Добавлено')} ${date(word.date_added)}`),
                        ]),
                        h('div',{className:'vocab-detail-actions'},[
                            h('a',{className:'vocab-generate',href:`/#generate?word_id=${word.id}`},t('Make flashcards →','Создать карточки →')),
                            h('a',{href:`https://en.openrussian.org/ru/${encodeURIComponent(word.lemma)}`,target:'_blank',rel:'noopener noreferrer'},t('Open dictionary ↗','Открыть словарь ↗')),
                        ]),
                        h('p',{className:'vocab-record-note'},`${t('In-app cards','Карточки в приложении')}: ${word.native_count} · ${t('Saved card records','Сохранённых записей о карточках')}: ${word.native_total}. ${t('History includes unpublished and retired cards.','История включает неопубликованные и удалённые карточки.')}`),
                        word.anki_exports>0 && h('p',{className:'vocab-record-note'},t('Anki exports are a historical count; deleting a card in Anki does not update it.','Экспорты в Anki — исторический счётчик. Удаление карточки в Anki его не меняет.')),
                        detailError ? h('p',{role:'alert'},detailError) : !detail ? h('p',{role:'status'},t('Loading forms…','Загружаем формы…')) : h('details',{className:'vocab-forms'},[
                            h('summary',null,`${t('Word forms','Формы слова')} · ${detail.forms.length}`),
                            detail.forms.length ? h('ul',null,detail.forms.map(form=>h('li',{key:form.id},[
                                h('strong',{lang:'ru'},form.form),h('span',null,Object.values(form.tags).filter(v=>typeof v==='string').map(label).join(' · ') || t('Grammar not recorded','Грамматические признаки не указаны')),
                                form.native_count>0 && h('small',null,counted(form.native_count,'in-app card','in-app cards','карточка в приложении','карточки в приложении','карточек в приложении')),
                            ]))) : h('p',null,t('No forms recorded for this word.','Для этого слова формы не записаны.')),
                        ]),
                    ]))),
                ])),
            ]),
            totalPages>1 && h('nav',{className:'vocab-pagination','aria-label':t('Vocabulary pages','Страницы словаря')},[
                h('button',{type:'button',disabled:current===1,onClick:()=>changePage(current-1)},t('← Previous','← Назад')),
                h('span',null,`${current} / ${totalPages}`),
                h('button',{type:'button',disabled:current===totalPages,onClick:()=>changePage(current+1)},t('Next →','Далее →')),
            ]),
        ]),
    ]);
}
