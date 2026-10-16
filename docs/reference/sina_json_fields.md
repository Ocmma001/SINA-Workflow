# SINA 产出的 JSON：字段与用途（实测记录）

本文记录 SINA IC 模块产出的 JSON 各自有什么用。**结论由读代码 + 追本次实际运行
数据得出**，不是从文件名猜的。对应 `labpilot/ingest/schematic/adapter.py` 的字段来源。

样例来自运放电路图 OPA191（759×474）的一次实际运行。

---

## 总览

| 文件 | 定位 | 内容 | 谁读 | 删掉的后果 |
|---|---|---|---|---|
| `circuit_info.json` | ★ **核心** | 元件类型 + 检测框 + 引脚坐标 | `generate_netlists`、`ocr_module` | **流程直接崩** |
| `crossing_data.json` | ★ 核心（交叉线场景） | 交叉点坐标与所涉线段 | `generate_netlists` | 交叉线消歧失效 |
| `region_to_node_mapping.json` | 辅助 | 节点区域 → 节点号 | `generate_netlists` | 节点号无法回溯 |
| `testing_all_lines.json` | 调试 | 检测到的线段 | `nodes_analysis`（只画图） | 少一张调试图 |
| `ocr_results.json` | **预留** | OCR 文本 + 置信度 + 归属 | **无人读取** | 无影响 |

位置：`outputs/debugging/<图名>/`（`crossing_data.json` 与
`region_to_node_mapping.json` 在后续阶段才产生，可能出现在 `outputs/test_results/<图名>/`）。

---

## ① circuit_info.json —— 最重要，一切靠它

```json
[
  {
    "id": "Op-Amp_1",
    "label": "Op-Amp",
    "bounding_box": [294, 219, 389, 319],
    "connection_points": [[294, 246], [294, 291], [389, 269], [342, 219], [342, 319]]
  },
  { "id": "GND_1", "label": "GND", "bounding_box": [454, 422, 504, 450],
    "connection_points": [[478, 422]] }
]
```

| 字段 | 含义 | 对 LabPilot 的价值 |
|---|---|---|
| `id` | 唯一标识，形如 `<类型>_<序号>` | 中间表示的元件主键 |
| `label` | 元件类型（10 类之一） | 决定 SPICE 器件字母（R/C/L/Q/M/V/I/X） |
| `bounding_box` | `[x1, y1, x2, y2]` | 确认表里高亮元件位置 |
| `connection_points` | **引脚在图上哪里** | ★ **连通性的唯一依据** |

### 下游怎么用它（两处消费者）

**消费者 1：`generate_netlists.py:565`（决定网表的连接关系）**

```python
components = json.load(open('circuit_info.json'))          # 全量读入

for component in components:                                # line 487 / 992
    comp_id = component["id"]
    for point in component["connection_points"]:            # line 489 / 996
        px, py = point
        is_connected, connection_point = is_point_connected_or_nearest(node_labels, px, py)
        if is_connected:
            region = node_labels[connected_py, connected_px]  # 落在哪个节点区域
```

即：**把每个 `connection_point` 投到节点标签图上，看它落在哪个连通区域，
那个区域就是这个引脚所属的节点。** 网表的"谁和谁相连"完全由这一步决定。

**消费者 2：`ocr_module.py:681`（决定图片能否进入第二阶段）**

```python
image_components = extract_components_from_image_api(...)   # 视觉模型的判断
passed = check_component_consistency(image_components, circuit_json_path, ...)
```

比对「视觉模型识别出的元件类型计数」vs「本地 YOLO 检测的计数」。
一致才把图片复制进 `outputs/approved_images/`，否则标记为待人工复查。

本次结果：视觉 6 个（电阻 3 / 电容 2 / 运放 1）vs 本地 6 个 → **通过率 100%**。

### ⚠️ `connection_points` 为空 = 元件悬空

本次实测：

```
Resistor_1  connection_points 有 2 个   ✓
Resistor_2  connection_points 有 2 个   ✓
Resistor_3  connection_points = []      ✗ ← R3（竖向放置）
```

因为下游**只靠这个字段找引脚**，`Resistor_3` 在网表里会没有任何连接。
这是目前最需要修的问题，详见
[sina_integration.md 第八节](sina_integration.md)。

---

## ② crossing_data.json —— 交叉线消歧用

当图中有导线交叉时产生。消费者是 `generate_netlists.py:583`：

```python
crossing_data = json.load(open('crossing_data.json'))
region_to_node_mapping = json.load(open('region_to_node_mapping.json'))
region_to_node_mapping = {int(k): v for k, v in region_to_node_mapping.items()}
crossing_nodes = identify_crossing_nodes(crossing_data, node_labels, region_to_node_mapping)
```

用途：找出哪些节点包含交叉点，这些节点需要走**交叉线消歧流程**
（把交叉点抹掉、分别重连两条线、用虚拟桥接元件标记，最后合并两个网表）。

注意 `region_to_node_mapping` 的键在 JSON 里是**字符串**，读回时要转回 `int`。

---

## ③ testing_all_lines.json —— 只用来画一张调试图

```json
{
  "total_lines": 20,
  "vertical_lines": 7, "horizontal_lines": 13,
  "backward_diagonal_lines": 0, "forward_diagonal_lines": 0,
  "all_lines": [
    {"start": [635, 393], "end": [635, 339], "type": "vertical"}
  ]
}
```

唯一消费者 `nodes_analysis.py:23`，只为了把线段画到
`6a_all_detected_lines_and_crossings.png` 上。**不参与网表生成**，
删掉它网表照样出，只是少一张调试图。

> 本次运行里它报告检测到 20 条线，但图里其实没有交叉点
> （`backward/forward_diagonal_lines` 都是 0），所以没触发消歧流程。

---

## ④ ocr_results.json —— 写了没人读

```json
{
  "total_text_items": 106,
  "text_with_confidence": [
    {"text": "R1", "confidence": 0.89, "center": [x, y]}
  ],
  "text_by_component": {
    "Op-Amp_1": [{"text": "V+", ...}, {"text": "V-", ...}]
  }
}
```

**全仓库没有任何地方读它。** 写入处 `process_images.py:276` 的注释自己写着：

```python
# Save OCR results to JSON for potential future integration
```

即"存下来供将来可能集成用"。当前流程不依赖它。

### 但它对 LabPilot 反而是有用的

`text_by_component` 已经**按元件把附近文本归好类**了，正是 LabPilot 的 IR 需要的
"每个元件附近有哪些位号/数值文本"这一步。所以：

- SINA 自己不用它
- **LabPilot 应该读它**，用来做"OCR 文本 → 元件"的候选配对，
  再交给视觉模型确认（或交给用户在确认表里核对）

这比让 LabPilot 自己重新做一遍文本-元件邻近分析要省事，
而且 `assign_text_to_nearest_component()` 的结果与我们看到的一致。

---

## 对 adapter.py 的具体建议

```python
# 要读
circuit_info.json          → id / label / bounding_box / connection_points
crossing_data.json         → 交叉点（若存在）
region_to_node_mapping.json→ 节点号映射（键需 int() 转换）

# 可以读（对 IR 有用）
ocr_results.json           → text_by_component 作为位号候选

# 不要读
testing_all_lines.json     → 纯调试
```

### 一个必须注意的坑

`circuit_info.json` 的 `connection_points` 若为空，LabPilot **不能静默跳过**——
应当把该元件标为"连接未知"，在确认表里要求用户手工连线。否则会生成一个
看起来正常、实际缺元件的网表，而 ngspice 不会报错（只是结果不对）。

这与 [sina_integration.md 第七节](sina_integration.md) 里"空正文检测"是同一类
问题：**SINA 的失败模式是静默的，下游必须自己加校验。**
