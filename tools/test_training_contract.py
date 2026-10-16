"""Tests that prevent malformed annotations and unsupported confidence claims."""
import unittest
from training_contract import validate_label, detection_payload, locate_pin


class ContractTests(unittest.TestCase):
    def test_accepts_normalized_box(self):
        self.assertEqual(validate_label('0 0.5 0.5 0.2 0.1')[0], 0)

    def test_rejects_invalid_classes_and_nonfinite_boxes(self):
        for line in ('10 0.5 0.5 0.2 0.1', '1 nan 0.5 0.2 0.1',
                     '0 0.5 0.5 0 0.1', '0 1.4 0.5 0.2 0.1'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                validate_label(line)

    def test_detection_does_not_claim_parameter_or_topology_confirmation(self):
        data = detection_payload('a.png', [{'id': 'Resistor_1', 'type': 'Resistor',
                                           'bbox': [1, 2, 3, 4], 'confidence': 0.9}])
        self.assertFalse(data['ready_for_simulation'])
        self.assertEqual(data['scope'], 'component_detection')
        self.assertIsNone(data['components'][0]['value'])
        self.assertEqual(data['components'][0]['nodes'], [])
        self.assertTrue(data['components'][0]['needs_user_confirmation'])

    def test_pin_search_never_attaches_to_a_distant_wire(self):
        class Grid:
            shape = (3, 5)
            def __getitem__(self, pos):
                return 7 if pos == (1, 4) else 0
        self.assertIsNone(locate_pin(Grid(), 0, 1, radius=2))
        self.assertEqual(locate_pin(Grid(), 3, 1, radius=2)['region'], 7)
        self.assertIsNone(locate_pin(Grid(), -1, 1, radius=2))


if __name__ == '__main__':
    unittest.main()
