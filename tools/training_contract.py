"""Shared validation and honest output schema for detector training/delivery."""
import math


def validate_label(line):
    parts = line.split()
    if len(parts) != 5:
        raise ValueError('Expected class cx cy width height')
    cid = int(parts[0])
    box = tuple(float(v) for v in parts[1:])
    if not 0 <= cid < 10 or not all(math.isfinite(v) and 0 <= v <= 1 for v in box):
        raise ValueError('Invalid class or normalized coordinates')
    if box[2] <= 0 or box[3] <= 0:
        raise ValueError('Box dimensions must be positive')
    return cid, box


def detection_payload(image, components):
    return {
        'schema_version': '1.0', 'image': str(image),
        'scope': 'component_detection', 'ready_for_simulation': False,
        'components': [dict(c, value=None, nodes=[], needs_user_confirmation=True)
                       for c in components],
        'warnings': ['Detection does not determine values, semantic pin order, or topology.'],
    }


# Backward-compatible public import.
from modules.pins import locate_pin
