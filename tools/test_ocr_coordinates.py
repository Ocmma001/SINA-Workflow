import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from modules import ocr


class OcrCoordinateTests(unittest.TestCase):
    def test_upscale_restores_original_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('modules.ocr._reader') as factory:
                factory.return_value.readtext.return_value = [([[30,30],[90,30],[90,60],[30,60]],'R1',.9)]
                result = ocr.recognize(np.zeros((100,200,3),np.uint8),Path(directory),Path(directory),'cpu',min_side=300)
                self.assertEqual(factory.return_value.readtext.call_args.args[0].shape,(300,600,3))
                self.assertEqual(result[0]['bbox'],[[10.,10.],[30.,10.],[30.,20.],[10.,20.]])

    def test_preprocessing_bounds_and_preserves_native_default(self):
        image=np.zeros((100,1000,3),np.uint8)
        prepared,sx,sy=ocr._prepare_image(image,800,'gray')
        self.assertLessEqual(prepared.shape[0]*prepared.shape[1],4_000_000)
        self.assertLessEqual(sx,3)
        native,sx,sy=ocr._prepare_image(image,0,'none')
        self.assertIs(native,image)
        self.assertEqual((sx,sy),(1,1))
        with self.assertRaises(ValueError): ocr._prepare_image(image,10,'unknown')


    def test_reader_cache_uses_requested_gpu_index(self):
        import sys,types
        from unittest.mock import Mock
        constructor=Mock(return_value=object())
        ocr.clear_reader_cache()
        with patch.dict(sys.modules,{'easyocr':types.SimpleNamespace(Reader=constructor)}):
            first=ocr._reader('models','user','1',())
            self.assertIs(first,ocr._reader('models','user','1',()))
            self.assertEqual(constructor.call_args.kwargs['gpu'],'cuda:1')
            self.assertEqual(constructor.call_count,1)
        ocr.clear_reader_cache()
