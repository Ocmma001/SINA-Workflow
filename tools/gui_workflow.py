"""Shared callable recognition service and stage artifacts for the desktop GUI."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
from gui_contract import build_draft
from local_extract import extract
from model_selection import selected_weights

ROOT = Path(__file__).resolve().parent.parent


def recognize(image, output, weights, sina_root, ocr_models, device='cpu', conf=.25,
              imgsz=960, allow_cloud=False, config=None, on_event=None, ocr_min_side=0, ocr_preprocess='none', detector_iou=.7, class_conf=None, tile_size=None, tile_overlap=.2):
    image, output = Path(image).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('请使用新的识别输出目录，原始识别记录不会覆盖。')
    output.mkdir(parents=True, exist_ok=True)
    events = []
    start = time.monotonic()
    def emit(stage, message, status='running'):
        event = {'stage': stage, 'status': status, 'message': message,
                 'elapsed_seconds': round(time.monotonic()-start, 3),
                 'timestamp': datetime.now(timezone.utc).isoformat()}
        events.append(event)
        with (output / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        if on_event:
            on_event(event)
    import torch
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    args = argparse.Namespace(image=image, weights=Path(weights), out=output / 'evidence',
        device=device, conf=conf, imgsz=imgsz, detections=None, skip_ocr=False,
        skip_crossings=False, sina_root=Path(sina_root), ocr_model_dir=Path(ocr_models),
        detector_iou=detector_iou, class_conf=class_conf, tile_size=tile_size, tile_overlap=tile_overlap,
        ocr_min_side=ocr_min_side, ocr_preprocess=ocr_preprocess,
        ocr_user_dir=Path(ocr_models) / 'user_network', ocr_optional=True)
    try:
        candidates = extract(args, emit)
    except (Exception, SystemExit):
        emit('local', '本地识别未完成，已保留运行日志。', 'failed')
        raise
    (output / 'candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding='utf-8')
    artifacts = {'candidates': 'candidates.json', 'detections_image': 'evidence/detected.jpg',
                 'connection_image': 'evidence/debug/11_final_connection_points.png',
                 'events': 'events.jsonl', 'workflow': 'workflow.json', 'draft': 'recognized.json'}
    review, review_error = None, None
    stage_metrics = dict(candidates.get('stage_metrics', {}))
    stage_metrics['vision_review'] = {'status': 'skipped', 'seconds': 0.0}
    # Local editable result is available even if the optional network stage is cancelled/fails.
    draft = build_draft(candidates, artifacts=artifacts)
    image_sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    draft['recognition']['image_sha256'] = image_sha256
    draft['recognition']['stages'] = events
    (output / 'recognized.json').write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
    if allow_cloud:
        review_start = time.monotonic()
        emit('vision_review', '正在通过火山引擎豆包 Pro 复核编号、参数和引脚语义…')
        try:
            from modules.vision import review_candidates
            review = review_candidates(image, output, candidates, config)
            draft = build_draft(candidates, review, artifacts)
            stage_metrics['vision_review'] = {'status': 'completed', 'seconds': time.monotonic() - review_start}
            emit('vision_review', 'Pro 复核完成，建议仍需人工确认。', 'completed')
        except KeyboardInterrupt:
            emit('vision_review', '复核已取消，保留本地识别草稿。', 'cancelled')
            draft['recognition']['stages'] = events
            (output / 'recognized.json').write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
            raise
        except (Exception, SystemExit) as exc:
            review_error = type(exc).__name__
            stage_metrics['vision_review'] = {'status': 'failed', 'seconds': time.monotonic() - review_start, 'error_type': review_error}
            draft['recognition']['warnings'].append('Pro 复核未完成，已保留本地草稿；请手动核对。')
            emit('vision_review', 'Pro 复核未完成，保留本地识别结果。', 'failed')
    else:
        emit('vision_review', '本次为本地识别，未上传图片。', 'skipped')
    draft['recognition']['image_sha256'] = image_sha256
    draft['recognition']['stages'] = events
    (output / 'recognized.json').write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
    workflow = {'schema_version': '2.0', 'status': 'needs_review', 'detector': 'YOLO11m',
                'model_sha256': candidates['model_sha256'], 'inference': candidates['inference'],
                'image_sha256': draft['recognition']['image_sha256'], 'cloud_requested': allow_cloud,
                'cloud_completed': review is not None and review_error is None,
                'cloud_error_type': review_error, 'artifacts': artifacts, 'ready_for_simulation': False,
                'stage_metrics': stage_metrics}
    (output / 'workflow.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
    emit('complete', f"识别完成，已生成 {len(draft['components'])} 个可编辑元件，等待核对。", 'completed')
    draft['recognition']['stages'] = events
    (output / 'recognized.json').write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
    return output / 'recognized.json'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--weights', type=Path)
    p.add_argument('--sina-root', type=Path, default=ROOT / 'SINA')
    p.add_argument('--ocr-model-dir', type=Path, default=ROOT / 'SINA-venv/easyocr_models')
    p.add_argument('--config', type=Path)
    p.add_argument('--device', default='cpu')
    p.add_argument('--conf', type=float, default=.25)
    p.add_argument('--imgsz', type=int, default=960)
    p.add_argument('--nms-iou', type=float, default=.7)
    p.add_argument('--class-thresholds', type=Path)
    p.add_argument('--tile-size', type=int)
    p.add_argument('--tile-overlap', type=float, default=.2)
    p.add_argument('--ocr-min-side', type=int, default=0)
    p.add_argument('--ocr-preprocess', choices=['none','gray','clahe'], default='none')
    p.add_argument('--allow-cloud', action='store_true')
    a = p.parse_args()
    weights = a.weights or selected_weights(ROOT, ROOT / 'runs/round-002/delivery/detector.pt')
    recognize(a.image, a.out, weights, a.sina_root, a.ocr_model_dir,
              device=a.device, conf=a.conf, imgsz=a.imgsz,
              allow_cloud=a.allow_cloud, config=a.config,
              detector_iou=a.nms_iou, class_conf=json.loads(a.class_thresholds.read_text(encoding='utf-8')) if a.class_thresholds else None,
              tile_size=a.tile_size, tile_overlap=a.tile_overlap,
              ocr_min_side=a.ocr_min_side, ocr_preprocess=a.ocr_preprocess,
              on_event=lambda e: print('LABPILOT_EVENT ' + json.dumps(e, ensure_ascii=False), flush=True))


if __name__ == '__main__':
    main()
