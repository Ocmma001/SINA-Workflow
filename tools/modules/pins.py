"""Bounded, direction-aware contact attachment without model dependencies."""
import math
from collections import Counter

MAX_PIN_RADIUS = 32


def _candidates(labels, x, y, radius=5, direction=None):
    if type(radius) is not int or not 0 <= radius <= MAX_PIN_RADIUS:
        raise ValueError(f'pin radius must be an integer in [0, {MAX_PIN_RADIUS}]')
    height, width = labels.shape
    if not all(math.isfinite(float(v)) for v in (x, y)):
        return []
    if not 0 <= x < width or not 0 <= y < height:
        return []
    x, y = int(x), int(y)
    if direction is not None:
        if len(direction) != 2 or not all(math.isfinite(float(v)) for v in direction) or not any(direction):
            raise ValueError('pin direction must be a finite nonzero vector')
    nearest = {}
    for py in range(max(0, y-radius), min(height, y+radius+1)):
        for px in range(max(0, x-radius), min(width, x+radius+1)):
            region = int(labels[py, px])
            distance2 = (px-x)**2 + (py-y)**2
            if region <= 0 or distance2 > radius**2:
                continue
            if direction is not None and (px-x)*direction[0] + (py-y)*direction[1] < 0:
                continue
            candidate = (distance2, px, py)
            if region not in nearest or candidate < nearest[region]:
                nearest[region] = candidate
    ordered = sorted((value[0], region, value[1], value[2]) for region, value in nearest.items())
    return [{'region': region, 'pixel': [px, py], 'distance': math.sqrt(distance2)}
            for distance2, region, px, py in ordered]


def _unique_nearest(candidates):
    if not candidates:
        return None
    if len(candidates) > 1 and math.isclose(candidates[0]['distance'], candidates[1]['distance'], abs_tol=1e-9):
        return None
    return candidates[0]


def locate_pin(labels, x, y, radius=5, *, direction=None):
    """Resolve a unique nearest region; equal-distance different nets stay unknown."""
    return _unique_nearest(_candidates(labels, x, y, radius, direction))


def _outward_direction(point, bbox):
    if not bbox or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    x, y = point
    if not (x1-3 <= x <= x2+3 and y1-3 <= y <= y2+3):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    edges = sorted([(abs(x-x1), (-1, 0)), (abs(x-x2), (1, 0)),
                    (abs(y-y1), (0, -1)), (abs(y-y2), (0, 1))])
    # Only use a clear nearby edge. Corners/interior contacts carry no direction.
    if edges[0][0] > 3 or edges[1][0] - edges[0][0] <= 1:
        return None
    return edges[0][1]


def attach_pins(circuit, labels, radius=5):
    result = {}
    for component in circuit:
        points = component['connection_points']
        repeated = {point for point, count in Counter(map(tuple, points)).items() if count > 1}
        entries = []
        for point in points:
            direction = _outward_direction(point, component.get('bounding_box', component.get('bbox')))
            alternatives = _candidates(labels, *point, radius, direction)
            chosen = _unique_nearest(alternatives)
            duplicate = tuple(point) in repeated
            if duplicate:
                chosen = None
            entries.append({'image_point': point, 'connection_candidate': chosen,
                'connection_alternatives': alternatives, 'search_direction': list(direction) if direction else None,
                'connection_status': 'duplicate_contact' if duplicate else 'resolved' if chosen else 'ambiguous' if alternatives else 'unresolved'})
        result[component['id']] = entries
    return result
