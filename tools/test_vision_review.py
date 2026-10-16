import json
import unittest
from vision_review import build_payload, extract_json, validate_review


class VisionReviewTests(unittest.TestCase):
    def test_request_uses_image_and_no_search_tools(self):
        p = build_payload('model', 'data:image/jpeg;base64,abc', {'components': []})
        self.assertFalse(p['stream'])
        self.assertNotIn('tools', p)
        self.assertEqual(p['input'][0]['content'][1]['type'], 'input_image')
        self.assertEqual(p['thinking']['type'], 'disabled')

    def test_extracts_text_output_not_reasoning(self):
        response = {'status': 'completed', 'output': [
            {'type': 'reasoning', 'summary': []},
            {'type': 'message', 'content': [{'type': 'output_text',
                                           'text': json.dumps({'components': []})}]}]}
        self.assertEqual(extract_json(response), {'components': []})
        response['status'] = 'incomplete'
        with self.assertRaises(ValueError):
            extract_json(response)

    def test_rejects_unknown_duplicate_and_invalid_components(self):
        for parts in ([{'id': 'unknown'}], [{'id': 'R1'}, {'id': 'R1'}],
                      [{'id': 'R1', 'confidence': 2}], ['invalid']):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                validate_review({'components': parts}, {'R1'})

    def test_never_auto_confirms_model_output(self):
        r = validate_review({'components': [{'id': 'R1', 'ref': 'R1'}],
                             'ready_for_simulation': True}, {'R1'})
        self.assertFalse(r['ready_for_simulation'])
        self.assertTrue(r['components'][0]['needs_user_confirmation'])

    def test_rejects_pin_index_outside_local_evidence(self):
        r = {'components': [{'id': 'Q1', 'pin_semantics': [
            {'candidate_pin_index': 3, 'semantic': 'B', 'confidence': 0.9}]}]}
        with self.assertRaises(ValueError):
            validate_review(r, {'Q1'}, {'Q1': 3})

    def test_rejects_nontext_values_and_duplicate_pin_indices(self):
        for c in ({'id': 'R1', 'value': {'guessed': 100}},
                  {'id': 'R1', 'pin_semantics': [
                      {'candidate_pin_index': 0, 'semantic': 'A'},
                      {'candidate_pin_index': 0, 'semantic': 'B'}]}):
            with self.subTest(component=c), self.assertRaises(ValueError):
                validate_review({'components': [c]}, {'R1'}, {'R1': 2})


if __name__ == '__main__':
    unittest.main()
