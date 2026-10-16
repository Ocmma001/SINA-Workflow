# LabPilot 项目交接报告

**交接日期**：2026-10-15
**当前阶段**：环境就绪 + SINA 集成完成，LabPilot 业务代码尚未开始
**最重要的一句话**：本机环境已经踩平且全部实测验证过；SINA 的识别能力可用，
但它的输出存在**三种静默失效**，必须由确认层兜住。

---

## 目录

1. [项目现状总览](#1-项目现状总览)
2. [已就绪的环境与软件](#2-已就绪的环境与软件)
3. [SINA 集成部分（已完成并实测）](#3-sina-集成部分已完成并实测)
4. [实测得到的关键结论（花了很多轮才查清）](#4-实测得到的关键结论花了很多轮才查清)
5. [本机环境特有的坑与修复](#5-本机环境特有的坑与修复)
6. [尚未完成的工作](#6-尚未完成的工作)
7. [建议的下一步与优先级](#7-建议的下一步与优先级)
8. [被删除的内容及原因](#8-被删除的内容及原因)
9. [文档与脚本索引](#9-文档与脚本索引)
10. [必须由你确认或处理的事项](#10-必须由你确认或处理的事项)

---

## 1. 项目现状总览

### 做了什么

| 部分 | 状态 |
|---|---|
| 项目目录骨架（`LabPilot/`） | ✅ 已建，65 个文件（占位模块 + 文档） |
| 计划书 PDF 解析 | ✅ 正文已提取为可读文本 |
| 两套 Python 虚拟环境 | ✅ 已建并逐个验证 |
| ngspice 仿真内核 | ✅ 已装并**跑通真实电路仿真** |
| Tesseract OCR | ✅ 已装并**实测比 easyocr 更准** |
| SINA 项目 | ✅ 已克隆，依赖已装，模型已实测可用 |
| SINA 的 AI 接入改为 DeepSeek | ✅ **已用真实密钥端到端跑通** |
| LabPilot 业务代码（engine/agent/ui…） | ❌ **尚未开始**，只有占位文件 |

### 一句话描述当前能力

**可以做到**：把一张电路图交给 SINA，得到元件清单、位号、数值、
拓扑连线；用 ngspice 对这个电路的**正确网表**做仿真。

**还做不到**：从 SINA 的输出**自动**得到可仿真的网表 —— 中间缺
"器件类型映射 + 器件模型 + 电源激励 + 引脚语义"这四样，
这部分本应是 `labpilot/engine/netlist.py` 的职责，尚未实现。

---

## 2. 已就绪的环境与软件

### 2.1 目录布局

```
C:\Users\lenovo\Documents\deepseek-harness\default-workspace\
├── LabPilot\                    本项目（骨架已建，业务代码待写）
│   ├── main.py                  程序入口（九项职责已分块，含 TODO）
│   ├── labpilot\                主包，40 个占位模块
│   ├── docs\                    6 份文档
│   ├── data\samples\            固定实验样例（离线演示兜底）
│   └── build\runtime\ngspice\   ★ 仿真内核，供 exe 捆绑
├── SINA\                        SINA 检出（3.94 GB，commit a4f13885）
├── SINA-venv\                   SINA 运行环境（1.41 GB）
├── LabPilot-venv\               LabPilot 运行环境（1.05 GB）
├── downloads\                   安装包缓存
└── tools\                       诊断与安装脚本，70 个
```

磁盘占用约 **6.5 GB**。

> ⚠️ **剩余磁盘空间无法用脚本查询**：`Get-Volume`、
> `Get-CimInstance Win32_LogicalDisk`、`fsutil volume diskfree` 三者
> 全部返回"拒绝访问"（本机策略）。请自行用文件资源管理器确认。

### 2.2 ngspice（★ 已实测可用）

| 项 | 值 |
|---|---|
| 版本 | **ngspice-41** |
| 来源 | conda-forge（`ngspice-exe` + `ngspice-lib`） |
| 位置 | `LabPilot\build\runtime\ngspice\` |
| 体积 | 22.13 MB |
| 控制台版 | `bin\ngspice_con.exe` ← **自动化必须用这个** |
| GUI 版 | `bin\ngspice.exe` |

**实测仿真结果**（分压偏置共射放大器，`Vcc=12V, Rb1=100k, Rb2=33k,
Rc=3k, Re=1k, Q2N3904`）：

```
base = 2.653076e+00     coll = 6.127130e+00     emit = 1.970696e+00
Q1: ic = 1.95763e-03    vbe = 0.682248    vbc = -3.47223
```

物理自洽性已核对：`Ic=(12−6.127)/3k=1.958mA` ✓、
`Ie=1.971/1k=1.971mA` ✓、晶体管在放大区 ✓。

**两个必须记住的调用要点**：
1. **必须用 `ngspice_con.exe`** —— `ngspice.exe` 是 GUI 版，
   用 `--version` 调用会挂起（实测 60 秒超时）
2. **`cwd` 要设到 `bin\`** —— 它从相对路径找 `spinit` 与 `.cm` 代码模型

### 2.3 Tesseract（★ 已实测可用，免管理员安装）

| 项 | 值 |
|---|---|
| 版本 | **5.5.3** |
| 来源 | conda-forge（win-64，170.68 MB） |
| 位置 | `tools\tesseract\` |
| 体积 | 419.7 MB（bin 79.3 + tessdata 339，含 125 种语言） |
| 语言数据 | `tools\tesseract\share\tessdata\` |

`tools/sina_lab.py` 启动时会自动发现并配置（`tesseract_cmd` 与
`TESSDATA_PREFIX`）。

**实测它比 easyocr 更准**（同一张运放图）：

| 文本 | Tesseract | easyocr |
|---|---|---|
| `VOUT` | ✅ 0.96 | ❌ `V0UT` |
| `GND` | ✅ 0.96 | ❌ `6ND` |
| `OPA191` | ✅ 0.91 | ❌ `0PA191` |

接入 SINA 后提取文本项从 44 增至 **106**（+141%），Tesseract 报错从
12 次/图降至 **0**。

> 要省空间：删掉除 `eng.traineddata`、`osd.traineddata` 之外的语言包
> 可省约 335 MB（本次未执行）。

### 2.4 两套 Python 环境（刻意分开）

| 用途 | 解释器 | 版本 |
|---|---|---|
| LabPilot 本体 | `LabPilot-venv\Scripts\python.exe` | 3.11.0 |
| SINA 识别 | `SINA-venv\Scripts\python.exe` | 3.11.0 |

**LabPilot-venv**（1.05 GB，12 个包全部导入验证通过）：
PySide6 6.12.0、numpy 2.4.6、pandas 3.0.6、matplotlib 3.11.2、
scipy 1.17.1、scikit-learn 1.9.1、pypdf 6.20.1、python-docx 1.2.0、
openpyxl 3.1.5、python-dotenv 1.2.4、pydantic 2.14.1、
PyInstaller 6.22.3、zstandard 0.25.0

验证细节：PySide6 的 `QApplication` 实测可创建（平台插件 offscreen）；
matplotlib 中文字体 `Microsoft YaHei`/`SimHei`/`SimSun`/`DengXian` 均可用。

**SINA-venv**（1.41 GB）：torch 2.14.1+cpu、ultralytics 8.4.177、
easyocr 1.7.2、cv2 5.0.0、openai 3.31.0 等。

### 2.5 Git 与 CA 证书

| 项 | 值 |
|---|---|
| Git | 2.56.0.2，`C:\Program Files\Git` |
| CA 证书 | `tools\certs\windows_roots.pem`（80 张，从系统证书库导出） |

**必须执行一次**（在你自己终端里，需要能写 `%USERPROFILE%`）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\fix-git-tls.ps1
```

原因见 [第 5 节](#5-本机环境特有的坑与修复)。

### 2.6 重新拉起环境的脚本

| 脚本 | 用途 |
|---|---|
| `tools/setup_labpilot_env.py` | 重建 LabPilot-venv |
| `tools/setup_sina_env.py` | 重建 SINA-venv（分四阶段） |
| `tools/install_easyocr_models.py` | 下载 easyocr 模型 |
| `tools/install_tesseract.py` | 安装 Tesseract（免管理员） |
| `tools/get_ngspice_conda.py` + `tools/assemble_ngspice.py` | 取 ngspice 并组装 |
| `tools/verify_environment.py` | **一键复检全部环境**（38 项检查） |

---

## 3. SINA 集成部分（已完成并实测）

### 3.1 SINA 检出

| 项 | 值 |
|---|---|
| 来源 | `https://github.com/medal-ece/SINA`（犹他大学 MEDAL 实验室） |
| commit | `a4f13885`，分支 `main` |
| 位置 | `SINA\` |
| 体积 | 3.94 GB（主要是模型权重与 `.git` 历史） |

权重齐全，**不需要自己训练**：IC 的 `best.pt`/`last.pt` 各 38.6 MB
（`IC/current_trained_model/train/weights/`），
PCB 的 `best.pt` 50.7 MB。

### 3.2 我改动了 SINA 的源码（换用 DeepSeek）

原代码硬编码 `gpt-4o` + `api.openai.com`。改为读环境变量，
新增共享配置模块：

```
SINA/Netlist Generator/IC/program_test/netlist_generator_algorithm_test/helper_files/llm_config.py
```

**改动位置**（原始文件备份在 `tools/sina_original_backup/`）：

| 文件 | 原来 | 现在 |
|---|---|---|
| `ocr_module.py:129` | `os.getenv("OPENAI_API_KEY")` + 抛错 | 读 `llm_config` |
| `ocr_module.py:219` | `"model": "gpt-4o"` + `api.openai.com` | `build_request(...)` |
| `generate_netlists.py:76` | 同上 | 同上 |
| `generate_netlists.py:321` | 同上 | 同上 |

**配置**（在**工作区根**的 `.env`，刻意放在 SINA 仓库之外，
避免被 git 提交；`SINA/.gitignore` 也已加忽略规则）：

```env
LABPILOT_API_KEY=DEEPSEEK_API_KEY     # 指针变量，切换供应商只改这行
DEEPSEEK_API_KEY=sk-...
SINA_API_BASE=https://api.deepseek.com
SINA_API_MODEL=deepseek-flash
SINA_API_TIMEOUT=60
SINA_VISION=1
SINA_DISABLE_THINKING=1
```

### 3.3 实测通过的关键配置（★ 三条都是踩坑换来的）

**① 模型 ID 是 `deepseek-flash`，不是 `deepseek-v4.1-flash`**

写成后者时 API 回：

```
The supported API model names are deepseek-flash, deepseek-v4-pro,
but you passed deepseek-v4.1-flash.
```

备选 `deepseek-v4-pro`。**API 的报错比任何文档都权威** —— 模型 ID
拿不准时直接发一次请求问它。

**② 必须关闭思维链，否则正文为空**

`deepseek-flash` 是推理型模型，面对 SINA 的长提示词会把整个
`max_tokens` 额度烧在思维链上，**正文返回空字符串**。而 SINA 只读
`message['content']`，于是**不报错、只是网表里没有位号** —— 静默失效。

实测（同图同提示词，`max_tokens=1800`）：

| 参数 | reasoning_tokens | content |
|---|---|---|
| （不加） | 1800 | **0 字符** ❌ |
| **`thinking={"type":"disabled"}`** | **0** | **483 字符** ✅ 且快 3 倍 |
| `reasoning_effort="none"` | 0 | 458 字符 ✅ 但慢 |
| `enable_thinking=False` | 1800 | 0 字符 ❌ 参数被忽略 |
| `reasoning_effort="minimal"` | 1800 | 0 字符 ❌ 无效 |
| `max_tokens=8000` | 1822 | 562 字符 ✅ 但贵 16 倍 |

采用 `thinking={"type":"disabled"}`，由 `SINA_DISABLE_THINKING` 控制
（默认 1）。另新增**空正文检测**，再出现会抛带诊断的错误。

**③ easyocr 有三个目录，缺一个就 PermissionError**

`easyocr.py` 第 55–65 行：`MODULE_PATH` 来自环境变量，缺省
`~/.EasyOCR`；`model_storage_directory` 与 `user_network_directory`
只是对它的**分别覆盖**。只传后者时，`user_network` 仍会去写
`%USERPROFILE%\.EasyOCR` 而失败。

```python
os.environ["EASYOCR_MODULE_PATH"] = "<可写目录>"
reader = easyocr.Reader(lang_list, gpu=False,
                        model_storage_directory="<可写目录>",
                        user_network_directory="<可写目录>",
                        download_enabled=False)   # 离线时禁下载
```

### 3.4 实测性能

| 指标 | 值 |
|---|---|
| 视觉识别延迟 | **3.0 – 4.9 秒/张**（关思维链后；开启时 14.6 秒） |
| token 消耗 | 输入约 520，输出约 120 |
| YOLO 推理 | 0.2 – 2.8 秒/张（CPU） |

### 3.5 试验台：`tools/sina_lab.py`

在 **cmd** 里跑：

```cmd
cd /d C:\Users\lenovo\Documents\deepseek-harness\default-workspace

SINA-venv\Scripts\python.exe tools\sina_lab.py --check
SINA-venv\Scripts\python.exe tools\sina_lab.py --stage 1 --image tools\test_images\你的图.jpg
SINA-venv\Scripts\python.exe tools\sina_lab.py --stage 2
```

`--stage 1` 是本地识别（YOLO + CCL + OCR，**不需要密钥**）；
`--stage 2` 才调 LLM。

脚本会自动完成三件事：
1. 摆好 easyocr 模型 + **包装 `Reader` 强制 `download_enabled=False`**
2. 自动发现并配置 Tesseract
3. 创建 SINA 入口写死的四个目录，清理输入图上的只读属性

---

## 4. 实测得到的关键结论（花了很多轮才查清）

### 4.1 检测质量（用 662 张数据集对标注算出，非估算）

用 `last.pt` 对全部 662 张图推理，按 **IoU 0.5** 贪心匹配标注：

| 类别 | GT | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|---|
| Resistor | 1740 | 1711 | 54 | 29 | 0.969 | 0.983 | 0.976 |
| Capacitor | 713 | 698 | 28 | 15 | 0.961 | 0.979 | 0.970 |
| Inductor | 195 | 194 | 8 | 1 | 0.960 | 0.995 | 0.977 |
| Transistor_BJT | 441 | 438 | 12 | 3 | 0.973 | 0.993 | 0.983 |
| Transistor_MOSFET | 1429 | 1427 | 42 | 2 | 0.971 | 0.999 | 0.985 |
| **Voltage_src** | 335 | 327 | 22 | 8 | **0.937** | **0.976** | **0.956** |
| Current_src | 166 | 165 | 12 | 1 | 0.932 | 0.994 | 0.962 |
| GND | 1165 | 1141 | 43 | 24 | 0.964 | 0.979 | 0.971 |
| Op-Amp | 101 | 99 | 6 | 2 | 0.943 | 0.980 | 0.961 |
| Diode | 164 | 154 | 3 | 10 | 0.981 | 0.939 | 0.960 |
| **【总体】** | **6449** | **6354** | **230** | **95** | **0.965** | **0.985** | **0.975** |

逐图结果在 `tools/dataset_validation/per_image.csv`（662 行），
汇总在 `summary.json`。复现脚本：`tools/validate_on_dataset.py`。

**这个数字的意义**：论文报的是**网表级**准确率 96.67%（含拓扑推断），
而 97.5% 是**元件检测级** F1。两者不可直接比较 —— 检测对不等于网表对。

### 4.2 三种静默失效（★ 这是本项目最需要知道的事）

SINA 的失败模式**几乎都不报错**，会产出"看起来正常但实际错误"的结果：

| # | 失效 | 表现 | 根因 |
|---|---|---|---|
| 1 | 思维链吃光 max_tokens | 网表里没有位号，HTTP 200 | 见 3.3 ② |
| 2 | `connection_points` 为空 | 元件悬空消失，不报错 | 连通性推断失败 |
| 3 | 电源/激励未识别 | 仿真跑出全零，**退出码 0** | 符号画法超出训练分布 |

**第 3 条的实测细节**（这是最隐蔽的一条）：

在运放 OPA191 那张图上，模型对 `Vcc`/`-Vcc`/`Vin` **一个都没检出**。
排查三步都做了：

1. **模型有没有这一类？** 有 —— `Voltage_src` 是 id 5，
   训练集 284 个实例
2. **是不是被阈值滤掉了？** 不是 —— 把阈值压到 **0.01** 重跑，
   13 个候选里仍无电压源（连 0.016 的垃圾候选都列出来了）
3. **为什么看不见？** 符号画法差异：

| | 训练集的 `Voltage_src` | 测试图的 `Vcc` |
|---|---|---|
| 画法 | 圆圈 + **正弦波** + 正负号 | **实心红圆 + 一根引线** + 文字 `Vcc` |
| 含义 | 传统独立信号源 | KiCad 式**电源端口标记** |

而且实心圆点在原理图里通常是**连接点（junction dot）**，
本身就是强干扰特征。

**注意不要过度解读**：在数据集的 662 张图上，`Voltage_src` 的
F1 是 **0.956**（335 个检出 327 个）。所以准确说法是
**"模型对训练分布内泛化良好，但换一种原理图工具的电源端口画法就会失效"**，
而不是"模型识别不了电源"。

**第 2 条的实测细节**：运放图里 `Resistor_3`（R3 10.0k）的
`connection_points` 是 `[]`。它是**竖向**放置的（bbox 12×34），
另两个横向电阻（35×16）都正常拿到 2 个接点。我换用 Tesseract 后
文本项从 44 翻到 106，**这个问题纹丝不动** —— 说明根因在连线提取，
不在 OCR。

### 4.3 ngspice 原样读 SINA 网表的结果

把 SINA 生成的网表**原样**喂给 ngspice：

```
ngspice-41 done                    ← 退出码 0
Transient Analysis ...
V(1) V(2) V(3) V(4) 全部 0.000000e+00
```

**它把 `Op-Amp_1 1 1 2 3 4` 当成了标题行**（SPICE 规定第一行是标题，
无条件忽略），于是运放整个消失，剩下 4 个元件里 C1/C2 悬空、
R1/R2 没有激励源 —— 输出恒为 0 且**不报错**。

SINA 原网表的四个硬伤：

| 问题 | 原文 |
|---|---|
| 运放首卡不是合法器件卡 | `Op-Amp_1 1 1 2 3 4` |
| 节点重复（等于两输入端短接） | `1 1` |
| R3 完全丢失 | 因 `connection_points` 为空 |
| `.model` 定义了却没人用 | `.model QMOD NPN(...)` 改用 BJT 冒充运放 |

### 4.4 `ngspice -b` 模式的关键约束（★ 四个变体对照得出）

| 变体 | 内容 | 结果 |
|---|---|---|
| a | 只有点指令 `.op` + `.tran` | ❌ `no data saved for Transient analysis`，退出码 1 |
| **b** | **只用 `.control` 块** | ✅ **退出码 0**，有完整数据 |
| c | 点指令 + `.control` 共存 | ❌ 冲突报错 |
| d | 点指令 + `.control`（块内用带点的 `.tran`） | ❌ 报错 |

**结论：分析命令必须写在 `.control` 块内，且与点指令不能共存。**

而且**块内的 `tran` 必须带参数** —— 裸写 `tran` 会被当成传输线元件：

```
Fatal error: tran: transmission line z0 must be given
```

> 这解释了 SINA 原网表里那个 `quit`（紧跟在 `tran` 之后）——
> 很可能就是在掩盖同类问题。

### 4.5 SINA 产出的 JSON 各有什么用

用代码追了每个 JSON 的消费者，结论：

| 文件 | 定位 | 谁读 | 删掉的后果 |
|---|---|---|---|
| `circuit_info.json` | ★ **核心** | `generate_netlists`（连通性）、`ocr_module`（一致性校验） | **流程直接崩** |
| `crossing_data.json` | ★ 核心（交叉线场景） | `generate_netlists` | 交叉线消歧失效 |
| `region_to_node_mapping.json` | 辅助 | `generate_netlists` | 节点号无法回溯 |
| `testing_all_lines.json` | 调试 | `nodes_analysis`（只画图） | 少一张调试图 |
| `ocr_results.json` | **预留** | **无人读取** | 无影响 |

`circuit_info.json` 的结构：

```json
[{"id": "Op-Amp_1", "label": "Op-Amp",
  "bounding_box": [294, 219, 389, 319],
  "connection_points": [[294,246],[294,291],[389,269],[342,219],[342,319]]}]
```

**`connection_points` 是连通性的唯一依据** —— `generate_netlists.py`
遍历它，把每个引脚点投到节点标签图上，落在哪个连通区域就属于哪个节点。
所以它为空 = 元件在网表里悬空。

> `ocr_results.json` 虽然 SINA 自己不用，但它的 `text_by_component`
> 已经把"每个元件附近有哪些文本"归好类了，**这对 LabPilot 做位号
> 匹配直接可用**，比重新做一遍邻近分析省事。

### 4.6 桥接能力边界（虽然桥接已删除，但结论要记住）

我实现过一版"SINA 网表 → ngspice 网表"的桥接并做了批量验证
（560 个合成用例），得到两条有用结论：

**① 语法层面的转换是可以做到高可靠度的。**
用修正后的分类器，桥接产出的网表 **96.9% 能被 ngspice 正确解析**
（3.1% 失败，且原因可解释为合成用例自身的缺陷）。

**② 但有三样东西桥接补不出来，必须人工/确认层提供**：

| 缺什么 | 后果 | 能否自动补 |
|---|---|---|
| 器件类型 → SPICE 器件字母 | 无法生成器件卡 | ✅ 可（查表） |
| 器件模型（真实运放等） | 无法精确仿真 | ⚠️ 只能用通用宏模型凑 |
| **电源与激励** | 仿真全零且不报错 | ❌ SINA 不识别，必须人工 |
| **引脚顺序** | 拓扑可能错 | ❌ **无法从 SINA 输出唯一确定** |

**最后一条是根本局限**：SINA 只给节点号，不给引脚语义。
`X1 1 2 3 4 ...` 里的 `1 2 3 4` 对应 inp/inn/vcc/vee 还是别的顺序，
从它的输出无法判断。这正是计划书说"首版允许用户确认节点和器件参数"
的技术原因。

---

## 5. 本机环境特有的坑与修复

这些都是**本机特有**的（不是通用问题），换机器不会遇到，
但在这台机器上必须知道。

### 5.1 Schannel 故障导致所有 HTTPS 失败

**根因**：`%APPDATA%\Microsoft\Crypto` **不可写** →
Windows Schannel 无法获取 TLS 凭据：

```
schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)
```

**表现**：TCP 443 可连通、HTTP 正常（example.com 返回 200）、
但 **PowerShell / curl / winget / pip / git(默认) 的 HTTPS 全部失败**。

**修复**（`tools/fix-git-tls.ps1`）：

```powershell
git config --global http.sslBackend openssl
git config --global http.sslCAInfo <workspace>\tools\certs\windows_roots.pem
```

> ⚠️ **公共 CA 包不够用**：`curl.se/cacert.pem`（121 张根证书）
> 仍报 `unable to get local issuer certificate`。**必须导 Windows
> 证书库**（80 张，含本机注入的根证书）才通过。

`~/.gitconfig` 在沙箱内写不了，所以只写了仓库级配置 ——
**你要在自己终端里跑一次上面的脚本**。

### 5.2 harness 自带的 Python 3.12 装不了任何包

**根因**：向 `mkdtemp()` 新建的子目录写入文件必现 `PermissionError`。

验证过**不是沙箱权限问题** —— 同目录手工建目录、写文件、重命名、
删除全部正常。是这个 Python 构建自身的问题。

**解法**：用系统里的 Python 3.11 建虚拟环境（两套环境都是 3.11）。

### 5.3 SINA 输入图会被设成只读

SINA 的某个库（大概率 `cv2.imwrite` 覆盖已有文件）把输入图设成
`ReadOnly`。再次运行时报：

```
PermissionError: [WinError 5] 拒绝访问。: '...\inputs\test_images\xxx.jpg'
```

删除和写入都失败，**极易误判成"文件被占用"**（我一开始就判断错了）。
用独占打开测试也失败，看起来特别像锁。真正原因是只读属性。

`tools/sina_lab.py` 会在复制/删除前主动 `chmod`。

### 5.4 easyocr 会静默下载模型并卡死

`CircuitOCR.__init__` 调 `easyocr.Reader(['en'], gpu=True)` **不传
`model_storage_directory`**，回退到 `EASYOCR_MODULE_PATH/model/`。
那里只有检测模型没有识别模型，它就发起下载。

实测表现：**卡在 `Progress: 53%` 十几分钟、进程零网络连接、
日志零增长**，看起来完全像死锁。我一开始怀疑是 CPU 慢，
查了进程 CPU 时间只有 19.5s 才排除。

修好后 Reader 构建从"卡死十几分钟"变成 **1.3 秒**。

### 5.5 conda 的 `.conda` 包内层是 zstd

Python 3.11 的 `tarfile` 不认（3.14 才支持），需要 `zstandard` 库。
装 ngspice 与 Tesseract 都踩到了。

### 5.6 Tesseract 最难的一个坑：libssh2 与 OpenSSL 版本不匹配

conda 的 tesseract 把依赖拆成很多独立包，DLL 必须手工合并到同一目录。
但即使把官方依赖清单里的包**全下齐**、递归解析 PE 导入表补齐到
110 个 DLL，`tesseract.exe` 仍以 **`0xC0000135`
(STATUS_DLL_NOT_FOUND)** 退出。

根因：

| DLL | 它要的 | 问题 |
|---|---|---|
| `libssh2.dll` | `libcrypto-1_1-x64.dll` | **1.9.0 是为 OpenSSL 1.1 构建的** |
| `libcurl.dll` | `libcrypto-4-x64.dll` | 8.23 用 OpenSSL 3/4 |

两者对不上，且 conda-forge 已不再提供 OpenSSL 1.1 的 Windows 包。
**解法：把 libssh2 换成 1.11.1**（依赖 `openssl >=3.5.7`），
立刻启动成功。

排查过程中我还犯了几个错，值得记录：
- 按"版本号排序取最新"给 libcurl 拿到了 **8.9.1**，而 tesseract 要求
  `>=8.21.0`。**版本不匹配的症状是 `WinError 127`（找不到导出函数），
  不是"缺文件"**，我一开始误判了。要读依赖约束，不能只看版本号。
- 用 `ctypes.WinDLL` 测加载，它的报错**对同目录依赖是误导性的** ——
  把"依赖解析失败"也报成 "Could not find module"，而且不搜索 exe
  所在目录。换 `LoadLibraryExW` + `LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR`
  才拿到真实错误码。
- 把错误信息截断到 90 字符，而**缺失的 DLL 名恰好就在被截断的部分**。

### 5.7 各下载源的实测速率（判断"慢"时先看这张表）

| 源 | 速率 | 用途 |
|---|---|---|
| 清华 PyPI 镜像 | **15–18 MB/s** | pip 装包 |
| conda-forge (anaconda.org) | 120–450 KB/s | ngspice、Tesseract |
| PyTorch 官方 CDN | 35 KB/s – 16 MB/s | torch |
| GitHub 仓库克隆 | **1.76 MiB/s** | SINA 2.17 GB，约 25 分钟 |
| GitHub 发行版下载 | **14.9 KB/s ～ 1.83 MB/s** | easyocr 模型 |

> ⚠️ **GitHub releases 速率几分钟内会剧烈波动**：同一批 URL 首次
> 14.9 KB/s，重测 1830 KB/s（**123 倍**）。且国内代理镜像
> （ghproxy 84 KB/s、gh-proxy 146 KB/s、ghfast 127 KB/s；
> moeyy / gitmirror 直接 TLS 失败）**全部慢于直连**。
>
> **结论：GitHub 下载慢时先杀掉重试，不要急着换镜像。**

### 5.8 SourceForge 全面 403

ngspice 最新的 Windows 包在 SourceForge（`ngspice-47_64.7z`），
但 SourceForge 对脚本请求**全面返回 403** —— 跳转页、镜像直链、
连 API 都挡，加 Referer 也没用。这是 Cloudflare 级反爬。

所以走了 conda-forge（版本 41 而非 47）。41 完全够用：
`.op`/`.dc`/`.ac`/`.tran` 与 `.model` 都支持。

---

## 6. 尚未完成的工作

### 6.1 LabPilot 业务代码（全部未开始）

`LabPilot/labpilot/` 下 40 个模块**全是占位文件**，每个只有
docstring 说明职责。`main.py` 列出九项职责与签名，含 9 处
`raise NotImplementedError("TODO: ...")`。

按优先级，建议的实现顺序：

| 优先级 | 模块 | 为什么先做 |
|---|---|---|
| **P0** | `engine/`（5 个） | 不需要 AI，可独立测试，是项目的地基 |
| **P0** | `analysis/compare.py` | "三重对照"是核心卖点 |
| P1 | `ingest/schematic/`（SINA 集成层） | 识别能力已验证，接上即可 |
| P1 | `agent/` + `viz/` | 需要 API Key |
| P2 | `rag/`、`diagnosis/`、`report/` | 计划书里的 P1 功能 |

### 6.2 明确未验证的事项

| # | 未验证 | 影响 |
|---|---|---|
| 1 | SINA 的 `use_gpu=True` 写死，**本机无 CUDA 时是否回退** | 阶段 1 实测**跑通了**（有 `defaulting to CPU` 提示），但那是 easyocr 打的，YOLO 部分是否全程 CPU 未单独确认 |
| 2 | `outputs/approved_images` 人工确认环节能否自动化 | 实测**自动通过了**（本地检测与视觉识别计数一致时自动 approve），但不一致时的行为未知 |
| 3 | OpenCV 5 与 SINA 的兼容性 | SINA 按 OpenCV 4.x 写的，本机装的是 **cv2 5.0.0**（easyocr 拉进来的）。**首版运行未报错**，但未做完整回归 |
| 4 | SINA 阶段 2 的完整产物 | 只跑过一次、且只到生成网表为止，PCB 模块完全没碰 |
| 5 | 真实 OPA191 的 SPICE 模型 | 用的是我写的通用宏模型（理想运放 + 输出限幅），只保留高开环增益与限幅两个特性。不能用于评估带宽/失调/噪声 |

### 6.3 已知但未处理的设计问题

1. **`SINA_REQUIRE_CONFIRM` 只是配置项，没有实现**
   `.env.example` 里有这个开关（默认 true），但确认表本身还没写。
   考虑到 4.2 的三种静默失效，**这是必须补的**。

2. **exe 打包未实测**
   `build/labpilot.spec` 已写并修正了排除项（可省约 380 MB），
   但**从没跑过 PyInstaller**。打包链路未验证。

3. **未做换机验证**
   ngspice 的捆绑是否真的能在没装 ngspice 的机器上跑，**没有验证过**。
   本机 PATH 里没有 ngspice，所以 `locator` 会正确回退到捆绑版 ——
   但这不等于换机可用。

---

## 7. 建议的下一步与优先级

### 第一步（无依赖，可立刻做）：`engine/` 五个模块 + `--cli` 闭环

**为什么先做这个**：它是计划书 W1 的验收标准
（"上传资料 + 输入参数 + 调用 ngspice + 显示结果"），
**完全不需要 API Key**、不依赖 SINA 的任何未验证部分，
而且 ngspice 已经实测可用。

```
labpilot/engine/
├── netlist.py    结构化参数 → SPICE 网表
├── runner.py     调用 ngspice_con.exe（子进程 + 超时 + 错误捕获）
├── parser.py     解析输出（工作点/DC/AC/瞬态）
├── models.py     器件模型库（2N3904、1N4148 等，可从 conda-forge 取）
└── locator.py    定位 ngspice（捆绑 → PATH → 友好报错）
```

**已有现成的测试基准**：`tools/simulate_opamp.py` 里的共射放大器网表
（实测 `base=2.653076, coll=6.127130, emit=1.970696`），
可以直接做回归用例。

### 第二步：确认层（`ingest/schematic/confirm.py`）

针对 4.2 的三种静默失效，至少实现三条校验：

1. **无激励源检查** —— 网表里没有任何 `V`/`I` 源就拒绝仿真
2. **`connection_points` 为空检查** —— 标为"连接未知"，要求用户手工连线
3. **声明元件数 vs 实际解析数比对** —— 不一致就报错

> 第 1 条成本最低、收益最大：**把"静默全零"变成显式报错**。

### 第三步：把 SINA 接进来

`tools/sina_lab.py` 已经跑通两个阶段，接进 `ingest/schematic/`
主要是把它的逻辑搬进去并加确认层。

### 第四步：exe 打包

`build/labpilot.spec` 已就绪，但**先做一次 `--selftest` 验证**再打包。

---

## 8. 被删除的内容及原因

本次删除了"桥接"相关文件（应要求）。**删除的都是代码与产物，
结论已全部整合进本报告**：

| 删除项 | 内容 | 为什么删 | 结论去哪了 |
|---|---|---|---|
| `labpilot/engine/netlist_bridge.py` | SINA 网表 → ngspice 网表 转换器（26.6 KB） | 应要求删除桥接 | 能力边界见 [4.6](#46-桥接能力边界虽然桥接已删除但结论要记住) |
| `tools/sina_to_ngspice.py` | 转换的 CLI 入口 | 同上 | — |
| `tools/validate_bridge.py`、`validate_bridge2.py` | 桥接的批量验证（560 用例） | 同上 | 验证方法见 [4.6](#46-桥接能力边界虽然桥接已删除但结论要记住) |
| `tools/parse_ngspice_tables.py`、`check_connectivity.py`、`verify_bridge.py` | 专为分析桥接产物而写 | 同上 | — |
| `ngspice_work/`、`tools/bridge_validation*/` | 转换产物（约 700 个文件） | 同上 | — |
| `tools/ngtest*/` | ngspice 行为的临时实验目录 | 同上 | 实验结论见 [4.4](#44-ngspice--b-模式的关键约束-四个变体对照得出) |
| `LabPilot/docs/dataset_validation.md` | 数据集验证记录 | 前半是桥接健壮性，已无对象 | 检测质量数据见 [4.1](#41-检测质量用-662-张数据集对标注算出非估算) |

**保留的（有意不删）**：

- `tools/validate_on_dataset.py` + `dataset_validation/per_image.csv`
  + `summary.json` —— 数据集检测质量验证，**不依赖桥接**，
  可随时复跑
- `tools/test_classifier2.py` —— ngspice 错误分类器的对照实验
  （记录 [4.4](#44-ngspice--b-模式的关键约束-四个变体对照得出) 的发现）
- `tools/run_sina_netlist.py` —— 证明"SINA 网表不能直接仿真"
- `tools/simulate_opamp.py` —— 可仿真的运放网表 + 增益验证
  （实测增益 2.0000 与理论吻合）
- 全部调查脚本与文档

---

## 9. 文档与脚本索引

### 文档（`LabPilot/docs/`）

| 文件 | 内容 |
|---|---|
| **`HANDOVER.md`**（本文件） | ★ 交接总览 |
| `sina_integration.md`（37.7 KB） | SINA 集成详解：架构、实测事实、DeepSeek 接入、8.5 节电源识别排查 |
| `environment.md`（14.3 KB） | 环境清单：软件版本、路径、各项实测记录 |
| `sina_json_fields.md`（7.1 KB） | SINA 五个 JSON 的字段含义与消费者 |
| `main_file.md`（4.9 KB） | `main.py` 的九项职责详解 |
| `build_exe.md`（3.3 KB） | exe 打包说明与常见坑 |
| `LabPilot_项目计划书.pdf` | 原始计划书 |
| `项目计划书_正文提取.txt` | 已提取的正文（可直接做 RAG 语料） |

### 常用脚本（`tools/`）

| 脚本 | 用途 |
|---|---|
| **`verify_environment.py`** | ★ 一键复检全部环境（**38 项全部通过**） |
| `sina_lab.py` | SINA 试验台（cmd 可用） |
| `fix-git-tls.ps1` | 修复 git HTTPS（**需你手动跑一次**） |
| `validate_on_dataset.py` | 数据集检测质量验证（662 张图，F1=0.975） |
| `simulate_opamp.py` | 可仿真运放网表 + 增益验证（exit=0） |
| `run_sina_netlist.py` | 演示 SINA 网表不能直接仿真（exit=0） |
| `test_classifier2.py` | ngspice 错误分类对照实验（**7/7 通过**，exit=0） |
| `setup_labpilot_env.py` / `setup_sina_env.py` | 重建环境 |

> 上表中标注 exit=0 / 通过数的脚本，都是**本次删除操作之后重新跑过确认的**。

### 一个自查发现（值得记录）

交接前复检时发现 `test_classifier2.py` **处于失败状态**（exit=1）。
排查后确认**不是分类器的问题，是我给用例 A 写的期望值错了**：

用例 A 是一个**没有 `.control` 块**的网表，而 [4.4 节](#44-ngspice--b-模式的关键约束-四个变体对照得出)
刚论证过这种网表在批处理模式下分析不会执行、会报
`run simulation(s) aborted`。所以分类器判它 `simu_fail` 是**对的**，
我原先标注的期望 `ok` 才是错的。已修正用例并重跑，现在 7/7 通过。

这件事本身说明一个道理：**验证脚本自己也会错，而且错了会让人误信
或误疑被测对象。** 交接时最好把验证脚本也复跑一遍。

### 数据

| 路径 | 内容 |
|---|---|
| `tools/dataset_validation/per_image.csv` | 662 张图逐图检测结果 |
| `tools/dataset_validation/summary.json` | 检测质量汇总 |
| `tools/train_crops/`、`symbol_crops/` | 符号对比图（电源符号画法差异的证据） |
| `.env`（工作区根） | 密钥与配置，**在 SINA 仓库之外** |

---

## 10. 必须由你确认或处理的事项

### 10.1 立即要做

| # | 事项 | 命令 / 说明 |
|---|---|---|
| 1 | **轮换 DeepSeek API Key** | `sk-1612...df9c` 已出现在对话记录里，建议在 DeepSeek 控制台重置 |
| 2 | **跑一次 git TLS 修复** | `powershell -ExecutionPolicy Bypass -File tools\fix-git-tls.ps1`（沙箱内写不了 `~/.gitconfig`） |
| 3 | **确认磁盘剩余空间** | 已占约 6.5 GB。脚本查不出来（三种方法全"拒绝访问"） |

### 10.2 需要你决策

| # | 决策 | 背景 |
|---|---|---|
| 1 | **是否需要真实器件模型** | 现在用的是通用宏模型。要精确仿真需从 TI 官网下 OPA191 的 SPICE 模型 |
| 2 | **`tessdata` 要不要精简** | 125 种语言占 339 MB，本项目只需英文，可省 335 MB |
| 3 | **PCB 模块要不要碰** | 完全没验证过。它依赖 Google Cloud Vision 凭据，且输出格式与 IC 不同 |
| 4 | **是否保留 DeepSeek 作为唯一供应商** | 接入已实测可用，但 `deepseek-flash` 是推理型模型，每次调用都要显式关思维链（已在配置里默认关闭） |

### 10.3 交接时最该记住的三句话

1. **环境全部踩平了** —— `tools/verify_environment.py` 一键复检 38 项，
   本次交接前复跑确认 **38/38 通过**
2. **SINA 的失败是静默的** —— 三种失效都不报错（见 [4.2](#42-三种静默失效-这是本项目最需要知道的事)），
   确认层必须补
3. **`ngspice -b` 必须用 `.control` 块** —— 点指令单独用会报
   `run simulation(s) aborted` 且退出码 1（见 [4.4](#44-ngspice--b-模式的关键约束-四个变体对照得出)）

### 10.4 交接前的复跑记录

为确认删除操作没有破坏任何东西，以下脚本在删除后**重新跑过**：

| 脚本 | 结果 |
|---|---|
| `verify_environment.py` | 38 项全通过 |
| `simulate_opamp.py` | exit=0 |
| `run_sina_netlist.py` | exit=0 |
| `test_classifier2.py` | 7/7 通过，exit=0 |

> 复跑时发现 `test_classifier2.py` 当时处于失败状态，
> 排查确认是**我的用例期望值写错**（不是分类器错），已修正。
> 细节见 [第 9 节](#9-文档与脚本索引) 末尾。

---

*报告结束。有任何与实测数据矛盾的说法，以 `LabPilot/docs/` 下的
详细文档为准 —— 那些是本会话逐项跑出来的原始记录。*
