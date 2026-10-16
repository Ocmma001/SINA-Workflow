import unittest
from gui_contract import build_draft, normalize_document, update_review_state, validation_issues


def sample():
    return {'scope': 'local_sina_candidates', 'image': 'circuit.png', 'model_sha256': 'abc',
            'inference': {'imgsz': 960}, 'ocr': [], 'warnings': [], 'components': [
        {'id': 'Resistor_1', 'type': 'Resistor', 'bbox': [0, 0, 10, 20],
         'pin_candidates': [{'image_point': [1, 1], 'connection_candidate': {'region': 4}},
                            {'image_point': [2, 2], 'connection_candidate': {'region': 8}}],
         'confidence': .9, 'text_candidates': []},
        {'id': 'GND_1', 'type': 'GND', 'bbox': [1, 1, 2, 2],
         'pin_candidates': [{'image_point': [2, 2], 'connection_candidate': {'region': 8}}]},
        {'id': 'Transistor_BJT_1', 'type': 'Transistor_BJT', 'bbox': [20, 0, 30, 20],
         'pin_candidates': [{'image_point': [3, 3], 'connection_candidate': {'region': 4}}],
         'text_candidates': []}]}


class GuiContractTests(unittest.TestCase):
    def test_gui_types_ground_and_unknown_values(self):
        raw = sample()
        result = build_draft(raw)
        self.assertEqual(len(result['components']), 2)
        r, q = result['components']
        self.assertEqual(r['type'], 'resistor')
        self.assertEqual(r['nodes'], ['4', '0'])
        self.assertEqual(r['sina_id'], 'Resistor_1')
        self.assertIsNone(r['value'])
        self.assertEqual(q['nodes'], [])
        self.assertTrue(q['review_notes'])
        self.assertFalse(result['recognition']['user_confirmed'])
        self.assertFalse(result['ready_for_simulation'])
        self.assertEqual(raw['components'][0]['type'], 'Resistor')

    def test_model_review_cannot_rewrite_geometry_or_invent_bulk_pin(self):
        result = build_draft(sample(), {'components': [
            {'id': 'Resistor_1', 'ref': 'R_C', 'value': '1k', 'model': None, 'pin_semantics': []}]})
        self.assertEqual(result['components'][0]['ref'], 'R_C')
        self.assertEqual(result['components'][0]['nodes'], ['4', '0'])
        self.assertEqual(result['components'][1]['nodes'], [])
        self.assertTrue(result['components'][0]['needs_user_confirmation'])

    def test_duplicate_refs_are_not_silently_adopted(self):
        raw = sample()
        raw['components'].append(dict(raw['components'][0], id='Resistor_2'))
        review = {'components': [{'id': 'Resistor_1', 'ref': 'R1'}, {'id': 'Resistor_2', 'ref': 'R1'}]}
        result = build_draft(raw, review)
        refs = [c['ref'].lower() for c in result['components']]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(result['recognition']['warnings'])

    def test_confirmation_alone_does_not_make_incomplete_draft_ready(self):
        result = update_review_state(build_draft(sample()), True)
        self.assertTrue(result['recognition']['user_confirmed'])
        self.assertFalse(result['ready_for_simulation'])
        self.assertTrue(validation_issues(result))
        result = update_review_state(result, False)
        self.assertFalse(result['recognition']['user_confirmed'])

    def test_valid_human_confirmed_circuit_and_extra_fields_roundtrip(self):
        data = {'custom': {'note': 'keep'}, 'recognition': {'user_confirmed': False},
                'components': [{'ref': 'V1', 'type': 'voltage_source', 'value': '5', 'nodes': ['in', '0']},
                               {'ref': 'R1', 'type': 'resistor', 'value': '1k', 'nodes': ['in', '0']}]}
        result = update_review_state(normalize_document(data), True)
        self.assertEqual(result['custom'], {'note': 'keep'})
        self.assertTrue(result['ready_for_simulation'])
        self.assertFalse(validation_issues(result))

    def test_raw_workbench_output_can_be_loaded_by_gui(self):
        self.assertEqual(normalize_document(sample())['components'][0]['type'], 'resistor')

    def test_bad_waveform_and_overflow_cannot_become_ready(self):
        base = {'recognition': {}, 'components': [
            {'ref': 'V1', 'type': 'voltage_source', 'value': '0', 'nodes': ['in', '0'], 'waveform': 'SIN(0 1 -1k)'},
            {'ref': 'R1', 'type': 'resistor', 'value': '1k', 'nodes': ['in', '0']}]}
        self.assertFalse(update_review_state(base, True)['ready_for_simulation'])
        base['components'][0]['waveform'] = 'SIN(0 1 1k)'
        base['components'][1]['value'] = '1e300t'
        self.assertFalse(update_review_state(base, True)['ready_for_simulation'])


if __name__ == '__main__':
    unittest.main()
