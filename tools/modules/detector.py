"""Cached YOLO inference with optional class thresholds and original-pixel tiling."""
from collections import Counter
from functools import lru_cache
import math
import json
from pathlib import Path


def default_class_thresholds():
    """Selected teammate operating point; return a fresh mapping for each run."""
    path = Path(__file__).resolve().parents[2] / 'experiments/candidates/member-a-class-thresholds.json'
    return json.loads(path.read_text(encoding='utf-8'))


@lru_cache(maxsize=2)
def _model(path, size, mtime_ns, device):
    from ultralytics import YOLO
    return YOLO(path)


def clear_model_cache():
    _model.cache_clear()


def tile_windows(width, height, tile_size, overlap=.2):
    if type(tile_size) is not int or tile_size < 32 or not 0 <= overlap <= .5:
        raise ValueError('tile_size >=32 and overlap in [0,.5] are required')
    step = max(1, round(tile_size*(1-overlap)))
    def starts(length):
        values = list(range(0, max(1,length-tile_size+1), step))
        last = max(0,length-tile_size)
        return values if values[-1] == last else values+[last]
    xs, ys = starts(width), starts(height)
    if len(xs)*len(ys) > 256:
        raise ValueError('Too many tiles; increase tile_size')
    return [(x,y,min(width,x+tile_size),min(height,y+tile_size)) for y in ys for x in xs]


def _iou(a, b):
    width, height = max(0,min(a[2],b[2])-max(a[0],b[0])), max(0,min(a[3],b[3])-max(a[1],b[1]))
    intersection = width*height
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0


def merge_detections(records, iou=.7):
    kept=[]
    # Sorting is stable for equal confidence, including overlapping tile edges.
    for record in sorted(records,key=lambda r:-r['confidence']):
        if not any(record['type']==old['type'] and _iou(record['bbox'],old['bbox'])>iou for old in kept):
            kept.append(record)
    return kept


def predict_records(image, weights, device='cpu', conf=.25, imgsz=960, *, iou=.7,
                    class_conf=None, tile_size=None, overlap=.2):
    if not 0 <= conf <= 1 or not 0 <= iou <= 1 or imgsz<1:
        raise ValueError('Invalid detector thresholds or image size')
    thresholds = dict(class_conf or {})
    if any(not isinstance(k,str) or not math.isfinite(float(v)) or not 0<=float(v)<=1 for k,v in thresholds.items()):
        raise ValueError('class_conf must map class names to thresholds in [0,1]')
    thresholds = {k: float(v) for k,v in thresholds.items()}
    if image is None or image.size == 0:
        raise ValueError('Detector requires a nonempty image')
    path = Path(weights).resolve()
    stat = path.stat()
    model = _model(str(path),stat.st_size,stat.st_mtime_ns,str(device))
    if set(thresholds)-set(model.names.values()):
        raise ValueError('Unknown class name in class_conf')
    height,width = image.shape[:2]
    windows = [(0,0,width,height)]
    if tile_size is not None and (width>tile_size or height>tile_size):
        windows += tile_windows(width,height,tile_size,overlap)
    records=[]
    for left,top,right,bottom in windows:
        result = model.predict(image[top:bottom,left:right], imgsz=imgsz, conf=min([conf]+list(thresholds.values())),
                               iou=iou, device=device, verbose=False)[0]
        for box in result.boxes:
            kind = result.names[int(box.cls.item())]
            confidence = float(box.conf.item())
            if confidence < float(thresholds.get(kind,conf)):
                continue
            x1,y1,x2,y2 = box.xyxy[0].tolist()
            bbox = [max(0.,min(float(width),x1+left)),max(0.,min(float(height),y1+top)),
                    max(0.,min(float(width),x2+left)),max(0.,min(float(height),y2+top))]
            if bbox[2]>bbox[0] and bbox[3]>bbox[1]:
                records.append({'type':kind,'confidence':confidence,'bbox':bbox})
    return merge_detections(records,iou) if len(windows)>1 else records


def detect(image, weights, annotated_path, device='cpu', conf=.25, imgsz=960, *,
           iou=.7, class_conf=None, tile_size=None, overlap=.2):
    import cv2
    from .image_io import write_image
    if class_conf is None:
        class_conf = default_class_thresholds()
    records = predict_records(image,weights,device,conf,imgsz,iou=iou,class_conf=class_conf,tile_size=tile_size,overlap=overlap)
    counts, detected, confidences = Counter(), [], {}
    annotated = image.copy()
    for record in records:
        kind = record['type']
        counts[kind]+=1
        cid = f'{kind}_{counts[kind]}'
        bbox = [int(v) for v in record['bbox']]
        detected.append({'id':cid,'type':kind,'bbox':bbox,'color':[255,155,0]})
        confidences[cid]=record['confidence']
        cv2.rectangle(annotated,tuple(bbox[:2]),tuple(bbox[2:]),(255,155,0),2)
        cv2.putText(annotated,f'{cid} {record["confidence"]:.2f}',(bbox[0],max(12,bbox[1]-4)),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,155,0),1)
    write_image(annotated_path,annotated)
    return detected,confidences
