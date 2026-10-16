"""Sequential operating-point sweep on the existing development split, never a holdout."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from modules.detector import predict_records, _iou
from modules.image_io import read_image
from train_round import NAMES

ROOT=Path(__file__).resolve().parent.parent


def score(gt,predictions,threshold):
    used=set()
    tp=0
    for prediction in sorted(predictions,key=lambda p:-p['confidence']):
        best=(0.,None)
        for index,(kind,box) in enumerate(gt):
            if index in used or kind != prediction['type']:
                continue
            overlap=_iou(box,prediction['bbox'])
            if overlap>best[0]: best=(overlap,index)
        if best[1] is not None and best[0]>=threshold:
            used.add(best[1])
            tp+=1
    return {'tp':tp,'fp':len(predictions)-tp,'fn':len(gt)-tp}


def combine(rows,key):
    counts={k:sum(r[key][k] for r in rows) for k in ('tp','fp','fn')}
    tp,fp,fn=(counts[k] for k in ('tp','fp','fn'))
    counts.update(precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn) if tp+fn else 0,
                  f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--device',default='0')
    parser.add_argument('--weights',type=Path,default=ROOT/'runs/round-002/delivery/detector.pt')
    parser.add_argument('--map',action='store_true')
    parser.add_argument('--thresholds',type=float,nargs='+',default=[.15,.2,.25,.3,.35,.4,.5,.55,.6,.65,.7,.75,.8,.85,.9,.95])
    args=parser.parse_args()
    if not args.thresholds or any(not 0<=v<=1 for v in args.thresholds):
        parser.error('thresholds must be in [0,1]')
    if .25 not in args.thresholds:
        parser.error('thresholds must include the .25 baseline')
    args.out.mkdir(parents=True,exist_ok=False)
    import torch
    torch.set_num_threads(4)
    data=ROOT/'SINA/Netlist Generator/IC/model_training/data'
    images=sorted((data/'images/val').glob('*.jpg'))
    if not images: raise ValueError('No development images')
    profiles=[('native',960,.7,None),('nms50',960,.5,None),('nms60',960,.6,None),
              ('nms80',960,.8,None),('nms90',960,.9,None),('size1280',1280,.7,None),('tiles960',960,.7,960)]
    summaries=[]
    for name,size,nms,tile in profiles:
        records=[]
        started=time.perf_counter()
        for image_path in images:
            image=read_image(image_path)
            height,width=image.shape[:2]
            truth=[]
            label=data/'labels/val'/(image_path.stem+'.txt')
            for line in label.read_text(encoding='utf-8').splitlines():
                if not line.strip(): continue
                kind,cx,cy,w,h=map(float,line.split())
                truth.append((NAMES[int(kind)],[(cx-w/2)*width,(cy-h/2)*height,(cx+w/2)*width,(cy+h/2)*height]))
            failure=None
            start=time.perf_counter()
            try:
                predictions=predict_records(image,args.weights,args.device,.05,size,iou=nms,tile_size=tile)
            except Exception as exc:
                predictions=[]
                failure=type(exc).__name__
            records.append({'image':image_path.name,'image_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),
                            'gt':truth,'predictions':predictions,'failure':failure,'seconds':time.perf_counter()-start})
        (args.out/(name+'-predictions.json')).write_text(json.dumps(records,indent=2),encoding='utf-8')
        for conf in args.thresholds:
            rows=[]
            for record in records:
                predictions=[p for p in record['predictions'] if p['confidence']>=conf]
                rows.append({'image':record['image'],'failure':record['failure'],
                             'iou50':score(record['gt'],predictions,.5),'iou75':score(record['gt'],predictions,.75)})
            summary={'profile':name,'imgsz':size,'nms_iou':nms,'tile_size':tile,'conf':conf,'attempts':len(images),
                     'failures':sum(r['failure'] is not None for r in records),'profile_total_seconds':time.perf_counter()-started,
                     'iou50':combine(rows,'iou50'),'iou75':combine(rows,'iou75')}
            summaries.append(summary)
            (args.out/(name+'-conf'+str(conf)+'.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
        (args.out/'summary.json').write_text(json.dumps({'scope':'development_operating_point_sweep','images':len(images),
            'model_sha256':hashlib.sha256(args.weights.read_bytes()).hexdigest(),'results':summaries},indent=2),encoding='utf-8')
        print(name,'done',round(time.perf_counter()-started,2),flush=True)
    ranked=sorted((r for r in summaries if not r['failures']),key=lambda r:r['iou50']['f1']+r['iou75']['f1'],reverse=True)
    baseline=next(r for r in summaries if r['profile']=='native' and r['conf']==.25)
    best=ranked[0]
    comparison={'baseline':baseline,'best_operating_point':best,'promoted':False,'note':'Candidate only; downstream changes and mAP must be reviewed.'}
    if args.map:
        import yaml
        from ultralytics import YOLO
        config=args.out/'dataset.yaml'
        config.write_text(yaml.safe_dump({'path':data.as_posix(),'train':'images/train','val':'images/val','names':NAMES}),encoding='utf-8')
        map_results={}
        for name,profile in [('baseline',baseline),('candidate',best)]:
            if profile['tile_size']:
                map_results[name]={'status':'not_available_for_tiled_inference'}
                continue
            metrics=YOLO(str(args.weights)).val(data=str(config),split='val',imgsz=profile['imgsz'],batch=1,device=args.device,
                workers=0,conf=.001,iou=profile['nms_iou'],plots=False,verbose=False,project=str(args.out),name=name+'-map')
            map_results[name]={k:float(v) for k,v in metrics.results_dict.items()}
        comparison['mAP']=map_results
    (args.out/'comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
    print(json.dumps(comparison,indent=2),flush=True)


if __name__=='__main__':
    main()
