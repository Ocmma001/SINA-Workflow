# -*- coding: utf-8 -*-
"""安装 Tesseract，免管理员权限。

两条路一起做：
  A. 下载官方安装包存到 downloads/，供你在有管理员的终端里正规安装
  B. 从 conda-forge 取 win-64 的 tesseract，解压到 tools/tesseract/ 立即可用

为什么选 B 作为主路线：官方包 PE 清单是 highestAvailable，会弹 UAC，
而本机当前用户不是管理员。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import ssl
import sys
import time
import urllib.request
from pathlib import Path

# conda 的 .conda 内层是 zstd，Python 3.11 的 tarfile 不认
try:
    import zstandard
except ImportError:
    print("需要 zstandard：pip install zstandard")
    sys.exit(2)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WS = Path(__file__).resolve().parent.parent
DL = WS / "downloads" / "tesseract"
OUT = WS / "tools" / "tesseract"
WORK = DL / "_work"
DL.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Connection": "close",
}

OFFICIAL = ("https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/"
            "tesseract-ocr-w64-setup-5.5.3.20260724.exe")


def hr(t: str) -> None:
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}", flush=True)


def step(msg: str) -> None:
    print(f"\n>>> {msg}", flush=True)


def dl(url: str, dest: Path, min_size: int = 0) -> bool:
    if dest.exists() and dest.stat().st_size >= min_size:
        print(f"  已存在，跳过（{dest.stat().st_size/1024/1024:.2f} MB）")
        return True
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers=UA)
        t0 = time.time()
        got = 0
        with urllib.request.urlopen(req, timeout=300, context=CTX) as r:
            total = int(r.headers.get("Content-Length") or 0)
            with open(tmp, "wb") as fh:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        print(f"\r    {got*100/total:5.1f}%  "
                              f"{got/1024/1024:6.2f}/{total/1024/1024:.2f} MB  "
                              f"{got/max(time.time()-t0,.001)/1024:7.1f} KB/s",
                              end="", flush=True)
        print()
        if got < min_size:
            print(f"    文件过小（{got} < {min_size}），可能是错误页")
            tmp.unlink(missing_ok=True)
            return False
        shutil.move(str(tmp), str(dest))
        return True
    except Exception as exc:
        print(f"\n    失败: {type(exc).__name__}: {str(exc)[:150]}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def extract_conda(archive: Path, target: Path) -> list[str]:
    import tarfile, zipfile
    target.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    with zipfile.ZipFile(archive) as z:
        for n in z.namelist():
            if not n.endswith(".tar.zst") or n.startswith("info-"):
                continue
            raw = z.read(n)
            tar_bytes = zstandard.ZstdDecompressor().decompress(raw, max_output_size=1 << 31)
            tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:")
            names += tf.getnames()
            tf.extractall(target)
    return names


def main() -> int:
    # ═══════════════════════════════ A. 官方安装包（备用）
    hr("A. 下载官方安装包（供你在有管理员的终端里安装）")
    official = DL / "tesseract-ocr-w64-setup-5.5.3.20260724.exe"
    if dl(OFFICIAL, official, min_size=10_000_000):
        print(f"  已保存: {official}  ({official.stat().st_size/1024/1024:.2f} MB)")
    else:
        print("  官方包下载失败（不影响 B 路线）")

    # ═══════════════════════════════ B. conda-forge（主路线）
    hr("B. conda-forge 的 tesseract（免管理员，解压即用）")
    try:
        req = urllib.request.Request(
            "https://api.anaconda.org/package/conda-forge/tesseract/files",
            headers={**UA, "Accept": "application/json",
                     "Referer": "https://anaconda.org/conda-forge/tesseract/files"})
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            files = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"  查询失败: {type(exc).__name__}: {str(exc)[:120]}")
        return 1

    win = [f for f in files if "win-64" in str(f.get("download_url", ""))]
    win.sort(key=lambda f: (str(f.get("version", "")), str(f.get("basename", ""))), reverse=True)
    if not win:
        print("  没有 win-64 包")
        return 1
    pick = win[0]
    url = pick["download_url"]
    if url.startswith("//"):
        url = "https:" + url
    print(f"  选定: {pick.get('basename')}  ({pick.get('size',0)/1024/1024:.2f} MB)")
    print(f"  版本: {pick.get('version')}")

    archive = DL / pick["basename"].split("/")[-1]
    step("下载")
    if not dl(url, archive, min_size=1_000_000):
        return 1
    print(f"  已保存 {archive.stat().st_size/1024/1024:.2f} MB")

    step("解包")
    if WORK.exists():
        shutil.rmtree(WORK)
    names = extract_conda(archive, WORK)
    print(f"  解出 {len(names)} 个条目")
    exes = [n for n in names if n.lower().endswith(".exe")]
    print(f"  其中 exe: {exes}")

    step("组装到 tools/tesseract")
    if OUT.exists():
        shutil.rmtree(OUT)
    copied = 0
    for src in WORK.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(WORK)
        parts = rel.parts
        if parts and parts[0].lower() == "library":
            rel = Path(*parts[1:])
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    print(f"  复制 {copied} 个文件")

    # ═══════════════════════════════ 验证
    hr("C. 验证 tesseract.exe")
    exes = list(OUT.rglob("tesseract.exe"))
    if not exes:
        print("  [x] 没找到 tesseract.exe")
        for p in sorted(OUT.rglob("*"))[:20]:
            print(f"      {p.relative_to(OUT)}")
        return 1
    exe = exes[0]
    print(f"  路径: {exe}")

    import subprocess
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                           timeout=90, encoding="utf-8", errors="replace",
                           cwd=str(exe.parent))
        print(f"  退出码: {r.returncode}")
        print(f"  stdout: {(r.stdout or '').strip()[:400]}")
        if r.stderr.strip():
            print(f"  stderr: {r.stderr.strip()[:400]}")
    except Exception as exc:
        print(f"  运行失败: {type(exc).__name__}: {exc}")

    # tessdata 是否带上
    hr("D. tessdata（语言数据）")
    td = [p for p in OUT.rglob("*.traineddata")]
    if td:
        for p in td[:12]:
            print(f"  {p.relative_to(OUT)}  ({p.stat().st_size/1024/1024:.1f} MB)")
    else:
        print("  [x] 没有 .traineddata —— 需要单独下载 eng.traineddata")
        print("      来源: https://github.com/tesseract-ocr/tessdata_fast")

    hr("E. 体积")
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"  tools/tesseract/  合计 {total/1024/1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
