# 检测继续优化002：减少误检且保持总漏检数的候选

本轮完成偏置预热与冻结backbone两组对照。新增warmup0候选在66图开发验证集上将误检50降至46，漏检总数20保持不变；冻结前11层没有进一步改善检测效果。默认权重不变。

## 同条件结果

全部使用img960、mAP验证batch1，部署conf=.25/NMS=.7；66图、707目标。下表各行使用同一输入与评分逻辑，未从分母删除失败或难图。

| 模型 | mAP50–95 | F1@IoU.5 | F1@IoU.75 | TP@.5 | FP@.5 | FN@.5 |
|---|---:|---:|---:|---:|---:|---:|
| 当前默认模型 | 74.50% | 95.15% | 88.37% | 687 | 50 | 20 |
| 上一轮Mosaic0候选 | 74.79% | 95.46% | 88.76% | 684 | 42 | 23 |
| 本轮warmup0候选 | 74.70% | 95.42% | 88.61% | 687 | 46 | 20 |
| 本轮freeze11对照 | 74.59% | 95.42% | 88.47% | 687 | 46 | 20 |

上一轮候选仍有略高F1/mAP，但总漏检23个。warmup0是另一种取舍：相对默认模型减少4个误检且不增加总漏检；不是声称它在所有指标上胜出。
**漏检总数相同不代表漏检目标完全相同**：IoU.5下恢复circuit_0007的一个电阻，同时新增漏检circuit_0097符号总表中的一个二极管。严格IoU.75下各有6个目标发生恢复/丢失交换，交接包含逐目标变化。
按图错误数比较，IoU.5下3图改善、0图退化、63图不变；同一图内的恢复与丢失可能抵消，不能用这个统计替代逐目标检查。

## 为什么试这个设置

此前显式AdamW使用lr0=.00005，但默认偏置预热起点warmup_bias_lr=.1，首轮lr/pg2约.05069；其余参数组约.00002467。
本机Ultralytics8.4.178在optimizer=auto选择AdamW时会把偏置预热设为0，而显式AdamW路径未自动覆盖。保持其他条件不变，将该起点设0，验证是否能减少已有强权重微调时的初期扰动。
warmup0组首轮三个组lr均约.00002467。它避免了原先的高偏置预热，但准确率收益只能以本轮实际评估为准，不将库默认行为称为普遍错误。
随后只增加freeze=11对照。YOLO11的层0–10属于backbone；该库也对匹配冻结层的BatchNorm设置eval，neck/head其余参数与统计继续训练。此设置降低训练显存开销，没有在本数据上进一步改善检测表现。

## 训练记录

两组从相同round-002权重初始化，使用AdamW、lr0=.00005、Mosaic0、img960、batch8、seed42，最多40轮/早停10轮；仅freeze设置不同。并非从上一轮候选继续训练。

| 对照 | warmup_bias_lr | freeze | 完成轮数 | 最佳轮 | CSV训练耗时 |
|---|---:|---:|---:|---:|---:|
| warmup0 | 0 | 0 | 11 | 1 | 290.7秒 |
| freeze11 | 0 | 11 | 11 | 1 | 213.4秒 |

早停依据是训练循环自身的验证；最终表格另用统一batch1独立运行模型评估。不要把不同批次、padding或训练中的半精度分数混在一起挑最高值。
实际库trainer.py的SHA256：`7016131a47b61a8b9b9ea51ef5a9e59b0fb896a328eed4901c89ac7a83169655`，可用于核对上述实现行为。

## 可复现

在opt/detector分支，导入workflow-v1资源并准备CUDA环境后：

```powershell
python tools/train_round.py --name my-warmup0 --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.00005 --patience 10 --mosaic 0 --warmup-bias-lr 0
python tools/train_round.py --name my-freeze11 --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.00005 --patience 10 --mosaic 0 --warmup-bias-lr 0 --freeze 11
python tools/detector_experiment.py --name my-warmup0-eval --weights runs/my-warmup0/finetune/weights/best.pt --sizes 960 --batch 1 --device 0
python tools/detector_pair_report.py --baseline PATH/baseline/predict-960 --candidate runs/my-warmup0-eval/predict-960 --out runs/my-warmup0-paired.json
```

基线逐图预测在实验001评估包；图片与标签清单哈希为 `e9528fe9494588be8316e524bcda5850891be48d2ae35e7ef754d4ee3fec8dbd`。实际训练代码commit与全部参数见summary.json。

## 给组员的交接

[下载warmup0候选与评估包](https://github.com/Ocmma001/SINA-Workflow/releases/tag/detector-exp002)，约35.8 MiB。包含warmup0模型、两组完整逐图预测、训练配置/CSV、配对结果和SHA256清单；freeze11仅作对照，未放入额外模型文件。

候选模型SHA256：`abb1849d9b718c798adff45f9e623bae7c2f73f6f694d3bd5990c784e8156a94`。
评估包SHA256：`ba08bc283deabb99927a10361e010df7fc7ad214a3a47b228cc19cebc3423c7c`。

```powershell
python tools/local_extract.py examples/user_bjt_bias.jpg --weights PATH/models/candidate-warmup0.pt --out runs/warmup0-connection-review --device cpu
```

重点检查新增漏检二极管、恢复的电阻、未解析引脚、导线错误合并和有向端子语义。跨权重运行不能只用检测ID对应器件；应按原图几何和语义匹配。
默认模型清单和主工作流未替换。候选只供组员显式指定权重做回归，确认连接与新图效果后再决定发布。

## 验证与限制

43项测试通过；新增参数的负值/NaN/无穷大在GPU与数据加载前拒绝，原训练默认值保持兼容。完整候选包、各文件SHA256与远程上传校验值验证后交付。
按图配对重采样1000次、seed42：warmup0相对基线F1@.5差值95%区间约[0,+0.63]个百分点；F1@.75约[-0.82,+1.23]个百分点。前者下界是0，不能据此声称严格正收益；这些区间也没有计入挑选方案/权重的偏差。
所有成绩来自已参与调优的开发集、单随机种子；没有独立测试或OCR/引脚/网络真值结果。训练损失下降不是整图准确率提高的证明。
本轮无API调用，未改GUI、OCR、网络、schema或人工确认状态。下一步优先拿组员的新标注与下游结果验证，而不是仅凭同一66图继续挑分数。
