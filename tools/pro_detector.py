"""Direct Ark Pro component localization without YOLO/OCR candidates."""
import argparse
import base64
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import time
from sina_ark_workflow import call_ark
from train_round import NAMES

ROOT = Path(__file__).resolve().parent.parent
MODEL = 'doubao-seed-2-1-pro-260915'
PROMPT = '''你是电路原理图元件目标检测器。只根据本次提供的原始图片检测，不猜测隐藏器件。
检测所有实际绘制的元件符号，包括没有位号的元件，以及所有接地符号。每个符号只输出一次。
允许类别严格限定为：Resistor, Capacitor, Inductor, Transistor_BJT, Transistor_MOSFET,
Voltage_src, Current_src, GND, Op-Amp, Diode。
不要把导线、连接点、跨线、文字标注、供电文字标签当作元件；有真实电源符号才标 Voltage_src/Current_src。
类别由符号形状决定，不由旁边的文本决定。框紧贴元件符号本体，包含本体内的圆圈/箭头，
不包围旁边的编号、数值或型号，也不包围延伸出去的导线，不将多个元件合成一个框。
坐标使用0到1000的归一化坐标，左上角为(0,0)，右下角为(1000,1000)，
bbox格式为[xmin,ymin,xmax,ymax]，按原图宽高分别归一化。
只输出合法JSON，不输出解释或Markdown：
{"components":[{"type":"Resistor","bbox":[100,200,150,300]}]}。
上述坐标只是格式示例，不是检测结果。认真检查小元件、重复元件和边缘处的符号，避免漏检。'''


def validate_detections(data, width, height):
    if not isinstance(data, dict) or not isinstance(data.get('components'), list):
        raise ValueError('Missing components array')
    counts, components = Counter(), []
    for item in data['components']:
        if not isinstance(item, dict) or item.get('type') not in NAMES:
            raise ValueError('Unknown component type')
        box = item.get('bbox')
        if not isinstance(box, list) or len(box) != 4 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            or not 0 <= v <= 1000 for v in box):
            raise ValueError('Invalid normalized box')
        x1, y1, x2, y2 = box
        if x1 >= x2 or y1 >= y2:
            raise ValueError('Empty or reversed box')
        pixels = [round(x1*width/1000), round(y1*height/1000),
                  round(x2*width/1000), round(y2*height/1000)]
        if pixels[0] >= pixels[2] or pixels[1] >= pixels[3]:
            raise ValueError('Box collapses in pixel coordinates')
        kind = item['type']
        counts[kind] += 1
        components.append({'id': f'{kind}_{counts[kind]}', 'type': kind,
                           'bbox': pixels, 'confidence': None})
    return components


def output_format():
    return {'type': 'json_schema', 'name': 'circuit_components', 'strict': True,
            'schema': {'type': 'object', 'properties': {'components': {'type': 'array',
                'items': {'type': 'object', 'properties': {
                    'type': {'type': 'string', 'enum': NAMES},
                    'bbox': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 4, 'maxItems': 4}},
                    'required': ['type', 'bbox'], 'additionalProperties': False}}},
                'required': ['components'], 'additionalProperties': False}}


def detect(image, out):
    from dotenv import load_dotenv
    from PIL import Image, ImageDraw
    load_dotenv(ROOT / '.env', override=False)
    key = os.environ.get('ARK_API_KEY', '').strip()
    if not key:
        raise ValueError('ARK_API_KEY is missing')
    out.mkdir(parents=True, exist_ok=False)
    picture = Image.open(image).convert('RGB')
    width, height = picture.size
    mime = Image.MIME.get(Image.open(image).format)
    if mime not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise ValueError('Unsupported input image format')
    image_url = f'data:{mime};base64,' + base64.b64encode(image.read_bytes()).decode('ascii')
    payload = {'model': MODEL, 'stream': False, 'thinking': {'type': 'disabled'},
               'text': {'format': output_format()},
               'max_output_tokens': 4000, 'input': [{'role': 'user', 'content': [
                   {'type': 'input_text', 'text': PROMPT + f'\n原图尺寸：{width}x{height}像素。'},
                   {'type': 'input_image', 'image_url': image_url}]}]}
    start = time.monotonic()
    raw, metadata = call_ark(payload, key)
    (out / 'raw-response.txt').write_text(raw, encoding='utf-8')
    clean = raw.strip()
    if clean.startswith('```'):
        clean = '\n'.join(clean.splitlines()[1:-1])
    components = validate_detections(json.loads(clean), width, height)
    result = {'schema_version': '1.0', 'scope': 'component_detection',
              'detector': MODEL, 'input': 'original image only; no YOLO or OCR candidates',
              'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
              'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
              'output_format': 'strict JSON schema',
              'size': [width, height], 'components': components,
              'ready_for_simulation': False, 'metadata': metadata,
              'seconds': time.monotonic() - start}
    (out / 'detection.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    draw = ImageDraw.Draw(picture)
    for c in components:
        draw.rectangle(c['bbox'], outline='red', width=max(1, width//700))
        draw.text(tuple(c['bbox'][:2]), c['id'], fill='red')
    picture.save(out / 'detected.jpg')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    result = detect(a.image.resolve(), a.out.resolve())
    print('Direct Pro detection:', len(result['components']), 'components')
