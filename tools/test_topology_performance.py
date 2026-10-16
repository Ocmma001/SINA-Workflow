import unittest
import numpy as np
from modules.topology_impl.nodes_analysis import perimeter_contacts,label_visualization


def legacy(labels,bbox):
    height,width=labels.shape
    x1,y1,x2,y2=bbox
    perimeter=np.zeros(labels.shape,bool)
    if y1<height: perimeter[y1,max(0,x1):min(width,x2+1)]=True
    if y2<height: perimeter[y2,max(0,x1):min(width,x2+1)]=True
    if x1<width: perimeter[max(0,y1):min(height,y2+1),x1]=True
    if x2<width: perimeter[max(0,y1):min(height,y2+1),x2]=True
    result={}
    for region in range(1,int(labels.max())+1):
        ys,xs=np.where(perimeter & (labels==region))
        if len(xs): result[region]=list(zip(xs,ys))
    return result


class TopologyPerformanceTests(unittest.TestCase):
    def test_perimeter_matches_legacy_pixels_and_order(self):
        rng=np.random.default_rng(42)
        for _ in range(50):
            labels=rng.integers(0,25,(24,32),dtype=np.int32)
            x1,x2=sorted(rng.integers(0,35,2).tolist())
            y1,y2=sorted(rng.integers(0,27,2).tolist())
            bbox=[x1,y1,x2,y2]
            self.assertEqual(perimeter_contacts(labels,bbox),legacy(labels,bbox))

    def test_negative_edge_does_not_wrap_around(self):
        labels=np.zeros((5,5),int)
        labels[4,2]=7
        self.assertEqual(perimeter_contacts(labels,[1,-1,3,1]),{})

    def test_palette_matches_legacy_seeded_colors(self):
        labels=np.array([[0,1,2],[3,2,0]],dtype=np.int32)
        np.random.seed(42)
        old=np.zeros((2,3,3),np.uint8)
        for region in range(1,4): old[labels==region]=np.random.randint(0,255,3)
        np.random.seed(42)
        np.testing.assert_array_equal(label_visualization(labels,range(1,4),4),old)
