"""Paired image bootstrap for development detection counts; failed rows are retained."""
import argparse
import json
from pathlib import Path
import numpy as np


def _rows(value):
    rows=value if isinstance(value,list) else value['per_image']
    result={r['image']:r for r in rows}
    if len(result)!=len(rows) or not rows:
        raise ValueError('Image IDs must be unique and nonempty')
    return result


def paired_bootstrap(baseline,candidate,*,samples=2000,seed=42):
    before,after=_rows(baseline),_rows(candidate)
    if set(before)!=set(after):
        raise ValueError('Paired image sets must match; do not drop failures')
    if samples<1: raise ValueError('samples must be positive')
    names=sorted(before)
    draws=np.random.default_rng(seed).integers(0,len(names),(samples,len(names)))
    output={'scope':'conditional development-image resampling; not independent generalization',
            'images':len(names),'samples':samples,'seed':seed,'metrics':{},
            'baseline_failures':sum(bool(before[n].get('failure')) for n in names),
            'candidate_failures':sum(bool(after[n].get('failure')) for n in names)}
    for key in ('iou50','iou75'):
        a=np.array([[before[n][key][c] for c in ('tp','fp','fn')] for n in names],dtype=float)
        b=np.array([[after[n][key][c] for c in ('tp','fp','fn')] for n in names],dtype=float)
        if not np.isfinite(a).all() or not np.isfinite(b).all() or (a<0).any() or (b<0).any():
            raise ValueError('Counts must be finite and nonnegative')
        def f1(counts):
            denominator=2*counts[...,0]+counts[...,1]+counts[...,2]
            return np.divide(2*counts[...,0],denominator,out=np.zeros_like(denominator),where=denominator>0)
        differences=f1(b[draws].sum(axis=1))-f1(a[draws].sum(axis=1))
        output['metrics'][key]={'baseline_f1':float(f1(a.sum(axis=0))),'candidate_f1':float(f1(b.sum(axis=0))),
            'delta_f1':float(f1(b.sum(axis=0))-f1(a.sum(axis=0))),
            'paired_bootstrap_95_percent_interval':np.percentile(differences,[2.5,97.5]).tolist()}
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    result=paired_bootstrap(json.loads(args.baseline.read_text(encoding='utf-8')),json.loads(args.candidate.read_text(encoding='utf-8')))
    args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
