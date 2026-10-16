"""Run local SINA extraction and an optimized Lite/Pro Ark profile."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MODELS = {'lite': 'doubao-seed-2-1-lite-260915', 'pro': 'doubao-seed-2-1-pro-260915'}


def review(image, candidates, out, profile):
    env = os.environ.copy()
    env['ARK_MODEL'] = MODELS[profile]
    env['PYTHONIOENCODING'] = 'utf-8'
    subprocess.run([sys.executable, '-u', str(ROOT / 'tools/vision_review.py'),
                    str(image), '--candidates', str(candidates), '--out', str(out),
                    '--ocr-context', 'boxes', '--netlist-image'], env=env, check=True)


def extract(image, out, device='cpu', weights=None):
    weights = weights or ROOT / 'runs/round-002/delivery/detector.pt'
    subprocess.run([sys.executable, '-u', str(ROOT / 'tools/local_extract.py'),
                    str(image), '--weights', str(weights),
                    '--out', str(out), '--device', device], check=True)
    return out / 'recognized.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', choices=MODELS, default='pro')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--weights', type=Path, help='Override detector for controlled comparisons')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    candidates = extract(args.image.resolve(), args.out / 'local', args.device, args.weights)
    review(args.image.resolve(), candidates, args.out / args.profile, args.profile)
    (args.out / 'workflow.json').write_text(json.dumps({
        'profile': args.profile, 'model': MODELS[args.profile],
        'optimized_context': 'component boxes plus original image in stage2',
        'topology': 'automatic local CCL; no manual correction',
        'ready_for_simulation': False}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
