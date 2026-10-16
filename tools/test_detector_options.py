import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from modules.detector import tile_windows,merge_detections,predict_records


class DetectorOptionTests(unittest.TestCase):
    def test_tiles_cover_edges_and_bound_work(self):
        windows=tile_windows(135,99,64,.25)
        cover=np.zeros((99,135),bool)
        for x1,y1,x2,y2 in windows: cover[y1:y2,x1:x2]=True
        self.assertTrue(cover.all())
        with self.assertRaises(ValueError): tile_windows(10000,10000,32,.5)

    def test_class_aware_merge_keeps_distinct_symbols(self):
        records=[{'type':'R','confidence':.9,'bbox':[0,0,10,10]},
                 {'type':'R','confidence':.8,'bbox':[1,0,11,10]},
                 {'type':'C','confidence':.7,'bbox':[0,0,10,10]}]
        result=merge_detections(records,.5)
        self.assertEqual([r['type'] for r in result],['R','C'])

    def test_tile_offsets_and_class_thresholds_restore_original_pixels(self):
        class Scalar:
            def __init__(self,value): self.value=value
            def item(self): return self.value
        class Coordinates:
            def __getitem__(self,index): return self
            def tolist(self): return [2.,3.,10.,12.]
        class Box:
            cls,conf,xyxy=Scalar(0),Scalar(.6),Coordinates()
        class Result:
            names={0:'Resistor'}
            boxes=[Box()]
        class Model:
            names={0:'Resistor'}
            def predict(self,*args,**kwargs): return [Result()]
        with tempfile.TemporaryDirectory() as directory:
            weights=Path(directory)/'model.pt'
            weights.write_bytes(b'fixture')
            with patch('modules.detector._model',return_value=Model()):
                result=predict_records(np.zeros((64,100,3),np.uint8),weights,tile_size=64)
                self.assertTrue(any(r['bbox']==[38.,3.,46.,12.] for r in result))
                rejected=predict_records(np.zeros((64,100,3),np.uint8),weights,class_conf={'Resistor':.7})
                self.assertEqual(rejected,[])


    def test_model_cache_is_device_specific(self):
        import sys,types
        from unittest.mock import Mock
        from modules.detector import _model,clear_model_cache
        constructor=Mock(side_effect=[object(),object()])
        clear_model_cache()
        with patch.dict(sys.modules,{'ultralytics':types.SimpleNamespace(YOLO=constructor)}):
            cpu=_model('fixture.pt',1,1,'cpu')
            self.assertIs(_model('fixture.pt',1,1,'cpu'),cpu)
            gpu=_model('fixture.pt',1,1,'0')
            self.assertIsNot(cpu,gpu)
            self.assertEqual(constructor.call_count,2)
        clear_model_cache()
