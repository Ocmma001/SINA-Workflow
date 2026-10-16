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


def _point(item):
    box = item.get('bbox', [])
    if len(box) != 4:
        return None
    if isinstance(box[0], list):
        return [sum(p[i] for p in box)/4 for i in (0, 1)]
    return [(box[0]+box[2])/2, (box[1]+box[3])/2]


def assign_text(candidates):
    assignments = {c['id']: [] for c in candidates['components']}
    components = [c for c in candidates['components'] if c['type'] in DEVICE_TYPES]
    for item in candidates.get('ocr', []):
        point = _point(item)
        if point is None or not components:
            continue
        def distance(c):
            x1, y1, x2, y2 = c['bbox']
            return math.hypot(max(x1-point[0], 0, point[0]-x2), max(y1-point[1], 0, point[1]-y2))
        chosen = min(components, key=distance)
        assignments[chosen['id']].append(item)
    return assignments


