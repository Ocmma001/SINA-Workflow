"""Optional two-stage Pro review. Credentials never enter returned artifacts."""
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def review_candidates(image, output, candidates, config=None):
    from dotenv import load_dotenv
    from sina_ark_workflow import call_ark, load_prompts, build_stage_payload
    from vision_review import build_payload, extract_json, validate_review
    load_dotenv(config or ROOT / '.env', override=False)
    key = os.environ.get('ARK_API_KEY', '').strip()
    if not key:
        raise ValueError('缺少 ARK_API_KEY')
    mime = mimetypes.guess_type(image.name)[0]
    if mime not in {'image/jpeg', 'image/png', 'image/webp'}:
        # GUI accepts BMP locally; encode its pixel data to a supported format for the API.
        import cv2
        import numpy as np
        pixels = cv2.imdecode(np.frombuffer(image.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        ok, encoded = cv2.imencode('.png', pixels)
        if not ok:
            raise ValueError('无法编码图片')
        image_bytes, mime = encoded.tobytes(), 'image/png'
    else:
        image_bytes = image.read_bytes()
    image_url = f'data:{mime};base64,' + base64.b64encode(image_bytes).decode('ascii')
    inventory_prompt, _ = load_prompts()
    inventory, inventory_metadata = call_ark(build_stage_payload(
        'doubao-seed-2-1-pro-260915', 'inventory', inventory_prompt, image_url), key)
    (output / 'sina-inventory.txt').write_text(inventory, encoding='utf-8')
    context = dict(candidates, original_sina_inventory=inventory)
    raw, metadata = call_ark(build_payload('doubao-seed-2-1-pro-260915', image_url, context), key)
    (output / 'vision-response.txt').write_text(raw, encoding='utf-8')
    review = extract_json({'status': 'completed', 'output': [{'type': 'message',
        'content': [{'type': 'output_text', 'text': raw}]}]})
    review = validate_review(review, {c['id'] for c in candidates['components']},
                             {c['id']: len(c['pin_candidates']) for c in candidates['components']})
    review['metadata'] = metadata
    review['inventory_metadata'] = inventory_metadata
    review['inventory_prompt_sha256'] = hashlib.sha256(inventory_prompt.encode()).hexdigest()
    (output / 'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    return review
