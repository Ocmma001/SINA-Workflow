"""Small paired Ark benchmark; reference bindings/topology are manually checked."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
SIZES = {'R': 2, 'C': 2, 'L': 2, 'V': 2, 'I': 2, 'D': 2, 'Q': 3, 'M': 4, 'X': 5}


def canonical_ref(value):
    return unicodedata.normalize('NFKC', value).replace('_', '').upper()


def numeric_value(tokens):
    if not tokens:
        return None
    if tokens[0].upper() == 'DC':
        tokens = tokens[1:]
    if not tokens:
        return None
    m = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-zΩµμ]*)', tokens[0])
    if not m:
        return None
    suffix = m[2].lower().replace('µ', 'u').replace('μ', 'u')
    scale = 1.0
    for unit, factor in [('meg', 1e6), ('t', 1e12), ('g', 1e9), ('k', 1e3),
                         ('m', 1e-3), ('u', 1e-6), ('n', 1e-9), ('p', 1e-12), ('f', 1e-15)]:
        if suffix.startswith(unit):
            scale = factor
            break
    return float(m[1]) * scale


def score_draft(text, truth):
    cards = []
    for line in text.splitlines():
        t = line.split()
        if not t or t[0].startswith(('*', '.')) or t[0].startswith('GROUND_NODE:'):
            continue
        kind = t[0][0].upper()
        if kind in SIZES:
            n = SIZES[kind]
            cards.append({'ref': canonical_ref(t[0]), 'kind': kind, 'nodes': t[1:1+n],
                          'value': numeric_value(t[1+n:])})
    refs = Counter(c['ref'] for c in cards)
    expected = Counter((c['kind'], tuple(c['nodes'])) for c in truth)
    actual = Counter((c['kind'], tuple(c['nodes'])) for c in cards)
    labelled = [c for c in truth if c['ref'] is not None]
    labels_correct = values_correct = 0
    values_total = sum(c['value'] is not None for c in labelled)
    detail = []
    for gold in labelled:
        matched = [c for c in cards if c['ref'] == canonical_ref(gold['ref'])]
        correct = (len(matched) == 1 and matched[0]['kind'] == gold['kind'] and
                   matched[0]['nodes'] == gold['nodes'])
        labels_correct += int(correct)
        value_ok = gold['value'] is None or (correct and matched[0]['value'] is not None and
                    math.isclose(matched[0]['value'], gold['value'], rel_tol=1e-6, abs_tol=1e-9))
        if gold['value'] is not None:
            values_correct += int(value_ok)
        detail.append({'id': gold['id'], 'expected_ref': gold['ref'], 'binding_correct': correct,
                       'expected_value': gold['value'], 'known_value_correct': value_ok if gold['value'] is not None else None})
    unknown_clean = True
    for gold in truth:
        if gold['value'] is None and gold['kind'] in {'R', 'C', 'L'}:
            matched = [c for c in cards if c['kind'] == gold['kind'] and c['nodes'] == gold['nodes']]
            if not matched or any(c['value'] is not None for c in matched):
                unknown_clean = False
    has_end = any(line.strip().lower() == '.end' for line in text.splitlines())
    unique = all(count == 1 for count in refs.values())
    return {'labels_correct': labels_correct, 'labels_total': len(labelled),
            'values_correct': values_correct, 'values_total': values_total,
            'node_tuples_preserved': actual == expected, 'unique_refs': unique,
            'unknown_passives_not_invented': unknown_clean, 'has_end': has_end,
            'all_tasks_correct': labels_correct == len(labelled) and values_correct == values_total
                                 and actual == expected and unique and unknown_clean and has_end,
            'details': detail}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True)
    p.add_argument('--repeats', type=int, default=2)
    args = p.parse_args()
    if Path(args.name).name != args.name or args.name in {'.', '..'} or args.repeats < 1:
        p.error('invalid name or repeat count')
    cases = json.loads((ROOT / 'experiments/prompt-benchmark/cases.json').read_text(encoding='utf-8'))
    out = ROOT / 'runs' / args.name
    out.mkdir(parents=True, exist_ok=False)
    models = {'lite': 'doubao-seed-2-1-lite-260915', 'pro': 'doubao-seed-2-1-pro-260915'}
    jobs = [(tag, model, condition, case, repeat)
            for repeat in range(1, args.repeats + 1)
            for case in cases for condition in ('previous', 'updated')
            for tag, model in models.items()]
    manifest = {'cases': cases, 'models': models, 'repeats': args.repeats,
                'scope': 'Prompt-only controlled test, fixed manually checked topology; not end-to-end accuracy.',
                'previous': 'same original prompts, legacy OCR context, text-only stage2',
                'updated': 'same original prompts, component boxes in OCR context, image in stage2'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    def execute(job):
        tag, model, condition, case, repeat = job
        name = f"{tag}-{condition}-{case['name']}-r{repeat}"
        directory = out / name
        cmd = [sys.executable, '-u', str(ROOT / 'tools/vision_review.py'),
               str(ROOT / case['image']), '--candidates', str(ROOT / case['candidates']),
               '--raw-netlist', str(ROOT / case['raw']), '--out', str(directory),
               '--ocr-context', 'boxes' if condition == 'updated' else 'legacy']
        if condition == 'updated':
            cmd.append('--netlist-image')
        env = os.environ.copy()
        env['ARK_MODEL'] = model
        env['PYTHONIOENCODING'] = 'utf-8'
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=300)
            code, log = proc.returncode, proc.stdout + '\n' + proc.stderr
        except subprocess.TimeoutExpired:
            code, log = 124, 'Benchmark subprocess timed out'
        (out / (name + '.log')).write_text(log, encoding='utf-8')
        item = {'model_tag': tag, 'model': model, 'condition': condition, 'case': case['name'],
                'repeat': repeat, 'returncode': code, 'seconds': time.monotonic() - started,
                'directory': str(directory)}
        if code == 0:
            result = json.loads((directory / 'sina-ark-result.json').read_text(encoding='utf-8'))
            draft = (directory / 'sina-draft.cir').read_text(encoding='utf-8')
            item['score'] = score_draft(draft, case['truth'])
            item['tokens'] = {field: sum(result[stage]['usage'].get(field, 0) for stage in ('stage1', 'stage2'))
                              for field in ('input_tokens', 'output_tokens', 'total_tokens')}
            item['prompt_hashes'] = result['prompt_hashes']
        return item

    results = []
    print(f'Running {len(jobs)} paired jobs ({2*len(jobs)} API requests maximum)', flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(execute, job) for job in jobs]):
            item = future.result()
            results.append(item)
            (out / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            score = item.get('score', {})
            print(f"{len(results)}/{len(jobs)} {item['model_tag']} {item['condition']} {item['case']} r{item['repeat']} "
                  f"exit={item['returncode']} labels={score.get('labels_correct')}/{score.get('labels_total')}", flush=True)
    summary = []
    for tag in models:
        for condition in ('previous', 'updated'):
            chosen = [r for r in results if r['model_tag'] == tag and r['condition'] == condition]
            ok = [r for r in chosen if r['returncode'] == 0]
            summary.append({'model': tag, 'condition': condition, 'attempts': len(chosen),
                            'successful': len(ok),
                            **{field: sum(r['score'][field] for r in ok)
                               for field in ('labels_correct', 'labels_total', 'values_correct', 'values_total',
                                             'node_tuples_preserved', 'has_end', 'all_tasks_correct')},
                            'tokens': sum(r['tokens']['total_tokens'] for r in ok)})
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
