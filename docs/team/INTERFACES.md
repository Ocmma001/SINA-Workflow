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

交叉分析已复用detector传入的冻结元件框，不再内部加载YOLO；topology的weights/model_path参数仅保留调用兼容，可传None。接触点提取保留在topology_impl，pins负责有界、方向约束及歧义判定。阶段错误另写crossing_status.json；失败会在完整流程标为degraded。


## Python 接口（真实入口）

- detector.detect(image, weights, annotated_path, device='cpu', conf=.25, imgsz=960, *, iou=.7, class_conf=None, tile_size=None, overlap=.2) → (detected, confidences)。image 为 BGR 数组。detected 为 id/type/bbox/color 列表，bbox=[x1,y1,x2,y2] 原图像素。
- topology.analyze(image, detected, debug, weights, detect_crossings=True) → (circuit, labels)。labels 是 H×W 区域整数数组，0 在栅格中表示背景；它不等于电路节点地0。
- pins.attach_pins(circuit, labels, radius=5) → {id: [{image_point, connection_candidate}]}。candidate 为 {region,pixel,distance} 或 null；增加connection_alternatives、search_direction、connection_status。不同网络等距、重复触点保持null；搜索半径限定0–32像素，默认5。
- ocr.recognize(image, model_dir, user_dir, device='cpu', *, min_side=0, preprocess='none', allowlist=None) → [{text,confidence,bbox}]，bbox 为原图四个顶点，不是 xyxy。
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
旧模型对比与直接Pro检测研究入口已移除；生产入口统一为gui_workflow，单模块入口为run_stage。


## 离线推理实验参数

完整CLI/独立阶段支持`--nms-iou`、`--class-thresholds`（类别名到阈值的JSON文件）、`--tile-size`、`--tile-overlap`。分块默认关闭；元件框统一恢复到原图并按类别NMS去重。

OCR支持`--ocr-min-side`、`--ocr-preprocess none|gray|clahe`；默认不放大、不预处理。放大上限3倍，放大后总像素上限400万（原图已超出时不再放大，也不缩小原图），输出框分别按实际x/y比例恢复。Reader/检测模型缓存区分设备，模型文件尺寸/mtime变化会换缓存，可调用clear_reader_cache/clear_model_cache释放引用。

文字绑定保留原始OCR；候选增加text_binding诊断，记录距离、类型/单位约束、低置信度、远距离或歧义拒绝原因。归属函数签名兼容，原始文字不会因未绑定被删除。

`experiments/candidates/member-a-class-thresholds.json`仅为开发集候选；默认conf=.25及全局选定模型未变，不能把该候选当成独立测试结论。
