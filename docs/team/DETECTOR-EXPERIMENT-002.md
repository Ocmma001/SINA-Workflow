# YOLO11m继续优化002：AdamW偏置预热对照

日期：2026-10-17。分支opt/detector，接续实验001，当前默认权重仍为round-002。

## 假设与证据

实验001的显式AdamW配置使用lr0=.00005，但warmup_bias_lr默认.1，首轮结果中偏置组lr/pg2约.05069。
本机Ultralytics8.4.178的engine/trainer.py预热逻辑按参数组插值；在optimizer=auto分支选择AdamW时，库会将warmup_bias_lr设为0，而显式AdamW未进入该分支。
这提示高偏置预热可能干扰已有强权重的低学习率微调；它是待验证假设，不是已经证明的性能缺陷。

## 单变量实验

从相同round-002权重重新开始，保持img960、batch8、lr0=.00005、Mosaic0、seed42、最多40轮/早停10轮，只将偏置预热起点从.1改为0。
对照为实验001的no-Mosaic训练；不从该候选继续训练，以免混入初始化差异。
训练脚本新增可配置参数，默认.1保留既有兼容行为；负值、NaN或无穷大在GPU/数据加载前拒绝。

```powershell
python tools/train_round.py --name detector-exp002-train-warmup0 --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.00005 --patience 10 --mosaic 0 --warmup-bias-lr 0
```

## 验收

- 在相同66图/707目标、batch1/img960验证mAP；固定conf.25/NMS.7计算P/R/F1@IoU.5/.75。
- 与原默认权重、实验001候选分别逐图配对；全部失败计入分母，报告误检和漏检。
- 保留训练配置、结果CSV、权重/输入哈希和模型计时。
- 只有一个种子且使用开发验证集，不能声称独立泛化或网络正确率改善。
- 不调用API，不修改GUI/OCR/网络接口，不自动替换选定权重。

训练与部署验证完成后，结果写入experiments/detector-exp002，并给组员提供明确的下游回归输入。

## 扩展对照：冻结前11层参数

已有强权重继续训练时验证分数早期达到峰值后回落，可能存在对原特征的过度更新。新增一组在warmup_bias_lr=0基础上只改freeze=11。
本机YOLO11结构的前11层是backbone（至C2PSA）；后续neck/head参数继续训练。这里冻结的是参数，不声称所有BatchNorm运行统计保持不变。
与warmup0组使用相同原始初始化、学习率、增强、seed及早停。新增freeze参数默认0，不改变旧训练行为。

```powershell
python tools/train_round.py --name detector-exp002-train-freeze11 --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.00005 --patience 10 --mosaic 0 --warmup-bias-lr 0 --freeze 11
```

两组GPU任务顺序运行。全部候选仍须同条件逐图对照，不因损失下降或冻结层数改变而声称准确率提升。
