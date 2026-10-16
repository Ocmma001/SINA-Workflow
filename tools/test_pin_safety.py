import unittest
import numpy as np
from modules.pins import locate_pin, attach_pins


class PinSafetyTests(unittest.TestCase):
    def test_equidistant_distinct_nets_stay_unknown(self):
        labels = np.zeros((7,7), int)
        labels[3,2], labels[3,4] = 4, 8
        self.assertIsNone(locate_pin(labels,3,3))
        pin = attach_pins([{'id':'R1','connection_points':[[3,3]]}],labels)['R1'][0]
        self.assertEqual(pin['connection_status'],'ambiguous')
        self.assertEqual(len(pin['connection_alternatives']),2)

    def test_same_net_at_multiple_pixels_is_not_ambiguous(self):
        labels = np.zeros((7,7), int)
        labels[3,2] = labels[3,4] = 4
        self.assertEqual(locate_pin(labels,3,3)['region'],4)

    def test_outward_direction_rejects_closer_interior_net(self):
        labels = np.zeros((15,15), int)
        labels[5,9],labels[5,12] = 4,8
        pin = attach_pins([{'id':'R1','bounding_box':[0,0,10,10],'connection_points':[[10,5]]}],labels)['R1'][0]
        self.assertEqual(pin['search_direction'],[1,0])
        self.assertEqual(pin['connection_candidate']['region'],8)

    def test_duplicate_contacts_do_not_invent_two_pins(self):
        labels = np.ones((7,7), int)
        pins = attach_pins([{'id':'Q1','connection_points':[[3,3],[3,3]]}],labels)['Q1']
        self.assertTrue(all(p['connection_candidate'] is None for p in pins))
        self.assertTrue(all(p['connection_status']=='duplicate_contact' for p in pins))

    def test_bounds_radius_and_missing_net(self):
        labels = np.zeros((10,10),int)
        labels[5,9]=2
        self.assertIsNone(locate_pin(labels,3,5,radius=5))
        self.assertIsNone(locate_pin(labels,-.1,5))
        with self.assertRaises(ValueError): locate_pin(labels,3,5,radius=100)

    def test_renumbered_regions_preserve_choice(self):
        labels=np.zeros((5,5),int)
        labels[1,2],labels[0,2]=1,2
        first=locate_pin(labels,2,2)
        labels[labels==1]=7
        labels[labels==2]=3
        second=locate_pin(labels,2,2)
        self.assertEqual(first['pixel'],second['pixel'])
        self.assertEqual(second['region'],7)
