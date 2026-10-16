"""YOLO component detector. Replace here; caller owns files and workflow state."""
from collections import Counter

def detect(image, weights, annotated_path, device='cpu', conf=.25, imgsz=960):
    counts, detected, confidences = Counter(), [], {}
    from ultralytics import YOLO
    prediction = YOLO(str(weights)).predict(image, imgsz=imgsz,
                                                 conf=conf, device=device,
                                                 verbose=False)[0]
    prediction.save(filename=str(annotated_path))
    for box in prediction.boxes:
        kind = prediction.names[int(box.cls.item())]
        counts[kind] += 1
        cid = f'{kind}_{counts[kind]}'
        detected.append({'id': cid, 'type': kind,
                         'bbox': [int(v) for v in box.xyxy[0].tolist()],
                         'color': [255, 155, 0]})
        confidences[cid] = float(box.conf.item())
    return detected, confidences
