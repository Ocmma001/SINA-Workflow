# -*- coding: utf-8 -*-
"""SINA 试验台 —— 在 cmd 里跑通 SINA 的 IC 电路图识别流程。

用法（在 cmd 里）：

    D:\\...\\default-workspace\\SINA-venv\\Scripts\\python.exe tools\\sina_lab.py --help

本脚本做三件事：
  1. 修好 SINA 在本机的两个环境坑（easyocr 模型目录、缺失的输出目录）
  2. 把测试图放进 SINA 入口写死的 inputs/test_images/
  3. 分阶段跑：先识别（YOLO+CCL+OCR；启用 OCR 会调用视觉 API），再 LLM 环节

为什么需要包装脚本
------------------
SINA 的 IC 入口 netlist_generator.py 把路径全部写死，且内部调用
easyocr.Reader(['en'], gpu=True) 时不传 model_storage_directory，
而本机 %USERPROFILE%\\.EasyOCR 不可写 —— 直接跑必然 PermissionError。
本脚本支持 SINA_ROOT 配置；运行时设置 OCR 路径并创建输出目录。
使用独立实验副本；默认拒绝处理已有输入，原图不会自动删除。

阶段说明
--------
  stage1  本地识别：YOLO 检测 + CCL 连通性 + 交叉线消歧 + easyocr 取文本
          ★ 当前官方原版启用 OCR 后也会调用视觉 API，产物在 outputs/debugging/
  stage2  LLM 环节：视觉校验 + 位号分配 + 生成网表
          ★ 需要 API 密钥（DeepSeek），产物在 outputs/test_results/
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# 必须在 import easyocr 之前设置，否则它会去写 ~/.EasyOCR 并失败
# ─────────────────────────────────────────────────────────────
WS = Path(__file__).resolve().parent.parent
EASYOCR_MODULE_PATH = Path(os.environ.get("EASYOCR_MODULE_PATH", str(WS / "SINA-venv" / "easyocr_module")))
EASYOCR_MODELS = Path(os.environ.get("EASYOCR_MODEL_DIR", str(WS / "SINA-venv" / "easyocr_models")))
EASYOCR_USER_NET = WS / "SINA-venv" / "easyocr_user_network"

os.environ.setdefault("EASYOCR_MODULE_PATH", str(EASYOCR_MODULE_PATH))
os.environ.setdefault("MODULE_PATH", str(EASYOCR_MODULE_PATH))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("YOLO_VERBOSE", "False")
# 关掉思维链，否则 DeepSeek 会把 max_tokens 烧在推理上、正文为空
os.environ.setdefault("SINA_DISABLE_THINKING", "1")

EASYOCR_MODEL_DIR = EASYOCR_MODULE_PATH / "model"


# ─────────────────────────────────────────────────────────────
# 把已下载的模型放到 easyocr 默认查找的位置，并清掉半截的 temp.zip
#
# 背景：SINA 的 CircuitOCR.__init__ 调 easyocr.Reader(['en'], gpu=True)
# 不传 model_storage_directory，于是 easyocr 回退到
# EASYOCR_MODULE_PATH/model/。该目录里只有 craft_mlt_25k.pth 而没有
# english_g2.pth，easyocr 就去下载识别模型 —— 本机下载极慢且会卡死
# （实测卡在 53% 十分钟、零网络连接、日志零增长）。
# ─────────────────────────────────────────────────────────────
def ensure_easyocr_models() -> list[str]:
    """把模型摆到 easyocr 会找的位置。返回缺失的模型名列表。"""
    moved = []
    for name in ("craft_mlt_25k.pth", "english_g2.pth"):
        target = EASYOCR_MODEL_DIR / name
        source = EASYOCR_MODELS / name
        if not target.exists() and source.exists():
            shutil.copy2(source, target)
            moved.append(name)
    # 清掉下载残留，避免 easyocr 认为"已下载"
    leftover = EASYOCR_MODEL_DIR / "temp.zip"
    if leftover.exists():
        leftover.unlink()
    missing = [n for n in ("craft_mlt_25k.pth", "english_g2.pth")
               if not (EASYOCR_MODEL_DIR / n).exists()]
    return missing


# ─────────────────────────────────────────────────────────────
# 关掉 easyocr 的自动下载
#
# 默认 download_enabled=True，缺模型时会去 GitHub 下载（本机实测会卡死）。
# 这里把 Reader 包装一层强制 download_enabled=False：缺文件时立刻报错，
# 而不是静默挂起。必须在 SINA 导入 easyocr 之前完成，因为
# CircuitOCR 用的是模块级导入的 Reader 引用。
# ─────────────────────────────────────────────────────────────
def patch_easyocr_no_download() -> None:
    try:
        import easyocr
    except ImportError:
        return
    _orig = easyocr.Reader
    if getattr(_orig, "_labpilot_patched", False):
        return

    class _NoDownloadReader(_orig):  # type: ignore[misc,valid-type]
        _labpilot_patched = True

        def __init__(self, *a, **kw):
            kw["download_enabled"] = False
            kw["gpu"] = USE_GPU
            kw.setdefault("model_storage_directory", str(EASYOCR_MODEL_DIR))
            kw.setdefault("user_network_directory", str(EASYOCR_USER_NET))
            try:
                super().__init__(*a, **kw)
            except Exception as exc:
                raise RuntimeError(
                    f"easyocr 初始化失败（已禁用自动下载）: {exc}\n"
                    f"模型目录: {EASYOCR_MODEL_DIR}\n"
                    f"若提示缺文件，请运行 tools/install_easyocr_models.py 下载模型。"
                ) from exc

    _NoDownloadReader._labpilot_patched = True
    easyocr.Reader = _NoDownloadReader



# ─────────────────────────────────────────────────────────────
# 让 pytesseract 找到 tesseract
#
# SINA 用 pytesseract 作为**辅助** OCR 引擎（主力是 easyocr）。未安装时每张图
# 会刷十几次 "tesseract is not installed or it's not in your PATH"。
# 本机当前用户不是管理员，官方安装包需要 UAC，所以走的是"解压即用"路线，
# 装在 tools/tesseract/ 下 —— 这里显式指路，不依赖系统 PATH。
# ─────────────────────────────────────────────────────────────
TESSERACT_HOME = WS / "tools" / "tesseract"


def setup_tesseract() -> str | None:
    """找到 tesseract.exe 并告知 pytesseract。返回路径，找不到返回 None。"""
    candidates: list[Path] = []

    # 1) 环境变量优先（用户可覆盖）
    if os.getenv("TESSERACT_CMD"):
        candidates.append(Path(os.environ["TESSERACT_CMD"]))
    # 2) 我们自己的解压目录
    if TESSERACT_HOME.exists():
        candidates += sorted(TESSERACT_HOME.rglob("tesseract.exe"))
    # 3) 系统 PATH
    which = shutil.which("tesseract")
    if which:
        candidates.append(Path(which))
    # 4) 常见安装位置
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
              os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe")):
        candidates.append(Path(p))

    for exe in candidates:
        if exe.is_file():
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = str(exe)
            except ImportError:
                return None
            # tessdata 目录也要指对，否则报 "Failed loading language 'eng'"
            td = exe.parent / "tessdata"
            if not td.exists():
                for alt in exe.parent.parent.rglob("tessdata"):
                    if (alt / "eng.traineddata").exists():
                        td = alt
                        break
            if td.exists():
                os.environ["TESSDATA_PREFIX"] = str(td)
            return str(exe)
    return None


USE_GPU = os.environ.get("SINA_USE_GPU", "0").lower() in {"1", "true", "yes"}

SINA = Path(os.environ.get("SINA_ROOT", str(WS / "SINA"))).expanduser().resolve()
IC = SINA / "Netlist Generator" / "IC"
ALG = IC / "program_test" / "netlist_generator_algorithm_test"

INPUTS = ALG / "inputs" / "test_images"
OUT_DEBUG = ALG / "outputs" / "debugging"
OUT_APPROVED = ALG / "outputs" / "approved_images"
OUT_RESULTS = ALG / "outputs" / "test_results"


def hr(t: str) -> None:
    print(f"\n{'=' * 76}\n{t}\n{'=' * 76}", flush=True)


def step(msg: str) -> None:
    print(f"\n>>> {msg}", flush=True)


# ─────────────────────────────────────────────────────────────
def find_model() -> Path | None:
    """按 SINA 入口的逻辑找模型：current_trained_model/train*/weights/last.pt"""
    root = IC / "current_trained_model"
    if not root.exists():
        return None
    trains = sorted([d for d in root.iterdir() if d.is_dir() and d.name.startswith("train")],
                    key=lambda d: (0 if d.name == "train" else int(d.name[5:] or 0)))
    if not trains:
        return None
    latest = trains[-1]
    for fn in ("last.pt", "best.pt"):
        p = latest / "weights" / fn
        if p.exists():
            return p
    return None


def _unlock(path: Path) -> None:
    """清除只读属性。

    实测教训：SINA 的某个库（大概率是 cv2.imwrite 覆盖已有文件）会把输入图
    设成 ReadOnly。之后再次复制或删除会报 WinError 5 / PermissionError，
    极易误判成"文件被占用"。这里在写入前主动清掉。
    """
    try:
        if path.exists() and path.is_file():
            path.chmod(0o666)
    except OSError:
        pass


def stage_inputs(count: int, image: str | None = None) -> list[Path]:
    """把测试图复制进 SINA 写死的输入目录。

    image 可以是单个图片文件，也可以是目录；不指定则从 SINA/Database 取。
    """
    INPUTS.mkdir(parents=True, exist_ok=True)

    if image:
        src_path = Path(image).expanduser().resolve()
        if src_path.is_dir():
            src = sorted(p for p in src_path.rglob("*")
                         if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
            step(f"从目录取图：{src_path}（{len(src)} 张，取前 {count} 张）")
        elif src_path.is_file():
            src = [src_path]
            step(f"使用指定图片：{src_path}")
        else:
            raise SystemExit(f"指定的图片/目录不存在：{src_path}")
    else:
        src = sorted((SINA / "Database").rglob("*.jpg"))
        step(f"从 SINA/Database 取图（共 {len(src)} 张，取前 {count} 张）")

    if not src:
        raise SystemExit("没有可用的测试图")

    picked = src[:count]
    print(f"  输入目录: {INPUTS}")
    for p in picked:
        dst = INPUTS / p.name
        _unlock(dst)                       # 先清只读，否则覆盖写会失败
        shutil.copy2(p, dst)
        _unlock(dst)
        print(f"    {p.name}  ({p.stat().st_size/1024:.0f} KB)")
    return picked


def stage1(count: int, image: str | None = None, keep_inputs: bool = False) -> int:
    """识别：YOLO + CCL + OCR；原版 OCR 阶段包含视觉 API 调用。"""
    hr("阶段 1：元件/连接/OCR 识别（原版含在线视觉 API）")

    model = find_model()
    if model is None:
        print("  [x] 找不到模型权重（current_trained_model/train*/weights/*.pt）")
        return 1
    print(f"  模型: {model.relative_to(IC)}  ({model.stat().st_size/1024/1024:.1f} MB)")

    if not keep_inputs and INPUTS.exists() and any(INPUTS.iterdir()):
        print("[停止] 输入目录非空。请使用独立 SINA 实验副本；需要混合处理时显式传 --keep-inputs。")
        return 1
    stage_inputs(count, image)
    for d in (OUT_DEBUG, OUT_APPROVED, OUT_RESULTS):
        d.mkdir(parents=True, exist_ok=True)

    os.chdir(ALG)
    sys.path.insert(0, str(ALG))
    step("导入 SINA 模块")
    try:
        from helper_files.process_images import process_all_images
    except Exception:
        traceback.print_exc()
        return 1
    print("  导入成功")

    print(f"  调用 process_all_images(use_ocr=True, use_gpu=USE_GPU, detect_crossings=True)")
    print(f"  GPU 请求: {USE_GPU}；默认 CPU，可设 SINA_USE_GPU=1")
    t0 = time.time()
    try:
        process_all_images(
            str(INPUTS), str(model), str(OUT_DEBUG),
            use_ocr=True, use_gpu=USE_GPU, detect_crossings=True,
        )
    except Exception as exc:
        print(f"\n  [x] 阶段 1 失败: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1
    dt = time.time() - t0
    print(f"\n  阶段 1 完成，耗时 {dt:.1f}s")

    hr("阶段 1 产物")
    for d in (OUT_DEBUG, OUT_APPROVED):
        files = sorted(d.rglob("*"))
        print(f"\n  {d.relative_to(ALG)}/  （{len([f for f in files if f.is_file()])} 个文件）")
        for f in files[:25]:
            if f.is_file():
                print(f"    {f.relative_to(d)}  ({f.stat().st_size/1024:.1f} KB)")
            else:
                print(f"    {f.relative_to(d)}/")
    return 0


def stage2() -> int:
    """LLM 环节：需要 API 密钥。"""
    hr("阶段 2：LLM 环节（需要 API 密钥）")

    os.chdir(ALG)
    sys.path.insert(0, str(ALG))

    if (ALG / "helper_files" / "llm_config.py").is_file():
        from helper_files.llm_config import describe_config, get_api_key
        try:
            get_api_key()
        except RuntimeError as exc:
            print(f"  [x] {exc}")
            return 1
        print(f"  配置: {describe_config()}")
    else:
        # Official snapshot uses OPENAI_API_KEY with fixed gpt-4o endpoint.
        from dotenv import load_dotenv
        load_dotenv(ALG / ".env")
        if not os.getenv("OPENAI_API_KEY"):
            print("  [x] 官方原版需要 OPENAI_API_KEY；SINA_API_* 尚未接入原版。")
            return 1
        print("  配置: 官方原版 OpenAI / gpt-4o（密钥不显示）")

    if not OUT_APPROVED.exists() or not any(p.suffix.lower() in {".jpg", ".jpeg", ".png"} for p in OUT_APPROVED.iterdir() if p.is_file()):
        print(f"\n  [!] {OUT_APPROVED.relative_to(ALG)} 里没有待确认的图。")
        print("      说明阶段 1 没有产出可确认的结果，或组件一致性校验未通过。")
        return 1

    step("导入并调用 generate_all_netlists")
    try:
        from helper_files.generate_netlists import generate_all_netlists
    except Exception:
        traceback.print_exc()
        return 1

    t0 = time.time()
    try:
        generate_all_netlists(str(OUT_APPROVED), str(OUT_DEBUG), str(OUT_RESULTS),
                              create_test_netlist=True)
    except Exception as exc:
        print(f"\n  [x] 阶段 2 失败: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1
    print(f"\n  阶段 2 完成，耗时 {time.time()-t0:.1f}s")

    hr("生成的网表")
    for p in sorted(OUT_RESULTS.rglob("*")):
        if p.is_file():
            print(f"\n  --- {p.relative_to(OUT_RESULTS)} ({p.stat().st_size} 字节) ---")
            if p.suffix in (".txt", ".cir", ".sp", ".net", ""):
                try:
                    for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:30]:
                        print(f"    {line}")
                except Exception:
                    pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="sina_lab",
        description="SINA 试验台：跑通电路图 → 网表流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools\\sina_lab.py --check            只检查环境\n"
            "  python tools\\sina_lab.py --stage 1 -n 3     跑本地识别（3 张图）\n"
            "  python tools\\sina_lab.py --stage 2          跑 LLM 环节\n"
            "  python tools\\sina_lab.py --stage all -n 1   全流程\n"
        ),
    )
    ap.add_argument("--check", action="store_true", help="只做环境检查，不跑流程")
    ap.add_argument("--stage", choices=["1", "2", "all"], default="1", help="跑哪个阶段")
    ap.add_argument("-n", "--count", type=int, default=2, help="用几张测试图（默认 2）")
    ap.add_argument("--image", default=None,
                    help="指定测试图（文件或目录）；不指定则从 SINA/Database 取")
    ap.add_argument("--keep-inputs", action="store_true",
                    help="允许处理输入目录中已有图片；默认拒绝混入旧输入")
    args = ap.parse_args()
    if args.count < 1:
        ap.error("count 必须大于 0")
    for d in (EASYOCR_MODULE_PATH, EASYOCR_MODELS, EASYOCR_USER_NET,
              EASYOCR_MODEL_DIR, EASYOCR_MODULE_PATH / "user_network"):
        d.mkdir(parents=True, exist_ok=True)
    missing = ensure_easyocr_models()
    if missing:
        print(f"[缺失] easyocr 模型: {missing}; 目录: {EASYOCR_MODEL_DIR}")
    patch_easyocr_no_download()
    setup_tesseract()

    hr("SINA 试验台")
    print(f"  工作区  : {WS}")
    print(f"  解释器  : {sys.executable}")
    print(f"  Python  : {sys.version.split()[0]}")
    print(f"  easyocr 模型路径: {EASYOCR_MODULE_PATH}")

    hr("环境自检")
    ok = True
    checks = [
        ("SINA 仓库", SINA.exists()),
        ("IC 模块", IC.exists()),
        ("算法目录", ALG.exists()),

        ("模型权重", find_model() is not None),
        ("easyocr 模型", not missing),
    ]
    for name, passed in checks:
        print(f"  {'✅' if passed else '❌'} {name}")
        ok = ok and passed
    if not ok:
        print("\n  自检未通过，先修上面的问题。")
        return 1

    step("依赖导入检查")
    for mod in ("torch", "ultralytics", "cv2", "easyocr", "requests", "dotenv"):
        try:
            m = __import__(mod)
            print(f"  ✅ {mod:<12} {getattr(m, '__version__', '?')}")
        except Exception as exc:
            print(f"  ❌ {mod:<12} {type(exc).__name__}: {exc}")
            ok = False
    if not ok:
        return 1

    if args.check:
        print("\n  环境检查通过。")
        return 0

    rc = 0
    if args.stage in ("1", "all"):
        rc = stage1(args.count, args.image, args.keep_inputs)
        if rc != 0:
            return rc
    if args.stage in ("2", "all"):
        rc = stage2()
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用户中断。")
        sys.exit(130)
