# SINA 工作流协作仓库

只管理电路图片识别、模型训练、评测、输出契约和文档；不包含GUI前端或ngspice。

**新聊天入口：[docs/team/START-HERE.md](docs/team/START-HERE.md)**。
安装与资源导入：[SETUP](docs/team/SETUP.md)。模块接口：[INTERFACES](docs/team/INTERFACES.md)。设备分配：[HARDWARE](docs/team/HARDWARE.md)。

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
目前为本地Git仓库；GitHub发布需要目标账户/远程仓库地址，尚未配置。

历史实验与原版流程保留作参考；当前生产架构以team指南为准。
