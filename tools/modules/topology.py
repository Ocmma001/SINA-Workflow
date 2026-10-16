"""Wire-region extraction; returns raw contacts and the original-sized label raster."""
import json

def analyze(image, detected, debug, weights, detect_crossings=True):
    import cv2
    import numpy as np
    from .topology_impl.nodes_analysis import identify_circuit_nodes
    debug.mkdir(parents=True, exist_ok=True)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    merged = (cv2.dilate(binary, np.ones((3, 3), np.uint8), iterations=1) > 0).astype(np.uint8)
    identify_circuit_nodes(merged, detected, str(debug), image, str(weights),
                           detect_crossings=detect_crossings)
    circuit = json.loads((debug / 'circuit_info.json').read_text(encoding='utf-8'))
    return circuit, np.load(debug / 'node_labels.npy')
