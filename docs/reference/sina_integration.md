# SINA 集成说明

[SINA](https://github.com/medal-ece/SINA) 是犹他大学 MEDAL 实验室的开源项目，把电路原理图
图片转换成 IC / PCB 级网表（YOLO 检测元件 + Connected-Component Labeling 推连通性 +
交叉线消歧 + OCR/VLM 分配位号）。LabPilot 用它补上「电路图 → 网表」这一步。

> 论文：[SINA: A Fully Automated Circuit Schematic Image to Netlist Generator Using Artificial Intelligence](https://ar5iv.labs.arxiv.org/html/2607.01609)（arXiv:2607.01609）

---

## 一、SINA 放在哪里

**不要**把 SINA 的源码拷进 `LabPilot/`。它目录名含空格与中文、脚本是直接运行式写法、
没有 `pyproject.toml`，内联会踩硬编码路径与包名冲突。按第三方工具对待：

```
C:\Users\lenovo\Documents\deepseek-harness\default-workspace\SINA\    ← 独立检出
LabPilot\                                                              ← 本项目
```

在 `.env` 里指明位置：

```env
SINA_ROOT=C:\Users\lenovo\Documents\deepseek-harness\default-workspace\SINA
```

`availability.py` 会在启动自检时读取它，验证 SINA 是否可调用。

### 关于仓库体积

完整克隆约 **2.2 GB**，其中绝大部分是 `Database/` 下的 700+ 张标注原理图。
**你不重新训练模型的话并不需要它们。** 若磁盘吃紧，可用稀疏检出只取代码：

```bash
git clone --filter=blob:none --sparse https://github.com/medal-ece/SINA.git
cd SINA
git sparse-checkout set "Netlist Generator"
```

---

## 二、环境前提（SINA 侧）

SINA 自身不是开箱即用的，以下依赖必须先装好：

| 依赖 | 用途 | 离线可用 |
|---|---|---|
| `ultralytics` | YOLOv8/v11 元件检测 | ✅ 本地权重 |
| `opencv-python` | CCL、形态学、交叉线检测 | ✅ |
| `easyocr` | 提取位号与数值 | ✅（首次需下载模型） |
| `openai` | GPT-4o 做元件校验、位号分配、**最终网表生成** | ❌ 需 Key |
| `google-cloud-vision` | PCB 文字去除 | ❌ 需凭据 |

### ⚠️ 本项目已确认接受联网依赖

SINA 的位号分配与最终网表生成依赖 GPT-4o，PCB 路径还依赖 Google Cloud Vision。
**因此 LabPilot 的电路图识别功能无法离线使用。**

这直接影响答辩风险：计划书第 9 页要求"准备固定实验样例、离线数据和完整演示录像"
来应对现场环境故障。既然识别环节联网，就必须：

1. **至少一条演示线不依赖识别** —— 预先录好 SINA 对固定样例电路的输出
   （放 `data/samples/schematic/`），演示时可跳过调用直接加载
2. **完整演示录像必须包含识别成功的那一次** —— 现场网络出问题时放录像
3. 界面上明确标注当前结果来自"实时识别"还是"预录结果"

---

## 三、架构：子进程包装 + 网表由我们自己生成

### ⚠️ 关键事实：SINA 输出的"网表"不能直接仿真

已在 `medal-ece/SINA` 的 main 分支（commit `a4f13885`）上实测确认：

| 检查项 | 结果 |
|---|---|
| 全仓库 `.subckt` 定义 | **0 个** |
| 全仓库 `.model` 定义 | **0 个** |
| `.cir` 输出中的分析指令（`.op/.dc/.ac/.tran`） | **一个都没有** |
| 元件值 | **没有**。只有位号与节点名 |

看一个真实输出 `PCB/other/Results/spice_netlists/circuit001.cir`：

```spice
* SPICE netlist for circuit001.png
X1 N1 MISO SCK MOSI RST 2X3THM SUBCKT
X2 C1 C1 C1 100uF 0.1uF N2 SUBCKT
R6 RST N4 1k
.end
```

三个致命问题：

1. **`X` 卡的子电路名是字面量 `SUBCKT`** —— 全仓库没有任何 `.subckt SUBCKT` 定义，
   ngspice 会直接报 "unknown subckt"
2. **电阻被硬编码成 `1k`** —— 这不是识别出来的值，是脚本里的占位默认值
3. **存在两端同节点的元件** —— 实测 6 个 `.cir` 中：`R9 GND GND 1k`、`R15 OND OND 1k`、
   `R20 GND GND 1k`。这是短路，语法上就不合法

抽查统计：

| 文件 | 元件数 | `.end` | 分析指令 | 两端同节点的 R |
|---|---|---|---|---|
| circuit001 | 6 | ✓ | ✗ | 0 |
| circuit002 | 27 | ✓ | ✗ | 1 |
| circuit003 | 34 | ✓ | ✗ | 13 |
| circuit004 | 4 | ✓ | ✗ | 0 |
| circuit005 | 20 | ✓ | ✗ | 4 |
| circuit006 | 9 | ✓ | ✗ | 0 |

**结论：SINA 的 `.cir` 输出是一张"拓扑图"，不是一份可仿真网表。**
它含连接关系，但不含任何让 ngspice 能算出数值的东西。

### 因此架构必须这样切

```
电路图 PNG
   │
   ▼
sina_runner.py       子进程调用 SINA（详见第四节）
   │
   ▼
adapter.py           ★ 只取拓扑：元件、位号、节点、连接
   │                 丢弃它那个不能用的 SPICE 文本
   ▼
ir.py                中间表示 = 拓扑 + 待补的元件值/类型
   │
   ▼
confirm.py           ★ 用户确认拓扑 + 补齐元件值、类型、器件模型
   │
   ▼
engine/netlist.py    ★ 由 LabPilot 自己生成可仿真网表
                     （补元件值、.model、器件类型、.op/.dc/.ac/.tran）
   │
   ▼
ngspice              真正的仿真
```

一句话：**SINA 负责"看见拓扑"，LabPilot 负责"变成能算的电路"。**

这个切分与计划书第 9 页的范围控制原则完全一致——"首版允许用户确认节点和器件参数"。
而且因为 SINA 本来就不给元件值，确认这一步**不再是可选的谨慎措施，而是必需步骤**。

选子进程包装的理由：SINA 用相对路径写死、`py script.py` 直接运行、且更新频繁。
隔离后 SINA 崩了不会拖垮 LabPilot，它换版本也不用改我们的代码。

### 为什么必须有 confirm 这一步

SINA 论文自报整体网表准确率 **96.67%**——但换算过来是**每 30 个元件约有 1 个错**，
且错误常出现在拓扑层（交叉线消歧、位号错配）。错一个连接，整个仿真结果就失去意义，
而 LabPilot 的全部价值建立在"ngspice 给出**正确**数值"这个前提上。

计划书本身也已定调（第 9 页）：「电路图自动识别不稳定 → 首版允许用户确认节点和器件
参数，**不把全自动识图作为 P0**」。

所以：**SINA 的输出永远不直接进 ngspice**，中间必须有一张用户可编辑的确认表。
这同时是个答辩亮点——展示"AI 提议 → 人确认 → 工具验证"的完整可信链条。

---

## 四、已核实的事实（2026-10-15 实测）

> 探测脚本：`python tools\probe_sina.py --root "<SINA 路径>"` 与
> `python tools\inspect_sina.py`。以下结论均由它们产出，不是照文档猜的。

检出位置：`C:\Users\lenovo\Documents\deepseek-harness\default-workspace\SINA`
分支 `main`，commit `a4f13885`，27514 个对象 / 2977 个文件检出，仓库 2.17 GiB。

### 两个模块的调用方式完全不同

**IC 模块：硬编码路径，无命令行参数。**

`Netlist Generator/IC/program_test/netlist_generator_algorithm_test/netlist_generator.py`
全文只有 1813 字节，逻辑是：

```python
script_dir   = <该脚本所在目录>
PROJECT_PATH = script_dir 上两级          # = Netlist Generator/IC

model_folder  = PROJECT_PATH/current_trained_model      # 取 train* 里编号最大的
latest_model  = <该目录>/weights/last.pt               # ← 用 last.pt，不是 best.pt
test_images   = script_dir/inputs/test_images          # ← 输入图放这里
debug_output  = script_dir/outputs/debugging
approved      = script_dir/outputs/approved_images
test_results  = script_dir/outputs/test_results
```

调用要点：

- **必须先往 `inputs/test_images/` 放图**，否则它读不到任何东西
- 固定 `use_ocr=True, use_gpu=True, detect_crossings=True`
- **`use_gpu=True` 是写死的**，没有 GPU 时是否自动回退需实测
- 用 `last.pt` 而非 `best.pt`（仓库里两者都在，各 38.6 MB）
- 中途会停在 `outputs/approved_images` 等人工确认，再跑 `generate_all_netlists`

因此 `sina_runner.py` 不能用传参方式，只能：**建好目录结构 → 放图 → 设 cwd → 执行 → 收输出**。

**PCB 模块：有完整的 argparse，可直接传参。**

`Netlist Generator/PCB/all models/Final/index.py` 实测参数：

| 参数 | 说明 |
|---|---|
| `--input` | 原始图片文件夹 |
| `--output` | 文字去除后的图片 |
| `--weights` | YOLO 符号检测权重 |
| `--yolo-conf` | 置信度阈值（默认 0.7） |
| `--netlist-output` | JSON 网表输出（默认 `netlists_json`） |
| `--spice-json-dir` | 要转 SPICE 的 JSON 目录 |
| `--spice-output` | SPICE `.cir` 输出（默认 `spice_netlists`） |
| `--pin-output` | 引脚检测结果 |
| `--expand` / `--sat` / `--val` / `--scale` / `--method` | 文字去除调参 |

同目录还有分工明确的模块：`jsonnetlists.py`、`pin.py`、`spice.py`、`text_removal.py`。

⚠️ PCB 依赖 `credentials.json`（Google Cloud Vision，联网）。

### 输出格式

**PCB JSON**（`PCB/other/Results/netlists_json/circuit001.json`）——结构清晰，可作为 IR 的主要来源：

```json
{
  "image": "circuit001.png",
  "components": [
    {
      "component_id": 1,
      "bbox": [209, 239, 302, 300],
      "pin_count": 6,
      "pins": [
        { "x": 277, "y": 237, "label": "" },
        { "x": 207, "y": 256, "label": "MISO" }
      ],
      "connected": [...]
    }
  ]
}
```

**IC 中间产物**（`helper_files/generate_netlists.py`，1186 行）：
`circuit_info.json`、`crossing_data.json`、`region_to_node_mapping.json`，
最终输出到 `outputs/test_results/`。

关键函数揭示了完整流程，也说明交叉线消歧是最复杂的一环：

```
generate_netlist_for_image            overlay_and_find_nodes_with_connected_regions
generate_all_netlists                 find_nearest_edge
identify_crossing_nodes               is_point_connected_or_nearest
create_crossing_enhanced_netlist      generate_crossing_disambiguation_images_and_netlists
run_pipeline_on_disambiguation_image  generate_disambiguation_netlist
merge_bridge_connected_nodes          clean_crossing_netlist
renumber_nodes_sequentially           fix_mosfet_nodes
```

### 依赖与模型权重

`Netlist Generator/IC/requirements.txt` 原文：

```
ultralytics  opencv-python  easyocr  numpy  matplotlib  scikit-learn
scipy  requests  python-dotenv  networkx  pytesseract
```

**权重齐全，不需要自己训练**：

| 文件 | 大小 |
|---|---|
| `IC/current_trained_model/train/weights/best.pt` | 38.6 MB |
| `IC/current_trained_model/train/weights/last.pt` | 38.6 MB |
| `PCB/all models/Final/model/best.pt` | 50.7 MB |
| `PCB/Model training/yolov8m-pose.pt` | 50.8 MB |

`Database/` 实测只有 **25 MB**（不是之前担心的 2 GB）——仓库体积主要是模型权重与
`.git` 历史。

### IC 模块官方安装方式

```bash
cd "Netlist Generator/IC"
.\setup_windows.bat <your_openai_api_key>
```

README 明确要求 **Python 3.12**（3.13 可能有问题）与 **OpenAI API key**，
训练另需 CUDA GPU。本机 harness 环境正好是 **Python 3.12.14**，版本匹配。

---

## 五、环境已装好（2026-10-15 完成）

### ✅ 可用环境

```
虚拟环境:  C:\Users\lenovo\Documents\deepseek-harness\default-workspace\SINA-venv
解释器:    SINA-venv\Scripts\python.exe
Python:    3.11.0        （系统自带，非 harness 的 3.12）
torch:     2.14.1+cpu    （CPU 版，118 MB）
ultralytics: 8.4.177
easyocr:   1.7.2         （模型已重定向到工作区）
```

13 个包全部导入通过：`torch torchvision ultralytics cv2 easyocr openai numpy
matplotlib scipy sklearn networkx dotenv pytesseract`

### ✅ 模型实测可加载可推理

**IC 模型**（`IC/current_trained_model/train/weights/best.pt`）——10 个类别，
**完全覆盖计划书的模电实验范围**：

| 类别 | 对应计划书场景 |
|---|---|
| `Resistor` `Capacitor` `Inductor` | 静态工作点、RC 电路 |
| `Transistor_BJT` | 共射放大器、偏置分析 |
| `Transistor_MOSFET` | 扩展场景 |
| `Voltage_src` `Current_src` | 供电与偏置 |
| `GND` | 接地合并（CCL 节点归并） |
| `Op-Amp` | 运算放大器实验 |
| `Diode` | 伏安特性、限幅电路 |

实测推理（`Database/001-099/circuit_0001.jpg`）：

```
Diode               conf=0.855
Resistor            conf=0.844
Resistor            conf=0.833
Transistor_MOSFET   conf=0.583
```

耗时 0.2–2.8 秒/张（CPU）。

**PCB 模型**（`PCB/all models/Final/model/best.pt`）——**只有 1 个类别 `Rectangle`**。
这印证了论文说的"PCB 级原理图由矩形离散元件构成"：它只负责框出矩形，
元件类型靠引脚与文字推断。

### ⚠️ 已知限制

| 限制 | 说明 | 影响 |
|---|---|---|
| **无 CUDA** | `torch.cuda.is_available() == False`，装的是 CPU 版 | 推理慢但不影响正确性；SINA 入口写死的 `use_gpu=True` 需实测能否回退 |
| **Python 3.11 而非 3.12** | SINA 官方要求 3.12 | 实测模型加载与推理正常，暂无问题；若遇到冷门 API 差异再处理 |
| **easyocr 模型目录** | 默认 `%USERPROFILE%\.EasyOCR` 不可写 | 已用 `model_storage_directory` 重定向；LabPilot 侧必须显式传这个参数 |

### 为什么不用 harness 的 Python 3.12

定位过程（`tools/diagnose_pip.py` 的测试矩阵）：

| 测试 | 结果 |
|---|---|
| Python 直接写 workspace 临时目录 | ✅ OK |
| `tempfile.mkdtemp` 建目录 | ✅ OK |
| **向该新建目录写入 wheel 文件** | ❌ **PermissionError** |
| 用户 Python 3.11 执行同样的 pip download | ✅ **OK** |

即：**harness 自带的 Python 3.12 在"向新建子目录写入文件"时必现 PermissionError**，
与 pip 无关，与沙箱权限也无关（同目录手工建目录、写文件、重命名、删除全部正常）。
修它的性价比很低，直接用系统里的 3.11 更快。

### 各下载源的实际速率（判断"慢"时先看这张表）

| 源 | 实测速率 | 用途 |
|---|---|---|
| 清华 PyPI 镜像 | **15–18 MB/s** | pip 装包 |
| PyTorch 官方 CDN | 35 KB/s – 16 MB/s（波动极大） | torch |
| GitHub 仓库克隆 | **1.76 MiB/s** | SINA 2.17 GB，约 25 分钟 |
| GitHub 发行版下载 | **14.9 KB/s ～ 1.83 MB/s** | easyocr 模型，最不稳定 |

⚠️ **GitHub releases 的速率会在几分钟内剧烈波动**：同一批 URL 第一次测是
14.9 KB/s，重测变成 1830 KB/s（**123 倍**）。且国内代理镜像
（ghproxy 84 KB/s、gh-proxy 146 KB/s、ghfast 127 KB/s；
moeyy / gitmirror 直接 TLS 失败、hf-mirror 502）**全部慢于直连**。

**结论：遇到 GitHub 下载慢，先杀掉重试，不要急着换镜像** ——
大概率是临时限速，而非稳定瓶颈。

### ✅ easyocr 已就位（模型 + 目录重定向）

模型（直连 GitHub releases 下载，比各国内代理都快）：

| 文件 | 大小 | 来源 |
|---|---|---|
| `craft_mlt_25k.pth` | 79.3 MB | CRAFT 文字检测 |
| `english_g2.pth` | 14.4 MB | 英文识别 |

实测 OCR 效果（`Database/001-099/circuit_0003.jpg`）：

```
'IRF9530'   conf=0.99     ← 器件型号
'2N3904'    conf=0.99     ← 器件型号
'47 0'      conf=0.90     ← 47Ω（Ω 被识别成 0）
'100 Q'     conf=0.60     ← 100Ω
```

位号与器件型号识别可靠；**阻值里的 Ω 易被误读**（`47Ω`→`47 0`），
确认表里应把数值列标为需人工核对。

### ⚠️ easyocr 的三个目录必须都设

`easyocr.py` 第 55–65 行：

```python
self.model_storage_directory = MODULE_PATH + '/model'
if model_storage_directory:  self.model_storage_directory = model_storage_directory

self.user_network_directory = MODULE_PATH + '/user_network'
if user_network_directory:   self.user_network_directory = user_network_directory
```

`MODULE_PATH` 来自环境变量 `EASYOCR_MODULE_PATH`（优先）或 `MODULE_PATH`，缺省 `~/.EasyOCR`。
后两个参数**只是它的分别覆盖**——只传 `model_storage_directory` 时，
`user_network_directory` 仍会去写 `%USERPROFILE%\.EasyOCR` 然后 PermissionError。

所以 `sina_runner.py` 必须设置：

```python
os.environ["EASYOCR_MODULE_PATH"] = "<可写目录>"
reader = easyocr.Reader(lang_list, gpu=False,
                        model_storage_directory=...,
                        user_network_directory=...,
                        download_enabled=False)   # 离线时禁下载
```

---

## 六、本机其他环境障碍（与 SINA 无关，但会影响开发）

### Schannel 故障影响 git / curl / winget

`%APPDATA%\Microsoft\Crypto` 不可写 → Schannel 无法获取 TLS 凭据：

```
schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)
```

表现为 TCP 443 可连通、HTTP 正常，但**所有 HTTPS 失败**。

**已修复**（`tools/fix-git-tls.ps1`）：让 git 改用自带 OpenSSL，并指向从
Windows 证书库导出的 PEM。

> 注意：公共 CA 包（curl.se/cacert.pem，121 张）**不够**，会报
> `unable to get local issuer certificate`。必须导 Windows 证书库
> （80 张，含本机注入的根证书）才通过。

### 磁盘空间无法查询

`Get-Volume`、`Get-CimInstance Win32_LogicalDisk`、`fsutil volume diskfree` 全部返回
"拒绝访问"。目前 SINA 仓库 3.94 GB + SINA-venv 约 1 GB。若后续要装 CUDA 版 torch
（+2.5 GB），请先用文件资源管理器确认剩余空间。

---

## 七、更换 AI 供应商 —— 已实施并实测通过（DeepSeek）

> **状态：已改完、已用真实密钥端到端跑通。** 原先硬编码的 `gpt-4o` +
> `api.openai.com` 已全部替换为读环境变量。

### 7.1 实际改动

新增共享配置模块（`helper_files/` 已在 import 路径上，两个调用点共用）：

```
SINA/Netlist Generator/IC/program_test/netlist_generator_algorithm_test/helper_files/llm_config.py
```

| 文件 | 原内容 | 现内容 |
|---|---|---|
| `ocr_module.py:129` | `os.getenv("OPENAI_API_KEY")` + 抛错 | `from helper_files.llm_config import ...` |
| `ocr_module.py:219` | `"model": "gpt-4o"` + `api.openai.com` | `build_request(prompt, image_block, 1800)` |
| `generate_netlists.py:76` | 同上 | 同上 |
| `generate_netlists.py:321` | 同上 | `build_request(prompt, image_block, 1500)` |

原始文件备份在 `tools/sina_original_backup/`。

### 7.2 ⚠️ 模型 ID 是 `deepseek-flash`，不是 `deepseek-v4.1-flash`

第一版按文档推断写成 `deepseek-v4.1-flash`，API 直接回：

```json
{"error": {"message": "The supported API model names are deepseek-flash,
 deepseek-v4-pro, but you passed deepseek-v4.1-flash."}}
```

**正确答案：`deepseek-flash`**（即 "DeepSeek V4.1 Flash (max)"），备选 `deepseek-v4-pro`。
API 的报错比任何文档都权威——模型 ID 拿不准时，直接发一次请求问它。

### 7.3 ⚠️ 必须关闭思维链，否则内容为空（最关键的发现）

`deepseek-flash` 是**推理型模型**。面对 SINA 的长提示词，它会把整个
`max_tokens` 额度烧在思维链上，**正文返回空字符串**。而 SINA 只读
`message['content']`，于是**不报错、只是网表里没有位号**——静默失效。

实测（同一张图、同一提示词、`max_tokens=1800`）：

| 参数 | reasoning_tokens | content | 结论 |
|---|---|---|---|
| （不加） | 1800 | **0 字符** | ❌ |
| **`thinking={"type":"disabled"}`** | **0** | **483 字符** | ✅ **采用，且快 3 倍** |
| `reasoning_effort="none"` | 0 | 458 字符 | ✅ 可用但慢 |
| `enable_thinking=False` | 1800 | 0 字符 | ❌ 参数被忽略 |
| `reasoning_effort="minimal"` | 1800 | 0 字符 | ❌ 无效 |
| `max_tokens=8000` | 1822 | 562 字符 | ✅ 但贵 16 倍 |

采用 `thinking={"type":"disabled"}`，由 `SINA_DISABLE_THINKING`（默认 1）控制。
另外新增了**空正文检测**：再出现这种情况会抛带诊断信息的 `RuntimeError`，
而不是把空字符串一路传下去生成没有位号的网表。

### 7.4 实测性能

| 指标 | 值 |
|---|---|
| 延迟 | **3.0 – 4.9 秒/张**（关闭思维链后；开启时 14.6 秒） |
| 输入 token | 约 520（含 99 KB 图片） |
| 输出 token | 约 120 |
| 识别质量 | 元件类型、符号描述、位号、数值都对（`R1: 47 Ω`、`Q1: 2N3904`、`M1: IRF9530`） |

### 7.5 ⚠️ SINA 的解析正则太窄（非 DeepSeek 特有）

`generate_netlists.py:84` 用这个正则提取元件行：

```python
re.findall(r"\)\s*[A-Za-z]+\d*:", line)   # 注意 [A-Za-z]+\d*
```

它**不接受下划线和空格**，也**要求以数字结尾**。实测对比：

| 模型输出 | 能否匹配 | 原因 |
|---|---|---|
| `...description)R1: 47 Ω` | ✅ | |
| `...description)Q1: 2N3904` | ✅ | |
| `...description)M1: IRF9530` | ✅ | |
| `...description)R_IN:` | ❌ | **下划线**不在 `[A-Za-z]` 中 |
| `...description)R_L:` | ❌ | 同上 |
| `...description)Flywheel diode:` | ❌ | 含**空格** |
| `...description)MOSFET:` | ❌ | 无数字 |

实测 3 张图：**2 张产出可解析的元件行，1 张（全部位号带下划线）产出 0 行**。

这**不是 DeepSeek 造成的**——gpt-4o 若把位号写成 `R_IN` 同样会被丢弃。
影响是：被丢弃的元件不会出现在最终网表里，**不报错**。

**处理建议（按优先级）**：

1. 改提示词，明确要求位号形如 `字母+数字`（`R1` 而非 `R_IN`），且描述与位号**同一行**
2. 放宽正则，例如 `r"\)\s*([A-Za-z][A-Za-z0-9_ ]*?)\s*:\s*(.*)$"`，
   并在 IR 层做位号归一化
3. 无论如何都要**统计"声明元件数 vs 实际解析数"并在不一致时报错**——
   目前 SINA 不比对，静默丢元件

> 注意：与"已确认的事实"里 `check_component_consistency()` 的交叉校验不同，
> 那个函数比的是**类型计数**；这里丢的是**整行标签**，两者不重叠。

### 7.6 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `LABPILOT_API_KEY` | — | "指针"变量，值为下面某个变量名 |
| `DEEPSEEK_API_KEY` | — | 当前生效的密钥 |
| `OPENAI_API_KEY` | — | 备用 |
| `SINA_API_BASE` | `https://api.deepseek.com` | 自动补 `/v1/chat/completions` |
| `SINA_API_MODEL` | `deepseek-flash` | ⚠️ 不是 `deepseek-v4.1-flash` |
| `SINA_API_TIMEOUT` | `60` | 原 `ocr_module` 写死 30 秒，偏短 |
| `SINA_VISION` | `1` | 设 0 则不发送图片 |
| `SINA_DISABLE_THINKING` | `1` | **必须保持 1**，否则正文为空 |

### 7.7 密钥的存放位置（重要）

密钥放在**工作区根目录的 `.env`**，刻意放在 SINA 仓库**之外**。
原因：SINA 是从 GitHub 克隆的真 git 仓库，根目录没有 `.gitignore`，
密钥写进去有被误提交的风险。

已在 `SINA/.gitignore` 补上 `.env` 等忽略规则作为第二道防线。

`llm_config.load_env()` 用**绝对路径**（从 `__file__` 上溯 6 层）查找 `.env`，
不依赖当前工作目录——因为 SINA 的入口脚本会先 `cd` 到自己的目录。

---

## 八、跑起来：试验台与实测结果

### 8.1 试验台

```
tools/sina_lab.py        主脚本
tools/test_images/       放自己的电路图
```

在 **cmd** 里跑：

```cmd
cd /d C:\Users\lenovo\Documents\deepseek-harness\default-workspace
SINA-venv\Scripts\python.exe tools\sina_lab.py --check
SINA-venv\Scripts\python.exe tools\sina_lab.py --stage 1 --image tools\test_images\你的图.jpg
SINA-venv\Scripts\python.exe tools\sina_lab.py --stage 2
SINA-venv\Scripts\python.exe tools\sina_lab.py --stage all -n 1
```

`--stage 1` 是本地识别（不需要密钥），`--stage 2` 才调 LLM。

### 8.2 实测结果（运放电路 OPA191，759×474）

三个引擎的结论**完全一致**，一致性校验通过：

```
Component Consistency Check
  API (视觉模型)   : Capacitor 2, Op-Amp 1, Resistor 3   共 6
  Object Detection : Capacitor 2, Op-Amp 1, Resistor 3   共 6
→ Pass Rate 100%，图片进入 approved_images
```

YOLO 检出 10 个目标（运放 1 + GND 4 + 电阻 3 + 电容 2），与肉眼点数一致。

视觉模型输出：

```
R1: 1.00k   R2: 1.00k   R3: 10.0k   C1: 0.1µF   C2: 0.1µF
U1A: OPA191
types: Resistor 3, Capacitor 2, Op-Amp 1
```

**位号与数值全部正确。** 另外上一节担心的"`U1A` 因正则 `[A-Za-z]+\d*` 尾部字母被丢"
**实测没有发生** —— easyocr 以 0.91 置信度正确识别 `U1A`，整行正常进入解析。

耗时与产物：

| 项 | 结果 |
|---|---|
| 交叉线检测 | 20 条线（7 垂直 / 13 水平 / 0 对角） |
| easyocr | 44 个文本项 |
| 产出 | `outputs/debugging/<图名>/` 下 30 个文件（含各阶段可视化 PNG） |

### 8.3 跑通过程中踩到的四个坑（都已修）

**坑 1：easyocr 会静默下载模型并卡死（最严重）**

`CircuitOCR.__init__` 调 `easyocr.Reader(['en'], gpu=True)` **不传
`model_storage_directory`**，于是回退到 `EASYOCR_MODULE_PATH/model/`。
该目录只有 `craft_mlt_25k.pth` 而没有 `english_g2.pth`，easyocr 就去下载识别模型。

实测表现：**卡在 `Progress: 53%` 十几分钟、进程零网络连接、日志零增长**，
极易误判成"死锁"或"CPU 太慢"。

修复（`sina_lab.py` 顶部，必须在 SINA 导入 easyocr 之前）：

1. 把模型从 `SINA-venv/easyocr_models/` 复制到 `easyocr_module/model/`
2. 清掉半截的 `temp.zip`（否则 easyocr 认为已下载）
3. **包装 `easyocr.Reader`**，强制 `download_enabled=False` 并显式指定三个目录

修好后 Reader 构建从"卡死十几分钟"变成 **1.3 秒**。

**坑 2：输入图被设成只读，导致二次运行报 WinError 5**

SINA 的某个库（大概率是 `cv2.imwrite` 覆盖已有文件）会把输入图设成 `ReadOnly`。
再次运行时报：

```
PermissionError: [WinError 5] 拒绝访问。: '...\inputs\test_images\xxx.jpg'
```

删除和写入都失败，**极易误判成文件被占用**。实测用 `[System.IO.File]::Open`
独占打开也失败，看起来更像锁——但真正原因是只读属性。

修复：`sina_lab.py` 在复制/删除前主动 `chmod`。

**坑 3：Tesseract 未安装（不致命，但刷屏）**

SINA 用 `pytesseract` 作为**辅助** OCR 引擎，未安装时每次调用打印：

```
Tesseract data extraction error: tesseract is not installed or it's not in your PATH
```

一张图刷 12 次。**easyocr 才是主力**，44 个文本项都来自它，所以不影响结果。
若要装：<https://github.com/UB-Mannheim/tesseract/wiki>，
并把安装目录加入 PATH。

**坑 4：SINA 的输入目录与输出目录都不存在**

`netlist_generator.py` 写死的 `inputs/test_images/`、`outputs/debugging/`、
`outputs/approved_images/`、`outputs/test_results/` 在仓库里**都不存在**，
必须自己创建，否则 `os.listdir` 直接抛异常。`sina_lab.py` 会自动建好。

### 8.4 实测发现的两处质量问题（尚未处理）

**问题 1：`Resistor_3` 的接点数为 0**

```
Resistor_3  bbox=[630, 297, 642, 331]  接点=0     ← R3 (10.0k)
Resistor_1  bbox=[122, 35, 157, 51]    接点=2
Resistor_2  bbox=[371, 36, 406, 51]    接点=2
```

R3 是**竖向**放置的（bbox 宽 12 高 34），另两个是横向的（宽 35 高 16）。
竖向元件的连接点没被提取出来 —— 若属实，R3 会在网表里悬空。
**这是下一步要查的第一件事。**

**问题 2：easyocr 在元件位号上有错字**

| 正确 | easyocr 输出 | 置信度 |
|---|---|---|
| `GND` | `6ND` / `6AD` | 1.00 / 0.47 |
| `OPA191` | `0PA191` | 1.00 |
| `VOUT` | `V0UT` / `V0L1T` | 1.00 / 0.83 |
| `0.1µF` | `0.1F` / `0.1PF` / `0.1UF` | 0.98 / 0.94 / 0.45 |

`O→0`、`G→6` 这类混淆是 OCR 常态，**但置信度高达 1.00 也出错**，说明不能靠
置信度阈值过滤。好在视觉模型（DeepSeek）**同时看了图和 OCR 文本**，
最终给出的 `OPA191`、`R3: 10.0k` 都是对的 —— 这正是"OCR 提文本 + VLM 做
分配"这个分工的价值，也印证了论文里那句"即使 VLM 也难以准确定位元件，
所以文本抽取要靠 OCR"的反向配合。

### 8.5 第三处质量问题：电源与激励完全识别不到（最要紧的一处）

它直接导致仿真输出全零。

#### 现象

`circuit_info.json` 里 10 个检测结果：运放 1、GND 4、电阻 3、电容 2 ——
**没有任何电压源**。而图里明明画着 `Vcc`、`-Vcc`、`Vin` 三个电源/输入端口。

#### 排查过程（三步都做了，不是推测）

**第一步：模型有没有这一类？** 有。

```
类别表: 0 Resistor  1 Capacitor  2 Inductor  3 Transistor_BJT
        4 Transistor_MOSFET  5 Voltage_src  6 Current_src
        7 GND  8 Op-Amp  9 Diode
```

`Voltage_src` 是 id 5，训练集里有 **284 个实例**。

**第二步：是不是被置信度阈值滤掉了？** 不是。

`process_images.py:213` 就是 `model(image_path)[0]`，用默认阈值，无任何过滤。
把阈值压到 **0.01** 重跑，13 个候选里**仍然没有一个电压源**：

```
conf  类别          bbox
0.895 Op-Amp       [294, 219, 390, 320]
0.860 GND          [454, 423, 504, 451]
...
0.020 Diode        [282, 239, 293, 254]     ← 连 0.02 的垃圾候选都列出来了
0.020 Capacitor    [404, 203, 412, 219]
0.016 Capacitor    [405, 430, 413, 446]     ← 0.016 都在
```

**电压源的置信度低于 0.01** —— 模型是真的"没看见"，不是被卡掉。

**第三步：为什么看不见？** 符号画法差异。

把训练集里的 `Voltage_src` 样本裁出来看：

| | 训练集的 `Voltage_src` | 测试图的 `Vcc` |
|---|---|---|
| 画法 | 圆圈 + **正弦波** + 正负号，两端有引脚 | **实心红圆 + 一根引线**，上方文字 `Vcc` |
| 含义 | 传统独立信号源（如信号发生器） | KiCad 式**电源端口标记** |
| 共同点 | 几乎只有"都是圆形" | |

训练集里的电源符号是 **"圆圈 + 正弦波 + 正负号"** 的完整信号源符号；
测试图用的是 **KiCad 风格的电源端口**（实心小圆 + 网络名标签）。

而且实心圆点在原理图里通常是**连接点（junction dot）**，
本身就是强烈的干扰特征 —— 测试图里那个深蓝小圆点才是真正的连接点。

#### 为什么 GND 能检出、Vcc 不能

这是个有意思的不对称：

- `GND` 训练 1033 个，且接地符号（三横线 / 三角）**视觉特征极强**，
  即使测试图用的是 KiCad 式 GND 也能泛化 → 检出 4 个
- `Voltage_src` 训练 284 个，样本是**信号源**符号，
  而测试图是**电源端口** → 0 个

#### 类别不均衡（训练集共 5742 个目标）

| 类别 | 实例数 | |
|---|---|---|
| Resistor | 1560 | ← 最多 |
| Transistor_MOSFET | 1286 | |
| GND | 1033 | |
| Capacitor | 639 | |
| Transistor_BJT | 410 | |
| **Voltage_src** | **284** | ← 偏少 |
| Inductor | 167 | |
| Current_src | 158 | |
| Diode | 130 | |
| **Op-Amp** | **75** | ← 最少，但本例检出了（conf 0.895） |

#### 后果链（最要紧）

```
电源/激励未识别
   ↓
circuit_info.json 里没有电压源
   ↓
生成的网表没有任何激励源
   ↓
ngspice 跑出 1010 个时间点、全是 0.000000e+00
   ↓
★ 退出码 0、零报错 ★
```

**用户拿到的是一个"跑成功了但结果全零"的网表。** 没有对照的话，
很容易误以为是仿真设置问题，而根因其实在识别阶段。

顺带说明：那些红色/黄色/橙色实心圆是图里的**电源与输入端口标记**，
Hough 线检测把它们下面的引线当成普通线段（本次检出 20 条线里的垂直段），
所以它们会落到某个节点区域 —— **但因为没有对应的元件记录，
这个"节点"在网表里没有任何器件连上去**。

#### 应对（计划书自己已经写对了）

计划书第 9 页的风险应对原文：

> 电路图自动识别不稳定 → 首版允许用户确认节点和器件参数，
> **不把全自动识图作为 P0**

本节就是这个判断的具体证据。工程上的做法：

1. **确认表加"缺失元件"检查** —— 比对图里可见的电源/地符号数量与
   `circuit_info.json` 的检测数，不一致就提示用户补
2. **网表生成前做"无激励源"检查** —— 若网表里没有任何 `V`/`I` 源，
   直接拒绝仿真并提示，而不是产出一堆零
3. **供应商电源符号允许用户手工标注** —— 比试图让 YOLO 认识所有
   原理图工具的电源端口符号更现实
4. 长期：扩充训练集，把 KiCad / Altium / OrCAD 等工具的电源端口符号纳入标注

> 第 2 条成本最低、收益最大：**把"静默全零"变成显式报错**。
> 与第七节的"空正文检测"、第十节的"connection_points 为空检测"是同一类防护。

---

## 九、原方案对比：为什么这样切更稳

### 结论：能换，改动极小 —— 但必须支持视觉

SINA **不使用 openai SDK**，而是裸 `requests.post` 打标准
`/v1/chat/completions`。全仓库只有 **2 个** AI 调用点，各需改 2 行。

| # | 位置 | 函数 | 职责 |
|---|---|---|---|
| 1 | `ocr_module.py:215` | `extract_components_from_image_api()` | 独立识别图中元件，用于与 YOLO 结果**交叉校验** |
| 2 | `generate_netlists.py:317` | `generate_named_netlist()` | 分配位号与数值 → **生成最终 SPICE 网表文本** |

要改的 4 处：

```python
# ocr_module.py:215 与 generate_netlists.py:317
"https://api.openai.com/v1/chat/completions"   # → 换端点
# ocr_module.py:220 与 generate_netlists.py:322
"model": "gpt-4o",                              # → 换模型名
```

两处 payload 结构（完全相同的形式）：

```python
{
  "model": "gpt-4o",
  "messages": [..., {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}],
  "max_tokens": 1500,       # ocr_module 是 1800
  "temperature": 0
}
```

**没有** function calling、**没有** `response_format`、**没有** SDK 依赖。
响应只取 `['choices'][0]['message']['content']` 然后做字符串处理
（剥 ```` ``` ```` 代码围栏、读 `GROUND_NODE:` 行、`fix_mosfet_nodes()`）。

### 兼容性三条件

1. **必须支持图片输入**（base64 data URL）—— 这是硬门槛
2. **必须接受 `temperature` 与 `max_tokens` 参数**
3. 视觉理解与指令遵循要够强，能输出合法 SPICE 语法

### ⚠️ 一个高频踩坑：新版 OpenAI 模型反而不兼容

SINA 写的是 `max_tokens` + `temperature: 0`。而 **o 系列与 GPT-5 系**要求
`max_completion_tokens`（`max_tokens` 直接报错），且 `temperature` 只接受默认值 1。
直接替换模型名会失败，必须同时改这两处参数——**"升级到更新的 OpenAI 模型"
不是零成本操作**。

同理，任何不认 `max_tokens` 或强制 `temperature=1` 的推理型模型都需要改代码。

### 选型提示（未实测，需自行验证）

- **DeepSeek**：新增了 Vision 指南（<https://api-docs.deepseek.com/guides/vision/>），
  说明已支持图片输入且为 OpenAI 兼容格式，值得优先试
- **阿里 Qwen-VL**：官方提供 [OpenAI Vision 兼容接口](https://help.aliyun.com/en/model-studio/qwen-vl-compatible-with-openai)
- 其余 OpenAI 兼容的多模态服务（GLM-4V、Gemini 兼容端点、自建 vLLM + 开源 VLM）同理

> 上述供应商能力均来自公开文档条目，**本项目尚未实测**。替换后必须用
> `data/samples/` 里的固定样例做回归，比对输出与 GPT-4o 的差异。

### 性能要求：不是"算力高"，而是"别瞎编"

延迟与算力不是问题：单次 `max_tokens` 只有 1500–1800，超时 30–60 秒，
每张图 1–2 次调用，用便宜的小模型完全够快。

**真正的要求是准确性与可靠性**，原因有三：

1. **解析代码不做校验。** `generate_named_netlist()` 对返回文本只做字符串处理，
   **不校验 SPICE 语法**。弱模型产出畸形网表不会报错，而是**静默污染**最终结果
2. **存在幻觉风险。** SINA 的 YOLO 只给元件类别 + bbox，**不给元件值**。
   数值完全靠 OCR 出候选、VLM 做分配。模型可能凭空编造图中不存在的数值
3. **错误会一路传下去。** 网表是终点产物，错了就没有下游环节能兜住

### 降低成本的关键：第 2 个调用点其实可以取消

按第三节的架构（**网表由 LabPilot 自己生成**），第 2 个调用点
`generate_named_netlist()` 产出的 SPICE 文本**我们并不使用**——它缺元件值、
无 `.model`、无 `.subckt`，本来就不能仿真。

于是可以这样切：

| 环节 | 交给谁 | 对模型的要求 |
|---|---|---|
| 元件检测与连通性 | YOLO + CCL（本地） | 无 |
| 位号/数值文本 | easyocr（本地） | 无 |
| **位号↔元件对应关系** | VLM（调用点 1） | 只需"看图 + 按给定清单分配"，**可用较弱模型** |
| **SPICE 网表生成** | LabPilot `engine/netlist.py` | 无（确定性代码） |

也就是说：**只保留调用点 1，把调用点 2 整段跳过**，既省钱又消除了最大的一处
幻觉来源，而且网表质量由确定性代码保证。这是本项目建议采用的方案。

副作用：`API_first_response.txt` 的按图缓存（`ocr_module.py:246`,
`generate_netlists.py:650`）仍然有效——同一张图重跑不会重复计费。

---

## 十、待核对清单（更新）

| # | 待确认 | 状态 |
|---|---|---|
| 1 | IC 入口的命令行参数 | ✅ 无参数，硬编码路径 |
| 2 | PCB 入口的命令行参数 | ✅ 完整 argparse，见第四节 |
| 3 | PCB 输出 JSON 字段 | ✅ `image` / `components[].{component_id,bbox,pin_count,pins,connected}` |
| 4 | YOLO 权重是否随仓库分发 | ✅ 齐全，`best.pt` 与 `last.pt` 都在 |
| 5 | SINA 输出能否直接仿真 | ✅ **不能**，见第三节 |
| 6 | IC 器件类型是否覆盖模电实验 | ✅ **完全覆盖**，10 个类别 |
| 7 | 依赖是否可安装 | ✅ **已装好**，见第五节 |
| 8 | 是否有 GPU | ✅ **无**，CPU 版 torch |
| 9 | easyocr 能否用 | ✅ **已实测可 OCR**，见第五节 |
| 10 | 能否换其他 AI API | ✅ **已换为 DeepSeek V4.1 Flash**，见第七节 |
| 11 | `use_gpu=True` 写死，无 GPU 时行为 | ⬜ 待实测 |
| 12 | `outputs/approved_images` 人工确认环节如何自动化 | ⬜ 待实测 |
| 13 | **DeepSeek 是否支持图片输入** | ⬜ **待实测（需 Key）** |
| 14 | DeepSeek 对 SINA 提示词的遵循度、输出能否被解析 | ⬜ **待实测（需 Key）** |
| 15 | 磁盘剩余空间 | ⬜ 需手动确认（当前已占约 6.5 GB） |
