# 豆包多模态复核：独立优化指南

## 任务边界

负责文件：tools/modules/vision.py、tools/vision_review.py；候选提示词放 prompts/variants/。
设备建议：普通电脑；主要消耗 API 用量而非本地显存。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 阅读prompts/provenance.json与原版清单提示词，保持原任务侧重点：识别已有标注，明确未知，复核已检测候选。
2. 先用缓存候选与API返回做离线验证，修复JSON解析/ID/角色索引的失败样例。原版提示词保持不可变基线。
3. 设计只复核低置信度元件的裁剪方案，附全图上下文和原图坐标；防止局部图丢失位号归属。
4. 使用同一图集比较Lite/Pro及提示词版本，每图至少记录请求数、耗时、token、失败、字段变更和真值评分。
5. 对比本地→Lite→Pro的升级条件，把预算留给难例；不能默认低置信度值就是概率可校准。
6. 全部API失败应退回本地草稿，不删除原始证据。批量调用前给出具体样本数、重复数和最大调用次数。

## 验收指标与常见误区

评估位号/值/型号/引脚角色与元件绑定的精确正确率，报告“纠正正确数”和“把正确改错数”。非法JSON、超时算失败。七轮直接检测结果已证明当前方案不宜取代YOLO，不重复全图直检竞赛。
当前默认Pro模型ID见modules/vision.py；是否更换服务型号须先核实可用性，本指南不声称某新模型更好。

## 独立运行

```powershell
python -m unittest discover -s tools -p test_vision_review.py
python -m unittest discover -s tools -p test_sina_prompts.py
# 付费单图例子：设置本机 .env 后才运行
python tools/gui_workflow.py examples/user_bjt_bias.jpg --out runs/vision-first --allow-cloud
```

## 新聊天启动语

```text
你负责 SINA 工作流的“豆包多模态复核”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/06-vision-review.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
