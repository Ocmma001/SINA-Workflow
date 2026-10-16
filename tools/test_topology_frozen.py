import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from modules.image_io import write_image
from modules.topology_impl import find_crossing


class FrozenCrossingTests(unittest.TestCase):
    def test_masks_frozen_boxes_without_mutating_image(self):
        image = np.full((20, 20, 3), 255, np.uint8)
        image[7:11, 7:11] = 0
        image[15, 15] = 0
        saved = image.copy()
        masked = find_crossing.removeObjects(image, [{'bbox': [7, 7, 11, 11]}], [])
        self.assertTrue(np.all(masked[7:11, 7:11] == 255))
        self.assertTrue(np.all(masked[15, 15] == 0))
        np.testing.assert_array_equal(image, saved)

    def test_crossing_needs_no_model_and_passes_fixed_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'input.png'
            write_image(source, np.full((20, 20, 3), 255, np.uint8))
            boxes = []
            with patch.object(find_crossing, 'removeObjects', wraps=find_crossing.removeObjects) as mask, patch.object(find_crossing, 'getLines', return_value=([], [], [])):
                find_crossing.detectCrossingLines(source, None, root/'out.png', root/'debug.png', components=boxes)
            self.assertIs(mask.call_args.args[1], boxes)
            self.assertTrue((root/'out.png').is_file())

    def test_missing_frozen_boxes_is_explicit_error(self):
        with self.assertRaises(ValueError):
            find_crossing.detectCrossingLines('missing.png', None, 'out.png', 'debug.png')

    def test_invalid_box_cannot_silently_remove_wrong_pixels(self):
        with self.assertRaises(ValueError):
            find_crossing.removeObjects(np.zeros((4,4,3), np.uint8), [{'bbox':[3,3,1,1]}], [])


    def test_cpu_extract_does_not_hide_gpus_from_later_calls(self):
        import argparse
        import os
        import local_extract
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image, weights = root/'input.png', root/'model.pt'
            image.write_bytes(b'fixture')
            weights.write_bytes(b'weights')
            args = argparse.Namespace(image=image, weights=weights, out=root/'out', device='cpu',
                conf=.25, imgsz=960, detections=None, skip_ocr=True, skip_crossings=False)
            with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES':'0'}), \
                 patch('local_extract.read_image', return_value=object()), \
                 patch('local_extract.detector.detect', return_value=([], {})), \
                 patch('local_extract.topology.analyze', return_value=([], None)), \
                 patch('local_extract.attach_pins', return_value={}):
                local_extract.extract(args)
                self.assertEqual(os.environ['CUDA_VISIBLE_DEVICES'], '0')


    def test_debug_variants_preserve_dots_in_parent_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'experiment.v1'/'0.25'
            root.mkdir(parents=True)
            find_crossing.getLines(np.full((40,40,3),255,np.uint8),str(root/'debug.png'))
            for tag in ('vert','horz','backD','forwD'):
                self.assertTrue((root/('debug'+tag+'.png')).is_file())
            self.assertTrue((root/'testing_all_lines.json').is_file())


    def test_precomputed_detection_keeps_model_provenance_without_yolo(self):
        import argparse,hashlib,json
        import local_extract
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            image=root/'input.png'
            image.write_bytes(b'fixed fixture')
            detections=root/'detection.json'
            detections.write_text(json.dumps({'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
                'model_sha256':'known-model-hash','detector':'YOLO','components':[{'id':'R1','type':'Resistor','bbox':[0,0,4,4]}],
                'confidences':{'R1':.9}}))
            args=argparse.Namespace(image=image,out=root/'out',weights=None,detections=detections,
                device='cpu',conf=.25,imgsz=960,skip_ocr=True,skip_crossings=False)
            circuit=[{'id':'R1','label':'Resistor','bounding_box':[0,0,4,4],'connection_points':[]}]
            with patch('local_extract.read_image',return_value=np.full((8,8,3),255,np.uint8)), \
                 patch('local_extract.detector.detect') as detect, \
                 patch('local_extract.topology.analyze',return_value=(circuit,None)), \
                 patch('local_extract.attach_pins',return_value={'R1':[]}):
                result=local_extract.extract(args)
            detect.assert_not_called()
            self.assertEqual(result['model_sha256'],'known-model-hash')
            self.assertEqual(result['components'][0]['confidence'],.9)
            self.assertTrue(result['inference']['crossing_detection'])
