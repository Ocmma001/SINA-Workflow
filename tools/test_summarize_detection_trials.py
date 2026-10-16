import json
from pathlib import Path
import tempfile
import unittest
from summarize_detection_trials import summarize


class TrialSummaryTests(unittest.TestCase):
    def test_failed_image_stays_in_recall_denominator(self):
        c = {'type': 'Resistor', 'bbox': [0, 0, 10, 10]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'runs', prefix='unit-summary-') as temp:
            directory = Path(temp)
            cases = [{'name': name, 'truth': [c], 'yolo_components': [c]} for name in ('good', 'bad')]
            (directory / 'cases.json').write_text(json.dumps(cases))
            (directory / 'results.json').write_text(json.dumps([
                {'name': 'good', 'success': True}, {'name': 'bad', 'success': False, 'error': 'JSONDecodeError'}]))
            (directory / 'good').mkdir()
            (directory / 'good/detection.json').write_text(json.dumps({'components': [c]}))
            result = summarize(directory)
            self.assertEqual(result['all_attempts']['yolo11m']['0.5']['f1'], 1)
            self.assertEqual(result['all_attempts']['pro_direct']['0.5']['recall'], 0.5)
            self.assertAlmostEqual(result['all_attempts']['pro_direct']['0.5']['f1'], 2/3)


if __name__ == '__main__':
    unittest.main()
