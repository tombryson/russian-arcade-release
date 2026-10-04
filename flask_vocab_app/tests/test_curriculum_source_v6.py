"""Cross-contract tests for bounded references and truthful Russian evidence."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from services import curriculum_situation_content as content
from tests.test_curriculum_situation_expansion import fixture_request, fixture_wire


def request_for_family(identity, family, mode='reading'):
    for n in range(40):
        request = fixture_request(identity, f'source-v6-{n}', mode)
        if request['language_plan']['family_id'] == family:
            return request
    raise AssertionError('The requested authored family must be reachable.')


def checked(request, wire):
    return content.validate_output(request, content.resolve_source_references(request, wire))


def reading_reference_fixture():
    request = request_for_family('present-actions-v1', 'present-reading-turns')
    return request, fixture_wire(request)


def ambiguous_reference_fixture(other_role=None):
    # Same-gender candidates make the ambiguity real in Russian; the test must
    # not demand rejection merely because an unrelated other-gender name exists.
    for n in range(80):
        request = fixture_request('present-actions-v1', f'ambiguous-v6-{n}', 'reading')
        plan = request['language_plan']['meaning_plan']
        if request['language_plan']['family_id'] != 'present-reading-turns':
            continue
        actor = next(p for p in plan['participants'] if p['name_ru'] == plan['facts'][0]['subject_name'])
        candidates = [plan[other_role]] if other_role else plan['participants']
        other = next((p for p in candidates if p['name_ru'] != actor['name_ru'] and p['gender'] == actor['gender']), None)
        if other:
            return request, fixture_wire(request), other['name_ru']
    raise AssertionError('Same-gender ambiguity fixture must be reachable.')


def pronoun_wire(request, wire, *, other_name=None, explicit_span=False, named_action=False):
    """Replace the first source with an introduction and the actual action.

The exercise's remaining source IDs move together. This is intentionally a
source fixture rather than a fake normalized response bypassing the adapter.
"""
    updated = deepcopy(wire)
    fact = request['language_plan']['meaning_plan']['facts'][0]
    person = next(p for p in request['language_plan']['meaning_plan']['participants'] if p['name_ru'] == fact['subject_name'])
    pronoun = 'Она' if person['gender'] == 'feminine' else 'Он'
    intro = f"Это {person['name_ru']}" + (f' и {other_name}' if other_name else '') + '.'
    action = f"{person['name_ru'] if named_action else pronoun} сначала читает."
    updated['sentences'] = [intro, action, *updated['sentences'][1:]]
    for key, question in updated['questions'].items():
        question['sentence_ids'] = (['s1', 's2'] if explicit_span else ['s2']) if key == 'f1' else [
            's' + str(int(ref[1:]) + 1) for ref in question['sentence_ids']]
    return updated


class SourceV6RegressionTests(unittest.TestCase):
    def test_unique_named_antecedent_expands_exact_evidence_without_changing_prose(self):
        for mode in ('reading', 'listening'):
            request = request_for_family('present-actions-v1', 'present-reading-turns', mode)
            wire = pronoun_wire(request, fixture_wire(request))
            original = deepcopy(wire)
            document = checked(request, wire)
            response = document['response']
            self.assertEqual(response['questions'][0]['evidence'], ' '.join(wire['sentences'][:2]))
            self.assertEqual(response['text'], ' '.join(wire['sentences']))
            self.assertEqual(wire, original)
            self.assertIn(wire['sentences'][0], response['questions'][0]['explanation'])

    def test_source_extension_does_not_reach_back_beyond_three_sentences(self):
        request, wire = reading_reference_fixture()
        fact = request['language_plan']['meaning_plan']['facts'][0]
        person = next(p for p in request['language_plan']['meaning_plan']['participants'] if p['name_ru'] == fact['subject_name'])
        pronoun = 'Она' if person['gender'] == 'feminine' else 'Он'
        wire['sentences'] = [f"Это {person['name_ru']}.", 'Да.', 'Вот.', f'{pronoun} сначала читает.', *wire['sentences'][1:]]
        for key, question in wire['questions'].items():
            question['sentence_ids'] = ['s4'] if key == 'f1' else ['s' + str(int(ref[1:]) + 3) for ref in question['sentence_ids']]
        with self.assertRaisesRegex(ValueError, 'named participant|exact source evidence'):
            checked(request, wire)

    def test_two_assessed_people_do_not_get_guessed_as_a_pronoun_antecedent(self):
        request, wire, other = ambiguous_reference_fixture()
        wire = pronoun_wire(request, wire, other_name=other)
        with self.assertRaisesRegex(ValueError, 'named participant|ambiguous|antecedent|exact source evidence'):
            checked(request, wire)

    def test_writer_or_addressee_is_not_ignored_when_resolving_a_pronoun(self):
        for role in ('writer', 'addressee'):
            with self.subTest(role=role):
                request, wire, other = ambiguous_reference_fixture(role)
                wire = pronoun_wire(request, wire, other_name=other)
                with self.assertRaisesRegex(ValueError, 'named participant|ambiguous|antecedent|exact source evidence'):
                    checked(request, wire)

    def test_explicit_ambiguous_two_sentence_citation_is_not_a_bypass(self):
        request, wire, other = ambiguous_reference_fixture()
        wire = pronoun_wire(request, wire, other_name=other, explicit_span=True)
        with self.assertRaisesRegex(ValueError, 'named participant|ambiguous|antecedent|exact source evidence'):
            checked(request, wire)

    def test_two_people_in_a_span_are_valid_when_action_explicitly_names_its_actor(self):
        request, wire = reading_reference_fixture()
        target = request['language_plan']['meaning_plan']['facts'][0]['subject_name']
        other = next(p['name_ru'] for p in request['language_plan']['meaning_plan']['participants'] if p['name_ru'] != target)
        wire = pronoun_wire(request, wire, other_name=other, explicit_span=True, named_action=True)
        document = checked(request, wire)
        self.assertIn(target, document['response']['questions'][0]['evidence'])

    def test_greeting_vocative_is_not_a_competing_third_person_antecedent(self):
        request, wire, other = ambiguous_reference_fixture('addressee')
        wire = pronoun_wire(request, wire)
        wire['sentences'][0] = f"Привет, {other}! " + wire['sentences'][0]
        document = checked(request, wire)
        self.assertEqual(document['response']['questions'][0]['evidence'], ' '.join(wire['sentences'][:2]))

    def test_gender_can_distinguish_two_named_people(self):
        request, wire = reading_reference_fixture()
        meaning = request['language_plan']['meaning_plan']
        actor = next(p for p in meaning['participants'] if p['name_ru'] == meaning['facts'][0]['subject_name'])
        other = next(p for p in [*meaning['participants'], meaning['writer'], meaning['addressee']]
                     if p['gender'] != actor['gender'])
        wire = pronoun_wire(request, wire, other_name=other['name_ru'])
        document = checked(request, wire)
        self.assertEqual(document['response']['questions'][0]['evidence'], ' '.join(wire['sentences'][:2]))

    def test_bound_indirect_object_does_not_require_a_single_person_in_the_span(self):
        request = request_for_family('personal-reference-v1', 'reference-giving-and-calling')
        wire = fixture_wire(request)
        self.assertIn('даёт ему', wire['sentences'][0])
        document = checked(request, wire)
        self.assertEqual(document['response']['questions'][0]['evidence'], wire['sentences'][0])

    def test_another_persons_negative_predicate_does_not_negate_the_positive_fact(self):
        request, wire = reading_reference_fixture()
        meaning = request['language_plan']['meaning_plan']
        other = next(p['name_ru'] for p in meaning['participants'] if p['name_ru'] != meaning['facts'][0]['subject_name'])
        wire['sentences'][0] += f" {other} не читает."
        document = checked(request, wire)
        self.assertIn(f"{other} не читает.", document['response']['questions'][0]['evidence'])

    def test_unannotated_unfamiliar_content_fails_and_valid_annotation_reaches_help(self):
        request, wire = reading_reference_fixture()
        self.assertNotIn('дельфин', request['known_lemmas'])
        wire['sentences'].append('Там дельфин.')
        with self.assertRaisesRegex(ValueError, 'Unfamiliar.*дельфин'):
            checked(request, wire)
        wire['new_vocabulary'] = [{'lemma': 'дельфин', 'pos': 'NOUN',
                                   'sentence_id': 's' + str(len(wire['sentences'])), 'meaning_en': 'dolphin'}]
        document = checked(request, wire)
        self.assertEqual(document['response']['new_vocabulary'][0]['form'], 'дельфин')
        pack = content.to_pack(document, content_id=content.PREFIX + 'present-actions-v1:word-help')
        for item in pack['items']:
            self.assertIn({'kind': 'word', 'text': 'дельфин', 'meaning_en': 'dolphin', 'sentence': 'Там дельфин.'}, item['passage_support'])
        self.assertNotIn('дельфин', request['known_lemmas'])

    def test_foundation_greeting_and_thanks_become_real_learner_support(self):
        request, wire = reading_reference_fixture()
        wire['sentences'].extend(['Привет!', 'Спасибо!'])
        document = checked(request, wire)
        pack = content.to_pack(document, content_id=content.PREFIX + 'present-actions-v1:foundation')
        help_entries = pack['items'][0]['passage_support']
        self.assertIn({'kind': 'phrase', 'text': 'Привет', 'meaning_en': 'Hi'}, help_entries)
        self.assertIn({'kind': 'phrase', 'text': 'Спасибо', 'meaning_en': 'Thank you'}, help_entries)
        for entry in help_entries:
            self.assertIn(entry['text'], document['response']['text'])

    def test_past_predicate_cannot_claim_evidence_for_current_reading(self):
        request, wire = reading_reference_fixture()
        first = request['language_plan']['meaning_plan']['facts'][0]
        actor = next(p for p in request['language_plan']['meaning_plan']['participants'] if p['name_ru'] == first['subject_name'])
        past = 'читала' if actor['gender'] == 'feminine' else 'читал'
        wire['sentences'][0] = wire['sentences'][0].replace('читает', past)
        with self.assertRaisesRegex(ValueError, 'predicate|grammatical form'):
            checked(request, wire)

    def test_negated_reading_cannot_answer_who_is_reading(self):
        request, wire = reading_reference_fixture()
        wire['sentences'][0] = wire['sentences'][0].replace('читает', 'не читает')
        with self.assertRaisesRegex(ValueError, 'negative|negat|predicate|meaning'):
            checked(request, wire)

    def test_negative_call_cannot_be_changed_to_a_positive_call(self):
        request = request_for_family('connected-messages-v1', 'messages-call-after-activity')
        wire = fixture_wire(request)
        index = next(i for i, sentence in enumerate(wire['sentences']) if 'не звонит' in sentence)
        wire['sentences'][index] = wire['sentences'][index].replace('не звонит', 'звонит')
        with self.assertRaisesRegex(ValueError, 'negative|negat|predicate|meaning'):
            checked(request, wire)

    def test_absence_cannot_be_replaced_by_positive_existence(self):
        request = request_for_family('possession-absence-v1', 'possession-borrow-missing-item')
        wire = fixture_wire(request)
        index = next(i for i, text in enumerate(wire['sentences']) if ' нет ' in text)
        wire['sentences'][index] = wire['sentences'][index].replace(' нет ', ' есть ')
        with self.assertRaisesRegex(ValueError, 'absence|negative|predicate|grammatical form'):
            checked(request, wire)

    def test_frozen_v5_contract_is_not_reinterpreted_under_new_support_or_references(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/curriculum_source_v5.json').read_text())
        original = deepcopy(fixture)
        provider = MagicMock()
        provider.flashcard_model = 'existing-model'
        provider.client.with_options.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(refusal=None,
                          content=json.dumps(fixture['provider_response'])))])
        with patch.object(content, '_antecedent_start', side_effect=AssertionError('New reference rules reached an old snapshot')):
            with patch('services.curriculum_passage_language.validate_language_support',
                       side_effect=AssertionError('New vocabulary rules reached an old snapshot')):
                document = content.generate(fixture['request'], provider)
        self.assertEqual(document, fixture['document'])
        self.assertEqual(content.prompt_for(fixture['request']), fixture['prompt'])
        self.assertEqual(content.provider_schema(fixture['request']), fixture['schema'])
        self.assertEqual(fixture, original)
        self.assertTrue(all('passage_support' not in item for item in content.to_pack(document,
            content_id=content.PREFIX + 'location-destination-v1:frozen-v5')['items']))

    def test_descriptions_allow_predicative_order_without_changing_the_owner(self):
        request = request_for_family('noun-adjective-agreement-v1', 'agreement-find-clothes')
        wire = fixture_wire(request)
        for fact in request['language_plan']['meaning_plan']['facts']:
            adjective, noun = fact['value_ru'].split()
            wire['sentences'] = [line.replace(fact['value_ru'], noun + ' ' + adjective) for line in wire['sentences']]
        document = checked(request, wire)
        self.assertEqual(document['response']['text'], ' '.join(wire['sentences']))
        wrong = deepcopy(wire)
        people = request['language_plan']['meaning_plan']['participants']
        owner = request['language_plan']['meaning_plan']['facts'][0]['subject_name']
        first = next(p for p in people if p['name_ru'] == owner)
        other = next(p for p in people if p['name_ru'] != owner)
        wrong['sentences'] = [line.replace(first['genitive_ru'], other['genitive_ru']) for line in wrong['sentences']]
        with self.assertRaisesRegex(ValueError, 'realize|participant|evidence'):
            checked(request, wrong)

    def test_parallel_description_can_omit_one_uniquely_recoverable_noun(self):
        request = request_for_family('noun-adjective-agreement-v1', 'agreement-separate-sets')
        wire = fixture_wire(request)
        first, second, third = request['language_plan']['meaning_plan']['facts']
        _, noun = second['value_ru'].split()
        wire['sentences'] = [first['checked_source_frame_ru'].rstrip('.') + ', а ' +
                            second['checked_source_frame_ru'].replace(noun, '').replace('У ', 'у ').replace(' .', '.'),
                            third['checked_source_frame_ru']]
        wire['questions'] = {'f1': {'sentence_ids': ['s1']}, 'f2': {'sentence_ids': ['s1']}, 'f3': {'sentence_ids': ['s2']}}
        checked(request, wire)
        from services.curriculum_plan_validation import description_realized
        ambiguous = wire['sentences'][0].replace(', а', ' и машина, а')
        self.assertFalse(description_realized(request, 'f2', ambiguous))
        different_noun = wire['sentences'][0].rstrip('.') + ' машина.'
        self.assertFalse(description_realized(request, 'f2', different_noun))
        wrong_form = wire['sentences'][0].replace(second['value_ru'].split()[0], 'красной')
        self.assertFalse(description_realized(request, 'f2', wrong_form))

    def test_meeting_venue_cannot_dangle_after_the_reason_predicate(self):
        request = request_for_family('connected-messages-v1', 'messages-meeting-change')
        phrases = {p['ru']: p['en'] for p in request['language_plan']['supported_phrases']}
        self.assertEqual(phrases['предлагает встретиться'], 'suggests meeting')
        self.assertEqual(phrases['предлагает встретиться позже'], 'suggests meeting later')
        wire = fixture_wire(request)
        reason, time, venue = request['language_plan']['meaning_plan']['facts']
        actor = reason['subject_name']
        sentence = f"{actor} предлагает встретиться позже, {time['value_ru']}, {reason['value_ru']}, {venue['value_ru']}."
        wire['sentences'] = [sentence]
        wire['questions'] = {fact['id']: {'sentence_ids': ['s1']} for fact in (reason, time, venue)}
        with self.assertRaisesRegex(ValueError, 'venue|meeting'):
            checked(request, wire)
        wire['sentences'] = [f"{actor} предлагает встретиться {venue['value_ru']} {time['value_ru']}, {reason['value_ru']}."]
        checked(request, wire)

    def test_phone_call_does_not_invent_an_in_person_encounter(self):
        request = request_for_family('personal-reference-v1', 'reference-giving-and-calling')
        base = fixture_wire(request)
        for extra in ('Она видит друга.', 'Она здесь.'):
            wire = deepcopy(base)
            wire['sentences'].append(extra)
            with self.assertRaisesRegex(ValueError, 'encounter|co-location'):
                checked(request, wire)

    def test_possessive_reference_needs_a_clause_not_dangling_owner_names(self):
        request = request_for_family('personal-reference-v1', 'reference-shared-belongings')
        wire = fixture_wire(request)
        shared = request['language_plan']['meaning_plan']['facts'][2]
        people = request['language_plan']['meaning_plan']['participants']
        male = next(p for p in people if p['name_ru'] == shared['subject_name'])
        female = next(p for p in people if p['gender'] == 'feminine')
        wire['sentences'][2] = f"А это {shared['value_ru']}: {male['name_ru']} и {female['name_ru']}."
        with self.assertRaisesRegex(ValueError, 'owners|dangling|grammatical clause'):
            checked(request, wire)

    def test_current_calendar_visits_use_being_somewhere_without_rewriting_old_request(self):
        request = request_for_family('calendar-and-duration-v1', 'calendar-completed-stay', 'listening')
        facts = request['language_plan']['meaning_plan']['facts']
        questions = ' '.join(fact['question_frame_ru'] for fact in facts)
        self.assertRegex(questions, r'\bбыл[а]?\b')
        self.assertNotRegex(questions, r'\bжил[а]?\b')
        fixture = json.loads((Path(__file__).parent / 'fixtures/curriculum_source_v5.json').read_text())
        self.assertEqual(fixture['request']['generation_revision'], 'source-v5')
        self.assertEqual(content.prompt_for(fixture['request']), fixture['prompt'])


if __name__ == '__main__':
    unittest.main()
