# YOLO11m检测优化001：候选有小幅开发集改善，默认权重不变

已完成三种输入分辨率、四个部署阈值和两组继续微调。关闭Mosaic的低学习率候选在当前66图开发集上小幅改善mAP与F1，但漏检增加，配对重采样区间包含零；仍需新图与引脚/网络回归。

## 同条件结果

下表统一imgsz=960、mAP验证batch=1；固定部署conf=.25、NMS IoU=.7。同一66图/707目标，失败全部计入分母。mAP与固定阈值F1是不同指标。

| 方案 | mAP50–95 | F1@IoU.5 | F1@IoU.75 | FP@.5 | FN@.5 |
|---|---:|---:|---:|---:|---:|
| 当前权重 | 74.50% | 95.15% | 88.37% | 50 | 20 |
| 低学习率，Mosaic=.2 | 74.00% | 95.14% | 88.75% | 48 | 22 |
| 低学习率，Mosaic=0 | 74.79% | 95.46% | 88.76% | 42 | 23 |

候选在IoU.5下正确检测684个（基线687），误检42个（基线50），漏检23个（基线20）。精确率提高、召回率下降，不能只报告F1改善。
严格IoU.75下正确检测636个（基线638），误检90个（基线99），漏检71个（基线69）。

配对按图重采样1000次、seed42：F1@.5差值95%区间约[-0.80,+1.38]个百分点；F1@.75约[-0.96,+1.76]个百分点，均包含0。这只是开发集抽样描述，不包含模型选择带来的不确定性。

## 分辨率与阈值结论

| 输入尺寸 | mAP50–95 | 固定conf=.25 F1@.5 | F1@.75 | 暖机后单图墙钟耗时 |
|---|---:|---:|---:|---:|
| 960 | 74.50% | 95.15% | 88.37% | 21.2 ms |
| 1280 | 73.15% | 94.53% | 87.75% | 26.6 ms |
| 1536 | 71.19% | 92.93% | 84.42% | 29.3 ms |

当前权重在960最好，保留960。最初batch4/1536验证出现接近16GB显存占满与停顿，已停止并记录；最终三个尺寸全部统一batch1完成，该未完成尝试不混入完整结果。
提高全局阈值可减少误检，也会增加漏检。例如候选conf=.35时F1@.5为96.12%，但漏检25个；conf=.5时漏检36个。当前默认阈值仍为.25。完整阈值结果见summary.json和Release的逐图预测。

## 训练配置

两组均从原选定权重继续微调：AdamW、lr0=.00005、img960、batch8、seed42、上限40轮、patience10；翻转/大角度旋转关闭，其他增强保持现有训练配置。第二组只相对第一组关闭Mosaic。
两组均完成13轮后早停，最佳权重来自第3轮。低学习率组约316秒，关闭Mosaic组约323秒（精确值见summary.json）。
训练内置batch8验证基线mAP50–95为74.54%，无Mosaic候选为74.96%；上表统一batch1得到74.50%与74.79%。矩形批次padding可能影响分数，不交叉挑选不同batch的结果作比较。
这是继续训练与增强方案的探索，不声称所有变化可仅归因于学习率；训练轮数、初始化、评估配置均已记录。只有一个随机种子，尚未做多种子复验。

## 可复现命令

```powershell
python tools/detector_experiment.py --name my-resolution-run --weights runs/round-002/delivery/detector.pt --sizes 960 1280 1536 --batch 1 --device 0
python tools/train_round.py --name my-low-lr --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.00005 --patience 10 --mosaic 0.2
python tools/train_round.py --name my-no-mosaic --initial runs/round-002/delivery/detector.pt --baseline runs/round-002/delivery/detector.pt --epochs 40 --imgsz 960 --batch 8 --device 0 --lr0 0.00005 --patience 10 --mosaic 0
python tools/detector_experiment.py --name my-candidate-eval --weights runs/my-no-mosaic/finetune/weights/best.pt --sizes 960 --batch 1 --device 0
python tools/detector_pair_report.py --baseline runs/my-resolution-run/predict-960 --candidate runs/my-candidate-eval/predict-960 --out runs/my-paired.json
```

初始数据为SINA快照的596张train/66张val。训练资源逐文件哈希在assets/manifest.json；部署评估输入清单哈希为 `e9528fe9494588be8316e524bcda5850891be48d2ae35e7ef754d4ee3fec8dbd`。代码从f0a0d22开始，完整改动在opt/detector分支。

## 组员接手

[下载候选与评估包](https://github.com/Ocmma001/SINA-Workflow/releases/tag/detector-exp001)，约36.1 MiB；包含候选权重、全部已完成方案逐图预测、训练配置/曲线CSV和包内SHA256清单。当前基线权重和全量数据仍从workflow-v1资源包导入。

候选SHA256：`43a5f9fdabe6c8c2da1cd7aad6ff772715d60c7eba60f71c2fe87090cea408f5`。
评估包SHA256：`b83e8b4c10b907d35a51510c1297d9196e409f09b172b66ab2a96246afa439fd`。

在自己的工作分支上显式指定候选路径即可跑已有本地引擎：

```powershell
python tools/local_extract.py examples/user_bjt_bias.jpg --weights PATH/models/candidate-no-mosaic.pt --out runs/candidate-connection-check --device cpu
```

重点核查新增漏检、未解析引脚、错误网络合并、三极管/MOS端子顺序，以及候选是否导致原先正确的整图连接退化。不同权重的检测ID不保证相同，按原图几何与元件语义对齐。
严格IoU下9图改善、9图退化、48图错误数不变；IoU.5下8图改善、5图退化、53图不变。列表见changed-images.json，完整预测在包内。
基线错误较多的circuit_0097是包含逻辑门/开关等类别的符号表，circuit_0046涉及电容符号；这些作为人工复核线索，未修改其真值或从分母删除。

## 实现与验证

新增可复现的分辨率实验、同类一对一匹配与严格配对报告；训练脚本增加可配置Mosaic，默认.2保持兼容。
评估工具默认batch1，记录图片/标签/权重哈希、阶段时间、模型计时与PyTorch峰值分配显存；后者不等于任务管理器全部专用显存。
41项测试通过。新增测试覆盖重复框/错类别、严格IoU、漏检分母、输入或标注不一致、缓存置信度范围与混合图片格式。代码只做检测专项改动，未更改GUI、OCR、连接、人工确认、schema或全局选定权重。
本轮没有API调用，没有独立测试集成绩，没有验证OCR/引脚/网络或仿真正确率。
默认模型清单保持原SHA256 `0d2e5ec31358fc099a8dbef0eca5466acfe8b39346e5cde13def8ce1806aae4d`。本候选进入组员回归队列，不能仅凭这组开发分数发布为新的默认模型。
