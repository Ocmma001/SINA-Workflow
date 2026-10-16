"""Paired YOLO11m / direct Pro detection evaluation using human bounding boxes."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
from pro_detector import detect, ROOT
from train_round import NAMES


def iou(a, b):
    inter = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0


def score(predicted, truth, threshold=0.5):
    pairs = sorted([(iou(p['bbox'], g['bbox']), pi, gi)
                    for pi, p in enumerate(predicted) for gi, g in enumerate(truth)
                    if p['type'] == g['type']], reverse=True)
    used_p, used_g = set(), set()
    for overlap, pi, gi in pairs:
        if overlap >= threshold and pi not in used_p and gi not in used_g:
            used_p.add(pi)
            used_g.add(gi)
    return {'tp': len(used_p), 'fp': len(predicted)-len(used_p), 'fn': len(truth)-len(used_g),
            'whole_image_correct': len(used_p) == len(truth) == len(predicted)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True)
    a = p.parse_args()
    if Path(a.name).name != a.name or a.name in {'.', '..'}:
        p.error('Invalid run name')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.ultralytics'))
    from dotenv import load_dotenv
    from PIL import Image
    from ultralytics import YOLO
    load_dotenv(ROOT / '.env')
    out = ROOT / 'runs' / a.name
    out.mkdir(parents=True, exist_ok=False)
    data = ROOT / 'SINA/Netlist Generator/IC/model_training/data'
    images = sorted((data / 'images/val').glob('*.jpg'))
    model = YOLO(str(ROOT / 'runs/round-002/delivery/detector.pt'))
    cases = []
    for image in images:
        w, h = Image.open(image).size
        truth = []
        for line in (data / 'labels/val' / (image.stem + '.txt')).read_text().splitlines():
            if not line.strip():
                continue
            cls, cx, cy, bw, bh = map(float, line.split())
            truth.append({'type': NAMES[int(cls)], 'bbox': [(cx-bw/2)*w, (cy-bh/2)*h,
                                                          (cx+bw/2)*w, (cy+bh/2)*h]})
        pred = model.predict(str(image), imgsz=960, conf=0.25, iou=0.7, device='cpu', verbose=False)[0]
        components = [{'type': pred.names[int(b.cls.item())], 'bbox': b.xyxy[0].tolist()}
                      for b in pred.boxes]
        cases.append({'image': str(image), 'name': image.stem, 'truth': truth, 'yolo_components': components})
    (out / 'cases.json').write_text(json.dumps(cases, indent=2), encoding='utf-8')
    results = []

    def execute(case):
        item = {'name': case['name'], 'ground_truth_count': len(case['truth'])}
        try:
            result = detect(Path(case['image']), out / case['name'])
            components = result['components']
            item.update(success=True, tokens=result['metadata']['usage'].get('total_tokens', 0),
                        seconds=result['seconds'])
            item['scores'] = {tag: {str(t): score(c, case['truth'], t) for t in (0.5, 0.75)}
                              for tag, c in [('yolo11m', case['yolo_components']), ('pro_direct', components)]}
            item['per_class'] = {tag: {kind: score([c for c in cs if c['type'] == kind],
                                      [c for c in case['truth'] if c['type'] == kind])
                                      for kind in NAMES}
                                 for tag, cs in [('yolo11m', case['yolo_components']), ('pro_direct', components)]}
        except (Exception, SystemExit) as exc:
            item.update(success=False, error=type(exc).__name__, error_message=str(exc)[:180])
        return item

    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(execute, case) for case in cases]):
            item = f.result()
            results.append(item)
            (out / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print('PROGRESS', len(results), '/', len(cases), item['name'], item['success'],
                  item.get('scores', {}).get('pro_direct', {}).get('0.5'), flush=True)
    ok = [r for r in results if r['success']]
    summary = {'attempted_images': len(cases), 'successful_images': len(ok),
               'failed_images': len(cases)-len(ok), 'pro_total_tokens': sum(r['tokens'] for r in ok),
               'scope': 'Human labels, paired successful images only; upstream val, not independent test; no Pro confidence/AP claims',
               'models': {}}
    for tag in ('yolo11m', 'pro_direct'):
        summary['models'][tag] = {}
        for threshold in ('0.5', '0.75'):
            counts = {k: sum(r['scores'][tag][threshold][k] for r in ok)
                      for k in ('tp', 'fp', 'fn', 'whole_image_correct')}
            tp, fp, fn = counts['tp'], counts['fp'], counts['fn']
            counts.update(precision=tp/(tp+fp) if tp+fp else 0, recall=tp/(tp+fn) if tp+fn else 0,
                          f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
            summary['models'][tag][threshold] = counts
    # Include failed Pro responses in a separate all-attempts usability score.
    by_name = {r['name']: r for r in results}
    summary['all_attempts'] = {}
    for tag in ('yolo11m', 'pro_direct'):
        totals = Counter()
        for case in cases:
            item = by_name[case['name']]
            scored = (score(case['yolo_components'], case['truth']) if tag == 'yolo11m' else
                      item['scores'][tag]['0.5'] if item['success'] else
                      {'tp': 0, 'fp': 0, 'fn': len(case['truth']), 'whole_image_correct': False})
            totals.update(scored)
        tp, fp, fn = totals['tp'], totals['fp'], totals['fn']
        summary['all_attempts'][tag] = dict(totals, precision=tp/(tp+fp) if tp+fp else 0,
            recall=tp/(tp+fn) if tp+fn else 0, f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('SUMMARY', json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
