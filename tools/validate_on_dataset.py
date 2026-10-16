# -*- coding: utf-8 -*-
"""元件检测评估：同类 IoU 匹配，输出 precision/recall/F1。
不评估 OCR 数值、引脚语义或完整连接关系；缺源统计仅是检测提示。"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ.setdefault("YOLO_VERBOSE", "False")

WS = Path(__file__).resolve().parent.parent
IC = Path(os.environ.get("SINA_ROOT", str(WS / "SINA"))) / "Netlist Generator" / "IC"
DATA = IC / "model_training" / "data"
MODEL = IC / "current_trained_model" / "train" / "weights" / "last.pt"
OUT = WS / "tools" / "dataset_validation"


CLASS_NAMES = {0: "Resistor", 1: "Capacitor", 2: "Inductor", 3: "Transistor_BJT",
               4: "Transistor_MOSFET", 5: "Voltage_src", 6: "Current_src",
               7: "GND", 8: "Op-Amp", 9: "Diode"}

# 能进网表的元件类型（GND 合并成节点 0，不算器件）
DEVICE_CLASSES = {0, 1, 2, 3, 4, 5, 6, 9, 8}
# 提供激励的类型
SOURCE_CLASSES = {5, 6}


def hr(t: str) -> None:
    print(f"\n{'=' * 76}\n{t}\n{'=' * 76}", flush=True)


# ───────────────────────────────────────────── 标注解析
def load_labels(path: Path) -> list[tuple[int, float, float, float, float]]:
    """读 YOLO 标注：class cx cy w h（归一化）。"""
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = line.split()
        if len(p) >= 5:
            try:
                out.append((int(p[0]), *[float(x) for x in p[1:5]]))
            except ValueError:
                pass
    return out


def yolo_to_xyxy(cx, cy, w, h, W, H) -> tuple[float, float, float, float]:
    return ((cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H)


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def main() -> int:
    global DATA, MODEL, OUT
    ap = argparse.ArgumentParser(description="检测评估（不代表整图识别准确率）")
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--out", type=Path, required=True, help="每次实验使用新的结果目录")
    ap.add_argument("--split", choices=("train", "val", "test"), default="val")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--match-iou", type=float, default=0.5)
    ap.add_argument("--nms-iou", type=float, default=0.7)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    if not all(0 <= x <= 1 for x in (args.conf, args.match_iou, args.nms_iou)) or args.imgsz < 1:
        ap.error("阈值必须在 0 到 1 之间，imgsz 必须大于 0")
    DATA, MODEL, OUT = args.data.resolve(), args.model.resolve(), args.out.resolve()
    if OUT.exists() and any(OUT.iterdir()):
        ap.error("输出目录非空，请为本次实验指定新的目录")
    hr("0. 准备")
    from PIL import Image
    from ultralytics import YOLO

    pairs: list[tuple[str, Path, Path]] = []
    for split in (args.split,):
        imgdir = DATA / "images" / split
        lbldir = DATA / "labels" / split
        if not imgdir.exists():
            continue
        for img in sorted(p for p in imgdir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}):
            lbl = lbldir / (img.stem + ".txt")
            if lbl.exists():
                pairs.append((split, img, lbl))
    print(f"  图片/标注配对数: {len(pairs)}")

    if not pairs:
        print("没有图片与标注配对，请检查 data/images/<split> 和 data/labels/<split>")
        return 1
    if not MODEL.is_file():
        print(f"模型不存在: {MODEL}")
        return 1
    model = YOLO(str(MODEL))
    if dict(model.names) != CLASS_NAMES:
        raise ValueError("模型类别顺序与评估器定义不一致，请先核对类别映射")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"  模型: {MODEL.name}  类别 {len(model.names)}")

    hr("1. 逐图推理并评估")
    rows = []
    # 逐类统计 TP / FP / FN
    tp = Counter(); fp = Counter(); fn = Counter()
    t0 = time.time()

    for k, (split, img, lbl) in enumerate(pairs, 1):
        with Image.open(img) as im:
            W, H = im.size
        gt_raw = load_labels(lbl)
        gt = [(c, yolo_to_xyxy(cx, cy, w, h, W, H)) for c, cx, cy, w, h in gt_raw]

        r = model(str(img), verbose=False, conf=args.conf, iou=args.nms_iou, imgsz=args.imgsz, device=args.device)[0]
        preds = []
        for b in r.boxes:
            c = int(b.cls.item())
            conf = float(b.conf.item())
            xyxy = tuple(b.xyxy[0].tolist())
            preds.append((c, conf, xyxy))

        # 按 IoU 0.5 做贪心匹配（同类才匹配）
        used_gt = set()
        matched = 0
        for c, conf, box in sorted(preds, key=lambda x: -x[1]):
            best, bi = 0.0, None
            for i, (gc, gb) in enumerate(gt):
                if i in used_gt or gc != c:
                    continue
                v = iou(box, gb)
                if v > best:
                    best, bi = v, i
            if best >= args.match_iou and bi is not None:
                used_gt.add(bi)
                tp[c] += 1
                matched += 1
            else:
                fp[c] += 1
        for i, (gc, _) in enumerate(gt):
            if i not in used_gt:
                fn[gc] += 1

        # ---- 结构可转换性检查
        n_dev = sum(1 for c, _ in gt if c in DEVICE_CLASSES)
        n_src = sum(1 for c, _ in gt if c in SOURCE_CLASSES)
        n_pred_src = sum(1 for c, _, _ in preds if c in SOURCE_CLASSES)
        gt_classes = {c for c, _ in gt}
        pred_classes = {c for c, _, _ in preds}

        rows.append({
            "split": split,
            "image": img.name,
            "gt_total": len(gt),
            "pred_total": len(preds),
            "matched": matched,
            "gt_devices": n_dev,
            "gt_sources": n_src,
            "pred_sources": n_pred_src,
            "gt_has_opamp": int(8 in gt_classes),
            "pred_has_opamp": int(8 in pred_classes),
            "gt_classes": "|".join(CLASS_NAMES[c] for c in sorted(gt_classes)),
            "pred_classes": "|".join(CLASS_NAMES[c] for c in sorted(pred_classes)),
            "no_source_detected": int(n_pred_src == 0),
            "missing_source_vs_gt": int(n_src > 0 and n_pred_src == 0),
        })

        if k % 50 == 0 or k == len(pairs):
            dt = time.time() - t0
            print(f"  {k}/{len(pairs)}  已用 {dt:.0f}s  预计剩余 "
                  f"{dt / k * (len(pairs) - k):.0f}s", flush=True)

    # ───────────────── 汇总：检测质量
    hr(f"2. 检测质量（IoU {args.match_iou} 贪心匹配）")
    print(f"  {'类别':<20} {'GT':>6} {'TP':>6} {'FP':>6} {'FN':>6} "
          f"{'precision':>10} {'recall':>8} {'F1':>7}")
    tot_tp = tot_fp = tot_fn = 0
    per_class = []
    for cid in sorted(CLASS_NAMES):
        n_gt = tp[cid] + fn[cid]
        if n_gt == 0 and fp[cid] == 0:
            continue
        p = tp[cid] / (tp[cid] + fp[cid]) if (tp[cid] + fp[cid]) else 0.0
        rc = tp[cid] / n_gt if n_gt else 0.0
        f1 = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        tot_tp += tp[cid]; tot_fp += fp[cid]; tot_fn += fn[cid]
        per_class.append((CLASS_NAMES[cid], n_gt, tp[cid], fp[cid], fn[cid], p, rc, f1))
        print(f"  {CLASS_NAMES[cid]:<20} {n_gt:>6} {tp[cid]:>6} {fp[cid]:>6} {fn[cid]:>6} "
              f"{p:>10.3f} {rc:>8.3f} {f1:>7.3f}")
    P = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else 0
    R = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) else 0
    F = 2 * P * R / (P + R) if (P + R) else 0
    print(f"  {'【总体】':<20} {tot_tp+tot_fn:>6} {tot_tp:>6} {tot_fp:>6} {tot_fn:>6} "
          f"{P:>10.3f} {R:>8.3f} {F:>7.3f}")

    # ───────────────── 汇总：可转换性
    hr("3. 电源检测提示（不代表拓扑正确性）")
    n = len(rows)
    no_src = sum(r["no_source_detected"] for r in rows)
    miss_src = sum(r["missing_source_vs_gt"] for r in rows)
    gt_has_src = sum(r["gt_sources"] > 0 for r in rows)
    opamp_gt = sum(r["gt_has_opamp"] for r in rows)
    opamp_pred = sum(r["pred_has_opamp"] for r in rows)
    print(f"图片 {n}；未检测到源 {no_src}；相对标注漏掉所有源 {miss_src}")
    print("此脚本不检测连接点、OCR 或完整网表，不判断仿真是否为零。")

    # ───────────────── 保存
    hr("4. 保存结果")
    csv_path = OUT / "per_image.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  逐图结果: {csv_path}  ({len(rows)} 行)")

    summary = {
        "images": n,
        "evaluation": {"scope": "component_detection_only", "split": args.split, "data": str(DATA), "model": str(MODEL), "conf": args.conf, "match_iou": args.match_iou, "nms_iou": args.nms_iou, "imgsz": args.imgsz, "device": args.device},
        "detection": {
            "overall": {"precision": P, "recall": R, "f1": F,
                        "tp": tot_tp, "fp": tot_fp, "fn": tot_fn},
            "per_class": [
                {"class": a, "gt": b, "tp": c, "fp": d, "fn": e,
                 "precision": f, "recall": g, "f1": h}
                for a, b, c, d, e, f, g, h in per_class
            ],
        },
        "source_detection_hints": {
            "images_with_gt_source": gt_has_src,
            "images_without_detected_source": no_src,
            "images_source_missed": miss_src,
            "images_gt_opamp": opamp_gt,
            "images_pred_opamp": opamp_pred,
        },
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  汇总: {OUT}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
