# 导线与交叉连接：独立优化指南

## 任务边界

负责文件：tools/modules/topology.py、tools/modules/topology_impl/nodes_analysis.py、find_crossing.py。
设备建议：CPU 为主；比较学习式分割才需 GPU。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 用固定检测框保存基线，标注有点交叉、无点交叉、T结点、跨线桥、断线和文字粘连等样例。
2. 优先消除find_crossing内隐藏的二次YOLO检测，复用传入元件框；与02/08约定接口并比较输出。
3. 对比固定阈值150与自适应二值化；线宽自适应膨胀、骨架提取、线段融合，防止断线和过度粘连。
4. 先在已知元件/文本区域建立掩码，保留真实引脚端点；分析遮盖造成的导线断裂。
5. 将交叉点的点/桥/间隙证据转成显式连接决策，确保分支结果进入最终labels，而非仅画在调试图里。
6. 遇到歧义保留候选与置信度，不强行合并。学习式线分割作为后续提案，先准备像素/网络真值。

## 验收指标与常见误区

输出H×W labels、circuit_info与坏例图。比较引脚对连通F1、错误合并数、错误断开数、整图拓扑正确率，不能仅看连通区域数量。
当前上游CCL+DBSCAN仍是基线，模块化没有自动解决交叉点问题。

## 独立运行

```powershell
python tools/run_stage.py detector --image examples/user_bjt_bias.jpg --out runs/topology-detector
python tools/run_stage.py topology --image examples/user_bjt_bias.jpg --input runs/topology-detector/detection.json --out runs/topology-first
```

## 新聊天启动语

```text
你负责 SINA 工作流的“导线与交叉连接”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/04-topology.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
