"""Pair saved predictions without silently dropping missing or failed images."""
import argparse
import json
from pathlib import Path
import random
from detector_metrics import score_detections


def pair_cases(baseline, candidate, confidence=.25):
    # Earlier files from this same evaluator had an implicit .05 cache floor.
    if any(confidence < case.get('prediction_cache_confidence', .05) for case in baseline + candidate):
        raise ValueError('Requested confidence is below the prediction cache floor')
    left, right = {c['image']: c for c in baseline}, {c['image']: c for c in candidate}
    if len(left) != len(baseline) or len(right) != len(candidate) or left.keys() != right.keys():
        raise ValueError('Missing or duplicate paired images')
    paired = []
    for name in sorted(left):
        a, b = left[name], right[name]
        if any(a[key] != b[key] for key in ['image_sha256', 'label_sha256', 'truth']):
            raise ValueError(f'Input or truth differs: {name}')
        paired.append({'image': name, 'baseline_error': a.get('error'), 'candidate_error': b.get('error'),
            'scores': {str(iou): {label: {key: value for key, value in score_detections(
                data['truth'], [] if data.get('error') else data['predictions'], iou, confidence).items()
                if key in {'tp', 'fp', 'fn', 'precision', 'recall', 'f1'}}
                for label, data in [('baseline', a), ('candidate', b)]} for iou in [.5, .75]}})
    return paired


def total_score(rows, iou, label):
    counts = {key: sum(row['scores'][str(iou)][label][key] for row in rows) for key in ['tp', 'fp', 'fn']}
    tp, fp, fn = counts['tp'], counts['fp'], counts['fn']
    return dict(counts, precision=tp/(tp+fp) if tp+fp else 0, recall=tp/(tp+fn) if tp+fn else 0,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True, help='predict-960 directory')
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--confidence', type=float, default=.25)
    args = p.parse_args()
    if args.out.exists():
        p.error('output file already exists')
    rows = pair_cases([json.loads(f.read_text(encoding='utf-8')) for f in args.baseline.rglob('*.json')],
                      [json.loads(f.read_text(encoding='utf-8')) for f in args.candidate.rglob('*.json')], args.confidence)
    if not rows:
        p.error('no prediction pairs')
    summaries = {}
    for iou in [.5, .75]:
        baseline, candidate = total_score(rows, iou, 'baseline'), total_score(rows, iou, 'candidate')
        rng = random.Random(42)
        deltas = []
        for _ in range(1000):
            sample = rng.choices(rows, k=len(rows))
            deltas.append(total_score(sample, iou, 'candidate')['f1'] - total_score(sample, iou, 'baseline')['f1'])
        deltas.sort()
        wins = losses = ties = 0
        for row in rows:
            a, b = row['scores'][str(iou)]['baseline'], row['scores'][str(iou)]['candidate']
            old_error, new_error = a['fp']+a['fn'], b['fp']+b['fn']
            wins += new_error < old_error
            losses += new_error > old_error
            ties += new_error == old_error
        summaries[str(iou)] = {'baseline': baseline, 'candidate': candidate,
            'f1_delta': candidate['f1']-baseline['f1'], 'f1_delta_paired_bootstrap_95': [deltas[24], deltas[974]],
            'image_error_count_improved': wins, 'image_error_count_regressed': losses, 'image_error_count_tied': ties}
    result = {'images': len(rows), 'confidence': args.confidence, 'iou': summaries, 'per_image': rows,
        'bootstrap': {'seed': 42, 'samples': 1000, 'unit': 'image',
          'limitation': 'Descriptive development-set sampling uncertainty; does not account for model/threshold selection or establish independent generalization.'},
        'independent_test': False, 'ready_for_simulation': False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'images': len(rows), 'iou': summaries}, indent=2))


if __name__ == '__main__':
    main()
