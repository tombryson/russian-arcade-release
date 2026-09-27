"""Saved delivery content can improve without moving its destinations."""
from copy import deepcopy
import unittest

from services.route_guidance import CONTENT_REVISION, clarify_pack
from services.route_town import all_audio, build_mission, build_world, validate_mission, variant_seeds


class RouteGuidanceTests(unittest.TestCase):
    def test_both_bridge_variants_explain_the_meeting_and_delivery(self):
        for seed in variant_seeds('town-detour'):
            pack = build_mission(build_world('guidance'), 'town-detour', seed=seed)
            first, second = pack['legs']
            closed = pack['mission_facts']['closed_bridge']
            approach = pack['town']['places'][closed + '-approach']
            self.assertEqual(pack['content_revision'], CONTENT_REVISION)
            self.assertIn('на этом берегу', first['lines'][0]['text'])
            self.assertIn('на мост не заходи', first['lines'][0]['text'])
            self.assertEqual(first['visible_contacts'], [{'position': approach, 'speaker': 'worker'}])
            self.assertIn('между рекой и жёлтым домом', second['lines'][0]['text'])
            self.assertIn('до входа', second['lines'][0]['text'])
            self.assertIn('передай письмо Лене', second['lines'][0]['text'])
            self.assertTrue(validate_mission(pack))

    def test_saved_geometry_routes_and_original_are_unchanged(self):
        pack = build_mission(build_world('saved-guidance'), 'town-detour')
        pack.pop('content_revision')
        pack['legs'][0]['lines'][0]['text'] = 'Earlier saved instructions.'
        pack['legs'][0].pop('visible_contacts')
        before = deepcopy(pack)
        clarified = clarify_pack(pack)
        self.assertIsNot(pack, clarified)
        self.assertEqual(pack, before)
        for field in ('town', 'map', 'lesson_version', 'generator_version', 'mission_seed', 'mission_facts'):
            self.assertEqual(clarified[field], before[field])
        for old_leg, new_leg in zip(before['legs'], clarified['legs']):
            for field in ('id', 'start', 'target', 'route', 'rules'):
                self.assertEqual(new_leg[field], old_leg[field])
        self.assertEqual(clarify_pack(clarified), clarified)

    def test_old_south_facing_entrance_uses_the_same_recordings(self):
        pack = build_mission(build_world('old-guidance'), 'town-detour')
        original = deepcopy(pack)
        # Older saved towns place the library above its entrance. The wording
        # must not assume the current north-facing frontage or redraw that map.
        library = next(b for b in pack['town']['buildings'] if b['id'] == 'library')
        yellow = next(b for b in pack['town']['buildings'] if b['id'] == 'yellow-house')
        door = next(n for n in pack['map']['nodes'] if n['id'] == pack['town']['places']['library'])
        library['y'] = yellow['y'] = door['y'] - 1
        library['frontage'] = 's'
        pack['generator_version'] = 'delivery-town-v2'
        before = deepcopy(pack)
        clarified = clarify_pack(pack)
        self.assertEqual(clarified['map'], before['map'])
        self.assertEqual(clarified['town'], before['town'])
        self.assertEqual([l['lines'] for l in clarified['legs']], [l['lines'] for l in original['legs']])

    def test_unrecognised_geography_and_other_missions_are_left_alone(self):
        other = build_mission(build_world('other-mission'), 'town-address')
        self.assertIs(clarify_pack(other), other)
        pack = build_mission(build_world('other-geography'), 'town-detour')
        library = next(b for b in pack['town']['buildings'] if b['id'] == 'library')
        library['x'] = 0
        self.assertIs(clarify_pack(pack), pack)
        missing = {'mission_id': 'town-detour', 'map': {'scene': 'town'}}
        self.assertIs(clarify_pack(missing), missing)

    def test_every_replacement_recording_is_in_the_finite_audio_catalogue(self):
        clips = {item['id']: item for item in all_audio()}
        replacement_ids = set()
        for seed in variant_seeds('town-detour'):
            pack = build_mission(build_world('recordings'), 'town-detour', seed=seed)
            for leg in pack['legs']:
                for item in [*leg['lines'], leg['clarify']]:
                    self.assertIn(item['id'], clips)
                    self.assertEqual(clips[item['id']]['text'], item['text'])
                    replacement_ids.add(item['id'])
        self.assertEqual(len(replacement_ids), 4)


if __name__ == '__main__':
    unittest.main()
