import unittest
from detector_pair_report import pair_cases


def example(image='a.jpg'):
    return {'image': image, 'image_sha256': 'image', 'label_sha256': 'label',
            'truth': [{'class': 0, 'bbox': [0, 0, 10, 10]}], 'predictions': [], 'error': None}


class PairingTests(unittest.TestCase):
    def test_missing_images_cannot_disappear_from_paired_denominator(self):
        with self.assertRaises(ValueError):
            pair_cases([example(), example('b.jpg')], [example()])

    def test_changed_annotations_cannot_be_compared_as_same_data(self):
        changed = dict(example(), label_sha256='changed')
        with self.assertRaises(ValueError):
            pair_cases([example()], [changed])

    def test_failed_prediction_is_counted_as_missing_detection(self):
        baseline = example()
        baseline['predictions'] = [{'class': 0, 'bbox': [0, 0, 10, 10], 'confidence': .9}]
        failed = dict(example(), error='RuntimeError')
        row = pair_cases([baseline], [failed])[0]
        self.assertEqual(row['scores']['0.5']['baseline']['fn'], 0)
        self.assertEqual(row['scores']['0.5']['candidate']['fn'], 1)
        self.assertEqual(row['candidate_error'], 'RuntimeError')
