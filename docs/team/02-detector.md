# YOLO11m 专项优化：独立优化指南

## 任务边界

负责文件：tools/modules/detector.py、tools/train_round.py；新增检测专项评估。
设备安排：组员A的RTX 5070 Laptop 8GB负责推理、评测、训练方案与小批量训练适配；用户RTX 5080 Laptop 16GB负责高显存训练和较重复验。具体配置与移交规则见[组员A任务单](ASSIGNMENT-MEMBER-A.md)。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 复现选定YOLO11m的66图基线，固定imgsz=960/conf=.25，尤其查看GND、电容、二极管与贴近文字的小框。
2. 先做推理对照：960→1280（显存允许时）、分块推理并还原坐标、分类阈值/NMS。每次改一个因素；统计重复框和耗时。
3. 与01整理漏检/误检/框边界困难样本，统一框是否包含引脚的标注规范；不要通过扩大框吞掉导线获得表面召回。
4. 只在训练集加轻度模糊、压缩、线宽与扫描噪声增强；增强后引脚/文字语义保持正确。
5. 从当前选定权重微调，首轮保留AdamW/lr=.0002/img960/batch8/seed42，降低batch以适配显存。重复最佳候选种子以排除波动。
6. 通过检测指标后，检查下游未解析引脚和整图网络是否退化，再交08决定是否替换。

## 验收指标与常见误区

不能仅提高召回而不报告误检；mAP50-95与IoU.75衡量框对后续连接的影响。基线mAP50-95=.745407，固定阈值F1@.5=.951524。拟定目标为改进这些开发指标且无明确下游退化，不预先承诺某个准确率。
训练命令的默认initial仍是上游权重，继续微调必须显式传入下面的initial/baseline。

## 独立运行

```powershell
python tools/run_stage.py detector --image examples/user_bjt_bias.jpg --out runs/detector-first
python tools/train_round.py --name yolo11m-team-001 --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.0002 --patience 10
```

## 新聊天启动语

```text
你负责 SINA 工作流的“YOLO11m 专项优化”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/02-detector.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
