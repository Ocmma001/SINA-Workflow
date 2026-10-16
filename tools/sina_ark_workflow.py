"""Ark adapter for SINA's verbatim original inventory and netlist prompts."""
import base64
from collections import Counter
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def load_prompts():
    paths = ROOT / 'prompts'
    return tuple((paths / name).read_text(encoding='utf-8') for name in
                 ('sina_inventory.txt', 'sina_named_netlist.txt'))


def build_stage_payload(model, stage, prompt, image_url=None):
    content = [{'type': 'input_text', 'text': prompt}]
    if image_url is not None:
        content.append({'type': 'input_image', 'image_url': image_url})
    return {'model': model, 'stream': False, 'thinking': {'type': 'disabled'},
            'max_output_tokens': 1800 if stage == 'inventory' else 1500,
            'input': [{'role': 'user', 'content': content}]}


def raw_structure(candidates):
    ground = set()
    for c in candidates['components']:
        if c['type'].upper() == 'GND':
            for pin in c.get('pin_candidates', []):
                connection = pin.get('connection_candidate')
                if connection:
                    ground.add(int(connection['region']))
    lines = []
    for c in candidates['components']:
        if c['type'].upper() == 'GND':
            continue
        pins = c.get('pin_candidates', [])
        if not pins or any(not p.get('connection_candidate') for p in pins):
            raise ValueError(f"{c['id']}: unresolved topology; confirm connections first")
        regions = [int(p['connection_candidate']['region']) for p in pins]
        nodes = [0 if r in ground else r for r in regions]
        lines.append(c['id'] + ' ' + ' '.join(map(str, nodes)))
    return lines


def response_text(raw):
    if raw.get('status') != 'completed':
        raise ValueError('Incomplete Ark response; do not adopt the output')
    result = ''.join(p.get('text', '') for item in raw.get('output', [])
                     if item.get('type') == 'message'
                     for p in item.get('content', []) if p.get('type') == 'output_text').strip()
    if not result:
        raise ValueError('Empty Ark response')
    return result


def call_ark(payload, key):
    import requests
    try:
        response = requests.post('https://ark.cn-beijing.volces.com/api/v3/responses',
                                 headers={'Authorization': 'Bearer ' + key,
                                          'Content-Type': 'application/json'},
                                 json=payload, timeout=(15, 120))
    except requests.RequestException:
        raise SystemExit('Ark connection failed or timed out') from None
    if not response.ok:
        try:
            code = str(response.json().get('error', {}).get('code', 'unknown'))[:100]
        except (ValueError, AttributeError):
            code = 'unknown'
        raise SystemExit(f'Ark HTTP {response.status_code}; code={code.replace(key, "[redacted]")}')
    raw = response.json()
    return response_text(raw), {'response_id': raw.get('id'), 'usage': raw.get('usage', {}),
                                'status': raw.get('status')}


def audit_netlist(raw_lines, draft):
    issues = []
    if not any(line.strip().lower() == '.end' for line in draft.splitlines()):
        issues.append('Missing .end directive')
    prefixes = {'Resistor': 'R', 'Capacitor': 'C', 'Inductor': 'L', 'Voltage_src': 'V',
                'Current_src': 'I', 'Transistor_BJT': 'Q', 'Transistor_MOSFET': 'M',
                'Op-Amp': 'X', 'Diode': 'D'}
    expected, actual = Counter(), Counter()
    for line in raw_lines:
        tokens = line.split()
        if not tokens or tokens[0].startswith(('*', '.')):
            continue
        prefix = next((v for k, v in prefixes.items() if tokens[0].startswith(k + '_')), None)
        if prefix:
            expected[(prefix, tuple(tokens[1:]))] += 1
    sizes = {'R': 2, 'C': 2, 'L': 2, 'V': 2, 'I': 2, 'D': 2, 'Q': 3, 'M': 4, 'X': 5}
    for line in draft.splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith(('*', '.')) or tokens[0] == 'GROUND_NODE:':
            continue
        prefix = tokens[0][0].upper()
        if prefix in sizes:
            n = sizes[prefix]
            actual[(prefix, tuple(tokens[1:1 + n]))] += 1
            if len(tokens) <= 1 + n:
                issues.append(f'{tokens[0]}: missing value or model')
    if actual != expected:
        issues.append('Node connectivity or component count changed; reject automatic adoption')
    return issues


def ocr_context(candidates, include_boxes=True):
    if not include_boxes:
        return {'ocr': candidates.get('ocr', []),
                'by_component': {c['id']: c.get('text_candidates', [])
                                 for c in candidates['components']}}
    return {'coordinate_system': 'original image pixels; origin at top-left',
            'ocr': candidates.get('ocr', []),
            'by_component': {c['id']: {'bbox': c.get('bbox'),
                                      'ocr_candidates': c.get('text_candidates', [])}
                             for c in candidates['components']}}


def run_aligned(args):
    from dotenv import load_dotenv
    load_dotenv(args.config, override=False)
    key = os.environ.get('ARK_API_KEY', '').strip()
    if not key:
        raise SystemExit('Set ARK_API_KEY in local configuration')
    if os.environ.get('ARK_RESPONSES_URL', 'https://ark.cn-beijing.volces.com/api/v3/responses') != 'https://ark.cn-beijing.volces.com/api/v3/responses':
        raise SystemExit('Only the official Beijing Ark endpoint is supported')
    model = os.environ.get('ARK_MODEL', 'doubao-seed-2-1-pro-260915')
    candidates = json.loads(args.candidates.read_text(encoding='utf-8'))
    supplied_raw = getattr(args, 'raw_netlist', None)
    raw_lines = supplied_raw.read_text(encoding='utf-8').splitlines() if supplied_raw else raw_structure(candidates)
    first, second_template = load_prompts()
    mime = mimetypes.guess_type(args.image.name)[0]
    if mime not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise SystemExit('Expected JPEG, PNG, or WebP')
    image_bytes = args.image.read_bytes()
    image_url = f'data:{mime};base64,' + base64.b64encode(image_bytes).decode('ascii')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'raw-netlist.txt').write_text('\n'.join(raw_lines) + '\n', encoding='utf-8')
    print('SINA stage 1: original symbol inventory prompt', flush=True)
    inventory_file = getattr(args, 'inventory_file', None)
    if inventory_file:
        inventory = inventory_file.read_text(encoding='utf-8')
        stage1 = {'status': 'reused', 'source': str(inventory_file),
                  'usage': {}, 'sha256': hashlib.sha256(inventory.encode()).hexdigest()}
    else:
        inventory, stage1 = call_ark(build_stage_payload(model, 'inventory', first, image_url), key)
    (args.out / 'API_first_response.txt').write_text(inventory, encoding='utf-8')
    # Keep all label names, including underscores. The original regex drops such labels.
    label_lines = [re.sub(r'^\(.*?\)', '', line).strip()
                   for line in inventory.splitlines() if re.search(r'\)\s*[^:\n]+:', line)]
    include_boxes = getattr(args, 'ocr_context', 'boxes') == 'boxes'
    ocr_text = json.dumps(ocr_context(candidates, include_boxes), ensure_ascii=False)
    prompt2 = second_template.replace('__RAW_NETLIST__', '\n'.join(raw_lines))
    prompt2 = prompt2.replace('__COMPONENT_LABEL_TEXT__', '\n'.join(label_lines)).replace('__OCR_TEXT__', ocr_text)
    attach_image = getattr(args, 'netlist_image', False)
    print(f'SINA stage 2: original label/value/netlist prompt (image={attach_image})', flush=True)
    draft, stage2 = call_ark(build_stage_payload(model, 'netlist', prompt2,
                                               image_url if attach_image else None), key)
    (args.out / 'named-netlist-response.txt').write_text(draft, encoding='utf-8')
    lines = draft.splitlines()
    if lines and lines[0].strip().startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith('```'):
        lines = lines[:-1]
    ground = next((line.split(':', 1)[1].strip() for line in lines
                   if line.strip().startswith('GROUND_NODE:')), None)
    # Keep original node IDs; do not automatically apply the suggested ground remap.
    netlist = '\n'.join(line for line in lines if not line.strip().startswith('GROUND_NODE:'))
    (args.out / 'sina-draft.cir').write_text(netlist + '\n', encoding='utf-8')
    type_counts = Counter(c['type'] for c in candidates['components'] if c['type'] != 'GND')
    result = {'schema_version': '1.0', 'scope': 'sina_original_prompt_candidates',
              'ready_for_simulation': False, 'model': model,
              'image_sha256': hashlib.sha256(image_bytes).hexdigest(),
              'candidate_sha256': hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
              'prompt_hashes': {'inventory': hashlib.sha256(first.encode()).hexdigest(),
                                'netlist_template': hashlib.sha256(second_template.encode()).hexdigest()},
              'raw_topology_source': str(supplied_raw) if supplied_raw else 'local CCL candidates, explicit GND region -> 0, pin order unchanged',
              'local_component_counts_excluding_ground': dict(type_counts),
              'netlist_stage_image_attached': attach_image,
              'ocr_context_has_component_boxes': include_boxes,
              'netlist_validation_issues': audit_netlist(raw_lines, netlist),
              'ground_node_suggestion': ground, 'stage1': stage1, 'stage2': stage2,
              'warnings': ['Original stage1 excludes GND and unlabelled symbols; counts are not the YOLO total.',
                           'Original stage2 may add generic transistor models and MOSFET bulk nodes. These are assumptions, not recognized device facts.',
                           'Unknown values may be omitted by the original prompt. This draft is not guaranteed simulation-ready.',
                           'Original prompts retained verbatim, including their ambiguities; human confirmation remains required.']}
    (args.out / 'sina-ark-result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Original-prompt SINA workflow completed; draft requires confirmation.', flush=True)
    print('Stage1 usage:', json.dumps(stage1['usage']), flush=True)
    print('Stage2 usage:', json.dumps(stage2['usage']), flush=True)
    print('Result:', args.out.resolve(), flush=True)
