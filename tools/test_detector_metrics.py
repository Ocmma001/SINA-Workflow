import unittest
from detector_metrics import score_detections


class DetectionMetricTests(unittest.TestCase):
    def test_duplicate_detection_cannot_match_one_truth_twice(self):
        truth = [{'class': 0, 'bbox': [0, 0, 10, 10]}]
        predictions = [{'class': 0, 'bbox': [0, 0, 10, 10], 'confidence': c} for c in [.9, .8]]
        result = score_detections(truth, predictions, .5)
        self.assertEqual((result['tp'], result['fp'], result['fn']), (1, 1, 0))

    def test_wrong_class_does_not_match(self):
        result = score_detections([{'class': 0, 'bbox': [0, 0, 10, 10]}],
            [{'class': 1, 'bbox': [0, 0, 10, 10], 'confidence': .9}], .5)
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))

    def test_tighter_iou_and_confidence_keep_the_same_truth_denominator(self):
        truth = [{'class': 0, 'bbox': [0, 0, 10, 10]}]
        predictions = [{'class': 0, 'bbox': [2, 0, 12, 10], 'confidence': .2}]
        self.assertEqual(score_detections(truth, predictions, .5)['tp'], 1)
        self.assertEqual(score_detections(truth, predictions, .75)['fn'], 1)
        self.assertEqual(score_detections(truth, predictions, .5, confidence=.25)['fn'], 1)

    def test_empty_prediction_still_counts_truth(self):
        result = score_detections([{'class': 0, 'bbox': [0, 0, 10, 10]}], [], .5)
        self.assertEqual((result['tp'], result['fp'], result['fn'], result['f1']), (0, 0, 1, 0))

    def test_invalid_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            score_detections([], [], 1.1)
