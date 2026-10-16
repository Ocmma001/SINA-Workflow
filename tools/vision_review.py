"""Review local SINA candidates with Ark Responses; credentials stay local."""
import argparse
import base64
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_payload(model, image_url, candidates):
    prompt = '''你是电路原理图复核助手。根据原图和本地识别候选复核元件位号、参数、类型及引脚语义。
仅输出合法 JSON，不输出 Markdown。不得依据常识填入图片没有标注的数值或器件型号。
原图只有 R_C、U_CC 等符号时保留符号；没有具体数值则 value=null。
图像坐标原点在左上角；通过 bbox 识别每个候选，id 必须与输入完全一致。不要将别的元件位号分配给此 id。
连接只是候选，不得假定已确认。无法判断的内容写 null 并加入 issues。
格式：{"components":[{"id":"输入id","ref":null,"value":null,"model":null,
"type":"候选类型","pin_semantics":[],"confidence":0.0,"issues":[]}],
"missing_components":[],"warnings":[]}。
pin_semantics 每项为 {"candidate_pin_index":0,"semantic":"B/C/E等","confidence":0.0}，只有清晰时填写。
新增漏检元件放 missing_components，不要混入 components。所有结果必须经用户确认。
本地候选：
''' + json.dumps(candidates, ensure_ascii=False)
    return {'model': model, 'stream': False, 'max_output_tokens': 3500,
            'thinking': {'type': 'disabled'},
            'input': [{'role': 'user', 'content': [
                {'type': 'input_text', 'text': prompt},
                {'type': 'input_image', 'image_url': image_url}]}]}


def extract_json(response):
    if response.get('status') != 'completed':
        raise ValueError('Model response did not complete; no review was adopted')
    text = ''.join(part.get('text', '') for item in response.get('output', [])
                   if item.get('type') == 'message'
                   for part in item.get('content', []) if part.get('type') == 'output_text').strip()
    if text.startswith('```'):
        lines = text.splitlines()
        text = '\n'.join(lines[1:-1])
    return json.loads(text)


def validate_review(review, known_ids, pin_counts=None):
    if not isinstance(review, dict) or not isinstance(review.get('components'), list):
        raise ValueError('Review must contain a components array')
    seen = set()
    for c in review['components']:
        if not isinstance(c, dict) or c.get('id') not in known_ids or c['id'] in seen:
            raise ValueError('Unknown, duplicate, or malformed component in model output')
        seen.add(c['id'])
        for field in ('ref', 'value', 'model', 'type'):
            if c.get(field) is not None and not isinstance(c[field], str):
                raise ValueError('Component text fields must be strings or null')
        confidence = c.get('confidence')
        if confidence is not None and (not isinstance(confidence, (int, float)) or
                                       not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError('Invalid model confidence')
        pins = c.get('pin_semantics', [])
        if not isinstance(pins, list):
            raise ValueError('pin_semantics must be an array')
        pin_indices = set()
        for pin in pins:
            if not isinstance(pin, dict):
                raise ValueError('Malformed pin annotation')
            index = pin.get('candidate_pin_index')
            if type(index) is not int or index < 0 or index in pin_indices:
                raise ValueError('Invalid or duplicate pin index')
            if pin_counts is not None and index >= pin_counts[c['id']]:
                raise ValueError('Pin index outside local evidence')
            if not isinstance(pin.get('semantic'), str):
                raise ValueError('Pin semantic must be text')
            pc = pin.get('confidence')
            if pc is not None and (not isinstance(pc, (int, float)) or
                                   not math.isfinite(pc) or not 0 <= pc <= 1):
                raise ValueError('Invalid pin confidence')
            pin_indices.add(index)
        c['needs_user_confirmation'] = True
    review['ready_for_simulation'] = False
    review['unreviewed_ids'] = sorted(known_ids - seen)
    return review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--config', type=Path, default=ROOT / '.env')
    p.add_argument('--prompt-mode', choices=('sina', 'review'), default='sina',
                   help='sina: original two-stage prompts; review: previous custom review prompt')
    p.add_argument('--raw-netlist', type=Path, help='Optional upstream netlist_structure.txt')
    p.add_argument('--netlist-image', action='store_true',
                   help='Attach image to stage2 as supported by the original SINA function')
    p.add_argument('--inventory-file', type=Path,
                   help='Reuse a previous API_first_response.txt for a stage2 comparison')
    p.add_argument('--ocr-context', choices=('boxes', 'legacy'), default='boxes',
                   help='boxes: current layout evidence; legacy: previous text-only input for comparison')
    args = p.parse_args()
    if not args.image.is_file() or not args.candidates.is_file():
        p.error('Image and candidate JSON must exist')
    if args.out.exists() and any(args.out.iterdir()):
        p.error('Use a new output directory')
    if args.prompt_mode == 'sina':
        if args.out.exists():
            p.error('For SINA mode, use an output directory that does not yet exist')
        from sina_ark_workflow import run_aligned
        run_aligned(args)
        return
    from dotenv import load_dotenv
    import requests
    load_dotenv(args.config, override=False)
    key = os.environ.get('ARK_API_KEY', '').strip()
    if not key:
        p.error('Set ARK_API_KEY in the local configuration')
    model = os.environ.get('ARK_MODEL', 'doubao-seed-2-1-lite-260915')
    url = os.environ.get('ARK_RESPONSES_URL', 'https://ark.cn-beijing.volces.com/api/v3/responses')
    # Prevent sending credentials to a mistyped or unrelated endpoint.
    if url != 'https://ark.cn-beijing.volces.com/api/v3/responses':
        p.error('This adapter only supports the official Beijing Ark Responses endpoint')
    candidates = json.loads(args.candidates.read_text(encoding='utf-8'))
    if not isinstance(candidates.get('components'), list):
        p.error('Candidate JSON lacks components')
    compact = {'components': [{k: c.get(k) for k in
                               ('id', 'type', 'bbox', 'pin_candidates', 'text_candidates')}
                              for c in candidates['components']],
               'ocr': candidates.get('ocr', [])}
    mime = mimetypes.guess_type(args.image.name)[0]
    if mime not in {'image/jpeg', 'image/png', 'image/webp'}:
        p.error('Expected JPEG, PNG, or WebP')
    image_bytes = args.image.read_bytes()
    image_url = f'data:{mime};base64,' + base64.b64encode(image_bytes).decode('ascii')
    try:
        response = requests.post(url, headers={'Authorization': 'Bearer ' + key,
                                              'Content-Type': 'application/json'},
                                 json=build_payload(model, image_url, compact), timeout=(15, 120))
    except requests.RequestException:
        raise SystemExit('Ark connection failed or timed out; no result was adopted') from None
    if not response.ok:
        code = 'unknown'
        try:
            code = str(response.json().get('error', {}).get('code', 'unknown'))[:100]
        except (ValueError, AttributeError):
            pass
        raise SystemExit(f'Ark HTTP {response.status_code}; error code={code.replace(key, "[redacted]")}')
    raw = response.json()
    known_ids = {c['id'] for c in candidates['components']}
    pin_counts = {c['id']: len(c.get('pin_candidates', [])) for c in candidates['components']}
    review = validate_review(extract_json(raw), known_ids, pin_counts)
    # Keep the original local evidence unchanged; review is a separate layer.
    result = {'schema_version': '1.0', 'scope': 'vision_review_candidates',
              'ready_for_simulation': False, 'model': model,
              'image_sha256': hashlib.sha256(image_bytes).hexdigest(),
              'candidate_sha256': hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
              'review': review, 'usage': raw.get('usage', {}),
              'response_id': raw.get('id'), 'status': raw.get('status')}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'vision-review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                               encoding='utf-8')
    print('Ark image review completed; reviewed components:', len(review['components']))
    print('Usage:', json.dumps(result['usage']))
    print('Result:', (args.out / 'vision-review.json').resolve())


if __name__ == '__main__':
    main()
