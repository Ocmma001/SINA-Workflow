import unittest
from modules.detector import default_class_thresholds


class SelectedThresholdTests(unittest.TestCase):
    def test_selected_profile_is_complete_and_returns_fresh_mapping(self):
        thresholds = default_class_thresholds()
        self.assertEqual(len(thresholds), 10)
        self.assertEqual(thresholds['Resistor'], .3)
        self.assertEqual(thresholds['Diode'], .25)
        thresholds['Resistor'] = 1
        self.assertEqual(default_class_thresholds()['Resistor'], .3)
