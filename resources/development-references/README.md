# 组员需要的现有材料与缺口

结论：已有检测数据与少量开发参考，但没有完整、经第二人复核的OCR/引脚/网络人工真值，也没有找到符合独立性要求的测试集。
本目录供组员完成基线、整理坏例和准备人工复核；不能据此宣布独立测试准确率。

## 已有的材料

| 材料 | 位置 | 可以用来做什么 |
|---|---|---|
| 596张训练图、66张开发验证图及YOLO元件框标注 | [Release资源包](https://github.com/Ocmma001/SINA-Workflow/releases/tag/workflow-v1)，按[SETUP](../../docs/team/SETUP.md)导入 | 检测训练/开发验证；不包含完整OCR或网络真值 |
| BJT偏置图 | [原图](../../examples/user_bjt_bias.jpg)、[开发参考](bjt_bias.reference.json) | 位号/未知数值/连接参考的人工复核起点 |
| circuit_0003 | [原图](circuit_0003.jpg)、[上游YOLO标注](circuit_0003.yolo.txt)、[开发参考](circuit0003.reference.json) | 已知电阻/电源数值、位号与引脚网络的复核起点；此图属于原val |
| 第二张用户样例 | [图片](../../examples/user_switch_led.jpg) | 开发坏例或待标注图片；没有配套完整真值 |
| 数据审核 | [类别/数量](../../experiments/data-audit.json)、[近重复候选](../../experiments/near-duplicate-audit.json) | 数据清理；三组相似图尚需人工判断 |
| 待复核清单 | [review-queue.json](review-queue.json) | 安排两张参考图及三组近重复候选的人工检查；不是已经完成的复核记录 |

完整可用性清单：[availability.json](availability.json)。新增上游图片和标注按[SINA许可](SINA-LICENSE.txt)提供，固定来源commit见根目录[UPSTREAM.json](../../UPSTREAM.json)。

## 开发参考为什么不能直接当人工真值

两份reference JSON来自此前保存的局部核对记录，不是模型API原始返回；但没有记录可核实的人类标注者身份和第二人签核。
因此统一设置 `approved_for_scoring=false`、`human_review_status=not_documented`、`second_human_review=null`。历史文件曾使用的truth字段不能证明它已完成人工真值流程。

- `normalized_ref`只提供规范化位号，不是逐字OCR转录；R_C与RC等写法需要统一标注规范。
- 没有经过人工审定的OCR文字多边形框或引脚像素坐标。
- `legacy_instance_id`与整数网络号属于旧运行；新检测的同名ID不能直接假定对应同一元件，网络也应按连接关系比较。
- MOS旧参考将体端网络重复为源端网络，缺少独立复核证据；这个问题已显式标记，不能直接拿来评分或补接线。
- 两张图此前都参与过工作流调优，不符合独立测试图要求。

## 明确没有找到的材料

1. 未参与训练、阈值选择、提示词调优的隔离测试集及来源清单。
2. 完整OCR原文/文字框/元件归属人工标注。
3. 完整引脚坐标、C/B/E或D/G/S/B语义与所属网络的人工标注。
4. 对争议样本的第二位人类复核者、日期和最终裁定记录。

另外，本机旧`confirmed_bjt.json`/`.cir`填入了12V、100k等仿真参数，原图未标这些数值；它们是仿真演示数据，不能作为图片参数真值，所以未上传到本目录。

## 组员现在可以继续做什么

先运行现有代码测试、66图检测开发基线、单阶段回放和坏例整理；报告中将OCR/引脚/网络结果明确列为未完成独立人工评估。
使用本目录参考准备人工标注草稿，之后由真实标注者检查，第二人复核争议项；记录审核来源后才形成可评分真值。
不需要等待用户提供不存在的材料才开始现有资源支持的工作；也不能用API自报置信度或重复调用同一模型替代第二人复核。

截图中提到的完整CLI指定GPU、阶段独立计时、OCR/API失败与取消行为属于组员正在处理的集成事项，本次只补充材料，不覆盖其代码修改。
