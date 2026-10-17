# SINA 电路图识别工作流

将电路原理图图片转换为可编辑的结构化电路数据，供 LabPilot 展示、人工核对和后续网表生成使用。

## 工作流程

```text
电路图片
   ├─ YOLO11m → 元件类型、位置
   ├─ EasyOCR → 位号、参数文字 → 文字与元件关联
   └─ OpenCV 连通区域分析 → 导线、交叉点 → 引脚连接候选
                         ↓
                 recognized.json
                         ↓
                      人工核对
```

支持电阻、电容、电感、BJT、MOSFET、电压源、电流源、地、运放和二极管的检测。默认流程在本地运行，可使用 CPU 或 NVIDIA GPU，无需 API 密钥。

识别结果保留元件位置、文字证据和连接候选。无法确定的参数或引脚顺序留空，结果需人工确认后再用于生成仿真网表。本仓库提供识别工作流，不包含 GUI 前端或 ngspice。

## 安装

以下命令使用 Windows PowerShell，在安装 Python 和 Git 后执行。

### 1. 获取代码并创建环境

```powershell
git clone https://github.com/Ocmma001/SINA-Workflow.git
cd SINA-Workflow
python -m venv SINA-venv
.\SINA-venv\Scripts\Activate.ps1
```

### 2. 安装依赖

CPU 环境：

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-workflow.txt
```

使用 NVIDIA GPU 时，将第一条命令的安装索引替换为与设备、驱动兼容的 CUDA 版本。本项目已验证的 CUDA 安装索引为 `https://download.pytorch.org/whl/cu128`。

### 3. 导入模型资源

从 [workflow-v1 Release](https://github.com/Ocmma001/SINA-Workflow/releases/tag/workflow-v1) 下载 `SINA-workflow-assets.zip`，然后导入：

```powershell
python tools/import_assets.py "D:\Downloads\SINA-workflow-assets.zip"
```

请将示例路径替换为实际下载位置。导入器会校验文件哈希并恢复所需资源，包括：

| 资源 | 导入位置 |
|---|---|
| YOLO11m 权重 | `runs/round-002/delivery/detector.pt` |
| EasyOCR 权重 | `SINA-venv/easyocr_models/` |
| SINA 资源 | `SINA/` |

权重和虚拟环境不随 Git 仓库分发。先创建环境，再导入资源。

## 使用方法

### 识别一张电路图

```powershell
python tools/gui_workflow.py examples/user_bjt_bias.jpg --out runs/first-local
```

识别自己的图片时，替换输入路径。每次使用一个新的输出目录，避免覆盖已有识别记录。

### 使用 GPU

```powershell
python tools/gui_workflow.py "D:\Pictures\circuit.png" --out runs/circuit-gpu --device 0
```

`--device cpu` 使用 CPU（默认），`--device 0` 使用第一张 NVIDIA GPU。

### 单独运行检测或 OCR

```powershell
python tools/run_stage.py detector --image examples/user_bjt_bias.jpg --out runs/detection-only
python tools/run_stage.py ocr --image examples/user_bjt_bias.jpg --out runs/ocr-only
```

查看完整参数：

```powershell
python tools/gui_workflow.py --help
python tools/run_stage.py --help
```

## 输出文件

完整流程的输出保存在 `--out` 指定的目录中：

| 文件 | 内容 |
|---|---|
| `recognized.json` | 可编辑电路草稿：元件、位号、参数、型号及候选节点 |
| `candidates.json` | 本地检测、OCR、引脚与连接证据 |
| `workflow.json` | 模型信息、运行参数、阶段状态和耗时 |
| `events.jsonl` | 各阶段进度记录 |
| `evidence/detected.jpg` | 元件检测框可视化 |
| `evidence/debug/` | 导线、交叉点及连接分析的中间结果 |

`recognized.json` 的 `components` 是可编辑元件列表；接地信息保存在识别与拓扑证据中。输出默认标记为待复核，不会自动视为可仿真的电路。

## 来源与许可

工作流基于 SINA，导线分析源码的许可见 [LICENSE](tools/modules/topology_impl/LICENSE)，第三方依赖说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。
