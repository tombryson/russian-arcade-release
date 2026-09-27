import {
    h,
    useState,
    useEffect,
    useRef,
} from './preact_deps.js';
import { WordModal } from './WordModal.js?v=2';
import { uiText } from './ui_text.js?v=2';

export function StoryText({ words, initialVisibility, source = {} }) {
    const [visibility, setVisibility] = useState(
        initialVisibility || 'revealed',
    );
    const [hiddenIndices, setHiddenIndices] = useState([]);
    const [hoveredWord, setHoveredWord] = useState(null);
    const [modalPosition, setModalPosition] = useState({ x: 0, y: 0 });
    const [hoveredIndex, setHoveredIndex] = useState(null); // Track hovered word for color change
    const [savedLemmas, setSavedLemmas] = useState([]);
    const lookupSequence = useRef(0);
    const debounceTimeout = useRef(null);

    const toggleVisibility = (newVisibility) => {
        setVisibility(newVisibility);
        if (newVisibility === 'partially_hidden') {
            const wordIndices = words
                .map((word, idx) =>
                    word.lemma &&
                    ![
                        'в',
                        'и',
                        'с',
                        'по',
                        'на',
                        'а',
                        'но',
                        'из',
                        'к',
                        'у',
                    ].includes(word.lemma.toLowerCase())
                        ? idx
                        : null,
                )
                .filter((idx) => idx !== null);
            const numToHide = Math.floor(wordIndices.length * 0.3);
            const shuffled = wordIndices.sort(() => 0.5 - Math.random());
            setHiddenIndices(shuffled.slice(0, numToHide));
        } else if (newVisibility === 'fully_hidden') {
            const wordIndices = words
                .map((word, idx) => (word.lemma ? idx : null))
                .filter((idx) => idx !== null);
            setHiddenIndices(wordIndices);
        } else {
            setHiddenIndices([]);
        }
    };

    const handleMouseEnter = (word, index) => {
        if (debounceTimeout.current) clearTimeout(debounceTimeout.current);
        debounceTimeout.current = setTimeout(() => {
            setHoveredIndex(index); // Highlight word
        }, 100);
    };

    const handleMouseLeave = () => {
        if (debounceTimeout.current) clearTimeout(debounceTimeout.current);
        setHoveredIndex(null); // Remove highlight
    };

    const handleClick = async (word, index, event) => {
        if (word.lemma) {
            const rect = event.target.getBoundingClientRect();
            const modalWidth = Math.min(320, window.innerWidth - 24);
            const x = Math.max(12, Math.min(rect.left, window.innerWidth - modalWidth - 12));
            const y = Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 350));
            const sequence = ++lookupSequence.current;
            setHoveredWord({ word: word.word, loading: true });
            setModalPosition({ x, y });
            let wordData;
            try {
                const url = `/word-details/${encodeURIComponent(word.word)}`;
                const response = source.task_id
                    ? await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''}, body: JSON.stringify(source)})
                    : await fetch(`${url}?${new URLSearchParams(source)}`);
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.word) throw new Error(result?.error?.message || uiText('error_load_word'));
                wordData = result;
            } catch (error) {
                wordData = { word: word.word, error: error instanceof TypeError ? uiText('error_load_word') : error.message || uiText('error_load_word') };
            }
            if (sequence !== lookupSequence.current) return;
            setHoveredWord(wordData);
            setModalPosition({ x, y });
        }
    };

    const closeModal = () => {
        lookupSequence.current += 1;
        setHoveredWord(null);
    };

    // Handle clicks outside the modal to close it
    useEffect(() => {
        const handleOutsideClick = (event) => {
            if (hoveredWord && !event.target.closest('.word-modal, .word-span')) {
                closeModal();
            }
        };
        document.addEventListener('click', handleOutsideClick);
        return () => document.removeEventListener('click', handleOutsideClick);
    }, [hoveredWord]);

    useEffect(() => () => { lookupSequence.current += 1; }, []);
    const activeLookup = lookupSequence.current;

    const renderedText = words.map((word, i) => {
        if (word.word === ' ' || !word.lemma) {
            return word.word;
        }
        const isHidden = hiddenIndices.includes(i);
        return h(
            'span',
            {
                key: i,
                className: `word-span ${word.added || savedLemmas.includes(word.lemma) ? 'added' : ''} ${
                    isHidden
                        ? 'hidden-word'
                        : `revealed-word ${
                              hoveredIndex === i ? 'hover:text-blue-500' : ''
                          }`
                }`,
                onMouseEnter: isHidden ? null : () => handleMouseEnter(word, i),
                onMouseLeave: isHidden ? null : handleMouseLeave,
                onClick: isHidden ? null : (e) => handleClick(word, i, e),
                role: isHidden ? undefined : 'button',
                tabIndex: isHidden ? undefined : 0,
                onKeyDown: isHidden ? null : (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        handleClick(word, i, event);
                    }
                },
                style: {
                    cursor: isHidden ? 'default' : 'pointer',
                    position: 'relative',
                },
            },
            isHidden ? '____' : word.word,
        );
    });

    return h(
        'div',
        { className: 'story-text', style: { position: 'relative', zIndex: 1 } },
        visibility !== 'fully_hidden'
            ? h('div', { id: 'story-text', className: 'mb-3', lang: 'ru', style: { whiteSpace: 'pre-wrap' } }, renderedText)
            : h(
                  'p',
                  null,
                  uiText('story_hidden'),
              ),
        hoveredWord &&
            h(WordModal, {
                key: hoveredWord.word,
                word: hoveredWord,
                source,
                onSaved: (result) => {
                    if (activeLookup !== lookupSequence.current) return;
                    setSavedLemmas(values => [...new Set([...values, result.lemma])]);
                    setHoveredWord(result);
                },
                position: modalPosition,
                onClose: closeModal,
            }),
        h(
            'button',
            {
                onClick: () => toggleVisibility('revealed'),
                'aria-pressed': visibility === 'revealed',
                className: 'btn btn-secondary me-2',
            },
            uiText('show_text'),
        ),
        h(
            'button',
            {
                onClick: () => toggleVisibility('partially_hidden'),
                'aria-pressed': visibility === 'partially_hidden',
                className: 'btn btn-secondary me-2',
            },
            uiText('hide_some_words'),
        ),
        h(
            'button',
            {
                onClick: () => toggleVisibility('fully_hidden'),
                'aria-pressed': visibility === 'fully_hidden',
                className: 'btn btn-secondary',
            },
            uiText('hide_text'),
        ),
    );
}
