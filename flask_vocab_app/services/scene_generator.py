"""Rule-driven scene construction with frozen, independently derived answers.

Sampling operates on semantic specifications before sentences exist. It balances
contrasts, avoids recent meanings (not merely names), and composes grammar and
visuals from the same facts. This is bounded procedural generation, not AI prose.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from itertools import product
import json
import random

from services.scene_lexicon import ACTORS, ADJECTIVES, CASES, NOUNS, adjective, reference
from services import scene_motion_generator as motion

VERSION = 'scene-rules-v1'
FAMILIES = ('location', 'motion', 'placement', 'agreement', 'roles')
SUBJECTS = ('cat', 'book', 'ball', 'cup', 'bag', 'letter')
ANCHORS = ('table', 'chair', 'box', 'shelf')
RELATIONS = {'table': ('on', 'under', 'behind', 'in-front', 'beside'),
             'chair': ('on', 'under', 'behind', 'in-front', 'beside'),
             'box': ('in', 'behind', 'in-front', 'beside'),
             'shelf': ('on', 'beside')}
ORIENTATIONS = {'book': ('flat', 'upright'), 'ball': ('flat',), 'cup': ('upright',),
                'bag': ('upright',), 'letter': ('flat',)}
RELATION_EN = {'on': 'on', 'under': 'under', 'behind': 'behind', 'in-front': 'in front of',
               'beside': 'beside', 'in': 'inside', 'above': 'above'}
RELATION_CUE_RU = {'on': 'Предмет касается верхней поверхности опоры.',
                   'under': 'Предмет ниже опоры, прямо внизу.',
                   'behind': 'Предмет с дальней от зрителя стороны опоры.',
                   'in-front': 'Предмет между зрителем и опорой.',
                   'beside': 'Предмет сбоку от опоры.',
                   'in': 'Предмет внутри коробки.',
                   'above': 'Предмет выше опоры.'}
RELATION_RU = {'on': 'на', 'under': 'под', 'behind': 'за', 'in-front': 'перед', 'in': 'в', 'above': 'над'}
INVERSE = {'on': 'under', 'under': 'above', 'behind': 'in-front', 'in-front': 'behind', 'beside': 'beside'}
ROOMS = {'home': ('at home', 'Дома'), 'classroom': ('in the classroom', 'В классе'), 'office': ('in the office', 'В кабинете')}
CASE_NAMES = {'nomn': ('nominative', 'именительный'), 'gent': ('genitive', 'родительный'),
              'datv': ('dative', 'дательный'), 'accs': ('accusative', 'винительный'),
              'ablt': ('instrumental', 'творительный'), 'loct': ('prepositional', 'предложный')}
ROLE_ACTIONS = {
    'calls': ('зовёт', 'accs', '.', 'calls to', 'зовёт другого человека'),
    'sees': ('видит', 'accs', '.', 'sees', 'смотрит на другого человека'),
    'thanks': ('благодарит', 'accs', '.', 'thanks', 'обращается к другому человеку со словом «спасибо»'),
    'waits': ('ждёт', 'accs', '.', 'waits for', 'ожидает другого человека'),
    'helps': ('помогает', 'datv', '.', 'helps', 'оказывает помощь другому человеку'),
    'phones': ('звонит', 'datv', '.', 'phones', 'разговаривает с другим человеком по телефону'),
    'greets': ('говорит', 'datv', ': «Привет!»', 'says hello to', 'приветствует другого человека'),
    'gives': ('даёт', 'datv', ' письмо.', 'gives a letter to', 'передаёт письмо другому человеку'),
    'shows': ('показывает', 'datv', ' книгу.', 'shows a book to', 'показывает книгу другому человеку'),
}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def semantic_key(plan):
    # Changing Anna to Nina, button order or the wallpaper does not constitute
    # a new grammatical situation. The identity retains referents, movement,
    # tense, role, order and relation, including the actual adjective tested.
    return _digest({k: v for k, v in plan.items() if k != 'setting'})


def contrast_key(plan):
    """Balance grammatical decisions before taking another lexical setting."""
    excluded = {'place', 'vehicle', 'setting', 'skill', 'family', 'level'}
    if plan['family'] == 'motion' and plan['rule'] == 'cargo':
        # A box and a parcel use the same carrying contrast; a child can walk.
        return _digest({**{k: v for k, v in plan.items() if k not in excluded | {'cargo'}},
                        'cargo_kind': 'person' if plan['cargo'] == 'child' else 'object'})
    return _digest({k: v for k, v in plan.items() if k not in excluded})


def _plans(family, level):
    if family == 'motion':
        yield from motion.plans(level)
    elif family == 'location':
        for subject, anchor in product(SUBJECTS, ANCHORS):
            for relation in RELATIONS[anchor]:
                for perspective in ('subject', 'anchor') if relation != 'in' else ('subject',):
                    yield dict(family=family, rule='relative-position', subject=subject, anchor=anchor,
                               relation=relation, perspective=perspective, skill='position-' + perspective)
    elif family == 'placement':
        for subject, orientations in ORIENTATIONS.items():
            for anchor, orientation, action in product(ANCHORS, orientations, (False, True)):
                relation = 'in' if anchor == 'box' else 'on'
                # A letter can be put into a box, not stood on its paper edge.
                yield dict(family=family, rule='position-or-placement', subject=subject, anchor=anchor,
                           relation=relation, orientation=orientation, action=action,
                           skill='placing' if action else 'resting')
    elif family == 'agreement':
        for subject, color, case in product(SUBJECTS[1:], ADJECTIVES, ('nomn', 'accs', 'loct')):
            yield dict(family=family, rule='adjective-agreement', subject=subject, color=color, case=case,
                       skill='agreement-' + case)
    elif family == 'roles':
        for action, actor, order in product(ROLE_ACTIONS, ('girl', 'boy'), ('actor-first', 'recipient-first')):
            yield dict(family=family, rule='participant-roles', action=action, actor=actor, order=order,
                       skill='roles-' + ROLE_ACTIONS[action][1])
    else:
        raise ValueError('Unknown scene family.')


@lru_cache(maxsize=15)
def _catalogue(family, level):
    # Only immutable serialized specifications are cached; rendered objects and
    # caller-owned plan dictionaries are never reused across sessions.
    return tuple(json.dumps(p, sort_keys=True) for p in _plans(family, level))


def specifications(family, level='A1'):
    return [json.loads(p) for p in _catalogue(family, level)]


def _case_slot(make_slot, identity, key, target, rng):
    # Nom./acc. inanimate and fem. dat./prep. are often identical. One visible
    # word gets one button; there must never be an invisible wrong duplicate.
    choices, seen = [], set()
    for case in ('nomn', 'accs', 'loct', 'ablt', 'gent', 'datv'):
        text = NOUNS[key]['forms'][case]
        if text not in seen:
            choices.append((case, text))
            seen.add(text)
    answer = next(case for case, text in choices if text == NOUNS[key]['forms'][target])
    rng.shuffle(choices)
    return make_slot(identity, 'Noun form', 'Форма существительного', choices), answer


def _prep(relation, noun_key):
    if relation == 'beside':
        return 'рядом со' if noun_key in ('table', 'chair') else 'рядом с'
    return RELATION_RU[relation]


def _position_case(relation):
    return 'loct' if relation in ('on', 'in') else 'ablt'


def _visual(plan, rng):
    return {'kind': 'spatial', 'subject': plan['subject'], 'anchor': plan.get('anchor', 'table'),
            'relation': plan.get('relation', 'on'), 'setting': rng.choice(tuple(ROOMS)),
            **({'orientation': plan['orientation']} if 'orientation' in plan else {}),
            **({'color': plan['color']} if 'color' in plan else {})}


def _case_explanation(key, case, *, preposition=None):
    text = NOUNS[key]['forms'][case]
    en_case, ru_case = CASE_NAMES[case]
    if preposition:
        return (f'Here «{preposition}» takes the {en_case}: «{text}».',
                f'Здесь после «{preposition}» нужен {ru_case} падеж: «{text}».')
    return f'This role needs the {en_case}: «{text}».', f'Эта роль требует {ru_case} падеж: «{text}».'


def _locations(plan, rng, make_item, make_slot):
    subject, anchor, relation = plan['subject'], plan['anchor'], plan['relation']
    visual = _visual(plan, rng)
    if plan['perspective'] == 'anchor':
        subject, anchor, relation = anchor, subject, INVERSE[relation]
    case = _position_case(relation)
    preps = [(rel, _prep(rel, anchor)) for rel in ('on', 'in', 'under', 'above', 'behind', 'in-front', 'beside')]
    # Six focused alternatives, always including the target. «Над» and «на»
    # differ (above without contact / on a surface), not interchangeable ids.
    preps = [p for p in preps if p[0] != ('above' if relation != 'above' else 'on')]
    rng.shuffle(preps)
    noun_slot, answer = _case_slot(make_slot, 'noun', anchor, case, rng)
    a, b = NOUNS[subject], NOUNS[anchor]
    row = make_item('pending', 'location', 'spatial-composed',
        f'Describe the {a["meaning"]}: it is {RELATION_EN[relation]} the {b["meaning"]}.',
        f'Опишите положение «{a["lemma"]}» относительно «{b["lemma"]}». ' + RELATION_CUE_RU[relation],
        [a['forms']['nomn'].capitalize() + ' ', ' ', '.'],
        [make_slot('preposition', 'Position', 'Положение', preps), noun_slot], [relation, answer],
        f'The {a["meaning"]} is {RELATION_EN[relation]} the {b["meaning"]}.',
        [(f'Use «{_prep(relation, anchor)}» for this relationship.', f'Это отношение передаёт «{_prep(relation, anchor)}».'),
         _case_explanation(anchor, case, preposition=_prep(relation, anchor))],
        'Read which object begins the sentence. Describe its position, then choose the noun ending.',
        'Проверьте, с какого предмета начинается предложение. Выберите положение и форму существительного.',
        reference(anchor, case))
    row['scene_builder']['scene_visual'] = visual
    return row


def _placements(plan, rng, make_item, make_slot):
    subject, anchor = plan['subject'], plan['anchor']
    flat, action = plan['orientation'] == 'flat', plan['action']
    actor = rng.choice(ACTORS)
    verb = ('положила' if actor['gender'] == 'femn' else 'положил') if flat else ('поставила' if actor['gender'] == 'femn' else 'поставил')
    if not action:
        verb = 'лежит' if flat else 'стоит'
    case = 'accs' if action else 'loct'
    prep = _prep(plan['relation'], anchor)
    bank = [('lies', 'лежит'), ('stands', 'стоит'), ('lay-m', 'положил'), ('stand-m', 'поставил'), ('lay-f', 'положила'), ('stand-f', 'поставила')]
    expected_verb = next(k for k, value in bank if value == verb)
    rng.shuffle(bank)
    noun_slot, ending = _case_slot(make_slot, 'noun', anchor, case, rng)
    a, b = NOUNS[subject], NOUNS[anchor]
    posture, posture_ru = ('flat', 'горизонтально') if flat else ('upright', 'вертикально')
    en = (f'{actor["en"]} has just put the {a["meaning"]} {posture} {RELATION_EN[plan["relation"]]} the {b["meaning"]}. Describe the completed placing action.' if action else
          f'The {a["meaning"]} is {posture} {RELATION_EN[plan["relation"]]} the {b["meaning"]}. Describe its current position, not a placing action.')
    ru = (f'{actor["ru"]} только что разместил{ "а" if actor["gender"] == "femn" else ""} предмет. Теперь {a["forms"]["nomn"]} расположен{ "а" if a["gender"] == "femn" else "о" if a["gender"] == "neut" else ""} {posture_ru}. Опишите завершённое действие.' if action else
          f'{a["forms"]["nomn"].capitalize()} расположен{ "а" if a["gender"] == "femn" else "о" if a["gender"] == "neut" else ""} {posture_ru}. Опишите положение сейчас, а не действие человека.')
    # Balls rest on a surface; they have no meaningful flat/upright axis.
    if subject == 'ball':
        en = en.replace(' flat', '')
        ru = ru.replace(' расположен горизонтально', ' на поверхности')
    segments = [actor['ru'] + ' ' if action else a['forms']['nomn'].capitalize() + ' ',
                (' ' + a['forms']['accs'] if action else '') + ' ' + prep + ' ', '.']
    explanation = ('Choose placing for a completed action; match the past form to the person. «Положить» places something lying down, «поставить» places it upright.',
                   'Для завершённого действия выберите «положил/положила» или «поставил/поставила». Форма прошедшего времени согласуется с человеком.') if action else (
                   '«Лежит» describes something lying; «стоит» describes something standing. No placing action is happening.',
                   '«Лежит» обозначает лежачее положение, «стоит» — стоячее. Действие перемещения здесь не описывается.')
    row = make_item('pending', 'placement', 'spatial-composed', en, ru, segments,
        [make_slot('verb', 'Position or action', 'Положение или действие', bank), noun_slot], [expected_verb, ending],
        (f'{actor["en"]} put the {a["meaning"]}' if action else f'The {a["meaning"]} is') + (f' {posture}' if subject != 'ball' else '') + f' {RELATION_EN[plan["relation"]]} the {b["meaning"]}.',
        [explanation, _case_explanation(anchor, case, preposition=prep)],
        'Are you describing where the object is or putting it there? Check its orientation and the person.',
        'Вы описываете положение или перемещение? Учитывайте положение предмета и того, кто действует.', reference(anchor, case))
    row['scene_builder']['scene_visual'] = _visual(plan, rng)
    row['_actor'] = actor['id'] if action else None
    return row


def _agreement(plan, rng, make_item, make_slot):
    key, color, case = plan['subject'], plan['color'], plan['case']
    noun = NOUNS[key]
    lemma, meaning, _ = ADJECTIVES[color]
    target = adjective(color, noun['gender'], case)
    # Show unique words, not duplicate grammatical labels for the same form.
    texts = [adjective(color, gender, c) for gender, c in product(('masc', 'femn', 'neut'), ('nomn', 'accs', 'loct'))]
    texts = list(dict.fromkeys(texts))
    rng.shuffle(texts)
    if len(texts) > 6:
        texts = [target] + [t for t in texts if t != target][:5]
    choices = [(str(i), text) for i, text in enumerate(texts)]
    answer = next(k for k, value in choices if value == target)
    rng.shuffle(choices)
    beginning = {'nomn': 'Это ', 'accs': 'Я вижу ', 'loct': 'Мы говорим о '}[case]
    translation = {'nomn': f'This is a {meaning} {noun["meaning"]}.',
                   'accs': f'I see a {meaning} {noun["meaning"]}.',
                   'loct': f'We are talking about a {meaning} {noun["meaning"]}.'}[case]
    row = make_item('pending', 'agreement', 'spatial-composed',
        f'The {noun["meaning"]} is {meaning}. Complete the sentence with the matching adjective form.',
        f'Предмет — «{noun["lemma"]}». Цвет — «{lemma}». Согласуйте прилагательное с существительным в предложении.',
        [beginning, ' ' + noun['forms'][case] + '.'], [make_slot('adjective', 'Adjective form', 'Форма прилагательного', choices)], [answer],
        translation, [(f'The noun is {CASE_NAMES[case][0]}. The adjective agrees in gender and case: «{target}».',
                      f'Согласуйте прилагательное с существительным: {CASE_NAMES[case][1]} падеж, форма «{target}».')],
        'Match both gender and the role of the noun in this sentence.',
        'Учитывайте род существительного и его роль в предложении.',
        (lemma, target, 'ADJF', {'gender': noun['gender'], 'number': 'sing', 'case': case}, meaning))
    row['scene_builder']['scene_visual'] = _visual(dict(plan, orientation='upright' if key in ('cup', 'bag') else 'flat'), rng)
    return row


def _roles(plan, rng, make_item, make_slot):
    actor = plan['actor']
    recipient = 'boy' if actor == 'girl' else 'girl'
    verb, case, ending, action_en, action_ru = ROLE_ACTIONS[plan['action']]
    parts = [(actor, 'nomn'), (recipient, case)]
    if plan['order'] == 'recipient-first':
        parts.reverse()
    slots, answers = [], []
    for identity, target in parts:
        part, answer = _case_slot(make_slot, identity, identity, target, rng)
        slots.append(part); answers.append(answer)
    a, b = NOUNS[actor], NOUNS[recipient]
    row = make_item('pending', 'roles', 'girl-calls-boy' if actor == 'girl' else 'boy-calls-girl',
        f'The {a["meaning"]} {action_en} the {b["meaning"]}. Keep these roles even if the other person comes first in the sentence.',
        f'{a["lemma"].capitalize()} {action_ru}. Действие направлено к персонажу «{b["lemma"]}». Сохраните роли при указанном порядке слов.',
        ['', ' ' + verb + ' ', ending], slots, answers,
        f'The {a["meaning"]} {action_en} the {b["meaning"]}.',
        [_case_explanation(identity, target) for identity, target in parts],
        'Identify the person doing the action, then the other person’s role. Word order alone does not decide this.',
        'Найдите действующее лицо, затем определите роль собеседника. Первое слово не обязательно обозначает действующее лицо.',
        reference(recipient, case))
    return row


def realize(plan, seed):
    """Realize a validated plan; source answers remain private in the frozen row."""
    from services.scene_builder import item, slot
    if json.dumps(plan, sort_keys=True) not in _catalogue(plan['family'], plan.get('level', 'A1')):
        raise ValueError('The scene plan is outside the supported grammar/visual combinations.')
    rng = random.Random(seed)
    family = plan['family']
    row = motion.realize(plan, rng, item, slot) if family == 'motion' else {
        'location': _locations, 'placement': _placements, 'agreement': _agreement, 'roles': _roles,
    }[family](plan, rng, item, slot)
    actor = row.pop('_actor', None)
    identity = _digest({'version': VERSION, 'plan': plan, 'actor': actor, 'sentence': row['correct_sentence']})
    row['id'] = 'scene-' + identity[:24]
    row['scene_builder']['skill'] = plan['skill']
    row['generation'] = {'version': VERSION, 'semantic_id': semantic_key(plan), 'plan': deepcopy(plan)}
    if actor:
        row['generation']['actor'] = actor
    validate_generated(row)
    return row


def validate_generated(row):
    """Reject malformed answer contracts without depending on a model/parser."""
    scene = row['scene_builder']
    if len(scene['segments']) != len(scene['slots']) + 1 or len(row['expected_answer']) != len(scene['slots']):
        raise ValueError('Every sentence blank needs one answer slot.')
    assembled = scene['segments'][0]
    for i, (part, expected) in enumerate(zip(scene['slots'], row['expected_answer'])):
        choices = part['choices']
        if not 2 <= len(choices) <= 6 or len({c['text'] for c in choices}) != len(choices):
            raise ValueError('Visible answer choices must be distinct and bounded.')
        if len({c['id'] for c in choices}) != len(choices) or expected not in {c['id'] for c in choices}:
            raise ValueError('Each expected answer must be one owned choice.')
        assembled += next(c['text'] for c in choices if c['id'] == expected) + scene['segments'][i + 1]
    assembled = assembled[0].upper() + assembled[1:]
    if assembled != row['correct_sentence'] or len(row['slot_explanations']) != len(scene['slots']):
        raise ValueError('Sentence and feedback must agree with the frozen slot answers.')
    if any(ref['form'].lower() not in assembled.lower() for ref in row.get('vocabulary_refs', [row['vocabulary']])):
        raise ValueError('Card targets must occur in the correct contextual sentence.')
    return row


def generate(seed, settings, recent=()):
    """Prefer unseen meanings, balance contrasts, then relax oldest exposure.

    ``recent`` is ordered newest first and scoped by the existing owned-session
    query. After the finite semantic pool is exhausted, reuse is explicit in
    private provenance; it does not manufacture a fresh skill/coin identity.
    """
    rng = random.Random(seed)
    focus, count = settings['grammar_focus'], settings['rounds']
    families = FAMILIES if focus == 'mixed' else (focus,)
    pools = {family: specifications(family, settings.get('motion_level', 'A1')) for family in families}
    for pool in pools.values():
        rng.shuffle(pool)
    seen = {}
    for index, identity in enumerate(recent):
        seen.setdefault(identity, index)
    selected, used, counts, contrasts = [], set(), Counter(), Counter()
    for index in range(count):
        family = families[index % len(families)]
        candidates = [p for p in pools[family] if semantic_key(p) not in used]
        fresh = [p for p in candidates if semantic_key(p) not in seen]
        available = fresh or candidates
        if not available:
            raise ValueError('The semantic grammar pool cannot fill this session without duplicates.')
        # Even when a pool is exhausted, avoid the most recent meanings before
        # balancing skills. Availability never silently reintroduces a fresh
        # candidate that failed grammar/visual validation.
        if not fresh:
            oldest = max(seen.get(semantic_key(p), -1) for p in available)
            available = [p for p in available if seen.get(semantic_key(p), -1) == oldest]
        least = min(counts[(family, p['skill'])] for p in available)
        available = [p for p in available if counts[(family, p['skill'])] == least]
        least_contrast = min(contrasts[(family, contrast_key(p))] for p in available)
        plan = next(p for p in available if contrasts[(family, contrast_key(p))] == least_contrast)
        key = semantic_key(plan)
        counts[(family, plan['skill'])] += 1
        contrasts[(family, contrast_key(plan))] += 1
        used.add(key)
        row = realize(plan, rng.getrandbits(128))
        row['generation']['recently_seen'] = key in seen
        selected.append(row)
    return selected
