POS_LIST = [
    {"value": ["NOUN"], "label": "Существительное", "examples": "например: книга, стол"},
    {"value": ["VERB"], "label": "Глагол", "examples": "например: бежать, говорить"},
    {"value": ["ADJ"], "label": "Прилагательное", "examples": "например: красивый, большой"},
    {"value": ["ADVB"], "label": "Наречие", "examples": "например: быстро, тихо"},
    {"value": ["PART"], "label": "Частица", "examples": "например: нельзя, ли"},
    {"value": ["NUMR"], "label": "Числительное", "examples": "например: один, два"},
    {"value": ["NPRO"], "label": "Местоимение", "examples": "например: я, он"},
    {"value": ["CONJ"], "label": "Союз", "examples": "например: и, но"},
    {"value": ["COMP"], "label": "Компаратив", "examples": "например: лучше, выше"},
    {"value": ["PRED"], "label": "Предикатив", "examples": "например: надо, жаль"},
    {"value": ["PREP"], "label": "Предлог", "examples": "например: в, на"}
]

CASE_LIST = [
    {"value": "nomn", "label": "Именительный"},
    {"value": "gent", "label": "Родительный"},
    {"value": "datv", "label": "Дательный"},
    {"value": "accs", "label": "Винительный"},
    {"value": "instr", "label": "Творительный"},
    {"value": "prep", "label": "Предложный"}
]

POS_MAP = {
    'VERB': 'VERB', 'INFN': 'VERB',
    'ADJF': 'ADJ', 'ADJS': 'ADJ',
    'PRTF': 'PART', 'PRTS': 'PART',
    'NOUN': 'NOUN', 'ADVB': 'ADVB', 'NUMR': 'NUMR',
    'NPRO': 'NPRO', 'CONJ': 'CONJ', 'COMP': 'COMP',
    'PRCL': 'PRCL', 'PRED': 'PRED', 'PREP': 'PREP'
}

def get_pos_tag(pos):
    pos_map = {
        'NOUN': 'noun', 'VERB': 'verb', 'ADJ': 'adjective',
        'ADVB': 'adverb', 'PART': 'participle', 'NUMR': 'numeral',
        'NPRO': 'pronoun', 'CONJ': 'conjunction', 'COMP': 'comparative',
        'PRCL': 'particle', 'PRED': 'particle', 'PREP': 'preposition'
    }
    return pos_map.get(pos, 'unknown')
