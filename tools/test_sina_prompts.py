from pathlib import Path
import unittest
from sina_ark_workflow import load_prompts, raw_structure, build_stage_payload, audit_netlist, ocr_context


class SinaPromptTests(unittest.TestCase):
    def test_original_task_focus_and_templates(self):
        first, second = load_prompts()
        self.assertIn('ONLY include components with drawn symbols', first)
        self.assertIn('DO NOT include ground symbols', first)
        self.assertIn('Skip components with no visible labels entirely', first)
        self.assertIn('NODE CONNECTIVITY IMMUTABILITY', second)
        self.assertIn('NEVER use the internal ID number', second)
        self.assertIn('GROUND_NODE:', second)

    def test_first_stage_has_image_second_stage_is_text_only(self):
        a = build_stage_payload('model', 'inventory', 'prompt', 'data:image/png;base64,abc')
        b = build_stage_payload('model', 'netlist', 'prompt')
        self.assertEqual(a['input'][0]['content'][1]['type'], 'input_image')
        self.assertEqual(len(b['input'][0]['content']), 1)
        self.assertNotIn('tools', a)
        self.assertEqual((a['max_output_tokens'], b['max_output_tokens']), (1800, 1500))

    def test_raw_topology_preserves_order_and_explicit_ground(self):
        data = {'components': [
            {'id': 'GND_1', 'type': 'GND', 'pin_candidates': [
                {'connection_candidate': {'region': 9}}]},
            {'id': 'Resistor_1', 'type': 'Resistor', 'pin_candidates': [
                {'connection_candidate': {'region': 5}},
                {'connection_candidate': {'region': 9}}]},
            {'id': 'Transistor_BJT_1', 'type': 'Transistor_BJT', 'pin_candidates': [
                {'connection_candidate': {'region': 7}},
                {'connection_candidate': {'region': 5}},
                {'connection_candidate': {'region': 9}}]}]}
        self.assertEqual(raw_structure(data), ['Resistor_1 5 0', 'Transistor_BJT_1 7 5 0'])
        data['components'][1]['pin_candidates'][0]['connection_candidate'] = None
        with self.assertRaises(ValueError):
            raw_structure(data)

    def test_audit_flags_missing_end_values_and_changed_nodes(self):
        issues = audit_netlist(['Resistor_1 1 2'], 'R1 1 3\n')
        self.assertTrue(any('.end' in w for w in issues))
        self.assertTrue(any('value' in w for w in issues))
        self.assertTrue(any('connectivity' in w for w in issues))
        self.assertEqual(audit_netlist(['Resistor_1 1 2'], 'R1 1 2 1k\n.end'), [])

    def test_ocr_context_anchors_internal_id_to_bbox_without_changing_text(self):
        c = {'components': [{'id': 'Resistor_1', 'bbox': [10, 20, 30, 40],
                              'text_candidates': [{'text': 'R₂'}]}], 'ocr': []}
        result = ocr_context(c)
        self.assertEqual(result['by_component']['Resistor_1']['bbox'], [10, 20, 30, 40])
        self.assertEqual(result['by_component']['Resistor_1']['ocr_candidates'][0]['text'], 'R₂')
        legacy = ocr_context(c, include_boxes=False)
        self.assertEqual(legacy['by_component']['Resistor_1'], [{'text': 'R₂'}])


if __name__ == '__main__':
    unittest.main()
