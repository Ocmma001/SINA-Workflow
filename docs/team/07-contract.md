# 输出 JSON 与电路校验：独立优化指南

## 任务边界

负责文件：tools/gui_contract.py、schemas/recognized.schema.json、tools/test_gui_contract.py。
设备建议：普通电脑，无 GPU 需求。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 固定v2草稿结构，添加正反例：缺值、重复位号、未知型号、未接地、缺源、孤立端、未知元件。
2. 检查候选/人工修改/确认/撤销状态转移；修改任何相关字段后都不能沿用旧确认连接快照。
3. 增强电气一致性检查，但不能凭电路常识生成不存在的元件或数值；用issues区分“未知”“不支持”“格式错误”。
4. 原图证据与suggested字段分开，字段来源可追踪；输出应能被任何前端读取。
5. 如需支持MOS/运放，先提出模型参数与节点接口变更，由外部仿真负责人确认能力，不能仅改supported集合。
6. 使用稳定的最小fixture验证JSON序列化与schema。版本升级由08安排，保留旧接口转换。

## 验收指标与常见误区

契约验收是字段/状态正确性与错误发现能力，不是图像准确率。ready_for_simulation只代表前置校验；API不能设置user_confirmed。保留额外字段，不能悄悄丢掉未支持器件。

## 独立运行

```powershell
python -m unittest discover -s tools -p test_gui_contract.py
python tools/run_stage.py contract --input runs/modular-smoke-001/candidates.json --out runs/contract-first
```

## 新聊天启动语

```text
你负责 SINA 工作流的“输出 JSON 与电路校验”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/07-contract.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
