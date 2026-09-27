"""Authored A1 course gates, independent of coins and provisional skill ratings.

Evidence is accepted only at the time a saved progression event is awarded.
Snapshots ignore reversed receipts, but passing a checkpoint is permanent.
Every checkpoint freezes its content and rubric and returns only public fields.
"""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlencode

from flask import current_app, has_app_context

from contracts.learning import key
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, timestamp
from services.curriculum import curriculum
from services.course_releases import DEFAULT_RELEASE_ID, RELEASES, load_release, release_metadata, default_release_id
from services.course_reference_notes import reference_groups
from services.speaking_curriculum import scenario_for_topic

DATA_FILE = Path(__file__).resolve().parents[1] / 'data' / 'course_chapters.json'
PRACTICE_POLICY = 'a1-course-practice-v1'
JOURNEY_PREPARATION_POLICY = 'activity-or-target-practice-v1'
REQUIRED_TASKS = 2
REQUIRED_ACTIVITIES = 2
ACTIVITIES = ('reading', 'writing', 'translation', 'word_jumble', 'speaking')
ACTIVITY_FAMILIES = {'speaking_step': 'speaking', 'first_delivery': 'reading'}
RUBRIC = {'minimum_score': 0.8, 'require_essential': True, 'require_listened': True,
          'require_independent': True}


def _execute(conn, statement, values=()):
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(statement, values)


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and '\x00' not in value


def _content_key(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}', value))


def validate_course(data, release=None):
    """Reject incomplete teaching content before it can become an assessment."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    release = release or release_metadata()
    if release['schema_version'] == 2:
        from services.course_authoring import validate_course_release
        require(data.get('release_id') == release['release_id'], 'Course release identity mismatch.')
        validate_course_release(data, publication=True)
        return data
    band = release['band']
    require(isinstance(data, dict) and type(data.get('version')) is int and data['version'] == release['schema_version'],
            'Course content must use its release schema version.')
    require(data.get('band') == band and _nonempty(data.get('rubric_version')),
            'Course content needs its release band and rubric version.')
    chapters = data.get('chapters')
    require(isinstance(chapters, list) and len(chapters) == release['chapter_count'] and len(chapters) > 0,
            'The complete release needs all its ordered chapters.')
    topic_band = 'C1-C2' if band in ('C1', 'C2') else band
    expected_topics = {topic['id'] for topic in curriculum()['topics'] if topic['band'] == topic_band}
    seen_topics, chapter_ids, variant_ids = [], set(), set()
    for number, chapter in enumerate(chapters, 1):
        require(isinstance(chapter, dict) and _content_key(chapter.get('id')),
                'Every chapter needs a stable ID.')
        require(chapter['id'] not in chapter_ids and type(chapter.get('number')) is int and chapter['number'] == number,
                'Chapter IDs must be distinct and chapter numbers sequential.')
        chapter_ids.add(chapter['id'])
        for field in ('title', 'title_ru', 'intro', 'intro_ru'):
            require(_nonempty(chapter.get(field)), 'Every chapter needs nonempty bilingual titles and introductions.')
        topics = chapter.get('topic_ids')
        require(isinstance(topics, list) and topics and all(isinstance(t, str) and t in expected_topics for t in topics),
                'Chapters must use known curriculum topics for their band.')
        seen_topics.extend(topics)
        objectives = chapter.get('objectives', [])
        require(isinstance(objectives, list) and all(isinstance(item, dict) and _nonempty(item.get('en'))
                and _nonempty(item.get('ru')) for item in objectives), 'Chapter objectives require both languages.')
        preparation = chapter.get('preparation', [])
        require(isinstance(preparation, list), 'Chapter preparation must be a list.')
        for item in preparation:
            require(isinstance(item, dict) and item.get('topic_id') in topics
                    and all(_nonempty(item.get(field)) for field in ('title', 'title_ru', 'explanation', 'explanation_ru')),
                    'Preparation needs a chapter topic and bilingual teaching content.')
            examples = item.get('examples')
            require(isinstance(examples, list) and examples and all(isinstance(example, dict)
                    and _nonempty(example.get('ru')) and _nonempty(example.get('en')) for example in examples),
                    'Preparation needs translated Russian examples.')
        variants = chapter.get('variants')
        require(isinstance(variants, list) and len(variants) >= 2, 'Every checkpoint needs at least two equivalent variants.')
        variant_shapes = []
        for variant in variants:
            require(isinstance(variant, dict) and _content_key(variant.get('id'))
                    and variant['id'] not in variant_ids, 'Checkpoint variant IDs must be distinct.')
            variant_ids.add(variant['id'])
            for field in ('letter', 'letter_title', 'letter_title_ru'):
                require(_nonempty(variant.get(field)), 'Every checkpoint needs a letter and bilingual title.')
            listening = variant.get('listening')
            require(isinstance(listening, dict) and _nonempty(listening.get('transcript'))
                    and listening.get('audio_url') == '/static/audio/course/' + variant['id'] + '.mp3',
                    'Every checkpoint needs its own bundled listening clip and transcript.')
            glossary = variant.get('glossary', [])
            require(isinstance(glossary, list), 'The glossary must be a list.')
            for item in glossary:
                require(isinstance(item, dict) and _nonempty(item.get('ru')) and _nonempty(item.get('en')),
                        'Glossary entries require both languages.')
            questions = variant.get('questions')
            require(isinstance(questions, list) and len(questions) >= 5, 'A checkpoint requires at least five questions.')
            question_ids, kinds, essential_count = set(), [], 0
            for question in questions:
                require(isinstance(question, dict) and _content_key(question.get('id'))
                        and question['id'] not in question_ids, 'Question IDs must be distinct within a variant.')
                question_ids.add(question['id'])
                require(question.get('kind') in ('reading', 'listening', 'response'), 'Unknown checkpoint question kind.')
                kinds.append(question['kind'])
                for field in ('prompt', 'prompt_ru', 'hint', 'hint_ru', 'explanation', 'explanation_ru'):
                    require(_nonempty(question.get(field)), 'Questions need bilingual prompts, hints and explanations.')
                require(type(question.get('essential')) is bool, 'Questions must explicitly mark essential decisions.')
                essential_count += question['essential']
                choices = question.get('choices')
                require(isinstance(choices, list) and 2 <= len(choices) <= 6, 'Each question needs 2–6 choices.')
                choice_ids, choice_texts = set(), set()
                for choice in choices:
                    require(isinstance(choice, dict) and _content_key(choice.get('id')) and _nonempty(choice.get('text')),
                            'Every choice needs an ID and text.')
                    require(choice['id'] not in choice_ids and choice['text'] not in choice_texts,
                            'Choice IDs and texts must be distinct.')
                    choice_ids.add(choice['id']); choice_texts.add(choice['text'])
                require(isinstance(question.get('answer'), str) and question['answer'] in choice_ids,
                        'Correct answers must reference offered choices.')
            require(set(kinds) == {'reading', 'listening', 'response'} and essential_count > 0,
                    'Each checkpoint must assess reading, listening and a response, including essential decisions.')
            variant_shapes.append((sorted(kinds), essential_count))
        require(all(shape == variant_shapes[0] for shape in variant_shapes),
                'Equivalent variants must cover the same question kinds and essential decision count.')
    require(len(seen_topics) == len(set(seen_topics)) and set(seen_topics) == expected_topics,
            'A complete release must cover each curriculum topic in its band exactly once.')
    return data


@lru_cache(maxsize=16)
def _catalogue(release_id=DEFAULT_RELEASE_ID):
    return validate_course(load_release(release_id), release_metadata(release_id))


def course_catalogue(release_id=None):
    release = release_metadata(default_release_id() if release_id is None else release_id)
    return deepcopy(_catalogue(release['release_id'])) | {
        name: release[name] for name in ('release_id', 'chapter_count', 'requirement_version')}


def _chapter(chapter_id, release_id):
    chapter = next((item for item in _catalogue(release_id)['chapters'] if item['id'] == chapter_id), None)
    if chapter is None:
        raise LearningError('chapter_not_found', 'That course chapter does not exist.', 404)
    return chapter


def record_evidence(conn, profile_id, event_id, activity, content_key, target_level, evidence, now):
    """Receive trusted, server-frozen task metadata after its event is saved.

    Supported practice can satisfy coverage; independence is checked separately
    by the checkpoint. Unsupported and unsuccessful tasks do not count here.
    Repeated events for the same activity/content never become distinct tasks.
    """
    metadata = evidence.get('_course') if isinstance(evidence, dict) else None
    if not isinstance(metadata, dict) or activity not in (*ACTIVITIES, *ACTIVITY_FAMILIES):
        return False
    if not _execute(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_evidence'").fetchone():
        return False
    score = metadata.get('score')
    if (metadata.get('level') != 'A1' or target_level not in (None, 'A1')
            or type(metadata.get('assisted')) is not bool
            or type(score) not in (int, float) or not math.isfinite(score) or not 0.7 <= score <= 1):
        return False
    topic_ids = {topic for chapter in _catalogue()['chapters'] for topic in chapter['topic_ids']}
    if metadata.get('topic_id') not in topic_ids:
        return False
    # Bind all attributes to the saved event, including its selected learner.
    event = _execute(conn, 'SELECT profile_id,activity,content_key,target_level,reversed_at FROM progression_events WHERE id=?',
                         (event_id,)).fetchone()
    if (not event or tuple(event[:4]) != (profile_id, activity, str(content_key), target_level)
            or event['reversed_at'] is not None):
        return False
    cursor = _execute(conn, 'INSERT OR IGNORE INTO course_evidence VALUES (?,?,?,?,?,?,?,?,?)',
                         (event_id, profile_id, metadata['topic_id'], ACTIVITY_FAMILIES.get(activity, activity), str(content_key), 'A1', score, PRACTICE_POLICY, now))
    return cursor.rowcount == 1


def _links(topic_id, band='A1'):
    query = urlencode({'topic': topic_id, 'level': band})
    result = [
        {'activity': activity, 'label': label, 'label_ru': label_ru, 'href': path + '?' + query}
        for activity, label, label_ru, path in (
            ('reading', 'Reading', 'Чтение', '/comprehension'),
            ('writing', 'Writing', 'Письмо', '/writing'),
            ('translation', 'Translation', 'Перевод', '/sentences'),
            ('word_jumble', 'Word Jumble', 'Составь предложение', '/word_jumble'))]
    scenario = scenario_for_topic(topic_id, band)
    if scenario:
        result.append({'activity': 'speaking', 'label': 'Speaking', 'label_ru': 'Разговорная практика',
                       'href': '/#speaking/scenario/' + scenario + '?' + urlencode({'level': band})})
    return result


def _reveal_course(course):
    """Keep future stops as numbered placeholders, including saved API receipts.

    The public curriculum and standalone practice stay available. This changes
    only the journey presentation; evidence and readiness are still calculated
    from the full authoritative catalogue before the next stop is revealed.
    """
    if not course or not isinstance(course.get('chapters'), list):
        return course
    chapters = []
    for chapter in course['chapters']:
        if chapter['status'] == 'locked':
            chapter = dict(chapter, title='', title_ru='', intro='', intro_ru='',
                           topics=[], objectives=[], preparation=[], target_coverage=None,
                           progress=0, preparation_progress=0, activity_count=0,
                           last_attempt_id=None, active_attempt_id=None)
            if 'activity_preparation_progress' in chapter:
                chapter.update(activity_preparation_progress=0, preparation_basis='none',
                               target_preparation_progress=0 if chapter['target_preparation_progress'] is not None else None)
        elif chapter.get('preparation'):
            chapter = dict(chapter, preparation=[dict(item, groups=reference_groups(
                chapter.get('release_id', course.get('release_id')), item.get('id')))
                for item in chapter['preparation']])
        chapters.append(chapter)
    return dict(course, chapters=chapters)


def _reveal_receipt(response):
    # Old receipts keep their exact assessment/result state, but cannot restore
    # a superseded presentation that advertised every future narrative stop.
    return dict(response, course=_reveal_course(response['course'])) if response.get('course') else response


def _current_release(conn, profile_id, band):
    enrolment = _execute(conn, 'SELECT release_id FROM course_enrolments WHERE profile_id=? AND band=?',
                         (profile_id, band)).fetchone()
    if enrolment:
        release = release_metadata(enrolment['release_id'])
        if release['band'] != band:
            raise LearningError('course_release_mismatch', 'This saved course has an inconsistent level.', 409)
        return release
    default = release_metadata(default_release_id())
    if default['band'] == band:
        return default
    candidates = [release for release in RELEASES.values() if release.get('status') == 'published' and release['band'] == band]
    preferred = [release for release in candidates if release.get('default_for_band')]
    if len(preferred) == 1 or len(candidates) == 1:
        return release_metadata((preferred or candidates)[0]['release_id'])
    raise LearningError('course_release_unavailable', 'There is no available course for this level.', 404)


def course_snapshot(conn, profile_id, *, release_id=None, band=None):
    """Project current preparation and permanent passes without writing state."""
    if not _execute(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_enrolments'").fetchone():
        return None
    # A read never creates enrolment. New learners receive the complete default
    # edition on their first checkpoint command; migration pins existing ones.
    if band is not None and band not in ('A1', 'A2', 'B1', 'B2', 'C1', 'C2'):
        raise LearningError('invalid_input', 'Choose a valid course level.')
    selected = release_metadata(release_id) if release_id is not None else None
    if selected and band is not None and selected['band'] != band:
        raise LearningError('invalid_input', 'The course release and level do not match.')
    band = band or (selected or release_metadata(default_release_id()))['band']
    current = _current_release(conn, profile_id, band)
    release = selected or current
    release_id, band = release['release_id'], release['band']
    catalogue = _catalogue(release_id)
    targeted_preparation = bool(release.get('preparation'))
    preparation_policy = JOURNEY_PREPARATION_POLICY if targeted_preparation else PRACTICE_POLICY
    topics = {topic['id']: topic for topic in curriculum()['topics']}
    passed = {row['chapter_id'] for row in _execute(conn, 'SELECT chapter_id FROM course_chapter_passes WHERE profile_id=? AND release_id=?', (profile_id, release_id))}
    evidence = _execute(conn,
        'SELECT DISTINCT c.topic_id,c.activity,c.content_key FROM course_evidence c '
        'JOIN progression_events e ON e.id=c.event_id AND e.profile_id=c.profile_id '
        'WHERE c.profile_id=? AND c.target_level=? AND e.reversed_at IS NULL', (profile_id, band)).fetchall()
    chapters, current_id = [], None
    for chapter in catalogue['chapters']:
        rows = [row for row in evidence if row['topic_id'] in chapter['topic_ids']]
        projected_topics = []
        for topic_id in chapter['topic_ids']:
            topic = topics[topic_id]
            count = sum(row['topic_id'] == topic_id for row in rows)
            projected_topics.append({'id': topic_id, 'title': topic['title_en'], 'title_ru': topic['title_ru'],
                                     'objectives': topic['objectives'], 'completed': count >= REQUIRED_TASKS,
                                     'successful_tasks': count, 'required_tasks': REQUIRED_TASKS, 'links': _links(topic_id, band)})
        activity_count = len({row['activity'] for row in rows})
        task_fraction = sum(min(item['successful_tasks'], REQUIRED_TASKS) for item in projected_topics) / (len(projected_topics) * REQUIRED_TASKS)
        activity_preparation = min(task_fraction, activity_count / REQUIRED_ACTIVITIES, 1.0)
        preparation = activity_preparation
        target_preparation = None
        coverage = None
        if targeted_preparation:
            from services.course_targets import target_coverage
            coverage = target_coverage(conn, profile_id, chapter['id'], release_id=release_id)
            target_preparation = coverage['prepared_count'] / max(coverage['required_count'], 1)
            # These are alternative preparation routes, not proficiency scores.
            # Aggregate activity success never creates target observations.
            preparation = max(activity_preparation, target_preparation)
        preparation_basis = ('none' if preparation == 0 else
                             'both' if target_preparation == activity_preparation else
                             'target_practice' if target_preparation is not None and target_preparation > activity_preparation else
                             'activity_practice')
        if chapter['id'] in passed:
            status, progress = 'passed', 1.0
        elif current_id is None:
            current_id = chapter['id']
            status, progress = ('ready' if preparation == 1 else 'practice'), preparation
        else:
            status, progress = 'locked', preparation
        last = _execute(conn, 'SELECT id,status FROM course_checkpoint_attempts WHERE profile_id=? AND release_id=? AND chapter_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                            (profile_id, release_id, chapter['id'])).fetchone()
        chapters.append({name: chapter[name] for name in ('id', 'number', 'title', 'title_ru', 'intro', 'intro_ru')} | {
            'status': status, 'progress': progress, 'topics': projected_topics, 'activity_count': activity_count,
            'release_id': release_id, 'preparation_progress': preparation,
            'preparation_policy': preparation_policy, 'preparation_basis': preparation_basis,
            'activity_preparation_progress': activity_preparation,
            'target_preparation_progress': target_preparation,
            'assessment_ready': status == 'ready', 'milestone_passed': status == 'passed',
            'required_activity_count': REQUIRED_ACTIVITIES, 'last_attempt_id': last['id'] if last else None,
            'active_attempt_id': last['id'] if last and last['status'] == 'active' else None,
            'target_coverage': coverage,
            'objectives': deepcopy(chapter.get('objectives', [])), 'preparation': deepcopy(chapter.get('preparation', []))})
    completed = all(chapter['status'] == 'passed' for chapter in chapters)
    active_progress = next((chapter['progress'] for chapter in chapters if chapter['id'] == current_id), 0)
    entitled = {row['target_level'] for row in _execute(conn,
        'SELECT target_level FROM course_continuation_entitlements WHERE profile_id=?', (profile_id,))}
    return _reveal_course({'version': catalogue['version'], 'profile_id': profile_id, 'band': band, 'release_id': release_id,
            'current_release_id': current['release_id'], 'is_current_release': release_id == current['release_id'],
            'preparation_policy': preparation_policy, 'assessment_scope': 'journey_checkpoint',
            'awards_proficiency_level': False,
            'chapter_count': len(chapters), 'completed_milestones': sum(chapter['status'] == 'passed' for chapter in chapters),
            'unlocked_levels': [level for level in ('A1', 'A2', 'B1', 'B2', 'C1', 'C2') if level == 'A1' or level in entitled],
            'current_chapter_id': current_id,
            'progress': 1.0 if completed else active_progress,
            'completed': completed, 'chapters': chapters,
            'release_upgrade': _release_upgrade(conn, profile_id, release_id, entitled) if release_id == current['release_id'] else None,
            'previous_courses': _previous_courses(conn, profile_id, release_id)})


def _attempt(conn, profile_id, attempt_id):
    key(attempt_id, 'Attempt ID')
    row = _execute(conn, 'SELECT * FROM course_checkpoint_attempts WHERE id=? AND profile_id=?', (attempt_id, profile_id)).fetchone()
    if not row:
        raise LearningError('checkpoint_not_found', 'That checkpoint was not found for this learner.', 404)
    return row


def _public_attempt(conn, profile_id, row):
    frozen = json.loads(row['frozen_json'])
    variant = frozen['variant']
    support = json.loads(row['support_json'])
    finished = row['status'] != 'active'
    listening = {'audio_url': variant['listening']['audio_url']}
    if finished or 'transcript' in support:
        listening['transcript'] = variant['listening']['transcript']
    questions = []
    for question in variant['questions']:
        item = {field: deepcopy(question[field]) for field in ('id', 'kind', 'prompt', 'prompt_ru')}
        # Authoring annotations include the correct role and distractor rationale.
        # Only the offered labels belong in an unanswered assessment.
        item['choices'] = [{field: choice[field] for field in ('id', 'text')} for choice in question['choices']]
        if finished or 'hint:' + question['id'] in support:
            item.update(hint=question['hint'], hint_ru=question['hint_ru'])
        questions.append(item)
    result = {field: frozen[field] for field in ('chapter_id', 'chapter_number', 'title', 'title_ru')}
    # Old frozen JSON remains untouched. Its added row identity supplies the
    # missing metadata without confusing the saved letter with today's route.
    release = release_metadata(row['release_id'])
    result.update(release_id=row['release_id'], band=row['band'],
                  chapter_count=frozen.get('chapter_count', release['chapter_count']))
    result.update(id=row['id'], letter=variant['letter'], letter_title=variant['letter_title'],
                  letter_title_ru=variant['letter_title_ru'], glossary=deepcopy(variant.get('glossary', [])),
                  listening=listening, questions=questions, status=row['status'], support_used=bool(support),
                  listened=row['listened_at'] is not None, course=course_snapshot(conn, profile_id))
    if 'draft_json' in row.keys():
        result.update(draft_answers=json.loads(row['draft_json']), draft_revision=row['draft_revision'])
    if frozen.get('blueprint'):
        result.update(sender=variant.get('sender_name_en', variant['sender_name_ru']), sender_ru=variant['sender_name_ru'],
                      letter_purpose=variant.get('reason_for_arrival_en', ''), letter_purpose_ru=variant.get('reason_for_arrival_ru', ''),
                      original_letter_state=variant.get('original_letter_state'),
                      component_minima=frozen['blueprint']['component_minima'])
    if finished and row['result_json']:
        result['result'] = json.loads(row['result_json'])
        answers = json.loads(row['answers_json'])
        for item in result['result']['feedback']:
            item['selected_answer'] = answers[item['question_id']]
        consequence = variant.get('consequence', {})
        if result['result']['passed']:
            result.update(consequence=consequence.get('text'), consequence_ru=consequence.get('text_ru'), achieved=True)
        else:
            result['achieved'] = False
        # Capture is offered only after checking; no link reveals assessed words early.
        words = list(dict.fromkeys(re.findall(r'[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*', variant['letter'])))
        # Anonymous sample sessions cannot save AI-backed follow-ups. Signed-in
        # workspaces use their existing metered services and collection stores.
        followups_available = not (has_app_context() and current_app.config.get('PUBLIC_DEMO'))
        result['vocabulary'] = [{'word': word, 'context': variant['letter']} for word in words] if followups_available else []
        result['writing_available'] = followups_available and bool(variant.get('writing_task'))
        result['flashcards_available'] = followups_available and bool(variant.get('flashcard_candidates'))
    return result


def checkpoint_read(conn, profile_id, attempt_id):
    return _public_attempt(conn, profile_id, _attempt(conn, profile_id, attempt_id))


def checkpoint_start(conn, profile_id, chapter_id, request_id, challenge=False, now=None, *, release_id=None):
    key(request_id, 'Request ID')
    if type(challenge) is not bool:
        raise LearningError('invalid_input', 'Challenge must be true or false.')
    choices = {'chapter_id': chapter_id, 'challenge': challenge}
    if release_id is not None:
        # Omitted identity deliberately keeps the exact schema-044 fingerprint.
        # Never rebind a saved request to the learner's later enrolment.
        release_metadata(release_id)
        choices['release_id'] = release_id
    fingerprint = payload_hash(choices)
    previous = _execute(conn, 'SELECT payload_hash,response_json FROM course_checkpoint_requests WHERE profile_id=? AND request_id=?',
                            (profile_id, request_id)).fetchone()
    if previous:
        if previous['payload_hash'] != fingerprint:
            raise LearningError('idempotency_conflict', 'This request ID was already used for different checkpoint choices.', 409)
        return _reveal_receipt(json.loads(previous['response_json']))
    state = course_snapshot(conn, profile_id, release_id=release_id)
    if state is None:
        raise LearningError('course_unavailable', 'The course is temporarily unavailable.', 503)
    if not state['is_current_release']:
        raise LearningError('course_release_mismatch', 'This learner is enrolled in a different course release.', 409)
    release_id = state['release_id']
    release = release_metadata(release_id)
    catalogue = _catalogue(release_id)
    chapter = _chapter(chapter_id, release_id)
    projected = next(item for item in state['chapters'] if item['id'] == chapter_id)
    if projected['status'] == 'locked':
        raise LearningError('chapter_locked', 'Complete the previous chapter checkpoint first.', 403)
    if projected['status'] == 'passed':
        raise LearningError('chapter_passed', 'This chapter is already complete. Continue to the next chapter.', 409)
    active = _execute(conn, "SELECT * FROM course_checkpoint_attempts WHERE profile_id=? AND release_id=? AND chapter_id=? AND status='active'", (profile_id, release_id, chapter_id)).fetchone()
    now = timestamp() if now is None else now
    if not active and projected['status'] != 'ready' and not challenge:
        raise LearningError('practice_required', 'Complete this chapter’s practice or choose to test out.', 403)
    _execute(conn, 'INSERT OR IGNORE INTO course_enrolments(profile_id,band,release_id,started_at) VALUES (?,?,?,?)',
             (profile_id, release['band'], release_id, now))
    if active:
        result = _public_attempt(conn, profile_id, active)
    else:
        previous_variants = [row['variant_id'] for row in _execute(conn,
            'SELECT variant_id FROM course_checkpoint_attempts WHERE profile_id=? AND release_id=? AND chapter_id=? ORDER BY created_at,rowid', (profile_id, release_id, chapter_id))]
        variants = chapter['variants']
        # Prefer unseen parallel forms, then rotate without repeating the last.
        variant = next((item for item in variants if item['id'] not in previous_variants), None)
        if variant is None:
            last_index = next((index for index, item in enumerate(variants) if item['id'] == previous_variants[-1]), -1)
            variant = variants[(last_index + 1) % len(variants)]
        attempt_id = identifier()
        frozen = {'chapter_id': chapter_id, 'chapter_number': chapter['number'], 'title': chapter['title'],
                  'title_ru': chapter['title_ru'], 'variant': variant, 'rubric': deepcopy(RUBRIC),
                  'release_id': release_id, 'band': release['band'], 'chapter_count': len(catalogue['chapters']),
                  'requirement_version': release['requirement_version'],
                  'preparation_policy': state['preparation_policy']}
        if chapter.get('checkpoint_blueprint'):
            blueprint = deepcopy(chapter['checkpoint_blueprint'])
            frozen['blueprint'] = blueprint
            frozen['rubric'].update(minimum_correct=blueprint['minimum_correct'],
                                    component_minima=blueprint['component_minima'])
        _execute(conn, 'INSERT INTO course_checkpoint_attempts(id,profile_id,chapter_id,chapter_number,variant_id,content_version,rubric_version,frozen_json,status,created_at,release_id,band) '
                     "VALUES (?,?,?,?,?,?,?,?,'active',?,?,?)", (attempt_id, profile_id, chapter_id, chapter['number'], variant['id'],
                      catalogue['version'], catalogue['rubric_version'], encoded(frozen), now, release_id, release['band']))
        result = checkpoint_read(conn, profile_id, attempt_id)
    _execute(conn, 'INSERT INTO course_checkpoint_requests VALUES (?,?,?,?,?)',
                 (profile_id, request_id, fingerprint, result['id'], encoded(result)))
    return result


def checkpoint_answer(conn, profile_id, attempt_id, answers, submission_id, now=None):
    key(submission_id, 'Submission ID')
    if not isinstance(answers, dict) or not all(isinstance(qid, str) and isinstance(choice, str) for qid, choice in answers.items()):
        raise LearningError('invalid_input', 'Send all checkpoint answers as question IDs and choice IDs.')
    fingerprint = payload_hash({'attempt_id': attempt_id, 'answers': answers})
    previous = _execute(conn, 'SELECT payload_hash,response_json FROM course_checkpoint_submissions WHERE profile_id=? AND submission_id=?',
                            (profile_id, submission_id)).fetchone()
    if previous:
        if previous['payload_hash'] != fingerprint:
            raise LearningError('idempotency_conflict', 'This submission ID was already used for different answers.', 409)
        return _reveal_receipt(json.loads(previous['response_json']))
    row = _attempt(conn, profile_id, attempt_id)
    if row['status'] != 'active':
        raise LearningError('checkpoint_completed', 'This checkpoint is already checked. Start the next attempt to practise again.', 409)
    frozen = json.loads(row['frozen_json'])
    questions, rubric = frozen['variant']['questions'], frozen['rubric']
    if set(answers) != {question['id'] for question in questions}:
        raise LearningError('invalid_input', 'Answer every checkpoint question before checking your work.')
    for question in questions:
        if answers[question['id']] not in {choice['id'] for choice in question['choices']}:
            raise LearningError('invalid_input', 'Choose one of the offered answers for each question.')
    if rubric['require_listened'] and row['listened_at'] is None and 'transcript' not in json.loads(row['support_json']):
        raise LearningError('listening_required', 'Listen to the message before checking your answers.', 409)
    feedback = [{'question_id': question['id'], 'correct': answers[question['id']] == question['answer'],
                 'answer': question['answer'], 'explanation': question['explanation'], 'explanation_ru': question['explanation_ru']}
                for question in questions]
    score = sum(item['correct'] for item in feedback)
    essential = all(answers[question['id']] == question['answer'] for question in questions if question['essential'])
    independent = not json.loads(row['support_json'])
    component_results = [{'kind': kind, 'score': sum(answers[q['id']] == q['answer'] for q in questions if q['kind'] == kind),
                          'total': sum(q['kind'] == kind for q in questions), 'required': minimum}
                         for kind, minimum in rubric.get('component_minima', {}).items()]
    for item in component_results:
        item['passed'] = item['score'] >= item['required']
    enough = score >= rubric['minimum_correct'] if 'minimum_correct' in rubric else score / len(questions) >= rubric['minimum_score']
    passed = (enough and all(item['passed'] for item in component_results) and (essential or not rubric['require_essential'])
              and (independent or not rubric['require_independent']))
    result = {'score': score, 'total': len(questions), 'passed': passed,
              'essential_passed': essential, 'feedback': feedback}
    if frozen.get('blueprint'):
        result['component_results'] = component_results
        missed_topics = {target.split('.')[1] for q in questions if answers[q['id']] != q['answer'] for target in q.get('target_ids', [])}
        result['next_practice'] = [link for topic in sorted(missed_topics) for link in _links(topic, row['band'])[:1]]
    now = timestamp() if now is None else now
    _execute(conn, 'UPDATE course_checkpoint_attempts SET status=?,answers_json=?,result_json=?,completed_at=? WHERE id=?',
                 ('passed' if passed else 'retry', encoded(answers), encoded(result), now, attempt_id))
    if frozen.get('blueprint'):
        from services.course_targets import record_checkpoint_targets
        record_checkpoint_targets(conn, profile_id, attempt_id, frozen, answers, not independent, now)
    if passed:
        _execute(conn, 'INSERT OR IGNORE INTO course_chapter_passes(profile_id,chapter_id,attempt_id,passed_at,release_id,requirement_version) VALUES (?,?,?,?,?,?)',
                 (profile_id, row['chapter_id'], attempt_id, now, row['release_id'], frozen.get('requirement_version', row['rubric_version'])))
        _grant_continuation(conn, profile_id, row['release_id'], now)
    response = checkpoint_read(conn, profile_id, attempt_id)
    _execute(conn, 'INSERT INTO course_checkpoint_submissions VALUES (?,?,?,?,?)',
                 (profile_id, submission_id, fingerprint, attempt_id, encoded(response)))
    return response


def _grant_continuation(conn, profile_id, release_id, now):
    """Award access from the completed attempt's edition, never current routing."""
    release = release_metadata(release_id)
    continuation = release.get('continuation_level')
    if not continuation:
        return
    required = {chapter['id'] for chapter in _catalogue(release_id)['chapters']}
    passed = {row['chapter_id'] for row in _execute(conn,
        'SELECT chapter_id FROM course_chapter_passes WHERE profile_id=? AND release_id=?', (profile_id, release_id))}
    if required and required <= passed:
        _execute(conn, 'INSERT OR IGNORE INTO course_continuation_entitlements(profile_id,target_level,source_release_id,source,earned_at) VALUES (?,?,?,?,?)',
                 (profile_id, continuation, release_id, 'course-completion', now))


def checkpoint_support(conn, profile_id, attempt_id, kind, question_id=None):
    row = _attempt(conn, profile_id, attempt_id)
    if kind not in ('hint', 'transcript'):
        raise LearningError('invalid_input', 'Choose hint or transcript support.')
    variant = json.loads(row['frozen_json'])['variant']
    if kind == 'hint':
        if not isinstance(question_id, str) or question_id not in {question['id'] for question in variant['questions']}:
            raise LearningError('invalid_input', 'Choose an existing question for the hint.')
        marker = 'hint:' + question_id
    else:
        if question_id is not None:
            raise LearningError('invalid_input', 'Transcript support does not take a question ID.')
        marker = 'transcript'
    if row['status'] == 'active':
        support = json.loads(row['support_json'])
        if marker not in support:
            _execute(conn, 'UPDATE course_checkpoint_attempts SET support_json=? WHERE id=?', (encoded(support + [marker]), attempt_id))
    return checkpoint_read(conn, profile_id, attempt_id)


def checkpoint_listened(conn, profile_id, attempt_id, now=None):
    row = _attempt(conn, profile_id, attempt_id)
    if row['status'] == 'active' and row['listened_at'] is None:
        _execute(conn, 'UPDATE course_checkpoint_attempts SET listened_at=? WHERE id=?', (timestamp() if now is None else now, attempt_id))
    return checkpoint_read(conn, profile_id, attempt_id)

def _previous_courses(conn, profile_id, current_release):
    rows = _execute(conn, 'SELECT id,release_id,status,frozen_json FROM course_checkpoint_attempts WHERE profile_id=? AND release_id!=? ORDER BY created_at DESC',
                    (profile_id, current_release)).fetchall()
    grouped = {}
    for row in rows:
        frozen = json.loads(row['frozen_json'])
        group = grouped.setdefault(row['release_id'], {'release_id': row['release_id'], 'title': 'Earlier journey',
                                    'title_ru': 'Предыдущее путешествие', 'attempts': []})
        group['attempts'].append({'id': row['id'], 'title': frozen['title'], 'title_ru': frozen['title_ru'], 'status': row['status']})
    return list(grouped.values())


def _release_upgrade(conn, profile_id, current_release, entitled):
    target = default_release_id()
    if (current_release == target or target == DEFAULT_RELEASE_ID
            or release_metadata(current_release)['band'] != release_metadata(target)['band']):
        return None
    pending = _execute(conn, "SELECT id,frozen_json FROM course_checkpoint_attempts WHERE profile_id=? AND release_id=? AND status='active' ORDER BY created_at", (profile_id, current_release)).fetchall()
    count = _execute(conn, 'SELECT COUNT(*) FROM course_chapter_passes WHERE profile_id=? AND release_id=?', (profile_id, current_release)).fetchone()[0]
    first = _catalogue(target)['chapters'][0]
    return {'release_id': target, 'title': 'The journey from home', 'title_ru': 'Путешествие из дома',
            'retained_access': sorted(entitled), 'retained_milestones': count,
            'starting_chapter': first['id'], 'starting_chapter_title': first['title'], 'starting_chapter_title_ru': first['title_ru'],
            'active_attempts': [{'id': row['id'], 'title': json.loads(row['frozen_json'])['title'],
                                'title_ru': json.loads(row['frozen_json'])['title_ru']} for row in pending]}


def switch_release(conn, profile_id, to_release, from_release, request_id, now=None):
    key(request_id, 'Request ID')
    if not isinstance(from_release, str):
        raise LearningError('invalid_input', 'Reopen your journey before switching.')
    fingerprint = payload_hash({'from_release_id': from_release, 'to_release_id': to_release})
    previous = _execute(conn, 'SELECT payload_hash FROM course_release_switches WHERE profile_id=? AND request_id=?', (profile_id, request_id)).fetchone()
    if previous:
        if previous['payload_hash'] != fingerprint:
            raise LearningError('idempotency_conflict', 'This switch was already used for a different journey.', 409)
        return course_snapshot(conn, profile_id)
    state = course_snapshot(conn, profile_id)
    offered = state.get('release_upgrade')
    if state['release_id'] != from_release or not offered or offered['release_id'] != to_release:
        raise LearningError('course_release_mismatch', 'Your journey has changed. Reload before switching.', 409)
    release = release_metadata(to_release)
    now = timestamp() if now is None else now
    _execute(conn, 'INSERT INTO course_enrolments(profile_id,band,release_id,started_at,migration_source) VALUES (?,?,?,?,?) '
                  'ON CONFLICT(profile_id,band) DO UPDATE SET release_id=excluded.release_id,started_at=excluded.started_at,migration_source=excluded.migration_source',
             (profile_id, release['band'], to_release, now, from_release))
    state = course_snapshot(conn, profile_id)
    _execute(conn, 'INSERT INTO course_release_switches VALUES (?,?,?,?,?,?,?)',
             (profile_id, request_id, fingerprint, from_release, to_release, now, encoded(state)))
    return state


def checkpoint_draft(conn, profile_id, attempt_id, answers, revision):
    row = _attempt(conn, profile_id, attempt_id)
    if row['status'] != 'active':
        raise LearningError('checkpoint_completed', 'This letter has already been checked.', 409)
    if not isinstance(answers, dict) or type(revision) is not int or revision < 0:
        raise LearningError('invalid_input', 'Send your saved answers and revision.')
    questions = {q['id']: q for q in json.loads(row['frozen_json'])['variant']['questions']}
    if any(qid not in questions or not isinstance(choice, str) or choice not in {c['id'] for c in questions[qid]['choices']} for qid, choice in answers.items()):
        raise LearningError('invalid_input', 'Choose an offered answer for this letter.')
    if json.loads(row['draft_json']) == answers:
        return checkpoint_read(conn, profile_id, attempt_id)
    if row['draft_revision'] != revision:
        raise LearningError('draft_conflict', 'A newer draft is saved. Reload the letter before changing it.', 409)
    _execute(conn, 'UPDATE course_checkpoint_attempts SET draft_json=?,draft_revision=draft_revision+1 WHERE id=?', (encoded(answers), attempt_id))
    return checkpoint_read(conn, profile_id, attempt_id)
