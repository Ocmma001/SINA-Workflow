"""Compare optimized Ark profiles with automatic SINA topology on checked examples."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
from run_workflow import ROOT, MODELS, extract, review
from prompt_benchmark import score_draft
from sina_ark_workflow import raw_structure


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True)
    p.add_argument('--repeats', type=int, default=3)
    a = p.parse_args()
    if Path(a.name).name != a.name or a.name in {'.', '..'} or a.repeats < 1:
        p.error('Invalid run name or repeats')
    out = ROOT / 'runs' / a.name
    out.mkdir(parents=True, exist_ok=False)
    cases = json.loads((ROOT / 'experiments/prompt-benchmark/cases.json').read_text(encoding='utf-8'))
    for case in cases:
        candidate = extract(ROOT / case['image'], out / ('local-' + case['name']))
        data = json.loads(candidate.read_text(encoding='utf-8'))
        old = json.loads((ROOT / case['candidates']).read_text(encoding='utf-8'))
        # Reference node numbers are comparable only for the same deterministic CCL evidence.
        evidence = lambda x: [(c['id'], c['bbox'], c['pin_candidates']) for c in x['components']]
        if evidence(data) != evidence(old):
            raise RuntimeError('Local evidence changed; reference node numbering must be reviewed')
        case['automatic_candidates'] = str(candidate)
        case['automatic_raw'] = raw_structure(data)
        case['automatic_topology_matches_reference'] = score_draft(
            '\n'.join({'Resistor':'R', 'Voltage_src':'V', 'Transistor_BJT':'Q',
                        'Transistor_MOSFET':'M'}[line.split()[0].rsplit('_', 1)[0]] +
                      str(i) + ' ' + ' '.join(line.split()[1:])
                      for i, line in enumerate(case['automatic_raw'], 1)), case['truth'])['node_tuples_preserved']
    (out / 'manifest.json').write_text(json.dumps({'models': MODELS, 'cases': cases,
        'repeats': a.repeats, 'manual_topology_supplied_to_model': False,
        'scope': 'Two known examples, automatic topology, shared local evidence per image; not independent test accuracy'}, indent=2), encoding='utf-8')

    def execute(profile, case, repeat):
        directory = out / f"{profile}-{case['name']}-r{repeat}"
        started = time.monotonic()
        item = {'profile': profile, 'case': case['name'], 'repeat': repeat}
        try:
            review(ROOT / case['image'], Path(case['automatic_candidates']), directory, profile)
            result = json.loads((directory / 'sina-ark-result.json').read_text(encoding='utf-8'))
            item.update(success=True, score=score_draft((directory / 'sina-draft.cir').read_text(encoding='utf-8'), case['truth']),
                        validation_issues=result['netlist_validation_issues'],
                        tokens=sum(result[s]['usage'].get('total_tokens', 0) for s in ('stage1', 'stage2')))
        except Exception as exc:
            item.update(success=False, error=type(exc).__name__)
        item['seconds'] = time.monotonic() - started
        return item

    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(execute, profile, case, repeat) for repeat in range(1, a.repeats + 1)
                 for case in cases for profile in MODELS]
        for f in as_completed(tasks):
            item = f.result()
            results.append(item)
            (out / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print('PROGRESS', len(results), '/', len(tasks), json.dumps(item), flush=True)
    summary = []
    for profile in MODELS:
        selected = [r for r in results if r['profile'] == profile]
        ok = [r for r in selected if r['success']]
        summary.append({'profile': profile, 'attempts': len(selected), 'successful': len(ok),
            **{k: sum(r['score'][k] for r in ok) for k in (
                'labels_correct', 'labels_total', 'values_correct', 'values_total',
                'node_tuples_preserved', 'has_end', 'all_tasks_correct')},
            'tokens': sum(r['tokens'] for r in ok)})
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('SUMMARY', json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
