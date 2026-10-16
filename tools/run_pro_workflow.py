"""Experimental direct Pro detection -> CCL/EasyOCR -> original SINA Pro prompts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from pro_detector import detect, ROOT
from run_workflow import review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--detections', type=Path, help='Reuse this image\'s direct Pro detection evidence')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    image = a.image.resolve()
    if a.detections:
        detections = a.detections.resolve()
    else:
        detect(image, a.out / 'direct-detection')
        detections = (a.out / 'direct-detection/detection.json').resolve()
    subprocess.run([sys.executable, '-u', str(ROOT / 'tools/local_extract.py'), str(image),
                    '--detections', str(detections), '--out', str(a.out / 'local'),
                    '--skip-crossings'], check=True)
    review(image, a.out / 'local/recognized.json', a.out / 'pro', 'pro')
    (a.out / 'workflow.json').write_text(json.dumps({
        'detector': 'Pro direct image localization', 'yolo_detection_used': False,
        'crossing_variants': 'disabled to avoid upstream YOLO re-detection',
        'ready_for_simulation': False}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
