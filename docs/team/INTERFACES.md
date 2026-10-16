# 模块边界和文件契约

```text
原图 → detector → 检测框 ─→ topology → 连通区域/接触点 → pins
原图 → ocr → 原始文字 ───→ text_binding
              ↓ local_extract 汇总 candidates.json
可选 vision：原图 + candidates → review.json
              ↓ gui_contract
recognized.json（待确认的电路草稿）
```

## 代码归属

| 模块 | 可独立修改文件 | 不应同时修改的文件 |
|---|---|---|
| 检测 | tools/modules/detector.py、tools/train_round.py | topology_impl、gui_contract |
| OCR/参数 | tools/modules/ocr.py、text_binding.py | detector、schemas |
| 导线 | tools/modules/topology.py、topology_impl/*.py | pins、vision |
| 引脚 | tools/modules/pins.py | 原始检测框/文字 |
| 视觉复核 | tools/modules/vision.py、tools/vision_review.py、版本化候选提示词 | 原版 prompts/sina_inventory.txt、几何图结构 |
| 输出 | tools/gui_contract.py、schemas/recognized.schema.json | 各模型参数 |
| 集成 | tools/local_extract.py、gui_workflow.py、run_stage.py、model_selection.py | 未经评测的模型选择 |

当前 topology 内仍包含上游交叉分析二次 YOLO 调用；这是已知耦合点，04 应优先复用 detector 输出，避免隐藏地重复检测。当前接触点提取也仍在 topology_impl；05 先优化接触点→区域的适配，若迁移接触点提取需与04约定接口后由08合并。

## Python 接口（真实入口）

- detector.detect(image, weights, annotated_path, device='cpu', conf=.25, imgsz=960) → (detected, confidences)。image 为 BGR 数组。detected 为 id/type/bbox/color 列表，bbox=[x1,y1,x2,y2] 原图像素。
- topology.analyze(image, detected, debug, weights, detect_crossings=True) → (circuit, labels)。labels 是 H×W 区域整数数组，0 在栅格中表示背景；它不等于电路节点地0。
- pins.attach_pins(circuit, labels, radius=5) → {id: [{image_point, connection_candidate}]}。candidate 为 {region,pixel,distance} 或 null。
- ocr.recognize(image, model_dir, user_dir, device='cpu') → [{text,confidence,bbox}]，bbox 为原图四个顶点，不是 xyxy。
- text_binding.assign_text(candidates) → {id:[OCR条目]}；parse_quantity(text,kind) → SPICE可读字符串或null。
- vision.review_candidates(image, output, candidates, config=None) → review，保留输入 ID，输出建议，不改变连通区域。
- gui_contract.build_draft(candidates, review=None, artifacts=None) → schema v2 JSON。
- gui_contract.update_review_state(data, confirmed) → 新对象，修改后调用 confirmed=False 撤销确认。

## 中间产物

单模块 run_stage 工具可输出 detection.json、ocr.json、circuit_info.json/node_labels.npy、pins.json、recognized.json。
完整服务保留 candidates.json、evidence/、events.jsonl、workflow.json、recognized.json；可选 API 增加 sina-inventory.txt、review.json。
原始文字、引脚候选不能只留最终猜测；裁剪坐标恢复、图片哈希、模型哈希必须可追溯。

## 不变量

每次识别 ready_for_simulation=false，user_confirmed=false；缺值为null，无法确认的有向节点为空数组。
地符号的区域映射到电路节点"0"，地符号本身不作为器件行。原始标签编号没有电气语义。
BJT C/B/E，二极管 A/K，电源 +/-，MOS D/G/S/B；不得假定 MOS 体端与源相连。
当前下游支持范围保留于 gui_contract；MOS/运放必须保留候选并报告不支持，不能删除来通过校验。
这个仓库截止于识别草稿/确认契约；.cir 生成和仿真由外部消费者实现。

## 兼容性

保留工具旧名称 gui_workflow/gui_contract 是为了避免 GUI 调用中断，它们不依赖 Qt。
local_extract 的 --sina-root 参数保留兼容；当前本地拓扑实际使用已纳管的 modules/topology_impl，SINA快照用于训练资源/研究入口。
历史研究脚本 run_workflow、run_pro_workflow、sina_lab 不作为当前发布入口；其指标不能直接冒充新流程指标。
