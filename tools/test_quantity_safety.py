import unittest
from modules.text_binding import parse_quantity


class QuantitySafetyTests(unittest.TestCase):
    def test_separate_numeric_tokens_are_not_concatenated(self):
        # Real circuit_0003 OCR output for the visually printed 47 ohm label.
        # Reject ambiguity instead of treating it as a known value of 470.
        for text in ('47 0', '4 7', '4 .7 kΩ', '4. 7kΩ'):
            with self.subTest(text=text):
                self.assertIsNone(parse_quantity(text, 'resistor'))

    def test_whitespace_before_units_and_case_sensitive_prefixes(self):
        cases = [('47 Ω', 'resistor', '47'), ('10 MΩ', 'resistor', '10meg'),
                 ('10 mΩ', 'resistor', '10m'), ('0.1 uF', 'capacitor', '0.1u'),
                 ('5 V', 'voltage_source', '5'), ('10 m A', 'current_source', '10m'),
                 ('R_C', 'resistor', None)]
        for text, kind, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_quantity(text, kind), expected)


    def test_contract_preserves_ambiguous_ocr_whitespace(self):
        from gui_contract import build_draft
        from test_gui_contract import sample
        raw = sample()
        raw['ocr'] = [{'text': '47 0', 'confidence': .9,
                       'bbox': [[1, 1], [3, 1], [3, 3], [1, 3]]}]
        draft = build_draft(raw)
        self.assertIsNone(draft['components'][0]['value'])
        self.assertFalse(draft['ready_for_simulation'])
