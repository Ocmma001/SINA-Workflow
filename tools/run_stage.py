"""Run an individual offline stage against saved inputs; no GUI or API required."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['detector', 'ocr', 'topology', 'pins', 'contract'])
    p.add_argument('--image', type=Path)
    p.add_argument('--input', type=Path, help='Saved detection.json / topology directory / candidates.json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--weights', type=Path)
    p.add_argument('--device', default='cpu')
    p.add_argument('--imgsz', type=int, default=960)
    p.add_argument('--conf', type=float, default=.25)
    p.add_argument('--radius', type=int, default=5)
    p.add_argument('--ocr-model-dir', type=Path, default=ROOT / 'SINA-venv/easyocr_models')
    p.add_argument('--ocr-min-side', type=int, default=0)
    p.add_argument('--ocr-preprocess', choices=['none','gray','clahe'], default='none')
    p.add_argument('--skip-crossings', action='store_true')
    a = p.parse_args()
    if a.stage in {'detector', 'ocr', 'topology'} and (not a.image or not a.image.is_file()):
        p.error('--image must exist')
    if a.stage in {'topology', 'pins', 'contract'} and (not a.input or not a.input.exists()):
        p.error('--input must exist')
    if not 0 <= a.conf <= 1 or a.imgsz < 1 or a.radius < 0:
        p.error('invalid conf/imgsz/radius')
    if a.out.exists() and any(a.out.iterdir()):
        p.error('use a new output directory')
    a.out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.ultralytics'))
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.matplotlib'))
    if a.stage in {'detector', 'ocr', 'topology'}:
        from modules.image_io import read_image
        image = read_image(a.image)
        digest = hashlib.sha256(a.image.read_bytes()).hexdigest()
        import torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
    weights = a.weights  # Topology now uses frozen boxes, not model inference.
    if a.stage == 'detector':
        from model_selection import selected_weights
        weights = a.weights or selected_weights(ROOT, ROOT / 'runs/round-002/delivery/detector.pt')
    if a.stage == 'detector':
        from modules.detector import detect
        detected, confidences = detect(image, weights, a.out / 'detected.jpg', a.device, a.conf, a.imgsz)
        save(a.out / 'detection.json', {'schema_version': '1.0', 'image_sha256': digest,
             'model_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
             'detector': 'YOLO', 'components': detected, 'confidences': confidences,
             'inference': {'imgsz': a.imgsz, 'conf': a.conf, 'device': a.device}})
    elif a.stage == 'ocr':
        from modules.ocr import recognize
        save(a.out / 'ocr.json', {'image_sha256': digest, 'ocr': recognize(
            image, a.ocr_model_dir, a.out / 'user_network', a.device, min_side=a.ocr_min_side, preprocess=a.ocr_preprocess)})
    elif a.stage == 'topology':
        from modules.topology import analyze
        detected = json.loads(a.input.read_text(encoding='utf-8'))
        if detected['image_sha256'] != digest:
            raise ValueError('Detection image hash mismatch')
        analyze(image, detected['components'], a.out, weights, not a.skip_crossings)
        save(a.out / 'stage.json', {'image_sha256': digest, 'input': str(a.input),
                                  'crossing_detection': not a.skip_crossings})
    elif a.stage == 'pins':
        import numpy as np
        from modules.pins import attach_pins
        circuit = json.loads((a.input / 'circuit_info.json').read_text(encoding='utf-8'))
        save(a.out / 'pins.json', attach_pins(circuit, np.load(a.input / 'node_labels.npy'), a.radius))
    else:
        from gui_contract import build_draft
        save(a.out / 'recognized.json', build_draft(json.loads(a.input.read_text(encoding='utf-8'))))
    print(f'{a.stage}: {a.out.resolve()}')


if __name__ == '__main__':
    main()
