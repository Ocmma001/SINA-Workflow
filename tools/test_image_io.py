import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from modules.image_io import read_image, write_image


class UnicodeImageIOTests(unittest.TestCase):
    def test_unicode_image_roundtrip_preserves_pixels_and_exact_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'电路测试.png'
            image = np.arange(180, dtype=np.uint8).reshape(6, 10, 3)
            self.assertTrue(write_image(path, image))
            self.assertTrue(path.is_file())
            np.testing.assert_array_equal(read_image(path), image)
            self.assertEqual([p.name for p in Path(directory).iterdir()], [path.name])

    def test_encoding_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'failed.png'
            with patch('cv2.imencode', return_value=(False, None)):
                with self.assertRaises(ValueError):
                    write_image(path, np.zeros((2, 2, 3), dtype=np.uint8))
            self.assertFalse(path.exists())
