from pathlib import Path
import subprocess
import sys
import unittest


class TrainOptionTests(unittest.TestCase):
    def test_invalid_augmentation_rejected_before_loading_gpu_or_data(self):
        script = Path(__file__).with_name('train_round.py')
        for value in ['-0.1', '1.1']:
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, str(script), '--mosaic', value],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn('mosaic must be between 0 and 1', result.stderr)
