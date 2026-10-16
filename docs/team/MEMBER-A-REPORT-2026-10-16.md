# 组员A本机执行与验收报告（2026-10-16）

已完成环境与资源准备、检测开发基线、集成修复、数字歧义安全修复、阶段回放和2轮训练适配。本报告不代表八个分区已全部完成；OCR/引脚/拓扑完整准确率仍缺少获准评分的人工真值和独立测试集。

## 代码与资源

- 起点：`f0a0d22`（已拉取新增开发参考）。
- 集成分支 `opt/member-a-integration`：`8856a34`。
- 数字安全分支 `opt/member-a-ocr-safety`：`600023c`，依赖集成分支；审查该修复时以`8856a34`为base，可避免将两个分区混入同一PR。
- 上述提交均为本地提交，尚未推送。
- Python 3.13.7；torch 2.11.0+cu128；CUDA 12.8；RTX 5070 Laptop；驱动573.24；8151MiB专用显存。依赖检查通过。
- Release ZIP SHA256：`b907ce6726a81d7b3df2813e0e8ac356d52f6fffaaa9172d07a60a92b47fb8af`。
- 官方torch wheel SHA256：`6f367e62fd81b75cdf23ca4b75ced834d2db2cf98d1588ac935bde345de9de23`。
- 资源清单SHA256：`a9eb8213533526b77fca121cffa69135f3b452f0c7fd1b4d1224b4b2edac5b6b`；全部1329项通过校验。
- 选定模型SHA256：`0d2e5ec31358fc099a8dbef0eca5466acfe8b39346e5cde13def8ce1806aae4d`；未更换。
- 最终源码逐文件哈希和66图逐图哈希：`runs/member-a-final-001/provenance.json`。
- 实际依赖快照：`runs/member-a-baseline/environment-lock.txt`。

## 命令与结果

```powershell
.\SINA-venv\Scripts\python.exe tools/verify_member_a.py --out runs/member-a-final-001 --evaluation
.\SINA-venv\Scripts\python.exe tools/train_round.py --name member-a-fit-001 --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 2 --imgsz 960 --batch 1 --device 0 --lr0 0.0002 --patience 10
```

最终验收12个命令，12成功、0失败；单测43项全部通过。首次验收12项、原代码三图配对回放与最终验收均留存，未删除旧尝试。这里的命令数不等于图像数或准确率分母。

| 项目 | 本机实测 |
|---|---|
| GPU张量运算 | CUDA可用；64个1的平方求和=64 |
| 单阶段GPU检测 | 成功；最终进程用时6.29秒 |
| CPU完整流程 | 3/3成功，三图均完成OCR |
| GPU完整流程 | 成功；12.52秒，整卡采样峰值5918MiB |
| 中文输入/中文输出路径 | 完整流程成功；PNG精确文件名和像素往返测试通过 |
| 固定候选契约/引脚回放 | 成功；不重新检测或调用API |
| 云端失败/取消与OCR失败 | mock回归通过，保留草稿、未知字段和错误状态，不泄露错误正文 |
| API实测 | 0次；没有付费复核评测 |
| 干净源码clone | 1329项资源重新导入成功；43项单测通过；离线完整识别及schema验证通过；使用相同已安装依赖环境 |

在固定`f0a0d22`完整Python源码上回放三张图，集成修复前后候选（除新增计时字段）逐字段一致。首次CPU运行49.61秒、最终20.97秒存在冷启动/缓存影响，不能解释为代码提速。

## 检测开发评估

固定66张原val图、选定YOLO11m、conf=.25、imgsz=960、NMS IoU=.7；所有66图成功，0失败。该集合已用于调优。

| 匹配阈值 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| IoU≥.5 | 687 | 50 | 20 | .932157 | .971711 | .951524 |
| IoU≥.75 | 638 | 99 | 69 | .865672 | .902405 | .883657 |

IoU .5 F1与仓库记录一致。逐图分母及每类指标在`runs/member-a-final-001/eval.5/`、`eval.75/`。按误检+漏检排序的坏例首项为`circuit_0111.jpg`（12误检、3漏检）和`circuit_0097.jpg`（9误检、4漏检），清单在`runs/member-a-baseline/detector-badcases.json`。

## 训练适配

- 960/batch1/2 epoch，workers=0、cache=False、amp=True、seed=42、deterministic=True。
- 全流程完成，返回码0、未OOM；总用时269.36秒，含训练前/后验证。
- 进程树RSS采样峰值3714.6MiB；整卡显存采样峰值3965MiB。
- 第1轮记录133.346秒；两轮累计220.755秒。CSV在`runs/member-a-fit-001/finetune/results.csv`。
- 同配置基线mAP50-95=0.744967；候选=0.732624。候选退化，保留原模型。2轮只证明可运行性，不作为最终训练结论。
- 本机batch1验证mAP与仓库旧记录.745407略有差异，未声称mAP逐位复现。
- 候选权重SHA256：`e158f8cc20fd4d88077d40bd2c647fa9ae6578a78f7ba2516ca5f31cd5375c2a`。权重仅保存在本地runs中。
- 未验证batch2、高分辨率、大batch、多种子或长期训练。

所有显存数值为约2秒间隔的整卡占用采样，含其他应用；RSS为进程树工作集之和。它们不是精确CUDA分配器峰值，可能漏掉瞬时尖峰。

## 已修复的真实问题

1. 完整CLI增加设备、尺寸、阈值参数；显式权重不再被缺失默认模型提前阻断。
2. 检测/拓扑/引脚/OCR/API分别记录耗时和状态；OCR失败显式标记。
3. 云端复核取消后，本地草稿仍保留图片哈希和取消日志；非空输出目录禁止复用，防止旧失败日志混入新尝试。
4. Windows OpenCV直接写中文文件名曾返回成功却生成乱码文件；统一使用编码字节读写，修复拓扑图片证据路径。仅更换图片读写，不修改几何算法。
5. `circuit_0003`的OCR原文`47 0`此前被拼成`470`。解析器和契约调用点现拒绝拼接分离数字，结果为null，等待核对；没有猜成47。

安全修复固定同三张候选配对回放：BJT偏置图和开关LED图的器件字段无变化；circuit_0003仅Resistor_1数值由470变为null。三图均通过schema且保持user_confirmed=false、ready_for_simulation=false。这是开发坏例安全验证，不是OCR独立测试准确率。

## 数据审核与任务覆盖

596张训练图/5742框，66张开发图/707框，非法YOLO标注0项。训练集内2组精确重复；跨集合的历史近重复候选仍等待人工确认，缩放算法不同会改变dHash距离。两份参考图片哈希匹配，但均approved_for_scoring=false。

已准备30张未审核开发图标注记录；它们不是人工真值。现有标注缺少经过审核的逐字OCR/文字框/绑定、语义引脚/网络以及第二位人类复核。

| 分区 | 本轮完成 | 尚未验收 |
|---|---|---|
| 01数据 | 数量/标注/资源/重复审核、冻结哈希、坏例和待标注清单 | 人工标注、第二人复核、来源隔离独立测试集 |
| 02检测 | 66图IoU .5/.75基线、GPU推理、小批量训练适配 | 阈值/分块/训练候选优化及下游真值评估 |
| 03OCR | 原始文字坏例、数字片段安全解析、三图配对回放 | OCR预处理/识别质量、绑定准确率完整评估 |
| 04导线 | 固定阶段输出、路径兼容修复、完整运行 | 断线/错合并/交叉拓扑准确率；二次YOLO耦合仍存在 |
| 05引脚 | 有界吸附现有回归与固定输入回放 | 角色/网络人工真值、方向约束候选和误吸附评估 |
| 06复核 | 离线mock失败/取消回归 | 明确API预算后的实测、纠错与成本评估 |
| 07契约 | schema/未知值/人工确认回归、阻止470伪确定值 | 消费者最终接口验收及完整电气真值评估 |
| 08集成 | 阶段计时/状态、CLI、Unicode、全流程/回放回归、干净源码交接验证 | 发布/PR合并、完整独立准确率验收 |

## 交接索引

- 使用说明：`docs/team/MEMBER-A-VERIFICATION.md`。
- 最终验收：`runs/member-a-final-001/summary.json`。
- 原代码配对：`runs/member-a-baseline/paired-replay.json`。
- 安全修复配对：`runs/member-a-quantity-paired/comparison.json`。
- 训练：`runs/member-a-fit-001/comparison.json`及`runs/member-a-baseline/training-fit-001.result.json`。
- 数据/待标注：`runs/member-a-baseline/data-audit.json`、`annotation-queue-30.json`。

大权重、数据集、虚拟环境、运行目录均未提交。下载曾断流、pip安装曾遇证书适配错误；完整哈希验证后才使用资源和torch。干净clone首次因本机Git所有权检查失败，增加仅本次命令生效的精确信任路径后重试成功。未将这些环境失败隐藏为识别成功样本。
