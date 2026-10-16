import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from modules.vision import review_candidates


class VisionStageTests(unittest.TestCase):
    def test_two_stage_review_keeps_unknowns_and_is_not_confirmed(self):
        candidates = {'components': [{'id': 'Resistor_1', 'pin_candidates': [], 'bbox': [0, 0, 2, 2]}]}
        response = json.dumps({'components': [{'id': 'Resistor_1', 'value': None, 'pin_semantics': []}]})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            image = output / 'input.jpg'
            image.write_bytes(b'mocked image, never sent')
            with patch.dict(os.environ, {'ARK_API_KEY': 'test-only'}), patch('dotenv.load_dotenv'), \
                 patch('sina_ark_workflow.call_ark', side_effect=[('R1', {}), (response, {})]) as api:
                result = review_candidates(image, output, candidates)
            self.assertEqual(api.call_count, 2)
            self.assertFalse(result['ready_for_simulation'])
            self.assertIsNone(result['components'][0]['value'])
            self.assertTrue(result['components'][0]['needs_user_confirmation'])
            self.assertTrue((output / 'review.json').is_file())
            self.assertNotIn('test-only', (output / 'review.json').read_text(encoding='utf-8'))

    def test_missing_key_never_calls_api(self):
        with patch.dict(os.environ, {'ARK_API_KEY': ''}), patch('dotenv.load_dotenv'), \
             patch('sina_ark_workflow.call_ark') as api:
            with self.assertRaises(ValueError):
                review_candidates(Path('missing.jpg'), Path('.'), {'components': []})
            api.assert_not_called()
