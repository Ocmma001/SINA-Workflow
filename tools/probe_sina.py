# -*- coding: utf-8 -*-
"""探测 SINA 检出的真实结构，供 LabPilot 适配层对齐字段。

用法：
    python tools/probe_sina.py --root "C:\\...\\SINA"
    python tools/probe_sina.py --root "..." --deep     # 额外尝试跑一次最小样例

默认只读探测；--deep 会执行上游脚本，可能产生文件或联网。
目的是把 docs/sina_integration.md 里「待核对清单」的问题一次性问清楚。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

# ---------------------------------------------------------------- 已知入口
KNOWN_ENTRIES = [
    "Netlist Generator/IC/program_test/netlist_generator_algorithm_test/netlist_generator.py",
    "Netlist Generator/PCB/all models/Final/index.py",
]

# 命中这些名字的脚本都可能是入口
ENTRY_PATTERNS = [
    "netlist_generator*.py",
    "netlist*.py",
    "main.py",
    "index.py",
    "run*.py",
    "pipeline*.py",
    "generate*.py",
]

# 依赖探测
DEPS = ["ultralytics", "cv2", "easyocr", "openai", "numpy", "torch"]


def hr(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def find_entries(root: Path) -> list[Path]:
    """列出可能的入口脚本，已知路径优先。"""
    found: list[Path] = []
    for rel in KNOWN_ENTRIES:
        p = root / rel
        if p.exists():
            found.append(p)
    for pat in ENTRY_PATTERNS:
        for p in root.rglob(pat):
            if "node_modules" in p.parts or ".git" in p.parts:
                continue
            if p not in found:
                found.append(p)
    return found


def probe_structure(root: Path) -> None:
    hr("1. 仓库结构")
    for rel in ["Netlist Generator", "Netlist Generator/IC", "Netlist Generator/PCB", "Database"]:
        p = root / rel
        print(f"{'[ok]  ' if p.exists() else '[miss]'} {rel}")

    # 目录体积，判断是否误克隆了完整 Database
    total = 0
    db = root / "Database"
    if db.exists():
        for f in db.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        print(f"\nDatabase/ 体积: {total / 1024 / 1024:.0f} MB "
              f"（完整克隆时约 2 GB；不需要重训模型可稀疏检出跳过）")

    # 权重文件
    hr("2. 模型权重")
    weights = [p for p in root.rglob("*")
               if p.suffix.lower() in (".pt", ".onnx", ".weights") and p.is_file()]
    if weights:
        for w in weights[:20]:
            print(f"  {w.relative_to(root)}  ({w.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        print("  未找到权重文件 —— 检查 current_trained_model/ 是否在仓库中")


def probe_deps() -> None:
    hr("3. Python 依赖")
    import importlib
    for d in DEPS:
        try:
            m = importlib.import_module(d)
            v = getattr(m, "__version__", "?")
            print(f"  [ok]   {d} {v}")
        except Exception:
            print(f"  [miss] {d}")


def probe_entries(entries: list[Path], root: Path) -> None:
    hr("4. 入口脚本与命令行参数")
    if not entries:
        print("  未找到候选入口脚本")
        return
    for e in entries[:12]:
        rel = e.relative_to(root)
        text = e.read_text(encoding="utf-8", errors="replace")
        print(f"\n--- {rel}  ({len(text)} 字符) ---")

        # 提取 argparse 参数
        args = re.findall(r'add_argument\(\s*["\']([^"\']+)["\'](.*?)\)', text, re.S)
        if args:
            print("  命令行参数：")
            for flag, rest in args:
                help_m = re.search(r'help\s*=\s*["\']([^"\']+)', rest)
                print(f"    {flag:<22} {help_m.group(1) if help_m else ''}")
        else:
            print("  未检测到 argparse —— 可能是硬编码路径式脚本（需用 cwd 方式调用）")

        # 输出文件线索
        outs = set(re.findall(r'["\']([^"\']*\.(?:json|cir|sp|net|spice))["\']', text))
        if outs:
            print(f"  提及的输出/输入文件：{sorted(outs)[:10]}")

        # 输入目录线索
        for key in ["--input", "input_dir", "INPUT_DIR", "data/input"]:
            if key in text:
                print(f"  含输入路径线索：{key}")


def probe_output_format(root: Path) -> None:
    """找已有的输出样例，反推字段名。"""
    hr("5. 已有输出样例（用于反推 JSON 字段）")
    samples = [p for p in root.rglob("*.json")
               if p.is_file() and p.stat().st_size < 2_000_000
               and any(k in str(p).lower() for k in ("result", "output", "netlist", "out"))]
    if not samples:
        print("  未找到结果类 JSON —— 需要实际跑一次才能确认字段")
        return
    for s in samples[:5]:
        print(f"\n--- {s.relative_to(root)} ---")
        try:
            data = json.loads(s.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            print(f"  解析失败: {exc}")
            continue
        if isinstance(data, dict):
            print(f"  顶层键: {list(data.keys())}")
            for k, v in list(data.items())[:5]:
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    print(f"    {k}[0] 字段: {list(v[0].keys())}")
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            print(f"  列表，元素字段: {list(data[0].keys())}")


def probe_deep(entries: list[Path], root: Path) -> None:
    """尝试运行入口脚本的 --help，判断是否可调用。"""
    hr("6. 试运行 --help（可能产生副作用）")
    for e in entries[:6]:
        for launcher in ("python",):
            try:
                r = subprocess.run(
                    [launcher, str(e), "--help"],
                    cwd=str(e.parent), capture_output=True, text=True, timeout=25,
                )
                head = (r.stdout or r.stderr or "").strip().splitlines()[:12]
                print(f"\n--- {e.relative_to(root)} via {launcher} (exit={r.returncode}) ---")
                for line in head:
                    print("   " + line)
            except subprocess.TimeoutExpired:
                print(f"\n--- {e.relative_to(root)} via {launcher} --- 超时（可能进入交互）")
            except Exception as exc:
                print(f"\n--- {e.relative_to(root)} via {launcher} --- 失败: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="探测 SINA 仓库结构")
    ap.add_argument("--root", required=True, help="SINA 检出目录")
    ap.add_argument("--deep", action="store_true", help="额外试运行入口脚本的 --help")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    print(f"SINA_ROOT = {root}")
    if not root.exists():
        print("[x] 目录不存在")
        return 1
    if not (root / "Netlist Generator").exists():
        print("[!] 未找到 'Netlist Generator' 目录 —— 确认这是 SINA 仓库根目录，"
              "而不是它的上层目录")

    probe_structure(root)
    probe_deps()
    entries = find_entries(root)
    probe_entries(entries, root)
    probe_output_format(root)
    if args.deep:
        probe_deep(entries, root)

    hr("结论")
    print("把以上输出贴回对话，即可确定 adapter.py 的字段映射与 sina_runner.py 的调用方式。")
    print("重点看：第 4 节的命令行参数、第 5 节的 JSON 字段、第 2 节权重是否存在。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
