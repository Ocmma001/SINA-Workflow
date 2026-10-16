"""CLI for the group's detector integration; no API or ngspice required."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from training_contract import detection_payload


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--conf', type=float, default=0.25)
    p.add_argument('--imgsz', type=int, default=960)
    args = p.parse_args()
    if not args.image.is_file() or not args.weights.is_file():
        p.error('image and weights must exist')
    if not 0 <= args.conf <= 1 or args.imgsz < 1:
        p.error('invalid confidence or image size')
    if args.out.exists() and any(args.out.iterdir()):
        p.error('use a new output directory')
    root = Path(__file__).resolve().parent.parent
    os.environ.setdefault('YOLO_CONFIG_DIR', str(root / '.ultralytics'))
    from ultralytics import YOLO
    result = YOLO(str(args.weights)).predict(str(args.image), conf=args.conf,
                                            imgsz=args.imgsz, device=args.device,
                                            verbose=False)[0]
    counts = Counter()
    components = []
    for box in result.boxes:
        kind = result.names[int(box.cls.item())]
        counts[kind] += 1
        components.append({'id': f'{kind}_{counts[kind]}', 'type': kind,
                           'bbox': [float(v) for v in box.xyxy[0].tolist()],
                           'confidence': float(box.conf.item())})
    output = detection_payload(args.image.resolve(), components)
    output['model_sha256'] = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    output['inference'] = {'conf': args.conf, 'imgsz': args.imgsz, 'device': args.device}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'detection.json').write_text(json.dumps(output, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    result.save(filename=str(args.out / 'annotated.jpg'))
    print(f'Detected {len(components)} components; output: {args.out.resolve()}')


if __name__ == '__main__':
    main()
