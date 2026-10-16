"""Choose development-only class thresholds without losing baseline per-class TP."""
import argparse
import hashlib
import json
from pathlib import Path
from evaluate_detector_options import score,combine
from train_round import NAMES


def select_thresholds(records,names,baseline_conf=.25,grid=None):
    grid=sorted(set(grid or [baseline_conf,.3,.35,.4,.45,.5,.55,.6,.65,.7,.75,.8,.85,.9,.95]))
    grid=[value for value in grid if baseline_conf<=value<=1]
    thresholds,per_class={},[]
    for kind in names:
        def evaluate(conf):
            rows=[{'iou50':score([g for g in r['gt'] if g[0]==kind],[p for p in r['predictions'] if p['type']==kind and p['confidence']>=conf],.5),
                   'iou75':score([g for g in r['gt'] if g[0]==kind],[p for p in r['predictions'] if p['type']==kind and p['confidence']>=conf],.75)} for r in records]
            return {key:combine(rows,key) for key in ('iou50','iou75')}
        baseline=evaluate(baseline_conf)
        candidates=[]
        for conf in [baseline_conf]+grid:
            metrics=evaluate(conf)
            observed=baseline['iou50']['tp']+baseline['iou50']['fn']>0
            if conf!=baseline_conf and not observed: continue
            if all(metrics[key]['tp']>=baseline[key]['tp'] for key in ('iou50','iou75')):
                candidates.append((sum(metrics[key]['fp'] for key in ('iou50','iou75')),conf,metrics))
        best=min(candidates,key=lambda c:(c[0],c[1]))
        thresholds[kind]=best[1]
        per_class.append({'class':kind,'threshold':best[1],'baseline':baseline,'candidate':best[2]})
    return thresholds,per_class


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    records=json.loads(args.predictions.read_text(encoding='utf-8'))
    thresholds,per_class=select_thresholds(records,NAMES)
    args.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for r in records:
        predictions=[p for p in r['predictions'] if p['confidence']>=thresholds[p['type']]]
        rows.append({'image':r['image'],'failure':r['failure'],'iou50':score(r['gt'],predictions,.5),'iou75':score(r['gt'],predictions,.75)})
    (args.out/'class-thresholds.json').write_text(json.dumps(thresholds,indent=2),encoding='utf-8')
    summary={'scope':'development_candidate_not_promoted','constraint':'No per-class TP reduction at IoU .5/.75',
        'prediction_cache_sha256':hashlib.sha256(args.predictions.read_bytes()).hexdigest(),'attempts':len(records),
        'failures':sum(r['failure'] is not None for r in records),'thresholds':thresholds,'per_class':per_class,
        'iou50':combine(rows,'iou50'),'iou75':combine(rows,'iou75'),'per_image':rows}
    (args.out/'evaluation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(summary['iou50'],summary['iou75'])


if __name__=='__main__': main()
