import unittest
from paired_detection_bootstrap import paired_bootstrap


def row(name):
    return {'image':name,'failure':None,'iou50':{'tp':1,'fp':1,'fn':0},'iou75':{'tp':1,'fp':1,'fn':0}}


class PairedBootstrapTests(unittest.TestCase):
    def test_identical_inputs_have_zero_delta_even_with_failed_rows(self):
        records=[row('a'),row('b')]
        records[1]['failure']='timeout'
        result=paired_bootstrap(records,records,samples=100,seed=42)
        self.assertEqual(result['baseline_failures'],1)
        self.assertEqual(result['metrics']['iou50']['paired_bootstrap_95_percent_interval'],[0.,0.])

    def test_missing_or_duplicate_images_are_rejected(self):
        with self.assertRaises(ValueError): paired_bootstrap([row('a')],[row('b')])
        with self.assertRaises(ValueError): paired_bootstrap([row('a'),row('a')],[row('a')])
