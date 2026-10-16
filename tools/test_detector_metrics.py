import unittest
from evaluate_detector_options import score,combine


class DetectorMetricTests(unittest.TestCase):
    def test_failed_image_predictions_count_as_misses(self):
        truth=[('Resistor',[0,0,10,10]),('Capacitor',[20,0,30,10])]
        self.assertEqual(score(truth,[],.5),{'tp':0,'fp':0,'fn':2})

    def test_duplicate_and_wrong_class_are_false_positives(self):
        truth=[('Resistor',[0,0,10,10])]
        predictions=[{'type':'Resistor','bbox':[0,0,10,10],'confidence':.9},
                     {'type':'Resistor','bbox':[0,0,10,10],'confidence':.8},
                     {'type':'Capacitor','bbox':[0,0,10,10],'confidence':.7}]
        metrics=score(truth,predictions,.75)
        self.assertEqual(metrics,{'tp':1,'fp':2,'fn':0})
        self.assertEqual(combine([{'metric':metrics}],'metric')['f1'],.5)
