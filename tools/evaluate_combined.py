"""Evaluate fixed teammate thresholds with three checkpoints on the development split."""
import hashlib
import argparse
import json
from pathlib import Path
import time
from evaluate_detector_options import score, combine
from paired_detection_bootstrap import paired_bootstrap
from modules.detector import predict_records
from modules.image_io import read_image
from train_round import NAMES

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-mosaic-weights', type=Path, required=True)
    parser.add_argument('--warmup0-weights', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT/'runs/combined-20261017')
    args = parser.parse_args()
    import torch
    torch.set_num_threads(4)
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    data = ROOT / 'SINA/Netlist Generator/IC/model_training/data'
    thresholds = json.loads((ROOT/'experiments/candidates/member-a-class-thresholds.json').read_text())
    profiles = [
        ('baseline', ROOT/'runs/round-002/delivery/detector.pt', None),
        ('member', ROOT/'runs/round-002/delivery/detector.pt', thresholds),
        ('combined-no-mosaic', args.no_mosaic_weights, thresholds),
        ('combined-warmup0', args.warmup0_weights, thresholds),
    ]
    summary = {'scope':'66 development images used for tuning; not independent test accuracy',
               'thresholds_fixed_before_this_run':thresholds, 'profiles':{}}
    baseline = None
    for name, weights, class_conf in profiles:
        rows = []
        frozen = []
        for path in sorted((data/'images/val').glob('*.jpg')):
            image = read_image(path)
            h,w = image.shape[:2]
            label = data/'labels/val'/(path.stem+'.txt')
            truth = []
            for line in label.read_text().splitlines():
                if not line.strip(): continue
                kind,cx,cy,bw,bh = map(float,line.split())
                truth.append((NAMES[int(kind)],[(cx-bw/2)*w,(cy-bh/2)*h,(cx+bw/2)*w,(cy+bh/2)*h]))
            start = time.perf_counter()
            failure = None
            try:
                predictions = predict_records(image,weights,'0',.25,960,class_conf=class_conf)
            except Exception as exc:
                failure = repr(exc)
                predictions = []
            record = {'image':path.name,'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'label_sha256':hashlib.sha256(label.read_bytes()).hexdigest(),
                      'gt':truth,'predictions':predictions,'failure':failure,'seconds':time.perf_counter()-start}
            frozen.append(record)
            rows.append({k:record[k] for k in ('image','image_sha256','label_sha256','failure')} |
                        {'iou50':score(truth,predictions,.5),'iou75':score(truth,predictions,.75)})
        if baseline is None: baseline = rows
        assert [(r['image'],r['image_sha256'],r['label_sha256']) for r in rows] == [(r['image'],r['image_sha256'],r['label_sha256']) for r in baseline]
        result = {'weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),
                  'images':len(rows),'objects':sum(len(r['gt']) for r in frozen),
                  'failures':sum(bool(r['failure']) for r in rows),
                  'iou50':combine(rows,'iou50'),'iou75':combine(rows,'iou75'),
                  'paired':paired_bootstrap(baseline,rows)}
        summary['profiles'][name] = result
        (out/(name+'-predictions.json')).write_text(json.dumps(frozen,indent=2))
        (out/(name+'-counts.json')).write_text(json.dumps(rows,indent=2))
        (out/'summary.json').write_text(json.dumps(summary,indent=2))
        print(name,json.dumps(result),flush=True)


if __name__ == '__main__': main()
