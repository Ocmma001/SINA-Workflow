"""Reproducible baseline -> fine-tune -> compare. Does not overwrite upstream."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from training_contract import validate_label

ROOT = Path(__file__).resolve().parent.parent
NAMES = ['Resistor', 'Capacitor', 'Inductor', 'Transistor_BJT', 'Transistor_MOSFET',
         'Voltage_src', 'Current_src', 'GND', 'Op-Amp', 'Diode']


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def evaluate(weight, config, directory, name, args):
    from ultralytics import YOLO
    result = YOLO(str(weight)).val(data=str(config), split='val', imgsz=args.imgsz,
                                  batch=args.batch, device=args.device, workers=0,
                                  project=str(directory), name=name, exist_ok=False,
                                  conf=0.001, iou=0.7, plots=True, verbose=False)
    return {
        'weight': str(weight), 'metrics': {k: float(v) for k, v in result.results_dict.items()},
        'per_class_map50_95': {NAMES[i]: float(v) for i, v in enumerate(result.box.maps)},
        'save_dir': str(result.save_dir),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', default='round-001')
    p.add_argument('--epochs', type=int, default=40)
    p.add_argument('--imgsz', type=int, default=960)
    p.add_argument('--batch', type=int, default=8)
    p.add_argument('--device', default='0')
    p.add_argument('--initial', type=Path, help='Alternative pretrained candidate checkpoint')
    p.add_argument('--baseline', type=Path, help='Existing circuit detector to compare against')
    p.add_argument('--lr0', type=float, default=0.0002)
    p.add_argument('--patience', type=int, default=10)
    p.add_argument('--mosaic', type=float, default=0.2, help='Mosaic augmentation probability; zero disables it')
    p.add_argument('--warmup-bias-lr', type=float, default=0.1,
                   help='Bias learning-rate warmup starting value; zero avoids the high-bias-lr warmup')
    p.add_argument('--freeze', type=int, default=0, help='Number of initial model layers whose parameters are frozen')
    args = p.parse_args()
    if Path(args.name).name != args.name or args.name in {'.', '..'}:
        p.error('name must be a single directory name')
    if min(args.epochs, args.imgsz, args.batch) < 1:
        p.error('epochs/imgsz/batch must be positive')
    if not 0 <= args.mosaic <= 1:
        p.error('mosaic must be between 0 and 1')
    if not math.isfinite(args.warmup_bias_lr) or args.warmup_bias_lr < 0:
        p.error('warmup bias learning rate must be finite and nonnegative')
    if args.freeze < 0:
        p.error('freeze must be nonnegative')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.ultralytics'))
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.matplotlib'))
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    import torch
    import ultralytics
    import yaml
    from ultralytics import YOLO
    if args.device != 'cpu' and not torch.cuda.is_available():
        raise RuntimeError('Requested GPU is not available')
    source = ROOT / 'SINA/Netlist Generator/IC'
    data = source / 'model_training/data'
    initial = args.initial.resolve() if args.initial else source / 'current_trained_model/train/weights/best.pt'
    baseline_weight = args.baseline.resolve() if args.baseline else initial
    if not initial.is_file() or not baseline_weight.is_file():
        p.error('Initial and baseline checkpoints must exist')
    for split in ('train', 'val'):
        images = list((data / 'images' / split).glob('*.jpg'))
        if not images:
            raise ValueError(f'Missing images: {split}')
        for image in images:
            label = data / 'labels' / split / (image.stem + '.txt')
            for line in label.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    validate_label(line)
    run = ROOT / 'runs' / args.name
    run.mkdir(parents=True, exist_ok=False)
    config = run / 'dataset.yaml'
    config.write_text(yaml.safe_dump({'path': data.as_posix(), 'train': 'images/train',
                                     'val': 'images/val', 'names': dict(enumerate(NAMES))}),
                      encoding='utf-8')
    environment = {'python': sys.version, 'torch': torch.__version__,
                   'ultralytics': ultralytics.__version__, 'platform': platform.platform(),
                   'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                   'cuda': torch.version.cuda, 'args': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                   'initial_sha256': hashlib.sha256(initial.read_bytes()).hexdigest(),
                   'started_utc': datetime.now(timezone.utc).isoformat(),
                   'evaluation_limit': 'Upstream validation set; not independent test data.'}
    write_json(run / 'environment.json', environment)
    print('PHASE baseline', flush=True)
    baseline = evaluate(baseline_weight, config, run, 'baseline-val', args)
    write_json(run / 'baseline.json', baseline)
    print('PHASE train', flush=True)
    model = YOLO(str(initial))
    model.train(data=str(config), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                device=args.device, workers=0, seed=42, deterministic=True, freeze=args.freeze,
                project=str(run), name='finetune', exist_ok=False,
                optimizer='AdamW', lr0=args.lr0, lrf=0.1, patience=args.patience,
                warmup_epochs=2, warmup_bias_lr=args.warmup_bias_lr,
                cos_lr=True, weight_decay=0.0005,
                mosaic=args.mosaic, close_mosaic=5, mixup=0.0, degrees=0.0,
                fliplr=0.0, flipud=0.0, hsv_h=0.0, hsv_s=0.0, hsv_v=0.15,
                scale=0.15, translate=0.05, amp=True, cache=False, plots=True,
                save=True, save_period=10)
    candidate_path = Path(model.trainer.save_dir) / 'weights/best.pt'
    print('PHASE candidate evaluation', flush=True)
    candidate = evaluate(candidate_path, config, run, 'candidate-val', args)
    write_json(run / 'candidate.json', candidate)
    key = 'metrics/mAP50-95(B)'
    improved = candidate['metrics'][key] > baseline['metrics'][key]
    selected = candidate_path if improved else baseline_weight
    bundle = run / 'delivery'
    bundle.mkdir()
    shutil.copy2(selected, bundle / 'detector.pt')
    write_json(bundle / 'classes.json', dict(enumerate(NAMES)))
    summary = {'baseline': baseline, 'candidate': candidate,
               'candidate_improved_map50_95': improved, 'selected_source': str(selected),
               'selected_sha256': hashlib.sha256(selected.read_bytes()).hexdigest(),
               'scope': 'component detection only',
               'warning': 'Validation reference only. OCR/topology and independent generalization unverified.'}
    write_json(run / 'comparison.json', summary)
    write_json(bundle / 'model-card.json', summary)
    print('PHASE complete', flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
