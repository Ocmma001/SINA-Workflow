import unittest
from pro_detector import validate_detections


class ProDetectorTests(unittest.TestCase):
    def test_pixel_conversion_and_ground_inclusion(self):
        result = validate_detections({'components': [
            {'type': 'Resistor', 'bbox': [100, 200, 300, 400]},
            {'type': 'GND', 'bbox': [500, 600, 700, 800]}]}, 200, 100)
        self.assertEqual(result[0]['bbox'], [20, 20, 60, 40])
        self.assertEqual(result[1]['id'], 'GND_1')
        self.assertIsNone(result[0]['confidence'])

    def test_invalid_types_and_boxes_are_rejected(self):
        bad = [('wire', [0, 0, 10, 10]), ('Resistor', [0, 0, 1001, 10]),
               ('Resistor', [10, 0, 0, 10]), ('Resistor', [0, 0, float('nan'), 10]),
               ('Resistor', [False, 0, 10, 10])]
        for kind, box in bad:
            with self.subTest(kind=kind, box=box), self.assertRaises(ValueError):
                validate_detections({'components': [{'type': kind, 'bbox': box}]}, 100, 100)


if __name__ == '__main__':
    unittest.main()
