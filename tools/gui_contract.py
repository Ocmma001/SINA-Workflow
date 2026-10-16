"""Pure, portable contract between SINA evidence, editable GUI data and simulation."""
from copy import deepcopy
from collections import Counter
import math
import re
import unicodedata

TYPES = {'Resistor': ('resistor', 'R'), 'Capacitor': ('capacitor', 'C'),
         'Inductor': ('inductor', 'L'), 'Voltage_src': ('voltage_source', 'V'),
         'Current_src': ('current_source', 'I'), 'Diode': ('diode', 'D'),
         'Transistor_BJT': ('bjt', 'Q'), 'Transistor_MOSFET': ('mosfet', 'M'), 'Op-Amp': ('opamp', 'X')}
PREFIXES = {kind: prefix for kind, prefix in TYPES.values()}
PREFIXES.update(led='D', switch='S')
PIN_COUNTS = {'resistor': 2, 'capacitor': 2, 'inductor': 2, 'voltage_source': 2,
              'current_source': 2, 'diode': 2, 'led': 2, 'bjt': 3, 'mosfet': 4, 'opamp': 5, 'switch': 2}
SUPPORTED = {'resistor', 'capacitor', 'inductor', 'voltage_source', 'current_source', 'diode', 'led', 'bjt'}
FIELDS = ('ref', 'type', 'value', 'nodes', 'model', 'waveform')
PIN_ROLES = {'bjt': ['C', 'B', 'E'], 'diode': ['A', 'K'], 'led': ['A', 'K'],
             'voltage_source': ['+', '-'], 'current_source': ['+', '-'], 'mosfet': ['D', 'G', 'S', 'B']}


from modules.text_binding import _spice_number, parse_quantity, assign_text as _local_text


def build_draft(candidates, review=None, artifacts=None):
    evidence = deepcopy(candidates)
    review = review or {}
    items = {c['id']: c for c in review.get('components', [])}
    if set(items) - {c['id'] for c in candidates['components']}:
        raise ValueError('Review contains unknown component IDs')
    warnings = list(review.get('warnings', []))
    warnings += ['识别结果为候选，请核对数值、接地和有方向器件的引脚顺序。']
    ground = set()
    for c in candidates['components']:
        if c['type'].upper() == 'GND':
            ground.update(p['connection_candidate']['region'] for p in c.get('pin_candidates', []) if p.get('connection_candidate'))
    assignments = _local_text(candidates)
    components, used_refs = [], set()
    for c in candidates['components']:
        if c['type'] not in TYPES:
            continue
        kind, prefix = TYPES[c['type']]
        identifier = c['id']
        notes = ['请对照原图核对识别建议。']
        temporary = prefix + '_auto' + identifier.rsplit('_', 1)[-1]
        texts = assignments[identifier]
        ref_options = []
        values = []
        for t in texts:
            normalized = unicodedata.normalize('NFKC', t['text']).replace(' ', '')
            if re.fullmatch(prefix + r'(?:_?[A-Za-z0-9]+)', normalized, re.IGNORECASE):
                ref_options.append((t.get('confidence', 0), normalized))
            parsed = parse_quantity(t['text'], kind)
            if parsed is not None:
                values.append(parsed)
        ref = max(ref_options)[1] if ref_options else temporary
        value = values[0] if len(set(values)) == 1 else None
        advice = items.get(identifier, {})
        if advice.get('ref'):
            ref = advice['ref']
        if advice.get('value') is not None:
            value = parse_quantity(advice['value'], kind)
            if value is None:
                notes.append('复核给出的数值无法转换为数值参数，已保留为空。')
        if not re.fullmatch(prefix + r'[A-Za-z0-9_]*', ref, re.IGNORECASE) or ref.casefold() in used_refs:
            warnings.append(f'{identifier} 的位号冲突或格式错误，已保留暂定位号。')
            ref = temporary
        used_refs.add(ref.casefold())
        if ref == temporary:
            notes.append('位号是临时编号，并非图片已识别事实。')
        if value is None and kind in {'resistor', 'capacitor', 'inductor', 'voltage_source', 'current_source'}:
            notes.append('数值未可靠识别，请补充。')
        pins = c.get('pin_candidates', [])
        regions = [p['connection_candidate']['region'] if p.get('connection_candidate') else None for p in pins]
        nodes = ['0' if r in ground else str(r) for r in regions] if all(r is not None for r in regions) else []
        ordered = []
        if kind in {'resistor', 'capacitor', 'inductor'} and len(nodes) == 2 and len(set(nodes)) == 2:
            ordered = nodes
        semantics = {'bjt': ['C', 'B', 'E'], 'diode': ['A', 'K'],
                     'voltage_source': ['+', '-'], 'current_source': ['+', '-'],
                     'mosfet': ['D', 'G', 'S', 'B']}.get(kind)
        annotations = advice.get('pin_semantics', [])
        index_map = {p['semantic'].upper(): p['candidate_pin_index'] for p in annotations}
        if semantics and len(nodes) == len(semantics) and all(s in index_map for s in semantics):
            indices = [index_map[s] for s in semantics]
            if len(set(indices)) == len(indices) and all(type(i) is int and 0 <= i < len(nodes) for i in indices):
                ordered = [nodes[i] for i in indices]
        if not ordered:
            notes.append('引脚缺失、连接未解决或语义顺序不明确；节点栏留空，候选仍保留在证据中。')
        if kind in PIN_ROLES:
            notes.append('节点栏要求顺序：' + ', '.join(PIN_ROLES[kind]) + '。')
        notes.extend(str(n) for n in advice.get('issues', []))
        components.append({'sina_id': identifier, 'ref': ref, 'type': kind, 'value': value,
            'nodes': ordered, 'model': advice.get('model'), 'waveform': None,
            'bbox': c.get('bbox'), 'confidence': c.get('confidence'),
            'pin_candidates': deepcopy(pins), 'text_candidates': deepcopy(texts),
            'pin_order_confirmed': False, 'needs_user_confirmation': True,
            'pin_order': PIN_ROLES.get(kind, ['1', '2'] if kind in {'resistor', 'capacitor', 'inductor'} else []),
            'simulation_supported': kind in SUPPORTED, 'review_notes': notes,
            'field_status': {f: 'suggested' if (ordered if f == 'nodes' else
                             ref if f == 'ref' else value if f == 'value' else
                             kind if f == 'type' else advice.get(f)) else 'missing' for f in FIELDS}})
    data = {'schema_version': '2.0', 'scope': 'labpilot_circuit_draft',
            'components': components, 'ocr': deepcopy(candidates.get('ocr', [])),
            'recognition': {'source': 'shared SINA / YOLO11m + CCL + EasyOCR',
                'image': candidates.get('image'), 'model_sha256': candidates.get('model_sha256'),
                'inference': deepcopy(candidates.get('inference', {})), 'api_completed': bool(review),
                'user_confirmed': False, 'status': 'needs_review', 'warnings': warnings,
                'ground_regions': sorted(ground), 'detected_count': len(candidates['components']),
                'editable_count': len(components)},
            'evidence': evidence, 'artifacts': artifacts or {}, 'ready_for_simulation': False}
    data['validation'] = {'issues': validation_issues(data)}
    data['topology'] = {'status': 'candidate', 'coordinate_system': 'original_image_pixels',
        'connections': [{'sina_id': c['id'], 'candidate_pin_index': index,
                         'image_point': p['image_point'],
                         'region': p['connection_candidate']['region'] if p.get('connection_candidate') else None}
                        for c in candidates['components'] for index, p in enumerate(c.get('pin_candidates', []))]}
    data['recognition']['warnings'].extend(dict.fromkeys(
        ((issue['ref'] + '：') if issue['ref'] else '') + issue['message']
        for issue in data['validation']['issues']))
    if review.get('missing_components'):
        data['recognition']['warnings'].append('Pro 提出了漏检候选，请对照原图手动添加；未静默改变元件清单。')
        data['recognition']['missing_component_suggestions'] = deepcopy(review['missing_components'])
    return data


def validation_issues(data):
    issues = []
    components = data.get('components', [])
    def add(ref, field, code, message):
        issues.append({'ref': ref, 'field': field, 'code': code, 'message': message})
    if not components:
        add(None, 'components', 'empty', '没有可用元件。')
    seen, ground, source = set(), False, False
    for c in components:
        kind, ref = c.get('type'), str(c.get('ref') or '')
        prefix = PREFIXES.get(kind)
        if not prefix or not re.fullmatch(prefix + r'[A-Za-z0-9_]*', ref, re.IGNORECASE):
            add(ref, 'ref', 'invalid_ref', '位号或元件类型不正确。')
        if ref.casefold() in seen:
            add(ref, 'ref', 'duplicate', '元件位号重复。')
        seen.add(ref.casefold())
        if kind not in SUPPORTED:
            add(ref, 'type', 'unsupported', 'GUI 当前仿真后端暂不支持此类元件，识别结果仍予以保留。')
        ns = c.get('nodes', [])
        if not isinstance(ns, list) or len(ns) != PIN_COUNTS.get(kind) or any(
                type(n) not in {str, int} or not re.fullmatch(r'[A-Za-z0-9_.+-]+', str(n)) for n in ns):
            add(ref, 'nodes', 'pin_count', '节点数量不正确或引脚顺序尚未确定。')
        elif len(set(map(str, ns))) != len(ns) and kind != 'mosfet':
            add(ref, 'nodes', 'duplicate_node', '存在重复连接节点，请核对短接。')
        if isinstance(ns, list):
            ground |= any(str(n).lower() in {'0', 'gnd', 'ground', '0v', 'vss'} for n in ns)
        if kind in {'resistor', 'capacitor', 'inductor', 'voltage_source', 'current_source'}:
            number = '' if c.get('value') is None else str(c['value']).strip()
            numeric = _spice_number(number)
            if numeric is None or (kind in {'resistor', 'capacitor', 'inductor'} and numeric <= 0):
                add(ref, 'value', 'invalid_value', '缺少有效的数值参数。')
        if kind in {'bjt', 'diode', 'led'} and not c.get('model'):
            add(ref, 'model', 'missing_model', '器件型号未确认，不会自动代入默认型号。')
        elif kind in {'bjt', 'diode', 'led'}:
            models = {'bjt': {'2n3904', '2n2222', 'bc547'}, 'diode': {'1n4148', 'led'}, 'led': {'led'}}
            if str(c['model']).strip().lower() not in models[kind]:
                add(ref, 'model', 'unsupported_model', '当前仿真后端没有此型号的可用模型。')
        for field in ('value', 'model', 'waveform'):
            if any(char in str(c.get(field, '')) for char in '\r\n'):
                add(ref, field, 'multiline', '参数只能填写一行。')
        waveform = str(c.get('waveform') or '').strip()
        if waveform:
            match = re.fullmatch(r'(SIN|PULSE)\(([^()\r\n]*)\)', waveform, re.IGNORECASE)
            values = match[2].replace(',', ' ').split() if match else []
            valid_numbers = all(_spice_number(v) is not None for v in values)
            if kind != 'voltage_source' or not match or not valid_numbers or not (
                3 <= len(values) <= 6 and _spice_number(values[2]) > 0 if match[1].upper() == 'SIN' else len(values) == 7):
                add(ref, 'waveform', 'invalid_waveform', '电源激励格式不正确。')
        source |= kind in {'voltage_source', 'current_source'}
    if not ground:
        add(None, 'nodes', 'missing_ground', '未确认接地节点 0。')
    if not source:
        add(None, 'components', 'missing_source', '缺少电源或输入激励，请核对外部供电标记。')
    return issues


def normalize_document(data):
    if data.get('scope') in {'local_sina_candidates', 'component_detection'}:
        return build_draft(data)
    return deepcopy(data)


def update_review_state(data, confirmed):
    data = deepcopy(data)
    metadata = data.setdefault('recognition', {})
    metadata['user_confirmed'] = bool(confirmed)
    issues = validation_issues(data)
    data['validation'] = {'issues': issues}
    data['ready_for_simulation'] = bool(confirmed) and not issues
    data['schema_version'] = '2.0'
    data['scope'] = 'labpilot_confirmed_circuit' if data['ready_for_simulation'] else 'labpilot_circuit_draft'
    metadata['status'] = 'confirmed' if data['ready_for_simulation'] else 'incomplete' if confirmed else 'needs_review'
    if data['ready_for_simulation']:
        data['confirmed_connections'] = [{'ref': c['ref'], 'type': c['type'], 'nodes': deepcopy(c['nodes'])}
                                         for c in data['components']]
    else:
        data.pop('confirmed_connections', None)
    for c in data.get('components', []):
        c['needs_user_confirmation'] = not confirmed
        c['pin_order_confirmed'] = bool(confirmed and len(c.get('nodes', [])) == PIN_COUNTS.get(c.get('type')))
        if 'field_status' in c:
            c['field_status'] = {f: 'confirmed' if confirmed and c.get(f) not in (None, '', []) else
                                 'suggested' if c.get(f) not in (None, '', []) else 'missing' for f in FIELDS}
    return data
