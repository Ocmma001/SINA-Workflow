# SINA 工作流协作仓库

只管理电路图片识别、模型训练、评测、输出契约和文档；不包含GUI前端或ngspice。

**组员先读：[分区指南](分区指南.md) · [优化指南](优化指南.md)**。分区指南明确负责文件、独立运行和协作边界；优化指南汇总各部分方案与验收要求。

| 独立优化部分 | 详细任务 |
|---|---|
| 数据与评估 | [01指南](docs/team/01-data-evaluation.md) |
| YOLO11m检测 | [02指南](docs/team/02-detector.md) |
| OCR与参数绑定 | [03指南](docs/team/03-ocr-text.md) |
| 导线与交叉连接 | [04指南](docs/team/04-topology.md) |
| 引脚分析 | [05指南](docs/team/05-pins.md) |
| 豆包复核 | [06指南](docs/team/06-vision-review.md) |
| 输出契约与校验 | [07指南](docs/team/07-contract.md) |
| 集成与发布 | [08指南](docs/team/08-integration.md) |

**新聊天入口：[docs/team/START-HERE.md](docs/team/START-HERE.md)**。
安装与资源导入：[SETUP](docs/team/SETUP.md)。模块接口：[INTERFACES](docs/team/INTERFACES.md)。设备分配：[HARDWARE](docs/team/HARDWARE.md)。

GitHub克隆、按需检出与分支提交：[组员GitHub指南](docs/team/GITHUB.md)。

当前人员分工：[组员A（RTX 5070 Laptop 8GB）任务单](docs/team/ASSIGNMENT-MEMBER-A.md)。可执行的开发与评测交给组员A，高显存训练由用户电脑承担。

```text
图片 → YOLO11m → 导线连通区域 → 引脚连接
图片 → EasyOCR → 位号/参数绑定
候选 + 可选豆包复核 → recognized.json 待确认草稿
```

生产入口 `python tools/gui_workflow.py 图片 --out runs/新目录`，不依赖GUI。
独立阶段 `python tools/run_stage.py --help`。单测 `python -m unittest discover -s tools -p "test_*.py"`。

选定模型：YOLO11m round-002，imgsz960/conf0.25。66张开发验证图mAP50-95=0.745407，固定阈值F1@IoU.5=0.951524。不是独立测试成绩或整图识别准确率。
代码已拆分至 `tools/modules/`：detector、ocr、text_binding、topology、pins、vision；输出契约在 `tools/gui_contract.py`。
上游拓扑源码在 `tools/modules/topology_impl`，含MIT许可和出处。依赖各自许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。

大资源单独分发，Git不含权重、数据集、虚拟环境、API密钥及运行历史。下载源码后按SETUP导入资源。
公开协作仓库：[Ocmma001/SINA-Workflow](https://github.com/Ocmma001/SINA-Workflow)。模型和数据下载：[workflow-v1 Release](https://github.com/Ocmma001/SINA-Workflow/releases/tag/workflow-v1)。

仓库保留当前工作流、YOLO11m训练基线与协作指南；旧Pro直接检测、Lite/Pro对比及重复历史交接材料已清理。
