# -*- coding: utf-8 -*-
"""下载并安装 easyocr 的两个模型，然后验证 Reader 可用。

easyocr 默认下到 %USERPROFILE%\\.EasyOCR（本机不可写），因此显式指定
model_storage_directory。直接走 GitHub releases —— 实测 1.83 MB/s，
比各镜像代理（84-146 KB/s）快得多。
"""
from __future__ import annotations

import io
import os
import shutil
import ssl
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WS = Path(__file__).resolve().parent.parent
MODELS = WS / "SINA-venv" / "easyocr_models"
MODELS.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0"}

ITEMS = [
    ("craft_mlt_25k.zip",
     "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip",
     "craft_mlt_25k.pth"),
    ("english_g2.zip",
     "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip",
     "english_g2.pth"),
]


def hr(t: str) -> None:
    print(f"\n{'=' * 70}\n{t}\n{'=' * 70}", flush=True)


def fetch(url: str, dest: Path) -> bool:
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers=UA)
        t0 = time.time()
        got = 0
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            total = int(r.headers.get("Content-Length") or 0)
            with open(tmp, "wb") as fh:
                while True:
                    chunk = r.read(128 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        pct = got * 100 / total
                        kbs = got / max(time.time() - t0, 0.001) / 1024
                        print(f"\r    {pct:5.1f}%  {got/1024/1024:6.1f}/{total/1024/1024:.1f} MB"
                              f"  {kbs:7.1f} KB/s", end="", flush=True)
        print()
        shutil.move(str(tmp), str(dest))
        return True
    except Exception as exc:
        print(f"\n    失败: {type(exc).__name__}: {str(exc)[:150]}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def main() -> int:
    hr("1. 清理上次的残留")
    for pat in ("temp.zip", "*.part"):
        for p in MODELS.glob(pat):
            p.unlink()
            print(f"  已删 {p.name}")

    hr("2. 下载模型")
    for name, url, pth in ITEMS:
        target = MODELS / pth
        if target.exists():
            print(f"  {pth} 已存在（{target.stat().st_size/1024/1024:.1f} MB），跳过")
            continue
        print(f"\n  {name}  <-  {url.split('/download/')[-1]}")
        zip_path = MODELS / name
        if not fetch(url, zip_path):
            return 1
        print(f"    已保存 {zip_path.name} ({zip_path.stat().st_size/1024/1024:.1f} MB)")

        hr(f"3. 解包 {name}")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            print(f"    含 {len(names)} 个条目: {names[:5]}")
            zf.extractall(MODELS)
        zip_path.unlink()
        print(f"    解包完成 -> {MODELS}")

    hr("4. 目录内容")
    total = 0
    for p in sorted(MODELS.rglob("*")):
        if p.is_file():
            total += p.stat().st_size
            print(f"  {p.name:<30} {p.stat().st_size/1024/1024:>8.1f} MB")
    print(f"  合计 {total/1024/1024:.1f} MB")

    hr("5. 验证 Reader 可用")
    os.environ["EASYOCR_MODULE_PATH"] = str(MODELS)
    try:
        import easyocr
        t0 = time.time()
        reader = easyocr.Reader(["en"], gpu=False, verbose=False,
                                model_storage_directory=str(MODELS),
                                download_enabled=False)
        print(f"  Reader 初始化 OK（{time.time()-t0:.1f}s，未触发下载）")

        imgs = [p for p in (WS / "SINA" / "Database").rglob("*.jpg")][:2]
        for img in imgs:
            t0 = time.time()
            res = reader.readtext(str(img))
            print(f"\n  --- {img.name}  ({time.time()-t0:.1f}s, {len(res)} 段文字) ---")
            for bbox, text, conf in res[:10]:
                print(f"      {text!r:<26} conf={conf:.2f}")
    except Exception as exc:
        import traceback
        print(f"  失败: {type(exc).__name__}: {str(exc)[:300]}")
        traceback.print_exc()
        return 1

    print("\n  OCR 链路打通。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
