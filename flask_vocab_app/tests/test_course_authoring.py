"""Authored A1 content is complete and cannot bypass release validation."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from services.course_authoring import (
    CourseAuthoringError, DATA_DIR, load_draft_release, validate_course_release,
)
from services.curriculum_targets import curriculum_targets


class CourseAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((DATA_DIR / 'a1-journey-v2.json').read_text(encoding='utf-8'))
        cls.targets = curriculum_targets()

    def setUp(self):
        self.draft = deepcopy(self.source)
        self.home = self.draft['chapters'][0]
        self.variant = self.home['variants'][0]

    def validate(self, **kwargs):
        return validate_course_release(self.draft, target_data=self.targets, **kwargs)

    def rejects(self, message, **kwargs):
        with self.assertRaises(CourseAuthoringError) as caught:
            self.validate(**kwargs)
        self.assertIn(message, str(caught.exception))
        return caught.exception.errors

    def test_internal_draft_is_valid_and_copies_do_not_modify_catalogue(self):
        self.validate()
        first = load_draft_release()
        first['chapters'][0]['title'] = 'Changed in caller'
        self.assertNotEqual(load_draft_release()['chapters'][0]['title'], first['chapters'][0]['title'])
        self.assertEqual(first['status'], 'draft')
        self.assertFalse(first['playable'])
        self.assertFalse(first['default_enrolment'])

    def test_v1_remains_complete_with_its_original_ids(self):
        from services.course_progression import course_catalogue
        live = course_catalogue('a1-v1')
        self.assertEqual(live['version'], 1)
        self.assertEqual([c['id'] for c in live['chapters']],
                         ['a1-post-office', 'a1-home', 'a1-market', 'a1-delivery'])
        self.assertTrue(all(len(c['variants']) == 3 for c in live['chapters']))

    def test_draft_publication_reports_unfinished_release_state_and_audio(self):
        errors = self.rejects('draft publication is forbidden', publication=True)
        self.assertTrue(any('incomplete section' in error for error in errors))
        self.assertEqual(sum('missing audio blocks publication' in error for error in errors), 12)
        self.assertTrue(any('unresolved publication blockers' in error for error in errors))

    def test_claimed_published_status_cannot_skip_publication_gate(self):
        self.draft['status'] = 'published'
        self.rejects('incomplete section blocks publication')

    def test_draft_cannot_advertise_public_playability_or_default_enrolment(self):
        for field, value in [('visibility', 'public'), ('playable', True), ('default_enrolment', True)]:
            with self.subTest(field=field):
                self.draft = deepcopy(self.source)
                self.draft[field] = value
                self.rejects('draft must stay internal')

    def test_sections_are_ordered_and_cover_each_primary_topic_once(self):
        expected = [['greetings', 'family', 'home'], ['numbers', 'daily_activities'],
                    ['food', 'colors', 'clothing'], ['places', 'weather']]
        self.assertEqual([c['topic_ids'] for c in self.draft['chapters']], expected)
        self.draft['chapters'][1], self.draft['chapters'][0] = self.draft['chapters'][:2]
        self.rejects('four ordered sections')

    def test_primary_topic_mismatch_is_rejected(self):
        self.home['topic_ids'].append('places')
        self.rejects('primary topic allocation mismatch')

    def test_all_sections_are_authored_without_a_false_public_playability_claim(self):
        for chapter in self.draft['chapters']:
            self.assertEqual(chapter['content_status'], 'authored_draft')
            self.assertEqual(len(chapter['variants']), 3)
            self.assertEqual({p['topic_id'] for p in chapter['preparation']}, set(chapter['topic_ids']))
            self.assertFalse(chapter['playable'])
            self.assertTrue(chapter['pending_work'])
        self.draft['chapters'][1]['playable'] = True
        self.rejects('unfinished section must not advertise playability')

    def test_pending_section_cannot_contain_a_placeholder_assessment(self):
        self.draft['chapters'][1]['content_status'] = 'pending_content'
        self.rejects('pending content must not pretend to be authored')

    def test_every_section_has_equivalent_authored_decisions(self):
        self.assertEqual(sum(len(v['questions']) for c in self.draft['chapters'] for v in c['variants']), 120)
        for chapter in self.draft['chapters']:
            expected = chapter['checkpoint_blueprint']['counts']
            for variant in chapter['variants']:
                self.assertEqual(Counter(q['kind'] for q in variant['questions']), expected)
                self.assertEqual([q['target_ids'] for q in variant['questions']],
                                 [s['target_ids'] for s in chapter['checkpoint_blueprint']['slots']])

    def test_every_cumulative_variant_actually_scores_all_ten_topics(self):
        for variant in self.draft['chapters'][-1]['variants']:
            topics = {t for q in variant['questions'] for t in q['topic_ids']}
            self.assertEqual(len(topics), 10)
            self.assertEqual(len(variant['questions']), 16)
            self.assertEqual(variant['consequence']['result'], 'a1_course_complete')
            self.assertIsNone(variant['consequence']['next_section_id'])
            self.assertEqual(variant['consequence']['original_letter_state'], 'sealed')

    def test_home_has_three_equivalent_eight_question_letters(self):
        expected_targets = self.home['required_target_ids']
        for variant in self.home['variants']:
            with self.subTest(variant=variant['id']):
                self.assertEqual(Counter(q['kind'] for q in variant['questions']),
                                 {'reading': 5, 'listening': 2, 'response': 1})
                self.assertEqual([q['target_ids'][0] for q in variant['questions']], expected_targets)
                self.assertEqual(sum(q['essential'] for q in variant['questions']), 2)
                self.assertEqual(variant['recipient_id'], 'barsik')
                self.assertEqual(variant['original_letter_state'], 'sealed')
                self.assertNotEqual(variant['story_facts']['helper']['value_ru'], variant['sender_name_ru'])

    def test_home_teaches_the_full_required_subset_before_assessment(self):
        introduced = {t for p in self.home['preparation'] for t in p['introduces_target_ids']}
        self.assertLessEqual(set(self.home['required_target_ids']), introduced)
        self.home['preparation'][0]['introduces_target_ids'].remove('a1.greetings.exchange-names.read')
        self.rejects('required targets lack teaching before assessment')

    def test_every_target_has_authored_teaching_and_an_explicit_assessment_policy(self):
        for row in self.draft['target_coverage']:
            self.assertEqual(row['teaching']['status'], 'authored_draft')
            self.assertTrue(row['teaching']['preparation_id'])
            self.assertEqual(row['practice']['status'], 'authored_brief')

    def test_guided_checks_only_credit_their_narrow_scored_targets(self):
        for chapter in self.draft['chapters']:
            for prep in chapter['preparation']:
                check = prep['guided_check']
                self.assertLessEqual(len(check['target_ids']), 2)
                self.assertLess(set(check['target_ids']), set(prep['introduces_target_ids']))
                self.assertFalse(check['pass_awarded'])
        self.home['preparation'][0]['guided_check']['target_ids'] = ['a1.greetings.polite-greeting.speak']
        self.rejects('written guided check cannot establish production or listening')

    def test_source_curriculum_coverage_is_explicit_for_every_target(self):
        self.assertEqual({r['target_id'] for r in self.draft['target_coverage']},
                         {t['id'] for t in self.targets['targets']})
        self.draft['target_coverage'].pop()
        self.rejects('every registered target needs one explicit coverage policy')

    def test_readiness_subset_cannot_be_silently_shrunk(self):
        self.home['required_target_ids'].pop()
        self.rejects('required_target_ids differs from target registry')

    def test_selected_reply_cannot_claim_independent_production(self):
        self.variant['questions'][-1]['target_ids'] = ['a1.greetings.polite-greeting.write']
        self.rejects('selected choice cannot claim independent writing or speaking')

    def test_unknown_target_is_rejected(self):
        self.variant['questions'][0]['target_ids'] = ['a1.greetings.invented.read']
        self.rejects('unknown target')

    def test_question_target_must_match_its_topic(self):
        self.variant['questions'][0]['topic_ids'] = ['home']
        self.rejects('target/topic mismatch')

    def test_question_must_follow_the_equivalent_blueprint(self):
        self.variant['questions'][0]['kind'] = 'listening'
        self.rejects('question kind or targets differ from equivalent blueprint')

    def test_duplicate_question_id_or_missing_slot_is_rejected(self):
        self.variant['questions'][1]['id'] = self.variant['questions'][0]['id']
        self.rejects('question order or blueprint slots mismatch')

    def test_correct_answer_must_match_the_authoritative_accepted_choice(self):
        question = self.variant['questions'][0]
        question['answer'] = next(c['id'] for c in question['choices'] if c['id'] != question['answer'])
        self.rejects('answer must reference the declared accepted choice')

    def test_distractor_cannot_duplicate_correct_text_with_punctuation_changes(self):
        question = self.variant['questions'][0]
        wrong = next(c for c in question['choices'] if c['id'] != question['answer'])
        wrong['text'] = question['accepted_answer_text'].upper().replace('.', '!')
        self.rejects('duplicate distractor text')

    def test_english_choices_are_rejected(self):
        self.variant['questions'][0]['choices'][0]['text'] = 'Misha'
        self.rejects('all choices must be nonempty Russian')

    def test_unreviewed_distractor_is_rejected(self):
        question = self.variant['questions'][0]
        wrong = next(c for c in question['choices'] if c['role'] == 'distractor')
        del wrong['error_type']
        self.rejects('distractor needs an explicit plausible error')

    def test_missing_bilingual_prompt_hint_or_explanation_is_rejected(self):
        for field in ['prompt_ru', 'hint_ru', 'explanation_ru']:
            with self.subTest(field=field):
                self.draft = deepcopy(self.source)
                del self.draft['chapters'][0]['variants'][0]['questions'][0][field]
                self.rejects('requires English and Russian text')

    def test_invented_source_evidence_is_rejected(self):
        self.variant['story_facts']['helper']['source_quote'] = 'Меня зовут Алексей.'
        self.rejects('lacks a literal source anchor')

    def test_listening_answers_require_new_spoken_facts(self):
        for variant in self.home['variants']:
            for question in variant['questions']:
                if question['kind'] == 'listening':
                    for fid in question['evidence']:
                        fact = variant['story_facts'][fid]
                        self.assertEqual(fact['source'], 'listening')
                        self.assertNotIn(fact['source_quote'], variant['letter'])
        self.variant['questions'][5]['evidence'] = ['written_location']
        self.rejects('listening answer must require new spoken information')

    def test_glossary_cannot_disclose_an_assessed_fact(self):
        self.variant['glossary'].append({'ru': 'На диване в комнате', 'en': 'On the sofa in the room', 'role': 'incidental'})
        self.rejects('glossary must not reveal an assessed fact')

    def test_variant_meaningful_facts_must_differ(self):
        duplicate = deepcopy(self.variant)
        duplicate['id'] += '-renamed'
        self.home['variants'][1] = duplicate
        self.rejects('variants must vary meaningful facts, not only names')

    def test_variants_must_change_at_least_three_substantive_facts(self):
        chapter = self.draft['chapters'][1]
        a, b = chapter['variants'][:2]
        for fid in chapter['checkpoint_blueprint']['variation_fact_ids'][:-2]:
            b['story_facts'][fid] = deepcopy(a['story_facts'][fid])
        self.rejects('variant pairs must vary at least three meaningful facts')

    def test_essential_details_need_justification_and_exact_designation(self):
        self.home['checkpoint_blueprint']['essential_justifications'].pop('l1')
        self.rejects('essential details need story justifications')

    def test_original_letter_cannot_be_delivered_or_opened(self):
        self.variant['original_letter_state'] = 'opened'
        self.rejects('original letter must remain sealed')

    def test_support_rules_cannot_silently_award_independent_listening(self):
        self.variant['support_policy']['transcript'] = 'independent'
        self.rejects('support policy mismatch')

    def test_audio_is_honestly_missing_and_transcript_is_versioned(self):
        for variant in [v for c in self.draft['chapters'] for v in c['variants']]:
            audio = variant['listening']
            self.assertEqual(audio['status'], 'missing')
            self.assertIsNone(audio['audio_url'])
            self.assertIsNone(audio['audio_sha256'])
            self.assertIsNone(audio['duration_seconds'])
            self.assertEqual(audio['text_sha256'], hashlib.sha256(audio['transcript'].encode()).hexdigest())
        self.variant['listening']['audio_url'] = '/static/audio/course/nonexistent.mp3'
        self.rejects('missing audio must not have fabricated asset metadata')

    def test_every_listening_question_requires_new_spoken_information(self):
        for chapter in self.draft['chapters']:
            for variant in chapter['variants']:
                for question in variant['questions']:
                    if question['kind'] == 'listening':
                        for fid in question['evidence']:
                            fact = variant['story_facts'][fid]
                            self.assertEqual(fact['source'], 'listening')
                            self.assertNotIn(fact['source_quote'], variant['letter'])

    def test_request_targets_require_a_full_request_rather_than_a_food_label(self):
        request_targets = {'a1.food.make-request.read', 'a1.food.make-request.listen'}
        for chapter in self.draft['chapters']:
            for variant in chapter['variants']:
                for question in variant['questions']:
                    if request_targets.intersection(question['target_ids']):
                        self.assertTrue(question['accepted_answer_text'].startswith('Можно '))
                        self.assertTrue(question['accepted_answer_text'].endswith(', пожалуйста?'))

    def test_final_garment_question_needs_both_spoken_colour_and_size(self):
        for variant in self.draft['chapters'][-1]['variants']:
            question = next(q for q in variant['questions'] if q['id'] == 'l4')
            answer = question['accepted_answer_text'].rstrip('.').split()
            self.assertIn(answer[0], ('Большая', 'Маленькая'))
            distractors = [c['text'].rstrip('.').split() for c in question['choices'] if c['id'] != question['answer']]
            self.assertTrue(any(wrong[0] != answer[0] and wrong[1:] == answer[1:] for wrong in distractors))
            self.assertTrue(any(wrong[0] == answer[0] and wrong[1] != answer[1] and wrong[2:] == answer[2:]
                                for wrong in distractors))
            self.assertIn('update-v2', variant['listening']['id'])

    def test_valid_russian_weather_synonym_is_not_marked_wrong(self):
        for variant in self.draft['chapters'][-1]['variants']:
            question = next(q for q in variant['questions'] if q['id'] == 'c3')
            distractors = [c['text'] for c in question['choices'] if c['id'] != question['answer']]
            self.assertNotIn('Сегодня жара.', distractors)
            self.assertNotIn('Сегодня холод.', distractors)

    def test_direction_prompt_does_not_supply_the_tested_russian_case_form(self):
        for variant in self.draft['chapters'][-1]['variants']:
            question = next(q for q in variant['questions'] if q['id'] == 'c1')
            for answer_phrase in ('в библиотеку', 'в школу', 'на почту'):
                self.assertNotIn(answer_phrase, question['prompt_ru'])

    def test_writing_continuations_keep_both_sources_and_remain_optional(self):
        for chapter in self.draft['chapters']:
            for variant in chapter['variants']:
                task = variant['writing_task']
                self.assertTrue(task['optional'])
                self.assertFalse(task['affects_milestone_pass'])
                for field in ('task', 'task_en'):
                    self.assertIn(variant['letter'], task[field])
                    self.assertIn(variant['listening']['transcript'], task[field])
        self.variant['writing_task']['task_en'] = 'Reply to the letter.'
        self.rejects('writing continuation must preserve the letter and spoken update context')

    def test_contextual_cards_have_real_inflected_sources_and_resolvable_morphology(self):
        from services.card_metadata import GRAMMAR
        from utils.story_processing import get_morph
        count = 0
        for chapter in self.draft['chapters']:
            for variant in chapter['variants']:
                for candidate in variant['flashcard_candidates']:
                    count += 1
                    self.assertIn(candidate['sentence'], variant['letter'])
                    self.assertTrue(candidate['translation'])
                    self.assertTrue(candidate['target_meaning'])
                    parses = [p for p in get_morph().parse(candidate['form']) if p.is_known
                              and p.normal_form == candidate['lemma'] and p.tag.POS == candidate['pos']
                              and all(getattr(p.tag, k, None) == value for k, value in candidate['grammar'].items())]
                    signatures = {tuple(getattr(p.tag, k, None) for k in GRAMMAR) for p in parses}
                    self.assertEqual(len(signatures), 1, candidate)
        self.assertEqual(count, 22)
        self.variant['flashcard_candidates'][0]['sentence'] = 'Неподтверждённый пример.'
        self.rejects('flashcard sentence must come from the received letter')

    def test_review_records_do_not_claim_external_review_or_a_learner_pilot(self):
        self.assertEqual(self.draft['editorial_review']['status'], 'author_reviewed')
        self.assertEqual(self.draft['editorial_review']['learner_pilot_status'], 'not_run')
        self.assertEqual(self.draft['editorial_review']['independent_review'], 'pending')
        self.draft['editorial_review']['unresolved_editorial_items'] = ['An unresolved semantic error.']
        self.rejects('unresolved semantic review blocks publication', publication=True)

    def test_changed_transcript_requires_new_metadata(self):
        self.variant['listening']['transcript'] += ' До встречи!'
        self.rejects('audio transcript hash mismatch')

    def test_claiming_audio_ready_still_requires_a_real_bundled_file(self):
        audio = self.variant['listening']
        audio['status'] = 'ready'
        audio['audio_url'] = f'/static/audio/course/a1-journey-v2/{audio["id"]}.mp3'
        audio['audio_sha256'] = '0' * 64
        audio['duration_seconds'] = 12
        with tempfile.TemporaryDirectory() as directory:
            self.rejects('published audio file is missing', static_root=Path(directory))

    def test_cumulative_blueprint_has_sixteen_decisions_and_all_ten_topics(self):
        final = self.draft['chapters'][-1]['checkpoint_blueprint']
        self.assertEqual(final['counts'], {'reading': 6, 'listening': 4, 'language': 4, 'response': 2})
        self.assertEqual(final['minimum_correct'], 13)
        self.assertEqual(final['component_minima'], {'reading': 4, 'listening': 3, 'language': 2, 'response': 1})
        topics = {t['id']: t['topic_id'] for t in self.targets['targets']}
        sampled = {topics[tid] for slot in final['slots'] for tid in slot['target_ids']}
        self.assertEqual(len(sampled), 10)
        self.assertIn('family', sampled)
        self.assertIn('home', sampled)

    def test_cumulative_blueprint_cannot_omit_home_even_when_topic_list_mentions_it(self):
        slot = self.draft['chapters'][-1]['checkpoint_blueprint']['slots'][2]
        slot['target_ids'] = ['a1.greetings.exchange-names.read']
        self.rejects('cumulative blueprint must score all ten A1 topics')

    def test_final_component_thresholds_are_immutable_for_this_blueprint(self):
        self.draft['chapters'][-1]['checkpoint_blueprint']['component_minima']['listening'] = 0
        self.rejects('component minima mismatch')

    def test_unscored_mentions_cannot_be_turned_into_checkpoint_coverage(self):
        row = next(r for r in self.draft['target_coverage'] if r['target_id'] == 'a1.home.singular-plural.select')
        row['evidence_policy'] = 'sampled_by_scored_checkpoint_decision'
        self.rejects('target evidence policy overclaims assessment')

    def test_unknown_draft_does_not_fall_back_to_a_partial_release(self):
        with self.assertRaisesRegex(ValueError, 'Unknown internal draft'):
            load_draft_release('../course_chapters')

    def test_malformed_nested_shapes_produce_authoring_errors(self):
        mutations = [
            lambda d: d['chapters'][0].update(id=[]),
            lambda d: d['chapters'][0]['checkpoint_blueprint'].update(essential_slot_ids=[{}, {}]),
            lambda d: d['chapters'][0]['variants'][0].update(letter=42),
            lambda d: d['chapters'][0]['variants'][0]['questions'][0].update(id=[]),
            lambda d: d['chapters'][0]['variants'][0]['story_facts']['object'].update(value_ru=[]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                self.draft = deepcopy(self.source)
                mutate(self.draft)
                with self.assertRaises(CourseAuthoringError):
                    self.validate()

    def test_editorial_limitations_remain_explicit_before_publication(self):
        review = self.draft['editorial_review']
        self.assertEqual(review['independent_review'], 'pending')
        self.assertEqual(review['semantic_review_status'], 'author_reviewed')
        self.assertIn('not a learner pilot', review['limitations'])
        self.assertEqual(review['unresolved_editorial_items'], [])
        for variant in self.home['variants']:
            self.assertEqual(variant['language_manifest']['independent_editorial_review'], 'pending')
            self.assertEqual(variant['listening']['status'], 'missing')
        self.assertFalse(self.draft['playable'])


if __name__ == '__main__':
    unittest.main()
