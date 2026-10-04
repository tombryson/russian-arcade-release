"""All unit plans survive the real source adapter, not only a plan shape check."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from services import curriculum_situation_content as content
from services.curriculum_passage_language import unfamiliar_content
from services.curriculum_units import DATA_DIR, UNIT_IDS


def fixture_request(unit_id, seed, mode, recent=()):
    unit = json.loads((DATA_DIR / (unit_id + '.json')).read_text())
    request = content.build_request(unit, seed, mode=mode, recent=recent)
    wire = fixture_wire(request)
    # Synthetic familiar lexemes make these structural-adapter tests independent
    # of unfamiliar-word coverage, which is checked in its own regression suite.
    response_text = ' '.join(wire['sentences'])
    missing = unfamiliar_content(request, {'text': response_text, 'new_vocabulary': []})
    familiar = [{'lemma': word['possible_lemmas'][0]} for word in missing if word['possible_lemmas']]
    return content.build_request(unit, seed, mode=mode, recent=recent, vocabulary=familiar)


def fixture_wire(request):
    facts = request['language_plan']['meaning_plan']['facts']
    exact = request['language_plan'].get('construction_contract') == 'exact-frames-v1'
    if not exact:
        from tests.test_curriculum_situation_content import meaning_provider_response
        wire = meaning_provider_response(request)
        # This helper's traditional fixtures deliberately test the old semantic
        # adapter. New thought disclosure needs its actual explicit frame.
        if request['language_plan']['family_id'] == 'topics-thought-and-speech':
            fact = next(f for f in facts if f['role'] == 'topic_thing')
            ref = int(wire['questions'][fact['id']]['sentence_ids'][0][1:]) - 1
            wire['sentences'][ref] = f"{fact['subject_name']} говорит: «Я думаю {fact['value_ru']}»."
        return wire
    sentences = list(dict.fromkeys(fact['checked_source_frame_ru'] for fact in facts))
    return {'title': 'Сообщение', 'title_en': 'A message',
            'sentences': sentences,
            'questions': {fact['id']: {'sentence_ids': [f's{sentences.index(fact["checked_source_frame_ru"]) + 1}']} for fact in facts},
            'new_vocabulary': []}


class SituationExpansionTests(unittest.TestCase):
    def test_every_unit_has_two_families_and_real_adapter_coverage_in_both_modes(self):
        for identity in UNIT_IDS:
            for mode in ('reading', 'listening'):
                recent = []
                seen = set()
                for index in range(2):
                    with self.subTest(unit=identity, mode=mode, index=index):
                        request = fixture_request(identity, 'extension-contract', mode, recent)
                        wire = fixture_wire(request)
                        resolved = content.resolve_source_references(request, wire)
                        document = content.validate_output(request, resolved)
                        family = request['language_plan']['family_id']
                        self.assertNotIn(family, seen)
                        seen.add(family)
                        self.assertEqual(len(document['response']['questions']), 3)
                        self.assertEqual(request['generation_revision'], 'source-v6')
                        self.assertEqual({row['requirement_id'] for row in resolved['grammar_coverage']},
                                         {row['id'] for row in request['language_targets']})
                        recent.insert(0, {'request': document['request']})  # exercise semantic history, not copied fixture prose

    def test_new_question_and_translation_are_bound_to_the_authored_relation(self):
        request = fixture_request('objects-recipients-v1', 'question-binding', 'reading')
        wire = fixture_wire(request)
        self.assertEqual(set(next(iter(wire['questions'].values()))), {'sentence_ids'})
        resolved = content.resolve_source_references(request, wire)
        for fact, question in zip(request['language_plan']['meaning_plan']['facts'], resolved['questions']):
            self.assertEqual(question['prompt_ru'], fact['question_frame_ru'])
            self.assertEqual(question['prompt_en'], fact['question_en'])
        bad = deepcopy(wire)
        bad['questions']['f1']['prompt_ru'] = 'Когда?'
        with self.assertRaises(ValueError):
            content.resolve_source_references(request, bad)

    def test_saved_source_v5_keeps_its_original_pack_without_word_support(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/curriculum_source_v5.json').read_text())
        document = content.validate_output(fixture['request'], fixture['document']['response'])
        pack = content.to_pack(document, content_id=content.PREFIX + 'location-destination-v1:legacy')
        self.assertTrue(all('passage_support' not in item for item in pack['items']))
