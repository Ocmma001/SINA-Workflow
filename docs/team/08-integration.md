# 集成、回归与交付：独立优化指南

## 任务边界

负责文件：tools/local_extract.py、gui_workflow.py、run_stage.py、model_selection.py、docs/team/、资源清单。
设备建议：CPU 可做全部小样本验收，GPU 仅加速批量推理。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 维护各模块输入输出与起始commit，给组员保存的阶段数据；默认不开API、不重训。
2. 每次只合并一个模块，先跑单测，再跑同一组冻结图片；保存逐阶段输出及端到端差异。
3. 分别验证OCR失败、API失败、损坏图片、缺模型、中文路径、取消时保留已有草稿的行为。
4. 将耗时拆到检测/拓扑/OCR/API，保证异常不泄露密钥、不把失败包装成空成功。
5. 更新模型选择前验证哈希、全66开发集检测与独立测试、后续连接回归。其他人仅提交候选，不能改全局选定权重。
6. 准备干净clone和资源包导入测试；输出纯工作流源码包/资产包，不把GUI源码纳入此仓库。GUI消费者的打包需另行同步modules目录。

## 验收指标与常见误区

单测全通过，离线流程无需Qt/GUI目录；中文路径、API降级、schema兼容、资源校验均有证据。优化合并须提供旧/新配对结果，不能把单图smoke称准确率提升。

## 独立运行

```powershell
python -m unittest discover -s tools -p "test_*.py"
python tools/gui_workflow.py examples/user_bjt_bias.jpg --out runs/integration-first
```

## 新聊天启动语

```text
你负责 SINA 工作流的“集成、回归与交付”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/08-integration.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
