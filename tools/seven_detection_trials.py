"""Run remaining six fixed-config Pro localization trials, two processes at a time."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
from pro_detector import ROOT


def main():
    root = ROOT / 'runs/pro-direct-seven-trials-20261016'
    root.mkdir(exist_ok=False)
    names = ['pro-direct-schema-benchmark-20261016-001'] + [
        f'pro-direct-schema-benchmark-20261016-{i:03d}' for i in range(2, 8)]
    (root / 'manifest.json').write_text(json.dumps({
        'trials': names, 'images_per_trial': 66, 'total_requested_detection_calls': 462,
        'pro_config': 'same original-image-only prompt, strict JSON schema; no candidate input',
        'baseline': 'round-002 YOLO11m, imgsz960, conf0.25, NMS IoU0.7',
        'primary_metric': 'all-attempts micro F1 at matching IoU0.5; failed output gives no usable detections',
        'secondary_metric': 'F1 at matching IoU0.75, output availability and CCL smoke checks',
        'selection': 'retain YOLO11m unless mean F1 improves with a majority of round wins and no tight-localization degradation',
        'independent_test_set': False}, indent=2), encoding='utf-8')

    def execute(name):
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        with (ROOT / 'runs' / (name + '.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, '-u', str(ROOT / 'tools/direct_detector_benchmark.py'),
                                     '--name', name], stdout=log, stderr=subprocess.STDOUT, env=env)
        return {'name': name, 'returncode': result.returncode}

    status = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(execute, name) for name in names[1:]]):
            status.append(f.result())
            (root / 'execution.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
            print('TRIAL FINISHED', status[-1], flush=True)
    if any(r['returncode'] for r in status):
        raise SystemExit('One or more trial processes failed; inspect execution.json')


if __name__ == '__main__':
    main()
