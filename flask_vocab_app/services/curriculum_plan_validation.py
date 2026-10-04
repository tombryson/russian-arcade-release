"""Validation for the extended, construction-led situation plans.

Authored form inventories constrain generation; they are not a general Russian
parser. Semantic entailment and idiomatic prose still need language evaluation.
"""
import re


def description_realized(request, fact_id, text):
    """Recognise a bounded Russian description without prescribing word order.

    У Оли белая шапка, а у Ивана красная permits one recoverable noun;
    у Димы сумка синяя permits a predicative adjective. A nearby colour alone
    does not establish the garment or its owner. This is deliberately narrower
    than general ellipsis or coreference resolution.
    """
    from services.curriculum_situation_content import _contains, _normal
    from utils.story_processing import get_morph
    plan = request.get('language_plan', {})
    fact = next((f for f in plan.get('meaning_plan', {}).get('facts', []) if f['id'] == fact_id), None)
    if not fact or fact['role'] != 'description' or plan.get('unit_id') != 'noun-adjective-agreement-v1':
        return False
    words = _normal(fact['value_ru']).split()
    if len(words) != 2:
        return False
    adjective, noun = words
    people = plan['meaning_plan']['participants']
    owner_forms = {_normal(p['genitive_ru']): p['name_ru'] for p in people}
    names = {value for p in people for key, value in p.items() if key.endswith('_ru') and isinstance(value, str)}
    name_tokens = {_normal(value) for value in names}
    garment_forms = {_normal(f['value_ru']).split()[-1] for f in plan['meaning_plan']['facts']}
    def common_nouns(clause):
        return {token for token in re.findall(r'[а-яё]+', clause) if token not in name_tokens
                and any(p.is_known and p.tag.POS == 'NOUN' and not any(tag in p.tag for tag in
                    ('Name', 'Surn', 'Patr', 'Geox')) for p in get_morph().parse(token))}
    for sentence in re.split(r'[.!?;]', text):
        owner = None
        previous_nouns = set()
        for clause in re.split(r',|\s+а\s+(?=у\b)', sentence.casefold().replace('ё', 'е')):
            ownership = list(re.finditer(r'\bу\s+([а-яё]+)\b', clause))
            if len(ownership) > 1:
                continue  # Do not guess where a second owner's description starts.
            if ownership:
                owner = owner_forms.get(ownership[0].group(1))
            explicit = {form for form in garment_forms if _contains(clause, form)}
            if owner == fact['subject_name']:
                if _contains(clause, adjective + ' ' + noun) or _contains(clause, noun + ' ' + adjective):
                    return True
                if _contains(clause, adjective) and not explicit and previous_nouns == {noun}:
                    # An unplanned noun (e.g. красная машина) cannot be silently
                    # treated as an omitted шапка just because both are feminine.
                    remaining = [token for token in re.findall(r'[а-яё]+', clause)
                                 if token != adjective and token not in name_tokens]
                    other_noun = any(any(p.is_known and p.tag.POS == 'NOUN' and not
                        any(tag in p.tag for tag in ('Name', 'Surn', 'Patr')) for p in get_morph().parse(token))
                        for token in remaining)
                    if not other_noun:
                        return True
            if common_nouns(clause):
                previous_nouns = common_nouns(clause)
    return False


def _validate_relation_context(plan, payload):
    """Reject specific relation ambiguities found in independent text review."""
    from services.curriculum_situation_content import _contains, _lemmas, _normal
    text = payload['text']
    family = plan['family_id']
    if family == 'reference-giving-and-calling':
        policy = plan['meaning_plan'].get('event_policy', {
            'unplanned_presence_event_lemmas': ['видеть', 'встретить', 'встречать', 'приходить', 'прийти', 'стоять', 'находиться'],
            'unplanned_presence_markers': ['здесь', 'тут', 'рядом'],
        })
        if _lemmas(text) & set(policy.get('unplanned_presence_event_lemmas', ())):
            raise ValueError('The phone-call plan does not establish an in-person encounter.')
        if any(_contains(text, marker) for marker in policy.get('unplanned_presence_markers', ())):
            raise ValueError('The phone-call plan does not establish physical co-location.')
    if family == 'reference-shared-belongings':
        people = plan['meaning_plan']['participants']
        names = {_normal(p['name_ru']) for p in people}
        # Bare names after an owned object are neither a naming construction
        # nor an ownership clause: «Это их журнал: Олег и Нина» is not accepted.
        for clause in re.split(r'[.!?;]', text):
            if ':' not in clause:
                continue
            before, after = clause.rsplit(':', 1)
            after_tokens = re.findall(r'[а-яё]+', after.lower())
            if (re.search(r'\b(?:его|её|ее|их)\b', before.lower())
                    and after_tokens and any(token in names for token in after_tokens)
                    and all(token in names or token == 'и' for token in after_tokens)):
                raise ValueError('Name the owners in a grammatical clause, not a dangling list after the item.')
    if family == 'messages-meeting-change':
        fact = next(f for f in plan['meaning_plan']['facts'] if f['role'] == 'location')
        evidence = next(q['evidence'] for q in payload['questions'] if q['fact_id'] == fact['id'])
        clear = False
        for clause in re.split(r'[.!?;]', evidence):
            normal = clause.casefold().replace('ё', 'е')
            for match in re.finditer(r'(?<!\w)' + re.escape(_normal(fact['value_ru'])) + r'(?!\w)', normal):
                before = normal[:match.start()]
                causes = list(re.finditer(r'\b(?:потому что|так как)\b', before))
                if not causes:
                    clear = True
                else:
                    # A venue after a because-clause can describe that clause's
                    # work/class instead of the meeting. A new explicit meeting
                    # relation restores the attachment; a comma alone does not.
                    resumed = before[causes[-1].end():]
                    if re.search(r'[,;]\s*(?:а|но)\b', resumed) and _lemmas(resumed) & {'встреча', 'встретиться'}:
                        clear = True
        if not clear:
            raise ValueError('The venue must clearly describe the meeting, not the cause of its delay.')


def validate_generated_frames(request, payload):
    from services.curriculum_situation_content import _contains, _normal, _lemmas
    plan = request['language_plan']
    from services import curriculum_situation_plans_personal as personal
    from services import curriculum_situation_plans_relations as relations
    # The owning module checks its sampled morphology and relation constraints.
    (personal if plan['unit_id'] in personal.UNITS else relations).validate_plan(plan)
    selected = {target['id'] for target in request['language_targets']}
    rules = {rule['requirement_id']: rule for rule in plan['contrast_rules']}
    if selected != set(rules):
        raise ValueError('The situation plan must match the selected taught constructions.')
    facts = {fact['id']: fact for fact in plan['meaning_plan']['facts']}
    _validate_relation_context(plan, payload)
    covered = set()
    for question in payload['questions']:
        fact = facts[question['fact_id']]
        requirement = fact.get('requirement_id')
        if requirement is None:
            continue
        frames = [frame for frame in plan['answer_frames'] if frame['role'] == fact['role'] and frame['requirement_id'] == requirement
                  and frame['form_key'] == fact['form_key']]
        if len(frames) != 1:
            raise ValueError('Each assessed relation needs one matching answer frame.')
        frame = frames[0]
        pattern = frame['question_pattern_ru']
        if not re.search(pattern, _normal(question['prompt_ru'])):
            raise ValueError('Use the question for this grammatical relation.')
        options = {_normal(row[frame['form_key']]) for row in plan['checked_forms'] if frame['form_key'] in row}
        if any(_normal(choice['text']) not in options for choice in question['choices']):
            raise ValueError('Every option must belong to the same checked answer frame.')
        # The correct value is checked separately against exact source evidence.
        # Retain the declared predicate as well; a name or object alone is not
        # evidence for tense, aspect, negation or the relation being assessed.
        source = fact['checked_source_frame_ru']
        people = _lemmas(' '.join(person['name_ru'] for person in plan['meaning_plan']['participants']))
        target = _lemmas(fact['value_ru'])
        from utils.story_processing import get_morph
        predicates = [word for word in re.findall(r'[А-Яа-яЁё]+', source)
                      if any(p.is_known and p.tag.POS in ('VERB', 'INFN', 'ADJS') for p in get_morph().parse(word))
                      and not (_lemmas(word) & (people | target))]
        if predicates and not all(_contains(question['evidence'], word) for word in predicates):
            raise ValueError('The cited passage must preserve the planned predicate and its grammatical form.')
        # A present predicate is not evidence of an affirmative event when
        # every occurrence is negated. Compare local не + predicate, not any
        # unrelated нет or negative clause elsewhere in the cited passage.
        def polarities(text, predicate):
            tokens = re.findall(r'[а-яё]+|[.!?;:,]', text.lower().replace('ё', 'е'))
            value = predicate.lower().replace('ё', 'е')
            return {index > 0 and tokens[index - 1] == 'не'
                    for index, token in enumerate(tokens) if token == value}
        for predicate in predicates:
            if not polarities(source, predicate) <= polarities(question['evidence'], predicate):
                raise ValueError('The cited passage must preserve the planned predicate negation.')
        if 'нет' in _normal(source).split() and not _contains(question['evidence'], 'нет'):
            raise ValueError('An absence fact must preserve its negative construction.')
        covered.add(requirement)
    if covered != selected:
        raise ValueError('Questions must use every selected construction in context.')
