"""Resolve the selected workspace model without importing inference libraries."""
import hashlib
import json
from pathlib import Path


def selected_weights(root, fallback):
    root = Path(root).resolve()
    manifest = root / 'experiments/detector-selection.json'
    if not manifest.is_file():
        return Path(fallback)
    selection = json.loads(manifest.read_text(encoding='utf-8'))
    weight = (root / selection['weights']).resolve()
    if not weight.is_relative_to(root) or not weight.is_file():
        raise ValueError('选定的检测器权重不存在或不在工作台目录内，请检查模型选择记录。')
    expected = selection.get('sha256')
    if expected and hashlib.sha256(weight.read_bytes()).hexdigest() != expected:
        raise ValueError('检测器权重与模型选择记录的校验值不一致。')
    return weight
