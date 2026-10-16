# 组员A本机验收入口

本页属于08集成分区。检测/OCR/拓扑/引脚算法与选定模型不因本入口改变。

## 运行

在仓库根目录使用本项目的 Python 环境，全部 GPU 工作顺序执行：

```powershell
.\SINA-venv\Scripts\python.exe tools/verify_member_a.py --out runs/member-a-acceptance-001 --evaluation
```

每次使用新目录。脚本先校验资源清单全部 SHA256，再运行单测、CUDA 张量计算、单阶段 GPU 检测、三张开发样例的默认 CPU 流程、一张 GPU 流程、契约/引脚回放。`--evaluation` 增加全部66张开发图的 IoU .5/.75 检测评估。

基线成功后，显式增加 `--training` 可按任务单执行960/batch1/2 epoch适配检查。此检查会训练前后验证，不更换选定权重。失败的前置步骤会阻止训练。它不是长期训练或模型胜出判定。

## 可追溯输出

- `provenance.json`：Git起点、当前Python源码哈希、资源清单哈希与资源校验结果。
- `summary.json`：每个命令的返回码、总尝试数、非零退出数；失败仍保留在分母。
- `*.log` / `*.result.json`：原始日志、耗时、资源采样和具体命令。
- `workflow-*/`：候选、待确认草稿、事件日志、检测图与导线调试图。
- `eval.5/`、`eval.75/`：逐图CSV及检测汇总；不属于独立测试成绩。

资源采样每约2秒加一次nvidia-smi调用开销。GPU数值为整张卡的占用，包含其他应用；RSS为进程树工作集求和，可能重复计算共享页。它们是采样峰值，不等同CUDA分配器的精确峰值，也不能据此认定没有瞬时尖峰。

命令成功不等于图像识别正确；OCR允许降级，须查看`stage_metrics.ocr.status`及草稿警告。新参考文件均未获人工评分批准，不能将旧实例ID/网络编号直接作为新输出的真值。

## 集成接口变化

完整流程CLI增加`--device`、`--conf`、`--imgsz`，默认仍为CPU/.25/960。显式`--weights`不再提前依赖默认模型。

`candidates.json`增加`stage_metrics`，逐项记录检测、拓扑、引脚、OCR的耗时和状态。`workflow.json`还记录可选复核的耗时/状态。既有阶段函数签名及识别schema不变。

云端复核取消时保留已写入图片哈希和事件记录的本地草稿，并继续抛出取消信号。任意非空输出目录均拒绝复用，防止旧失败日志混入新尝试。默认不调用API。

## 材料边界

资源可用性以`resources/development-references/availability.json`为准。两份历史参考可以辅助开发回放；独立测试图、审核后的OCR/引脚/网络标注以及第二人复核仍未提供。不能用模型预测填充人工审核状态。

Windows中文路径实测发现OpenCV直接读写可能产生乱码文件名；共享image_io新增write_image，拓扑内部仅替换图片读写调用，不改算法。回归包含准确文件名及PNG像素往返一致性，验收脚本另跑中文输入/输出路径的完整流程。
