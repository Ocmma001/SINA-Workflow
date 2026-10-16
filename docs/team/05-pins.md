# 引脚定位与语义：独立优化指南

## 任务边界

负责文件：tools/modules/pins.py；新增引脚标注/测试；接触点提取迁移先协调04。
设备建议：连接规则用 CPU；关键点模型训练优先交用户 GPU。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 用04保存的circuit_info和node_labels脱离YOLO/OCR调试，分类统计未解析、错吸附、同器件重复触点。
2. 现在采用半径5像素最近标签；比较按线宽/图尺寸调整但有上限的半径，并引入端点方向与距离约束。
3. 保留多候选和歧义证据，明确何时返回null；不要通过无限增大半径隐藏缺失引脚。
4. 与04拆分接触点检测职责，约定每个触点原图坐标、器件ID、候选线方向，不同时编辑同一算法文件。
5. 为BJT C/B/E、二极管A/K、电源正负、MOS D/G/S/B补充角色真值。规则不能判定时交06复核。
6. 若定位仍受符号旋转/密集框限制，先标注关键点数据，再提关键点训练实验；不直接重训无标签模型。

## 验收指标与常见误区

像素定位误差需按图尺寸/符号尺度报告，另算引脚到网络正确率、角色顺序正确率、缺失率和误吸附率。缺B极不能靠重复其他端子填充；MOS缺体端必须保持未解决。

## 独立运行

```powershell
python tools/run_stage.py pins --input runs/topology-first --out runs/pins-first --radius 5
python -m unittest discover -s tools -p test_modules.py
```

## 新聊天启动语

```text
你负责 SINA 工作流的“引脚定位与语义”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/05-pins.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
