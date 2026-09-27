"""Offline validation for authored course releases; never enrols a learner.

Authored A1 content stays separate from published course loading. Passing
draft validation is not permission to publish: publication also requires
every section, editorial sign-off and real audio.
Checks here verify declared contracts and source anchors, not Russian semantics.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re


DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / 'course_drafts'
STATIC_DIR = Path(__file__).resolve().parents[1] / 'static'
SECTION_TOPICS = {
    'home': ['greetings', 'family', 'home'],
    'postoffice': ['numbers', 'daily_activities'],
    'market': ['food', 'colors', 'clothing'],
    'leavingtown': ['places', 'weather'],
}
SECTION_COUNTS = {'reading': 5, 'listening': 2, 'response': 1}
FINAL_COUNTS = {'reading': 6, 'listening': 4, 'language': 4, 'response': 2}
KEY = re.compile(r'^[a-z0-9][a-z0-9_.:-]{0,119}$')
CYRILLIC = re.compile(r'[А-Яа-яЁё]')
LATIN = re.compile(r'[A-Za-z]')


class CourseAuthoringError(ValueError):
    """All deterministic authoring problems found in one inspection."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__('\n'.join(errors))


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and '\x00' not in value


def _items(value):
    return value if isinstance(value, list) else []


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _strings(value):
    return isinstance(value, list) and all(_text(item) for item in value)


def _normal_choice(value):
    return re.sub(r'[\W_]+', '', value.casefold()) if isinstance(value, str) else ''


def validate_course_release(data, *, publication=False, target_data=None, static_root=None):
    """Validate an internal draft, or strictly gate a proposed publication.

    ``target_data`` and ``static_root`` are injectable for deterministic tests.
    The default target registry is authored local data, never browser input.
    No runtime catalogue, database, network or enrolment is changed.
    """
    if target_data is None:
        from services.curriculum_targets import curriculum_targets
        target_data = curriculum_targets()
    targets = {item['id']: item for item in _items(_mapping(target_data).get('targets'))
               if isinstance(item, dict) and _text(item.get('id'))}
    target_sections = {item['id']: item for item in _items(_mapping(target_data).get('sections'))
                       if isinstance(item, dict) and _text(item.get('id'))}
    errors = []

    def require(condition, location, message):
        if not condition:
            errors.append(f'{location}: {message}')
        return bool(condition)

    def bilingual(item, fields, location):
        for field in fields:
            require(_text(item.get(field)) and _text(item.get(field + '_ru')),
                    location, f'{field} requires English and Russian text')

    def target_ids(value, location, topics=None):
        if not require(_strings(value) and value, location, 'nonempty target_ids required'):
            return []
        require(len(value) == len(set(value)), location, 'target IDs must be distinct')
        for target in value:
            require(target in targets, location, f'unknown target {target}')
            if target in targets:
                require(targets[target].get('target_level') == 'A1', location, 'target must be A1')
                if topics is not None:
                    require(targets[target].get('topic_id') in topics, location, 'target/topic mismatch')
        return value

    if not isinstance(data, dict):
        raise CourseAuthoringError(['release: expected an object'])
    # A claimed published release must never evade publication checks by
    # leaving the caller's explicit flag at its default.
    publication = publication or data.get('status') == 'published'
    require(data.get('schema_version') == 2, 'release', 'schema_version must be 2')
    require(data.get('release_id') == 'a1-journey-v2' and data.get('band') == 'A1',
            'release', 'expected the A1 journey v2 release identity')
    require(_text(data.get('content_version')) and _text(data.get('rubric_version')),
            'release', 'content and rubric versions are required')
    require(data.get('original_letter_state') == 'sealed', 'release', 'original letter must remain sealed')
    require(data.get('status') in ('draft', 'published'), 'release', 'unknown status')
    if data.get('status') == 'draft':
        require(data.get('visibility') == 'internal' and data.get('playable') is False
                and data.get('default_enrolment') is False,
                'release', 'draft must stay internal, unplayable and outside default enrolment')
    if publication:
        require(data.get('status') == 'published', 'release', 'draft publication is forbidden')
        require(_mapping(data.get('editorial_review')).get('status') in ('approved', 'author_reviewed'),
                'release', 'publication requires completed editorial review')
        require(_mapping(data.get('editorial_review')).get('semantic_review_status') in ('approved', 'author_reviewed')
                and _mapping(data.get('editorial_review')).get('unresolved_editorial_items') == [],
                'release', 'unresolved semantic review blocks publication')
        require(data.get('publication_blockers') == [], 'release', 'unresolved publication blockers remain')

    chapters = _items(data.get('chapters'))
    require([_mapping(c).get('id') for c in chapters] == list(SECTION_TOPICS),
            'release', 'four ordered sections must be home, postoffice, market, leavingtown')
    all_topics = {topic for topics in SECTION_TOPICS.values() for topic in topics}
    variant_ids = set()
    teaching_paths = {}
    checkpoint_paths = {}
    prior_topics = []
    for number, chapter_value in enumerate(chapters, 1):
        chapter = _mapping(chapter_value)
        sid = chapter.get('id')
        location = f'section[{number}]'
        if not isinstance(sid, str) or sid not in SECTION_TOPICS:
            require(False, location, 'unknown section ID')
            continue
        location = sid
        topics = SECTION_TOPICS[sid]
        require(chapter.get('number') == number and chapter.get('release_id') == data.get('release_id'),
                location, 'ordered number and release identity must match')
        require(chapter.get('topic_ids') == topics, location, 'primary topic allocation mismatch')
        require(chapter.get('prior_topic_ids') == prior_topics, location, 'prior topics must follow the route')
        previous = list(SECTION_TOPICS)[number - 2] if number > 1 else None
        require(chapter.get('prerequisites') == ([previous] if previous else []),
                location, 'prerequisites must follow the route')
        prior_topics.extend(topics)
        bilingual(chapter, ('title', 'intro'), location)
        require(_text(chapter.get('story_location')), location, 'story location is required')
        require(chapter.get('original_letter_state') == 'sealed', location, 'original letter must remain sealed')
        status = chapter.get('content_status')
        require(status in ('authored_draft', 'pending_content', 'complete'), location, 'unknown content status')
        if status != 'complete':
            require(chapter.get('playable') is False, location, 'unfinished section must not advertise playability')
        if publication:
            require(status == 'complete', location, 'incomplete section blocks publication')
        required = target_ids(chapter.get('required_target_ids'), location, topics + _items(chapter.get('prior_topic_ids')))
        target_section = target_sections.get(sid, {})
        for field in ('required_target_ids', 'additional_practice_target_ids', 'independent_production_target_ids'):
            require(chapter.get(field) == target_section.get(field), location, f'{field} differs from target registry')
        policy = _mapping(chapter.get('preparation_policy'))
        require(policy.get('successful_tasks_per_topic') == 2 and policy.get('minimum_score') == 0.7
                and policy.get('activity_families_per_section') == 2
                and policy.get('required_targets_introduced_and_attempted') is True
                and policy.get('independent_production_required') is False,
                location, 'preparation baseline or diagnostic production policy mismatch')
        blueprint = _mapping(chapter.get('checkpoint_blueprint'))
        final = sid == 'leavingtown'
        counts = FINAL_COUNTS if final else SECTION_COUNTS
        require(blueprint.get('counts') == counts, location, 'checkpoint blueprint count mismatch')
        require(all(type(value) is int for value in _mapping(blueprint.get('counts')).values()),
                location, 'blueprint counts must be integers')
        require(blueprint.get('minimum_correct') == (13 if final else 7), location, 'integer pass threshold mismatch')
        require(blueprint.get('component_minima') == ({'reading': 4, 'listening': 3, 'language': 2, 'response': 1}
                if final else {}), location, 'component minima mismatch')
        require(blueprint.get('require_listened') is True and blueprint.get('require_independent') is True,
                location, 'listening and independent support gates are required')
        slots = _items(blueprint.get('slots'))
        slot_map = {slot.get('id'): slot for slot in slots if isinstance(slot, dict) and _text(slot.get('id'))}
        require(len(slot_map) == len(slots) == sum(counts.values()), location, 'blueprint slots must be distinct and complete')
        require(Counter(str(_mapping(slot).get('kind')) for slot in slots) == counts, location, 'blueprint slot kinds mismatch')
        sampled = set()
        sampled_topics = set()
        for slot_value in slots:
            slot = _mapping(slot_value)
            tids = target_ids(slot.get('target_ids'), location + '/blueprint', all_topics if final else topics)
            require(_text(slot.get('evidence_requirement')), location, 'blueprint slot needs an evidence requirement')
            for tid in tids:
                if tid in targets:
                    require(slot.get('response_mode') == targets[tid].get('response_mode'),
                            location, 'blueprint target response mode mismatch')
                checkpoint_paths.setdefault(tid, []).append({
                    'section_id': sid, 'slot_id': slot.get('id'), 'status': status})
            sampled.update(tids)
            sampled_topics.update(targets[t]['topic_id'] for t in tids if t in targets)
        require(set(required) <= sampled, location, 'required target lacks a scored blueprint path')
        if final:
            require(sampled_topics == all_topics, location, 'cumulative blueprint must score all ten A1 topics')
        essentials = blueprint.get('essential_slot_ids')
        require(_strings(essentials) and len(essentials) == 2 and len(set(essentials)) == 2
                and set(essentials) <= set(slot_map), location, 'two distinct justified essential slots required')
        justifications = _mapping(blueprint.get('essential_justifications'))
        require(all(_text(justifications.get(slot)) for slot in essentials) if _strings(essentials) else False,
                location, 'essential details need story justifications')

        preparation = _items(chapter.get('preparation'))
        introduced = set()
        prep_ids = set()
        for prep_value in preparation:
            prep = _mapping(prep_value)
            pid = prep.get('id')
            require(_text(pid) and pid not in prep_ids, location, 'preparation IDs must be distinct')
            if _text(pid):
                prep_ids.add(pid)
            require(prep.get('topic_id') in topics, location, 'preparation topic mismatch')
            bilingual(prep, ('title', 'explanation'), location + '/preparation')
            examples = _items(prep.get('examples'))
            require(examples and all(_text(_mapping(e).get('ru')) and _text(_mapping(e).get('en')) for e in examples),
                    location, 'preparation requires translated examples')
            taught = target_ids(prep.get('introduces_target_ids'), location + '/preparation', topics)
            introduced.update(taught)
            if _text(pid):
                teaching_paths[(sid, pid)] = set(taught)
            target_ids(prep.get('practises_target_ids'), location + '/preparation', topics)
            check = _mapping(prep.get('guided_check'))
            assessed = target_ids(check.get('target_ids'), location + '/guided-check', topics)
            require(set(assessed) <= set(taught), location, 'guided check assesses an untaught target')
            require(not any(targets.get(t, {}).get('response_mode') in ('independent_writing', 'independent_speaking', 'listening_selection')
                            for t in assessed), location, 'written guided check cannot establish production or listening')
            choices = _items(check.get('choices'))
            require(len(choices) == 3 and sum(_mapping(choice).get('id') == check.get('answer') for choice in choices) == 1,
                    location, 'guided check requires three choices and one accepted answer')
            require(check.get('pass_awarded') is False, location, 'guided check cannot award a milestone')
        variants = _items(chapter.get('variants'))
        if status == 'pending_content':
            require(not variants and not preparation, location, 'pending content must not pretend to be authored')
            require(_strings(chapter.get('pending_work')) and chapter.get('pending_work'), location, 'pending work must be explicit')
            continue
        if publication:
            require(chapter.get('pending_work') == [], location, 'unresolved section work remains')
        require(len(variants) == 3, location, 'authored section requires three equivalent variants')
        require(set(required) <= introduced, location, 'required targets lack teaching before assessment')
        variation_ids = blueprint.get('variation_fact_ids')
        require(_strings(variation_ids) and len(variation_ids) >= 3
                and len(set(variation_ids)) == len(variation_ids),
                location, 'at least three explicit variation facts are required')
        fingerprints = []
        for variant_value in variants:
            variant = _mapping(variant_value)
            vid = variant.get('id')
            vloc = f'{location}/{vid}'
            require(isinstance(vid, str) and KEY.fullmatch(vid) and vid not in variant_ids, vloc, 'variant ID must be stable and unique')
            if isinstance(vid, str):
                variant_ids.add(vid)
            bilingual(variant, ('letter_title', 'support_note'), vloc)
            letter = variant.get('letter') if isinstance(variant.get('letter'), str) else ''
            require(_text(letter), vloc, 'Russian received letter required')
            require(variant.get('recipient_id') == 'barsik' and variant.get('letter_role') == 'received_section_letter',
                    vloc, 'checkpoint must be a separate received letter addressed to Barsik')
            require(_text(variant.get('sender_id')) and _text(variant.get('sender_name_ru')),
                    vloc, 'named sender required')
            for field in ('content_version', 'rubric_version', 'reason_for_arrival', 'expected_consequence'):
                require(_text(variant.get(field)), vloc, f'{field} required')
            require(all(_text(variant.get(field)) for field in ('sender_name_en', 'reason_for_arrival_en', 'reason_for_arrival_ru')),
                    vloc, 'sender and nonspoiling arrival context require English and Russian')
            require(variant.get('original_letter_state') == 'sealed', vloc, 'original letter must remain sealed')
            consequence = _mapping(variant.get('consequence'))
            require(_text(consequence.get('text')) and _text(consequence.get('text_ru'))
                    and consequence.get('original_letter_state') == 'sealed', vloc, 'bilingual consequence must keep the original letter sealed')
            require(consequence.get('next_section_id') == (list(SECTION_TOPICS)[number] if number < 4 else None),
                    vloc, 'story consequence must continue the authored route')
            writing = _mapping(variant.get('writing_task'))
            require(all(_text(writing.get(field)) for field in ('title', 'title_en', 'task', 'task_en'))
                    and writing.get('topic_id') in all_topics
                    and _strings(writing.get('required_words')) and len(writing['required_words']) == 3
                    and writing.get('optional') is True and writing.get('affects_milestone_pass') is False,
                    vloc, 'optional writing task requires a complete bilingual brief and three taught words')
            require(_mapping(variant.get('support_policy')) == {
                'hints': 'supported_attempt', 'transcript': 'supported_attempt',
                'audio_replay': 'independent', 'explanations': 'after_submission',
                'glossary': 'incidental_only', 'independent_retry': 'fresh_variant'},
                vloc, 'support policy mismatch')
            audio = _mapping(variant.get('listening'))
            transcript = audio.get('transcript') if isinstance(audio.get('transcript'), str) else ''
            require(_text(transcript) and transcript != letter, vloc, 'separate spoken update required')
            require(all(isinstance(writing.get(field), str) and letter in writing[field] and transcript in writing[field]
                        for field in ('task', 'task_en')),
                    vloc, 'writing continuation must preserve the letter and spoken update context')
            require(audio.get('text_sha256') == hashlib.sha256(str(transcript).encode()).hexdigest(),
                    vloc, 'audio transcript hash mismatch')
            require(isinstance(audio.get('id'), str) and KEY.fullmatch(audio['id'])
                    and _text(audio.get('media_version')), vloc, 'versioned audio identity required')
            require(audio.get('status') in ('missing', 'ready'), vloc, 'audio status must be honest and explicit')
            if audio.get('status') == 'missing':
                require(all(audio.get(k) is None for k in ('audio_url', 'audio_sha256', 'duration_seconds')),
                        vloc, 'missing audio must not have fabricated asset metadata')
            if publication:
                require(audio.get('status') == 'ready', vloc, 'missing audio blocks publication')
            if audio.get('status') == 'ready':
                expected_url = f"/static/audio/course/{data['release_id']}/{audio.get('id')}.mp3"
                if require(audio.get('audio_url') == expected_url, vloc, 'audio URL must identify the immutable release clip'):
                    root = Path(static_root) if static_root is not None else STATIC_DIR
                    asset = root / expected_url.removeprefix('/static/')
                    safe = asset.resolve().is_relative_to(root.resolve())
                    if require(safe and asset.is_file(), vloc, 'published audio file is missing'):
                        require(audio.get('audio_sha256') == hashlib.sha256(asset.read_bytes()).hexdigest(),
                                vloc, 'audio content hash mismatch')
                        from services.speech_provider import audio_info
                        try:
                            duration = audio_info(asset)
                            declared = audio.get('duration_seconds')
                            require(type(declared) in (int, float) and 3 < duration < 30
                                    and abs(duration - declared) < 0.15, vloc, 'audio duration or decode mismatch')
                        except Exception:
                            require(False, vloc, 'audio cannot be decoded')

            facts = _mapping(variant.get('story_facts'))
            for fact_id, fact_value in facts.items():
                fact = _mapping(fact_value)
                source = letter if fact.get('source') == 'letter' else transcript if fact.get('source') == 'listening' else ''
                quote = fact.get('source_quote')
                require(_text(fact.get('value_ru')) and _text(quote) and quote in source,
                        vloc, f'fact {fact_id} lacks a literal source anchor')
            require(variant.get('variation_fact_ids') == variation_ids, vloc, 'variant variation facts differ from blueprint')
            require(all(key in facts for key in _items(variation_ids)), vloc, 'variation fact is missing')
            fingerprints.append(tuple(_normal_choice(_mapping(facts.get(key)).get('value_ru'))
                                      for key in _items(variation_ids)))
            language = _mapping(variant.get('language_manifest'))
            require(language.get('review_scope') == ['letter', 'listening', 'prompts', 'choices', 'hints', 'explanations'],
                    vloc, 'language review must include prompts and distractors')
            require(_strings(language.get('taught_preparation_ids'))
                    and set(language.get('taught_preparation_ids', [])) <= prep_ids,
                    vloc, 'language manifest references missing teaching')
            require(_items(language.get('contextual_forms')), vloc, 'contextual forms manifest required')
            if publication:
                require(language.get('review_status') in ('approved', 'author_reviewed'), vloc, 'variant language review remains incomplete')
                require(language.get('unresolved_editorial_items') == [], vloc, 'unresolved variant editorial items block publication')
            vocabulary = _items(variant.get('flashcard_candidates'))
            require(1 <= len(vocabulary) <= 2, vloc, 'one or two contextual flashcard candidates required')
            for candidate_value in vocabulary:
                candidate = _mapping(candidate_value)
                sentence = candidate.get('sentence', '')
                require(all(_text(candidate.get(field)) for field in ('lemma', 'form', 'pos', 'sentence', 'translation', 'target_meaning'))
                        and isinstance(candidate.get('grammar'), dict), vloc, 'flashcard candidate needs contextual meaning and morphology')
                require(_text(sentence) and sentence in letter, vloc, 'flashcard sentence must come from the received letter')
                require(_text(sentence) and _text(candidate.get('form'))
                        and bool(re.search(r'(?<![А-Яа-яЁё])' + re.escape(candidate['form']) + r'(?![А-Яа-яЁё])', sentence, re.I)),
                        vloc, 'flashcard form must occur as a word in its source sentence')
            for entry in _items(variant.get('glossary')):
                entry = _mapping(entry)
                require(_text(entry.get('ru')) and _text(entry.get('en')) and entry.get('role') == 'incidental',
                        vloc, 'glossary must identify incidental bilingual entries')
                require(_normal_choice(entry.get('ru')) not in {_normal_choice(_mapping(f).get('value_ru')) for f in facts.values()},
                        vloc, 'glossary must not reveal an assessed fact')
            questions = _items(variant.get('questions'))
            require([_mapping(q).get('id') for q in questions] == [slot.get('id') for slot in slots],
                    vloc, 'question order or blueprint slots mismatch')
            for question_value in questions:
                question = _mapping(question_value)
                qloc = f"{vloc}/{question.get('id')}"
                slot = slot_map.get(question.get('id'), {}) if _text(question.get('id')) else {}
                bilingual(question, ('prompt', 'hint', 'explanation'), qloc)
                require(question.get('kind') == slot.get('kind') and question.get('target_ids') == slot.get('target_ids'),
                        qloc, 'question kind or targets differ from equivalent blueprint')
                target_ids(question.get('target_ids'), qloc, question.get('topic_ids', []))
                require(question.get('response_mode') == slot.get('response_mode'), qloc, 'response mode mismatch')
                for tid in _items(question.get('target_ids')):
                    if tid in targets:
                        require(question.get('response_mode') == targets[tid].get('response_mode'),
                                qloc, 'selected choice cannot claim independent writing or speaking')
                require(type(question.get('essential')) is bool and question['essential'] == (question.get('id') in _items(essentials)),
                        qloc, 'essential designation differs from blueprint')
                choices = _items(question.get('choices'))
                ids = [_mapping(choice).get('id') for choice in choices]
                texts = [_mapping(choice).get('text') for choice in choices]
                require(len(choices) == 3 and _strings(ids) and len(set(ids)) == len(ids), qloc, 'three distinct choice IDs required')
                require(all(_text(t) and CYRILLIC.search(t) and not LATIN.search(t) for t in texts),
                        qloc, 'all choices must be nonempty Russian')
                require(len({_normal_choice(t) for t in texts}) == len(texts), qloc, 'duplicate distractor text')
                correct = [c for c in choices if _mapping(c).get('id') == question.get('answer')]
                require(len(correct) == 1 and _mapping(correct[0]).get('text') == question.get('accepted_answer_text')
                        if correct else False, qloc, 'answer must reference the declared accepted choice')
                for choice_value in choices:
                    choice = _mapping(choice_value)
                    is_answer = choice.get('id') == question.get('answer')
                    require(choice.get('role') == ('correct' if is_answer else 'distractor')
                            and _text(choice.get('review_rationale')), qloc, 'choices need a reviewed correct/distractor role')
                    if not is_answer:
                        require(choice.get('error_type') in ('changed_fact', 'contextual_form', 'inappropriate_response'),
                                qloc, 'distractor needs an explicit plausible error')
                evidence = _items(question.get('evidence'))
                require(evidence, qloc, 'scored target needs source evidence')
                for eid in evidence:
                    fact = _mapping(facts.get(eid)) if isinstance(eid, str) else {}
                    require(bool(fact), qloc, 'unknown story fact in evidence')
                    if question.get('kind') == 'listening':
                        require(fact.get('source') == 'listening' and fact.get('source_quote') not in letter,
                                qloc, 'listening answer must require new spoken information')
                require(question.get('partial_credit') == 'none' and question.get('score_points') == 1,
                        qloc, 'selected decisions use one point and no partial credit')
        require(len(set(fingerprints)) == len(fingerprints), location, 'variants must vary meaningful facts, not only names')
        for left in range(len(fingerprints)):
            for right in range(left + 1, len(fingerprints)):
                require(sum(a != b for a, b in zip(fingerprints[left], fingerprints[right])) >= 3,
                        location, 'variant pairs must vary at least three meaningful facts')

    coverage = _items(data.get('target_coverage'))
    coverage_ids = [_mapping(item).get('target_id') for item in coverage]
    require(_strings(coverage_ids) and len(set(coverage_ids)) == len(coverage_ids)
            and set(coverage_ids) == set(targets), 'coverage', 'every registered target needs one explicit coverage policy')
    for row_value in coverage:
        row = _mapping(row_value)
        tid = row.get('target_id')
        if not isinstance(tid, str) or tid not in targets:
            continue
        target = targets[tid]
        location = f'coverage/{tid}'
        require(row.get('topic_id') == target.get('topic_id') and row.get('source') == target.get('source'),
                location, 'curriculum source mapping mismatch')
        teaching = _mapping(row.get('teaching'))
        sid = target.get('primary_section_id')
        require(teaching.get('section_id') == sid, location, 'teaching path must use the primary section')
        if teaching.get('status') in ('authored_draft', 'complete'):
            require(tid in teaching_paths.get((sid, teaching.get('preparation_id')), set()),
                    location, 'authored target lacks a teaching path')
        else:
            require(teaching.get('status') == 'planned', location, 'teaching status must be explicit')
            if publication:
                require(False, location, 'planned teaching blocks publication')
        if publication:
            require(teaching.get('status') == 'complete', location, 'teaching is not complete for publication')
        practice = _mapping(row.get('practice'))
        require(_strings(practice.get('activities')) and practice.get('activities')
                and set(practice['activities']) <= {'reading', 'translation', 'word_jumble', 'writing', 'speaking'}
                and practice.get('requires_saved_target_contract') is True,
                location, 'practice needs existing activities and saved target contracts')
        expected_paths = checkpoint_paths.get(tid, [])
        require(row.get('checkpoint_paths') == expected_paths, location, 'checkpoint coverage must match scored blueprint slots')
        diagnostic = tid in _items(target_sections.get(sid, {}).get('independent_production_target_ids'))
        expected_policy = ('optional_independent_production_diagnostic' if diagnostic else
                           'sampled_by_scored_checkpoint_decision' if expected_paths else
                           'additional_practice_not_established_by_checkpoint')
        require(row.get('evidence_policy') == expected_policy, location, 'target evidence policy overclaims assessment')

    if errors:
        raise CourseAuthoringError(errors)
    return data


def load_draft_release(release_id='a1-journey-v2'):
    """Explicit authoring access only; never a fallback for published loading."""
    if release_id != 'a1-journey-v2':
        raise ValueError('Unknown internal draft release.')
    data = json.loads((DATA_DIR / f'{release_id}.json').read_text(encoding='utf-8'))
    return deepcopy(validate_course_release(data))
