"""Recompute full-denominator metrics from all persisted detection trial evidence."""
from collections import Counter
import json
from pro_detector import ROOT
from direct_detector_benchmark import score


def summarize(directory):
    cases = json.loads((directory / 'cases.json').read_text(encoding='utf-8'))
    rows = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
    if len(rows) != len(cases):
        raise ValueError(f'Incomplete trial: {directory.name}')
    by_name = {r['name']: r for r in rows}
    result = {'run': directory.name, 'images': len(cases), 'successful': sum(r['success'] for r in rows),
              'errors': dict(Counter(r.get('error') for r in rows if not r['success'])), 'all_attempts': {}}
    for tag in ('yolo11m', 'pro_direct'):
        result['all_attempts'][tag] = {}
        for threshold in (0.5, 0.75):
            totals = Counter()
            for case in cases:
                row = by_name[case['name']]
                if tag == 'yolo11m':
                    pred = case['yolo_components']
                elif row['success']:
                    pred = json.loads((directory / case['name'] / 'detection.json').read_text(encoding='utf-8'))['components']
                else:
                    pred = []
                totals.update(score(pred, case['truth'], threshold))
            tp, fp, fn = totals['tp'], totals['fp'], totals['fn']
            result['all_attempts'][tag][str(threshold)] = dict(totals,
                precision=tp/(tp+fp) if tp+fp else 0, recall=tp/(tp+fn) if tp+fn else 0,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    (directory / 'full-denominator-summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    directory = ROOT / 'runs/pro-direct-seven-trials-20261016'
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    results = [summarize(ROOT / 'runs' / name) for name in manifest['trials']]
    baseline = results[0]['all_attempts']['yolo11m']
    if any(r['all_attempts']['yolo11m'] != baseline for r in results):
        raise ValueError('Baseline changed across trials; inspect before selecting')
    means = {threshold: sum(r['all_attempts']['pro_direct'][threshold]['f1'] for r in results)/len(results)
             for threshold in ('0.5', '0.75')}
    wins = sum(r['all_attempts']['pro_direct']['0.5']['f1'] > baseline['0.5']['f1'] for r in results)
    improved = means['0.5'] > baseline['0.5']['f1'] and means['0.75'] >= baseline['0.75']['f1'] and wins >= 4
    result = {'trials': results, 'baseline': baseline, 'pro_mean_f1': means, 'pro_round_wins': wins,
              'pro_metric_improved': improved,
              'recommendation': 'review CCL smoke checks before replacement' if improved else 'retain YOLO11m',
              'scope': 'Same 66 validation images repeated 7 times; not 462 independent images',
              'ready_for_simulation': False}
    (directory / 'comparison.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    lines = ['# Pro 直接检测七轮对照结果', '',
             '每轮使用同一套 66 张人工标注验证图，共 462 次检测尝试。YOLO11m 固定 conf=0.25、imgsz=960。',
             'Pro 只接收原图和相同检测提示词，请求严格结构化输出；人工标注没有发送给模型。', '',
             '| 轮次 | Pro 可用输出 | Pro F1（IoU≥0.5） | Pro F1（IoU≥0.75） | YOLO11m F1（IoU≥0.5） |',
             '|---|---:|---:|---:|---:|']
    for i, trial in enumerate(results, 1):
        metrics = trial['all_attempts']['pro_direct']
        lines.append(f"| {i} | {trial['successful']}/66 | {metrics['0.5']['f1']:.2%} | {metrics['0.75']['f1']:.2%} | {baseline['0.5']['f1']:.2%} |")
    lines += ['', f"Pro 七轮平均 F1：IoU≥0.5 为 {means['0.5']:.2%}，IoU≥0.75 为 {means['0.75']:.2%}。",
              f"YOLO11m 对应 F1：{baseline['0.5']['f1']:.2%}、{baseline['0.75']['f1']:.2%}。Pro 胜出轮数：{wins}/7。", '',
              '失败输出不从分母排除：该图全部参考目标计作没有可用预测的漏检。格式错误与服务错误另存于原始 results.json。',
              'F1 综合反映精确率与召回率；这里不是 Pro 的 mAP，也不是整张电路或完整网表准确率。', '',
              '## 选择', '',
              '继续保留 YOLO11m，Pro 保留为局部编号、参数和语义复核模块。' if not improved else
              'Pro 的检测指标达到预设比较条件，仍需检查连接分析效果后才能替换。', '',
              '## 完整流程观察', '',
              '在两张样例上已把 Pro 检测框接入 CCL、EasyOCR 和原版 SINA Pro 提示词。',
              'BJT 偏置图出现电阻只有一个接触点和多个端子被错误合并至接地网络；第二张图仍遗漏 BJT 基极，MOS 端子顺序也未恢复正确。',
              '这些是样例故障记录，没有完整独立拓扑测试集，不能报告完整工作流准确率。为避免隐含调用 YOLO，Pro 路线关闭了上游交叉检测分支。', '',
              '## 限制与原始证据', '',
              '同一批 66 张验证图重复七次，是 API 稳定性对照，不是 462 张独立测试图。原验证集曾参与 YOLO 电路训练方案选权重，不代表真实图片泛化成绩。',
              '七轮未改变主要配置，不能把波动当作提示词训练收益。先前普通文本输出测试、格式烟测和完整流程样例调用不包含在这 462 次尝试中。',
              '每轮原图路径、人工参考、YOLO 检测框在 cases.json，Pro 原始回复与检测框在各图片目录，全部结果在 results.json。',
              '完整分母指标在各轮 full-denominator-summary.json；总汇总为本目录 comparison.json。',
              '下一步优化详见 docs/superpowers/plans/2026-10-16-sina-workflow-optimization.md。']
    (ROOT / 'Pro直接检测七轮对照结果.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'trials'}, indent=2))


if __name__ == '__main__':
    main()
