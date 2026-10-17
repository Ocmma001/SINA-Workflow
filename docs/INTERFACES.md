# 工作流接口与数据契约

## 数据流

```text
原图 → detector → 元件框 → topology → 连通区域与接触点 → pins
原图 → ocr → 原始文字 → text_binding → 文字与元件关联
                         ↓ local_extract
                    candidates.json
                         ↓ gui_contract
                    recognized.json
```

完整识别入口为 `tools/gui_workflow.py`，单阶段入口为 `tools/run_stage.py`；两者不依赖桌面 GUI。

## Python 接口

| 接口 | 返回内容 |
|---|---|
| `detector.detect(image, weights, annotated_path, device='cpu', conf=.25, imgsz=960, **options)` | 元件列表与置信度映射 |
| `topology.analyze(image, detected, debug, weights, detect_crossings=True)` | 电路候选与连通区域标签图 |
| `pins.attach_pins(circuit, labels, radius=5)` | 按元件 ID 组织的引脚连接候选 |
| `ocr.recognize(image, model_dir, user_dir, device='cpu', **options)` | 原始文字、置信度与文字框 |
| `text_binding.assign_text(candidates)` | 各元件关联的 OCR 条目 |
| `gui_contract.build_draft(candidates, review=None, artifacts=None)` | schema v2 电路草稿 |
| `gui_contract.update_review_state(data, confirmed)` | 更新确认状态后的新对象 |

`image` 使用 BGR 数组。元件框是原图像素坐标 `[x1, y1, x2, y2]`；OCR 框是原图上的四个顶点。图像缩放或裁剪后必须还原坐标。元件 ID 在一次识别中保持稳定，不保证跨运行对应同一元件。

## 产物与状态

完整流程生成 `candidates.json`、`recognized.json`、`workflow.json`、`events.jsonl` 和 `evidence/`。单阶段可以生成 `detection.json`、`ocr.json`、`circuit_info.json`、`node_labels.npy` 或 `pins.json`。

工作流阶段状态和耗时写入 `workflow.json`。导线交叉分析异常会标记为降级，详细状态保存在 `evidence/debug/crossing_status.json`；产出草稿不代表所有阶段成功或识别正确。

默认模型及哈希记录在 `experiments/detector-selection.json`。默认分类阈值保存在 `experiments/candidates/member-a-class-thresholds.json`；这两个文件属于运行配置。

输出结构见 [recognized.schema.json](../schemas/recognized.schema.json)。

## 电路数据约定

- 未识别参数、型号和连接保留为 `null`，不补入图片未标注的内容。
- 不能确认有方向元件的引脚顺序时，`nodes` 留为空数组，原始连接候选保留在证据中。
- 新识别结果为待复核状态：`ready_for_simulation=false`、`user_confirmed=false`，不能自动认定为人工确认。
- 标签图的背景值 `0` 不等于电路地。只有与地符号关联的区域映射为节点字符串 `"0"`；地符号保存在证据中，不作为可编辑器件行。
- 引脚顺序：BJT 为 C/B/E，二极管为 A/K，电源为 +/-，MOSFET 为 D/G/S/B。不得假设 MOS 体端与源相连。
- 下游暂不支持的器件仍需保留候选，并明确其支持状态。
- `.cir` 生成和仿真由消费该 JSON 的应用完成。
