# -*- coding: utf-8 -*-
"""用可用的 Python 3.11 建虚拟环境，为 SINA 安装依赖。

背景：harness 自带的 Python 3.12 在"向新建子目录写入文件"时必现 PermissionError，
导致 pip 完全不可用；而系统里的 Python 3.11 正常。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WS = Path(__file__).resolve().parent.parent
PY311 = Path(os.environ.get("SINA_BOOTSTRAP_PYTHON", sys.executable))
VENV = WS / "SINA-venv"
CERT = WS / "tools" / "certs" / "windows_roots.pem"
TMP = WS / "tools" / "piptmp"

# 分阶段：先小包验证链路，再上大的
STAGE1 = ["python-dotenv", "networkx", "requests"]
STAGE2 = ["numpy<2", "opencv-python", "matplotlib", "scipy", "scikit-learn", "pytesseract"]
STAGE3 = ["torch", "torchvision"]
STAGE4 = ["ultralytics", "easyocr", "openai"]


def hr(t: str) -> None:
    print(f"\n{'=' * 70}\n{t}\n{'=' * 70}", flush=True)


def env() -> dict:
    e = os.environ.copy()
    TMP.mkdir(parents=True, exist_ok=True)
    e["TEMP"] = e["TMP"] = e["TMPDIR"] = str(TMP)
    e["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    if CERT.exists():
        e["SSL_CERT_FILE"] = str(CERT)
        e["PIP_CERT"] = str(CERT)
    return e


def run(cmd: list[str], timeout: int = 5400) -> int:
    r = subprocess.run(cmd, env=env(), timeout=timeout)
    return r.returncode


def main() -> int:
    if not PY311.exists():
        print(f"未找到 Python 3.11: {PY311}")
        return 1

    hr("0. 检查 Python 3.11")
    run([str(PY311), "-c",
         "import sys; print(' ', sys.version); print(' ', sys.executable)"])

    # ---------------------------------------------------------- venv
    if not (VENV / "Scripts" / "python.exe").exists():
        hr("1. 创建虚拟环境")
        rc = run([str(PY311), "-m", "venv", str(VENV)])
        print(f"  venv 返回码: {rc}")
        if rc != 0:
            return 1
    else:
        hr("1. 虚拟环境已存在，跳过创建")

    vpy = VENV / "Scripts" / "python.exe"
    run([str(vpy), "-c", "import sys; print('  venv python:', sys.version.split()[0])"])

    hr("2. 升级 pip")
    run([str(vpy), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

    stages = [("3. 基础包", STAGE1), ("4. 科学计算与图像", STAGE2),
              ("5. PyTorch（CPU 版，体积最小）", STAGE3),
              ("6. SINA 专用包", STAGE4)]

    failed: list[str] = []
    for label, pkgs in stages:
        hr(f"{label}: {' '.join(pkgs)}")
        t0 = time.time()
        # torch 走官方 CPU 索引以避开巨大的 CUDA 包
        extra = ["--index-url", "https://download.pytorch.org/whl/cpu"] if "torch" in pkgs else []
        rc = run([str(vpy), "-m", "pip", "install", "--no-cache-dir"] + extra + pkgs)
        dt = time.time() - t0
        print(f"  -> 返回码 {rc}，耗时 {dt / 60:.1f} 分钟", flush=True)
        if rc != 0:
            failed.append(label)
            print(f"  [!] {label} 失败，继续下一阶段", flush=True)

    # ---------------------------------------------------------- 验证
    hr("7. 验证导入")
    check = (
        "import importlib.util as u\n"
        "mods = ['torch','torchvision','ultralytics','cv2','easyocr','openai',\n"
        "        'numpy','matplotlib','scipy','sklearn','networkx','dotenv','pytesseract']\n"
        "for m in mods:\n"
        "    print(('  OK   ' if u.find_spec(m) else '  MISS ') + m)\n"
    )
    run([str(vpy), "-c", check])

    hr("结果")
    print(f"  虚拟环境: {VENV}")
    print(f"  解释器  : {vpy}")
    if failed:
        print(f"  失败阶段: {failed}")
        return 1
    print("  全部安装成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
