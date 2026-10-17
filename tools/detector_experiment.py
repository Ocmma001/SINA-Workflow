"""Reproducible resolution sweep: mAP plus saved per-image deployment predictions."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from detector_metrics import score_detections
from training_contract import validate_label

ROOT = Path(__file__).resolve().parent.parent


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def image_files(directory, formats):
    allowed = {'.' + value.lower().lstrip('.') for value in formats}
    return sorted(path for path in directory.rglob('*') if path.is_file() and path.suffix.lower() in allowed)


def summarize(cases, threshold, confidence):
    totals = {'tp': 0, 'fp': 0, 'fn': 0}
    exact, per_class = 0, {}
    for case in cases:
        result = score_detections(case['truth'], case['predictions'], threshold, confidence)
        for key in totals:
            totals[key] += result[key]
        exact += result['fp'] == 0 and result['fn'] == 0 and not case.get('error')
        for cid in range(10):
            score = score_detections([c for c in case['truth'] if c['class'] == cid],
                [c for c in case['predictions'] if c['class'] == cid], threshold, confidence)
            counts = per_class.setdefault(str(cid), {'tp': 0, 'fp': 0, 'fn': 0})
            for key in counts:
                counts[key] += score[key]
    tp, fp, fn = totals['tp'], totals['fp'], totals['fn']
    return dict(totals, precision=tp/(tp+fp) if tp+fp else 0, recall=tp/(tp+fn) if tp+fn else 0,
        f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0, whole_image_correct=exact,
        attempted_images=len(cases), failed_images=sum(bool(c.get('error')) for c in cases), per_class=per_class)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--sizes', type=int, nargs='+', default=[960, 1280, 1536])
    p.add_argument('--device', default='0')
    p.add_argument('--batch', type=int, default=1)
    p.add_argument('--data', type=Path, default=ROOT / 'SINA/Netlist Generator/IC/model_training/data')
    a = p.parse_args()
    if Path(a.name).name != a.name or a.name in {'.', '..'} or min(a.sizes) < 32 or a.batch < 1:
        p.error('invalid name/size/batch')
    if not a.weights.is_file():
        p.error('checkpoint does not exist')
    run = ROOT / 'runs' / a.name
    run.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.ultralytics'))
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.matplotlib'))
    import torch
    import ultralytics
    import yaml
    from PIL import Image, ImageOps
    from ultralytics import YOLO
    from ultralytics.data.utils import IMG_FORMATS
    if a.device != 'cpu' and not torch.cuda.is_available():
        raise RuntimeError('GPU requested but CUDA unavailable')
    data = a.data.resolve()
    config = run / 'dataset.yaml'
    from train_round import NAMES
    config.write_text(yaml.safe_dump({'path': data.as_posix(), 'train': 'images/train',
        'val': 'images/val', 'names': dict(enumerate(NAMES))}), encoding='utf-8')
    inputs = []
    for path in image_files(data / 'images/val', IMG_FORMATS):
        relative = path.relative_to(data / 'images/val')
        label = data / 'labels/val' / relative.with_suffix('.txt')
        with Image.open(path) as image:
            width, height = ImageOps.exif_transpose(image).size
        truth = []
        for line in label.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            cid, (cx, cy, w, h) = validate_label(line)
            truth.append({'class': cid, 'bbox': [(cx-w/2)*width, (cy-h/2)*height,
                                                  (cx+w/2)*width, (cy+h/2)*height]})
        inputs.append({'image': relative.as_posix(), 'image_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'label_sha256': hashlib.sha256(label.read_bytes()).hexdigest(), 'truth': truth})
    if not inputs:
        raise ValueError('No validation images')
    input_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    write_json(run / 'environment.json', {'git_commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'python': sys.version,
        'torch': torch.__version__, 'ultralytics': ultralytics.__version__, 'cuda': torch.version.cuda,
        'gpu': torch.cuda.get_device_name(0) if a.device != 'cpu' else None,
        'weights_sha256': hashlib.sha256(a.weights.read_bytes()).hexdigest(),
        'input_manifest_sha256': input_hash, 'images': len(inputs), 'objects': sum(len(c['truth']) for c in inputs),
        'sizes': a.sizes, 'batch': a.batch, 'device': a.device, 'nms_iou': .7, 'prediction_cache_conf': .05,
        'seed': 42, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'independent_test': False, 'warning': 'Development validation; no OCR, topology or independent test claims.'})
    model = YOLO(str(a.weights.resolve()))
    if len(model.names) != len(NAMES) or [model.names[i] for i in range(10)] != NAMES:
        raise ValueError('Class order mismatch')
    summaries = []
    for size in a.sizes:
        print(f'PHASE size={size} mAP', flush=True)
        if a.device != 'cpu':
            torch.cuda.reset_peak_memory_stats()
        start = time.monotonic()
        result = model.val(data=str(config), split='val', imgsz=size, batch=a.batch,
            device=a.device, workers=0, conf=.001, iou=.7, seed=42, plots=True,
            project=str(run), name=f'val-{size}', exist_ok=False, verbose=False)
        val_seconds = time.monotonic()-start
        directory = run / f'predict-{size}'
        directory.mkdir()
        cases = []
        print(f'PHASE size={size} deployment', flush=True)
        for index, item in enumerate(inputs):
            start = time.monotonic()
            case = dict(item, predictions=[], error=None, prediction_cache_confidence=.05)
            try:
                pred = model.predict(str(data / 'images/val' / item['image']), imgsz=size,
                    device=a.device, conf=.05, iou=.7, verbose=False)[0]
                case['predictions'] = [{'class': int(b.cls.item()), 'confidence': float(b.conf.item()),
                    'bbox': [float(v) for v in b.xyxy[0].tolist()]} for b in pred.boxes]
                case['model_timing_ms'] = pred.speed
            except Exception as exc:
                case['error'] = type(exc).__name__
            case['wall_seconds'] = time.monotonic()-start
            write_json(directory / Path(item['image']).with_suffix('.json'), case)
            cases.append(case)
            if (index+1) % 22 == 0:
                print(f'PROGRESS size={size} images={index+1}/{len(inputs)}', flush=True)
        summary = {'imgsz': size, 'map': {k: float(v) for k, v in result.results_dict.items()},
            'per_class_map50_95': dict(zip(NAMES, [float(v) for v in result.box.maps])),
            'val_seconds': val_seconds, 'prediction_wall_seconds': sum(c['wall_seconds'] for c in cases),
            'prediction_warm_mean_seconds': sum(c['wall_seconds'] for c in cases[3:])/max(1, len(cases)-3),
            'peak_gpu_allocated_bytes': torch.cuda.max_memory_allocated() if a.device != 'cpu' else None,
            'deployment': {str(conf): {str(iou): summarize(cases, iou, conf) for iou in [.5, .75]}
                           for conf in [.15, .25, .35, .5]},
            'predictions_dir': f'predict-{size}'}
        summaries.append(summary)
        write_json(run / 'summary.json', {'input_manifest_sha256': input_hash, 'sizes': summaries,
                                         'independent_test': False})
        print(json.dumps({'imgsz': size, 'map50_95': summary['map']['metrics/mAP50-95(B)'],
            'f1_iou50': summary['deployment']['0.25']['0.5']['f1'],
            'f1_iou75': summary['deployment']['0.25']['0.75']['f1']}, ensure_ascii=False), flush=True)
    print('PHASE complete', flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
