"""OCR quantities and exclusive text-to-symbol assignment; no model dependencies."""
import math
import re
import unicodedata
DEVICE_TYPES = {'Resistor', 'Capacitor', 'Inductor', 'Voltage_src', 'Current_src',
                'Diode', 'Transistor_BJT', 'Transistor_MOSFET', 'Op-Amp'}

def _spice_number(value):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(t|g|meg|k|m|u|n|p|f)?', str(value).strip(), re.IGNORECASE)
    if not match:
        return None
    scales = {'': 1, 't': 1e12, 'g': 1e9, 'meg': 1e6, 'k': 1e3, 'm': 1e-3,
              'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15}
    number = float(match[1]) * scales[(match[2] or '').lower()]
    return number if math.isfinite(number) else None


def parse_quantity(text, kind):
    text = unicodedata.normalize('NFKC', str(text)).replace('µ', 'u').replace('μ', 'u')
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[kKmMuUnNpPfF]?)\s*([A-Za-zΩΩ]*)', text.strip())
    if not match:
        return None
    value, scale, unit = match.groups()
    units = {'resistor': {'', 'ω', 'Ω', 'ohm', 'ohms'}, 'capacitor': {'', 'f'},
             'inductor': {'', 'h'}, 'voltage_source': {'', 'v'}, 'current_source': {'', 'a'}}
    if kind == 'capacitor' and scale in {'f', 'F'} and not unit:
        scale, unit = '', 'F'
    if unit.lower() not in units.get(kind, set()):
        return None
    if not math.isfinite(float(value)):
        return None
    if scale == 'M':
        scale = 'meg'
    return value + scale.lower()


def _rect(item):
    box = item.get('bbox', [])
    try:
        if len(box) != 4:
            return None
        if isinstance(box[0], (list, tuple)):
            xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
            rect = (min(xs), min(ys), max(xs), max(ys))
        else:
            rect = tuple(float(v) for v in box)
        if not all(math.isfinite(v) for v in rect) or rect[2] <= rect[0] or rect[3] <= rect[1]:
            return None
        return rect
    except (TypeError, ValueError, IndexError):
        return None


def _eligible_types(text):
    ref = re.fullmatch(r'([RCLVIDQM])_?(?:[0-9]+[A-Za-z]?|[A-Za-z])', str(text).strip(), re.IGNORECASE)
    if ref:
        return {'R': {'Resistor'}, 'C': {'Capacitor'}, 'L': {'Inductor'},
                'V': {'Voltage_src'}, 'I': {'Current_src'}, 'D': {'Diode'},
                'Q': {'Transistor_BJT'}, 'M': {'Transistor_MOSFET'}}[ref[1].upper()]
    kinds = {'Resistor':'resistor', 'Capacitor':'capacitor', 'Inductor':'inductor',
             'Voltage_src':'voltage_source', 'Current_src':'current_source'}
    valid = {name for name, kind in kinds.items() if parse_quantity(text, kind) is not None}
    # A bare number can be a pin/annotation, so it must not migrate away
    # from the geometrically closest transistor just to find a parseable value.
    return valid if valid and re.search(r'[A-Za-zΩΩµμ]', str(text)) else DEVICE_TYPES


def analyze_text_bindings(candidates, *, min_confidence=.5):
    """Exclusive bounded assignment with explicit evidence for rejected text."""
    assignments = {c['id']: [] for c in candidates['components']}
    components = [(c, _rect(c)) for c in candidates['components'] if c['type'] in DEVICE_TYPES]
    diagnostics = []
    for index, item in enumerate(candidates.get('ocr', [])):
        rect = _rect(item)
        record = {'ocr_index': index, 'status': 'unassigned', 'component_id': None}
        if rect is None:
            record['status'] = 'invalid_box'
            diagnostics.append(record)
            continue
        try:
            confidence = float(item.get('confidence', 0))
        except (TypeError, ValueError):
            confidence = float('nan')
        if not math.isfinite(confidence) or not min_confidence <= confidence <= 1:
            record['status'] = 'low_confidence'
            diagnostics.append(record)
            continue
        px, py = (rect[0]+rect[2])/2, (rect[1]+rect[3])/2
        text_height = rect[3]-rect[1]
        allowed = _eligible_types(item.get('text', ''))
        ranked = []
        for component, bbox in components:
            if bbox is None or component['type'] not in allowed:
                continue
            x1,y1,x2,y2 = bbox
            dx,dy = max(x1-px,0,px-x2),max(y1-py,0,py-y2)
            distance = math.hypot(dx,dy)
            limit = max(12.0, 3*text_height, .75*min(x2-x1,y2-y1))
            if distance > limit:
                continue
            score = distance + (.25*min(text_height,x2-x1,y2-y1) if dx and dy else 0)
            ranked.append((score, component['id'], distance))
        ranked.sort()
        record['alternatives'] = [{'component_id': cid, 'score': score, 'distance_pixels': distance}
                                  for score,cid,distance in ranked[:2]]
        if ranked:
            best = ranked[0]
            ambiguous = len(ranked)>1 and ranked[1][0]-best[0] <= max(1,.25*text_height) and ranked[1][0] <= best[0]*1.15+1
            if ambiguous:
                record['status'] = 'ambiguous'
            else:
                assignments[best[1]].append(item)
                record.update(status='assigned', component_id=best[1], distance_pixels=best[2])
        diagnostics.append(record)
    return {'assignments': assignments, 'diagnostics': diagnostics}


def assign_text(candidates):
    return analyze_text_bindings(candidates)['assignments']
