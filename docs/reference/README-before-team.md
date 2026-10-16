# SINA 识别调优工作区

本目录从 LabPilot 交接包提取识别相关脚本、样例和记录，不依赖 LabPilot、ngspice 或桌面界面。原项目文件保留。

**当前状态：官方 IC 快照、GPU 训练环境与 EasyOCR 权重已就位；首轮微调和交付包实跑已完成。** 详见 [训练结果与交付](训练结果与交付.md)。独立豆包视觉复核已接入并完成单图实测；完整参数/拓扑准确率与独立泛化仍待评估。历史记录以本轮源码和实测为准。

先读 [完整工作流](docs/完整工作流.md)，包含每阶段输入、输出、联网依赖与评估流程。


## 文件入口

| 位置 | 用途 |
|---|---|
| `tools/sina_lab.py` | 分阶段运行 SINA IC 识别；支持 `SINA_ROOT`，默认请求 CPU |
| `tools/probe_sina.py` | 查看上游结构、模型与输出字段；默认不执行上游入口 |
| `tools/validate_on_dataset.py` | YOLO 检测评估；可指定模型、split、阈值、分辨率和独立输出目录 |
| `tools/setup_sina_env.py` | 创建独立环境；默认使用执行它的 Python，也可设 `SINA_BOOTSTRAP_PYTHON` |
| `tools/install_easyocr_models.py` | 下载 OCR 模型 |
| `tools/install_tesseract.py` | 历史便携安装工具，需 zstandard；本机可优先使用已有 Tesseract |
| `examples/` | 两张原理图和历史识别草稿；草稿不是标准答案 |
| `datasets/` | 放人工标注的数据集 |
| `runs/` | 放每次检测评估结果 |
| `experiments/` | 记录配置、错误类别和调优结论 |
| `docs/reference/` | SINA 集成、JSON 字段、历史环境与交接记录 |

## 准备环境

从本目录打开 PowerShell。官方 IC README 要求 Python 3.12；历史改造环境使用过 3.11。建议为官方基线准备独立 3.12 环境，当前默认 3.13 尚未验证。

1. 准备 SINA 的**专用实验副本**，来源为 https://github.com/medal-ece/SINA 。记录 commit，并保留对上游的修改补丁。历史运行依赖 `helper_files/llm_config.py` 等供应方改造，不能假定新克隆的源码已含这些改动。
2. 用准备好的 Python 3.12 执行 `tools/setup_sina_env.py`。这是安装操作，会联网下载依赖；提取过程没有执行它。
3. 使用生成的 `SINA-venv/Scripts/python.exe` 运行 `tools/install_easyocr_models.py`。
4. 参考 `config.example.ps1` 设置路径；LLM 密钥在当前进程环境中配置，不写入实验日志。

```powershell
$env:SINA_ROOT = Join-Path $PWD 'SINA'
$sinaPython = '.\SINA-venv\Scripts\python.exe'
& $sinaPython .\tools\probe_sina.py --root $env:SINA_ROOT
& $sinaPython .\tools\sina_lab.py --check
```

`probe_sina.py --deep` 会执行上游脚本；上游未必处理 `--help`，可能产生文件或联网，常规探测不要加此参数。

## 跑一张图片

```powershell
& $sinaPython .\tools\sina_lab.py --stage 1 -n 1 --image .\examples\user_bjt_bias.jpg
& $sinaPython .\tools\sina_lab.py --stage 2
```

阶段 1 包装检测、连通处理、OCR 和一次在线视觉调用，阶段 2 包装上游网表生成及在线模型调用。当前官方原版两阶段均需联网。包装器现兼容原版与带 `llm_config` 的历史改造版；原版固定读取 OPENAI_API_KEY 并调用 gpt-4o。

产物仍写入 SINA 算法目录的 `outputs/debugging`、`outputs/approved_images` 和 `outputs/test_results`，并未自动归档到本目录。每轮将产物与日志复制到独立实验目录，避免旧结果混淆。

输入目录已有文件时脚本默认停止，不自动删除原文件。使用新的实验副本，或人工检查后整理入口。`--keep-inputs` 会允许处理旧图与新图，不能据此把结果认定为只来自当前图片。同一上游副本不要同时运行多个实验。

## 建立检测基线

数据格式为 YOLO，目录结构：

```text
datasets/my-circuits/
  images/train/  images/val/  images/test/
  labels/train/  labels/val/  labels/test/
```

每张图片对应同名 `.txt`，每行 `class cx cy width height`，坐标归一化到 0–1。类别顺序必须与脚本 `CLASS_NAMES` 和模型一致。每张待评图片都要有标注；没有标注的图片不会计入评估。当前评估器针对原 SINA 十类模型。

```powershell
& $sinaPython .\tools\validate_on_dataset.py `
  --data .\datasets\my-circuits `
  --model 'D:\你的路径\SINA-experiment\Netlist Generator\IC\current_trained_model\train\weights\last.pt' `
  --split val --conf 0.25 --match-iou 0.5 --nms-iou 0.7 --imgsz 640 --device cpu `
  --out .\runs\baseline-001
```

输出逐图 `per_image.csv` 与 `summary.json`，包含总体、各类别 precision/recall/F1 以及评估配置。每次用新输出目录。该指标采用固定阈值的同类 IoU 贪心匹配，**不是 mAP，也不是整张电路准确率**。不要混合 train 和 val 报告最终成绩；test 留到调参完成再使用。旧文档的 662 张 F1=0.975 混合了训练/验证数据，不能作为本工作流的独立泛化成绩。

## 调优顺序与验收口径

1. 明确输入范围：本提取版针对二维原理图图片，实物电路照片、面包板接线和 PCB 不是已验证范围。
2. 收集真实目标图片，按来源与电路家族划分 train/val/test；近重复图片放在同一 split。
3. 固定基线：上游 commit、YOLO 权重哈希、依赖版本、图片清单、预处理、阈值及 LLM 配置。
4. 分层查错：漏元件/类型错误 → 位号/数值/单位错误 → 引脚定位 → 导线交叉与节点连接 → 语义引脚映射。
5. 每轮只改变一个因素，在 val 上比较；成功和失败均保留。必要时重复 LLM 实验以观察波动。
6. 对难例补充人工真值，再决定改阈值、预处理、OCR 配对、提示词或重训检测器。
7. 最终在未参与调参的 test 上验证，人工改过的结果与自动输出分开统计。

| 层次 | 指标 | 当前自动化支持 |
|---|---|---|
| 元件检测 | 同类 IoU 下 precision / recall / F1，逐类与逐图错误 | 已有评估脚本 |
| 位号与参数 | 位号正确率、单位归一化后的数值正确率 | 需人工标注与后续评估器 |
| 连接关系 | 引脚到节点的正确率、误连/漏连；节点重命名后等价比较 | 需人工标注与后续评估器 |
| 整图结果 | 全部目标元件、参数、引脚与连接同时正确的图片比例 | 当前人工核对 |
| 可靠性 | 空正文、崩溃、超时、待确认率、成本与耗时 | 用实验记录模板统计 |

缺少电源只是检查提示，不等同于错误图片；存在电源也不保证结果正确或非零。空连接点、LLM 空正文和数量不一致必须显式记录，不能通过静默忽略提高成绩。

高准确率目标应以**目标场景的整图正确率和未检出错误率**为核心，由第一轮基线确定具体目标；本次提取不宣称已提高识别准确率。
