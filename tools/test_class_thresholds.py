import unittest
from select_class_thresholds import select_thresholds


class ClassThresholdTests(unittest.TestCase):
    def test_does_not_trade_true_positive_for_precision(self):
        records=[{'gt':[('R',[0,0,10,10])],'predictions':[
            {'type':'R','bbox':[0,0,10,10],'confidence':.6},
            {'type':'R','bbox':[20,0,30,10],'confidence':.3}]}]
        thresholds,rows=select_thresholds(records,['R'],grid=[.25,.4,.7])
        self.assertEqual(thresholds['R'],.4)
        self.assertEqual(rows[0]['candidate']['iou50']['tp'],1)
        self.assertEqual(rows[0]['candidate']['iou50']['fp'],0)

    def test_unobserved_class_keeps_baseline_threshold(self):
        thresholds,rows=select_thresholds([{'gt':[],'predictions':[]}],['D'],grid=[.25,.9])
        self.assertEqual(thresholds['D'],.25)
