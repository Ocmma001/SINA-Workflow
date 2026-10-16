import unittest
from direct_detector_benchmark import score


class MatchingTests(unittest.TestCase):
    def test_duplicate_detection_counts_as_false_positive(self):
        c = {'type': 'Resistor', 'bbox': [0, 0, 10, 10]}
        self.assertEqual(score([c, c], [c]), {'tp': 1, 'fp': 1, 'fn': 0, 'whole_image_correct': False})

    def test_wrong_class_cannot_match_and_tightness_matters(self):
        truth = [{'type': 'GND', 'bbox': [0, 0, 10, 10]}]
        self.assertEqual(score([{'type': 'Resistor', 'bbox': [0, 0, 10, 10]}], truth)['tp'], 0)
        loose = [{'type': 'GND', 'bbox': [0, 0, 12, 12]}]
        self.assertEqual(score(loose, truth, 0.5)['tp'], 1)
        self.assertEqual(score(loose, truth, 0.75)['tp'], 0)


if __name__ == '__main__':
    unittest.main()
