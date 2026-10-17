# 组员A第二轮：离线代码优化与实测（2026-10-17）

本轮按用户要求继续优化代码，不安排人工标注、不调用付费API、不新增训练。已交付导线/引脚/OCR/检测的代码改进和可复现评估工具；这不是对未来所有优化空间已经穷尽的声明。

## 已实现

| 模块 | 改动 | 默认行为 |
|---|---|---|
| 导线 | 复用冻结元件框，移除内部二次YOLO；不需要权重即可回放；输出crossing_status | 保留CCL/DBSCAN与阈值150；异常显式标为降级 |
| 性能 | 只读元件边界像素，查表生成标签图，点查询替代全图布尔掩码 | 随机等价性、颜色序列及三图精确比较通过 |
| 路径 | 调试变体只修改文件名，不替换父目录中的点；移除可能中断计算的emoji日志 | 中文及含点目录实测通过 |
| 引脚 | 清晰框边界的向外搜索、等距异网歧义留空、重复触点保护、多候选证据 | 半径仍为5；只接受0–32像素；不猜C/B/E或MOS体端 |
| OCR | Reader缓存、指定CUDA设备；可选放大/灰度/CLAHE；分别还原x/y坐标 | 原图策略保持；放大最多3倍，放大后像素预算400万 |
| 文字归属 | 距离上限、对齐惩罚、位号类型/单位限制、低置信度与等距歧义拒绝 | 原始OCR保留；候选保存拒绝原因和备选归属 |
| 检测 | 按设备缓存YOLO，NMS/分类阈值参数，分块坐标还原及类别内去重 | conf=.25、imgsz=960、iou=.7；默认不分块，不启用分类候选 |
| 数据评估 | 阈值扫描、保召回的分类阈值选择、固定框下游回放、按图配对bootstrap | 66张原val明确作为开发集，失败不删除 |

CPU调用不再修改CUDA_VISIBLE_DEVICES，避免同一服务之后无法使用GPU。预计算检测无需--skip-crossings，且保留原模型哈希/检测置信度。

## 验收结果

- 当前主工作区与干净源码检出均为 **78项单测通过**。
- 最终端到端验收 **12条命令、0失败**；包含当时的76项测试、GPU张量、检测、三图CPU流程、GPU流程、中文/含点路径、阶段回放及66图检测。随后新增两项统计工具测试，重跑全部78项通过。
- 组合CLI另有 **3条命令、0失败**：分类阈值+OCR放大、真实分块推理、无权重预计算检测回放。
- 三张控制图默认输出的ref/type/value/nodes/model与上一轮逐字段一致；连通栅格和circuit_info精确一致。
- 双阈值下游回放 **66图×2=132阶段、0失败**；分类阈值另有 **66阶段、0失败**，总计198次最终阶段执行成功。
- 干净源码检出重新校验1329项资源，76项生产/实验测试及新增统计测试全部通过；离线完整识别成功。复用同一已安装依赖环境，没有声称重新安装了操作系统或依赖。
- 选定模型SHA256仍为`0d2e5ec31358fc099a8dbef0eca5466acfe8b39346e5cde13def8ce1806aae4d`，未更换。

测试数量与命令数量分别统计，不能当作识别准确率。源码指纹见`runs/member-a-opt2/final-source-provenance.json`。

## 检测实验

固定66张开发图，权重不变；7种推理配置、16个置信度值，总计112个运行点。高阈值部分复用同一冻结预测，未重复运行GPU。推理profile共7×66张，所有图成功。

以下均固定conf=.25，作为单因素对照：

| 配置 | F1@IoU .5 | F1@IoU .75 | 失败 |
|---|---:|---:|---:|
| native | 0.951524 | 0.883657 | 0 |
| nms50 | 0.952183 | 0.884269 | 0 |
| nms60 | 0.952183 | 0.884269 | 0 |
| nms80 | 0.944979 | 0.880330 | 0 |
| nms90 | 0.905735 | 0.847726 | 0 |
| size1280 | 0.945329 | 0.877509 | 0 |
| tiles960 | 0.942138 | 0.861811 | 0 |

统一conf=.5的F1为.959660/.894551，但漏检20→29，且地符号/二极管召回下降，未采用。

分类阈值选择额外约束：每个类别在IoU .5与.75下的TP均不得低于conf=.25。候选在全部66图重新实际推理，预测与冻结计算逐条一致：

| 指标 | 原默认 | 分类阈值候选 |
|---|---:|---:|
| TP@.5 | 687 | 687 |
| FP@.5 | 50 | 32 |
| FN@.5 | 20 | 20 |
| F1@.5 | .951524 | 0.963534 |
| TP@.75 | 638 | 638 |
| FP@.75 | 99 | 81 |
| FN@.75 | 69 | 69 |
| F1@.75 | .883657 | 0.894811 |

固定这66张图，按图配对bootstrap（2000次、seed42）的F1增量95%区间：IoU .5为[0.004332, 0.021092]；IoU .75为[0.003982, 0.019347]。这些是开发图条件重采样区间；阈值也在同一开发集上选择，区间未计入选择偏差，不代表独立泛化。

原始排序检测器的mAP50-95控制值仍为.744967（val conf=.001、batch1）；没有声称分类阈值后处理提高了AP。

候选配置保存于`experiments/candidates/member-a-class-thresholds.json`，明确标为candidate。其66图下游阶段均完成，但3张图的共同触点部分连接关系改变；不能判定这些变化正确，故未自动替换默认设置。网络比较基于同一冻结检测表的显式ID/触点，不跨模型套用同名ID，也不直接比较任意region数值。

## 性能与失败记录

高密度`circuit_0097`在原接触点循环中长时间停留，旧回放在写出29张图的58条阶段记录后被主动中止，另有该图的1次未完成阶段。恢复后逐项审计发现：59次尝试的交叉阶段均为FileNotFoundError，旧summary中的stage_failures=0漏计了内部降级，不能据此宣称成功；保留原记录，并以`historical-failure-audit.json`更正解释。58次为降级结束，1次整体阶段中止，本批完整成功0/59。边界查询优化后，完整拓扑阶段在该图约1.52秒完成。原阶段没有完整耗时，不报告精确提速倍数。

随后首次快速回放132次均发现交叉阶段降级：`outputPath.replace('.',...)`改写了0.25父目录，触发FileNotFoundError。这批132次降级结果保留于`downstream-fast`，不与最终成功批次混淆。修复路径后重跑`downstream-final`才得到132/132完整成功。

四个下游回放批次合计389次阶段尝试：最终198次完整成功，早期190次降级结束、1次中止。198/198仅描述修复后的两批，不能替代全历史分母；这些计数也不是人工网络正确率。

随机50组栅格/边框测试确认边界触点及其排列与原算法一致；三张真实样例的连通栅格和电路候选也精确一致。性能优化没有改动线宽、二值化或聚类半径。

“未解析触点=0”不表示引脚齐全：基线66图仍有539个按符号端子数计算的名义缺失引脚。这是工程诊断，不能当作人工真值缺失率，也没有自动补接线。

OCR九组顺序实验显示小图放大可找回D1、5V、R2等文字，也出现VI/RI等误读。因此放大/CLAHE保留为可选实验，默认不启用；不以文字数量增多或置信度替代正确率。

## 运行命令

```powershell
# 默认离线GPU流程
.\SINA-venv\Scripts\python.exe tools/gui_workflow.py examples/user_bjt_bias.jpg --out runs/new-local --device 0
# 开发候选：显式启用分类阈值
.\SINA-venv\Scripts\python.exe tools/gui_workflow.py examples/user_bjt_bias.jpg --out runs/new-candidate --device 0 --class-thresholds experiments/candidates/member-a-class-thresholds.json
# 完整检测扫描；按顺序执行
.\SINA-venv\Scripts\python.exe tools/evaluate_detector_options.py --out runs/new-sweep --map
# 从冻结预测重新选择候选
.\SINA-venv\Scripts\python.exe tools/select_class_thresholds.py --predictions runs/new-sweep/native-predictions.json --out runs/new-class-candidate
```

分块实验使用`--tile-size 960 --tile-overlap .2`；OCR实验使用`--ocr-min-side 800 --ocr-preprocess gray`，均非默认。

## 代码提交与交接

以755178f为本轮起点，按职责拆分本地提交：

- e733c4e：冻结框交叉分析、CPU/GPU环境副作用与阶段兼容。
- aa62231：引脚方向/歧义/重复触点保护。
- 9deba3d：OCR预处理与有界文字归属。
- a5386cb：OCR元数据校验和指定设备缓存测试。
- cddce39：检测缓存/分块/实验入口与离线回放。
- df054e2：等价边界查询性能修复及含点路径修复。
- 6949df1：保召回的分类阈值选择、候选配置。
- 7f6fc18：不删除失败样本的配对重采样工具。

分支按前序提交叠加；若创建多个PR，应以前序分支为base分别审查。尚未推送、未创建PR、未发布。大权重、数据集、虚拟环境和运行目录不进入Git。

主要证据均位于`runs/member-a-opt2/`：acceptance.v1、extra-cli-results.json、detector-sweep、class-candidate、downstream-final、topology-performance-paired.json、pins-paired.json、binding-paired.json及clean-tests-final.log。

## 数据、证据与交付索引

- 本轮运行代码commit：`7f6fc1814ff23c43185e79d9aacba57432405bbb`；验收12命令时为`6949df1`，其后只增加统计工具及两项测试。源文件逐项哈希在`final-source-provenance.json`。
- 资源版本由`assets/manifest.json`固定，SHA256为`a9eb8213533526b77fca121cffa69135f3b452f0c7fd1b4d1224b4b2edac5b6b`；1329个资源文件已校验。596张训练图、66张开发验证图；独立OCR/语义引脚/网络人工真值未补齐。
- 参数及逐图预测：`detector-sweep/*-predictions.json`、`summary.json`及`extended-thresholds.json`；检测框、原图哈希及逐图真值/预测均保存在冻结记录。随机统计seed42；推理不新增随机增强或训练。
- 分类候选实际重推理：`class-candidate/actual-inference.json`；逐图下游：`downstream-final/summary.json`、`downstream-class-candidate/summary.json`；历史失败审计：`historical-failure-audit.json`。
- 最新源码ZIP、Git bundle、轻量证据ZIP、交接说明及SHA256清单位于`runs/member-a-delivery-002/`。证据包保留JSON、日志、实验脚本和文本；大型栅格/可视化以文件哈希清单索引，仍保留在本机`runs/member-a-opt2/`。模型和数据沿用单独校验资源包，不嵌入源码包。

本次恢复只做08集成交付的历史审计、报告更正与打包，没有更改推理代码、共享接口、选定权重，也没有重跑已完成的模型实验。
