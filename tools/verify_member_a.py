"""Sequential local acceptance runs; no cloud calls or model selection changes.

Use --training only after reviewing the baseline report. Resource peaks are sampled
whole-GPU and process-tree working-set values, not dedicated CUDA allocator peaks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, directory, name):
    import psutil
    started = time.perf_counter()
    peak_ram, peak_gpu = 0, 0
    samples = []
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    with (directory / (name+'.log')).open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
        try:
            while process.poll() is None:
                ram = 0
                try:
                    parent = psutil.Process(process.pid)
                    for child in [parent] + parent.children(recursive=True):
                        try:
                            ram += child.memory_info().rss
                        except psutil.Error:
                            pass
                except psutil.Error:
                    pass
                peak_ram = max(peak_ram, ram)
                try:
                    gpu = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
                    used = int(gpu.stdout.splitlines()[0]) if gpu.returncode == 0 else None
                except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                    used = None
                if used is not None:
                    peak_gpu = max(peak_gpu, used)
                samples.append({'seconds': round(time.perf_counter()-started, 3), 'rss_bytes': ram, 'whole_gpu_mib': used})
                time.sleep(2)
        except BaseException:
            process.terminate()
            process.wait(timeout=15)
            raise
    result = {'command': command, 'returncode': process.returncode,
              'seconds': time.perf_counter()-started, 'sampled_peak_process_tree_rss_bytes': peak_ram,
              'sampled_peak_whole_gpu_mib': peak_gpu, 'samples': samples, 'log': name+'.log'}
    write(directory/(name+'.result.json'), result)
    print(name, 'PASS' if process.returncode == 0 else 'FAIL', round(result['seconds'], 2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--training', action='store_true')
    parser.add_argument('--evaluation', action='store_true')
    args = parser.parse_args()
    directory = args.out.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest_path = ROOT/'assets/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))['files']
    invalid = [name for name, expected in manifest.items() if not (ROOT/name).is_file() or sha(ROOT/name) != expected]
    write(directory/'provenance.json', {'commit': commit, 'manifest_sha256': sha(manifest_path), 'resource_files': len(manifest), 'invalid_resources': invalid,
        'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'tools').rglob('*.py')},
        'selected_model_sha256': sha(ROOT/'runs/round-002/delivery/detector.pt'),
        'development_image_sha256': {p.name: sha(p) for p in sorted((ROOT/'SINA/Netlist Generator/IC/model_training/data/images/val').glob('*.jpg'))},
        'reference_scoring': 'unapproved development references; not independent ground truth',
        'sampling': '2 seconds plus nvidia-smi overhead; whole GPU includes other applications'})
    if invalid:
        raise RuntimeError('Resource validation failed; see provenance.json')
    py = sys.executable
    commands = [('tests', [py, '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py'])]
    commands.append(('environment', [py, '-c', "import torch,platform,json; print(json.dumps({'python':platform.python_version(),'torch':torch.__version__,'cuda':torch.version.cuda,'available':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None})); assert torch.cuda.is_available(); x=torch.ones(64,device='cuda'); print((x*x).sum().item())"]))
    images = ['examples/user_bjt_bias.jpg', 'examples/user_switch_led.jpg', 'resources/development-references/circuit_0003.jpg']
    commands.append(('detector', [py, 'tools/run_stage.py', 'detector', '--image', images[0], '--out', str(directory/'detector'), '--device', '0', '--imgsz', '960']))
    for i, image in enumerate(images):
        commands.append((f'workflow-{i}', [py, 'tools/gui_workflow.py', image, '--out', str(directory/f'workflow-{i}')]))
    unicode_image = directory/'电路测试.jpg'
    unicode_image.write_bytes((ROOT/images[0]).read_bytes())
    commands.append(('unicode-workflow', [py, 'tools/gui_workflow.py', str(unicode_image), '--out', str(directory/'中文结果')]))
    commands.append(('workflow-gpu', [py, 'tools/gui_workflow.py', images[0], '--out', str(directory/'workflow-gpu'), '--device', '0']))
    commands.append(('contract-replay', [py, 'tools/run_stage.py', 'contract', '--input', str(directory/'workflow-0/candidates.json'), '--out', str(directory/'contract-replay')]))
    commands.append(('pins-replay', [py, 'tools/run_stage.py', 'pins', '--input', str(directory/'workflow-0/evidence/debug'), '--out', str(directory/'pins-replay')]))
    if args.evaluation:
        for iou in ('.5', '.75'):
            commands.append(('eval'+iou, [py, 'tools/validate_on_dataset.py', '--model', 'runs/round-002/delivery/detector.pt', '--out', str(directory/('eval'+iou)), '--device', '0', '--imgsz', '960', '--conf', '.25', '--match-iou', iou]))
    results = []
    for name, command in commands:
        results.append({'name': name, **run(command, directory, name)})
        write(directory/'summary.json', {'attempts': len(results), 'failures': sum(r['returncode'] != 0 for r in results), 'results': results})
        if name in ('tests', 'environment') and results[-1]['returncode']:
            return 1
    if args.training and not any(r['returncode'] for r in results):
        name = directory.name+'-fit'
        result = run([py, 'tools/train_round.py', '--name', name, '--initial', 'runs/round-002/delivery/detector.pt', '--baseline', 'runs/round-002/delivery/detector.pt', '--epochs', '2', '--imgsz', '960', '--batch', '1', '--device', '0', '--lr0', '.0002', '--patience', '10'], directory, 'training')
        results.append({'name': 'training', **result})
        write(directory/'summary.json', {'attempts': len(results), 'failures': sum(r['returncode'] != 0 for r in results), 'results': results})
    return int(any(r['returncode'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
