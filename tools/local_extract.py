"""Offline SINA candidate extraction: trained detector + upstream CCL + EasyOCR.

Produces reviewable candidates, never a confirmed or simulation-ready circuit.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from modules import detector, topology, ocr as ocr_stage
from modules.pins import attach_pins
from modules.text_binding import analyze_text_bindings
from modules.image_io import read_image, write_image

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--weights', type=Path)
    p.add_argument('--detections', type=Path, help='Saved detection.json; bypass YOLO and reuse frozen boxes')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--conf', type=float, default=0.25)
    p.add_argument('--imgsz', type=int, default=960)
    p.add_argument('--nms-iou', type=float, default=.7)
    p.add_argument('--class-thresholds', type=Path)
    p.add_argument('--tile-size', type=int)
    p.add_argument('--tile-overlap', type=float, default=.2)
    p.add_argument('--ocr-min-side', type=int, default=0)
    p.add_argument('--ocr-preprocess', choices=['none','gray','clahe'], default='none')
    p.add_argument('--skip-ocr', action='store_true')
    p.add_argument('--skip-crossings', action='store_true')
    p.add_argument('--sina-root', type=Path, help='Override the SINA source snapshot')
    p.add_argument('--ocr-model-dir', type=Path, help='Override EasyOCR model directory')
    args = p.parse_args()
    args.class_conf = json.loads(args.class_thresholds.read_text(encoding='utf-8')) if args.class_thresholds else None
    return extract(args)


def extract(args, on_stage=None):
    """Callable pipeline shared by CLI and GUI; callbacks never launch child processes."""
    p = argparse.ArgumentParser(description=__doc__)
    emit = on_stage or (lambda stage, message: None)
    args.image, args.out = args.image.resolve(), args.out.resolve()
    if args.weights:
        args.weights = args.weights.resolve()
    if not args.image.is_file() or (not args.detections and (not args.weights or not args.weights.is_file())):
        p.error('image and either weights or precomputed detections must exist')
    if args.out.exists() and any(args.out.iterdir()):
        p.error('use a new output directory')
    if not 0 <= args.conf <= 1 or args.imgsz < 1:
        p.error('invalid confidence or image size')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.ultralytics'))
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.matplotlib'))
    os.environ.setdefault('EASYOCR_MODULE_PATH', str(ROOT / 'SINA-venv/easyocr_module'))
    import cv2
    import numpy as np
    image = read_image(args.image)
    args.out.mkdir(parents=True, exist_ok=True)
    debug = args.out / 'debug'
    debug.mkdir()
    counts, detected = Counter(), []
    confidences = {}
    stage_metrics = {}
    stage_start = time.perf_counter()
    emit('detection', '正在使用 YOLO11m 检测元件…')
    if args.detections:
        evidence = json.loads(args.detections.read_text(encoding='utf-8'))
        if evidence['image_sha256'] != hashlib.sha256(args.image.read_bytes()).hexdigest():
            p.error('Precomputed detections belong to a different image')
        for c in evidence['components']:
            detected.append({'id': c['id'], 'type': c['type'], 'bbox': c['bbox'], 'color': [255, 155, 0]})
            confidences[c['id']] = evidence.get('confidences', {}).get(c['id'], c.get('confidence'))
        write_image(args.out / 'detected.jpg', image)
    else:
        if getattr(args, 'class_conf', None) is None:
            args.class_conf = detector.default_class_thresholds()
        detected, confidences = detector.detect(image, args.weights, args.out / 'detected.jpg',
                                                   args.device, args.conf, args.imgsz, iou=getattr(args,'detector_iou',getattr(args,'nms_iou',.7)),
                class_conf=getattr(args,'class_conf',None), tile_size=getattr(args,'tile_size',None), overlap=getattr(args,'tile_overlap',.2))
    stage_metrics['detection'] = {'status': 'completed', 'seconds': time.perf_counter() - stage_start}
    stage_start = time.perf_counter()
    emit('topology', '正在分析导线和引脚连接候选…')
    circuit, labels = topology.analyze(image, detected, debug, args.weights, not args.skip_crossings)
    stage_metrics['topology'] = {'status': 'completed', 'seconds': time.perf_counter() - stage_start}
    crossing_file = debug / 'crossing_status.json'
    if crossing_file.is_file():
        crossing = json.loads(crossing_file.read_text(encoding='utf-8'))
        stage_metrics['topology']['crossing_status'] = crossing['status']
        if crossing['status'] == 'failed':
            stage_metrics['topology'].update(status='degraded', error_type=crossing.get('error_type'))
    stage_start = time.perf_counter()
    pin_map = attach_pins(circuit, labels)
    stage_metrics['pins'] = {'status': 'completed', 'seconds': time.perf_counter() - stage_start}
    ocr = []
    ocr_warning = None
    stage_metrics['ocr'] = {'status': 'skipped', 'seconds': 0.0}
    if not args.skip_ocr:
        emit('ocr', '正在使用 EasyOCR 识别编号和参数…')
        model_dir = args.ocr_model_dir or Path(os.environ.get('EASYOCR_MODEL_DIR', str(ROOT / 'SINA-venv/easyocr_models')))
        user_dir = getattr(args, 'ocr_user_dir', None) or ROOT / 'SINA-venv/easyocr_user_network'
        user_dir.mkdir(parents=True, exist_ok=True)
        stage_start = time.perf_counter()
        try:
            ocr = ocr_stage.recognize(image, model_dir, user_dir, args.device,
                min_side=getattr(args,'ocr_min_side',0), preprocess=getattr(args,'ocr_preprocess','none'))
            stage_metrics['ocr'] = {'status': 'completed', 'seconds': time.perf_counter() - stage_start}
        except Exception as exc:
            stage_metrics['ocr'] = {'status': 'failed', 'seconds': time.perf_counter() - stage_start,
                                    'error_type': type(exc).__name__}
            if not getattr(args, 'ocr_optional', False):
                raise
            ocr_warning = 'OCR 未完成，保留元件和连接候选，请手动补充编号和参数。'
    warnings = ['Review all values, pin semantics, and connections before netlist generation.',
                'Local CCL crossing output is a candidate; full upstream crossing variants are not merged here.']
    if stage_metrics['topology']['status'] == 'degraded':
        warnings.append('Crossing analysis failed; wire connectivity is provisional.')
    if ocr_warning:
        warnings.append(ocr_warning)
    if not any(c['label'] in {'Voltage_src', 'Current_src'} for c in circuit):
        warnings.append('No source symbol detected; review external supply labels and excitation.')
    components = []
    for c in circuit:
        cid = c['id']
        pins = pin_map[cid]
        if not pins or any(pin['connection_candidate'] is None for pin in pins):
            warnings.append(f'{cid}: missing or unresolved pin connection')
        x1, y1, x2, y2 = c['bounding_box']
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        nearby = sorted(ocr, key=lambda t: (
            sum(v[0] for v in t['bbox']) / 4 - cx) ** 2 + (
            sum(v[1] for v in t['bbox']) / 4 - cy) ** 2)[:3]
        components.append({'id': cid, 'type': c['label'], 'ref': None, 'value': None,
                           'model': None, 'bbox': c['bounding_box'],
                           'confidence': confidences.get(cid), 'pin_candidates': pins,
                           'text_candidates': nearby, 'nodes': [],
                           'pin_order_confirmed': False, 'needs_user_confirmation': True})
    output = {'schema_version': '1.0', 'scope': 'local_sina_candidates',
              'ready_for_simulation': False, 'image': str(args.image),
              'model_sha256': hashlib.sha256(args.weights.read_bytes()).hexdigest() if not args.detections else evidence.get('model_sha256'),
              'detector_source': evidence['detector'] if args.detections else 'YOLO',
              'components': components, 'ocr': ocr, 'warnings': warnings,
              'stage_metrics': stage_metrics,
              'inference': {'conf': args.conf, 'imgsz': args.imgsz, 'device': args.device,
                            'pin_search_radius_pixels': 5,
                            'nms_iou':getattr(args,'detector_iou',getattr(args,'nms_iou',.7)),
                            'class_conf':getattr(args,'class_conf',None),
                            'tile_size':getattr(args,'tile_size',None), 'tile_overlap':getattr(args,'tile_overlap',.2),
                            'crossing_detection': not args.skip_crossings,
                            'ocr_enabled': not args.skip_ocr,
                            'ocr_min_side': getattr(args,'ocr_min_side',0),
                            'ocr_preprocess': getattr(args,'ocr_preprocess','none')}}
    binding = analyze_text_bindings(output)
    output['text_binding'] = binding['diagnostics']
    for component in components:
        component['text_candidates'] = binding['assignments'][component['id']]
    (args.out / 'recognized.json').write_text(json.dumps(output, indent=2, ensure_ascii=False),
                                             encoding='utf-8')
    print(f'Local extraction complete: {len(components)} components, {len(ocr)} OCR texts')
    print(f'Review candidates at {args.out}')
    emit('local_complete', '本地识别完成，正在生成可编辑草稿…')
    return output


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
