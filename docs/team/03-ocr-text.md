# OCR 与参数绑定：独立优化指南

## 任务边界

负责文件：tools/modules/ocr.py、tools/modules/text_binding.py；新增独立 OCR 测试。
设备建议：CPU 可开发与评测；只有自训练 OCR 才安排 GPU。
优先优化当前实现，任何新增模型先提供数据需求和成本。本指南是待执行任务，不是已完成的准确率承诺。

## 统一验收与交接

先读 START-HERE.md、INTERFACES.md、AGENTS.md。全流程默认离线，未知信息不补猜，旧选定权重不覆盖。
执行 `python -m unittest discover -s tools -p "test_*.py"`；使用新输出目录，保留每个失败样本。
每次只改变一个主要变量；记录 commit、数据哈希、参数/种子、耗时/显存/调用次数及逐图结果。
提交代码、必要回归测试、对照报告、坏例可视化和资源哈希；大文件与私钥不进 Git。
可直接运行的命令假设终端位于仓库根且已激活识别环境；run_stage 可用 `--help` 查看参数。

## 首轮任务（按顺序）

1. 固定检测与拓扑结果，逐个分析 m/M、u/µ、0/O、1/I、小数点、Ω、位号和值的错误。
2. 对比原图与局部放大/灰度/对比度处理；单独记录旋转文本。所有OCR框恢复原图坐标。
3. 调整EasyOCR阈值和allowlist作为候选实验，区分位号与数值区域；避免全图allowlist损坏型号。
4. 优化文字归属：从当前最近框距离，增加方向、对齐、距离上限及一对一匹配；不把一段值重复分给多个元件。
5. 保留单位大小写，补充参数解析边界测试；将歧义交给06或人工。之后可在同一标注集比较另一OCR，达标再替换。
6. 只有现成OCR与预处理都受限且标注量足够时，再提出OCR微调，交给用户GPU排期。

## 验收指标与常见误区

报告字符错误率、数值/单位完整正确率和元件绑定准确率。必须测试10m与10M、47Ω、0.1uF、R_C无数字、模糊/缺失文字。不能用“可解析成数字”代替“与图相符”。

## 独立运行

```powershell
python tools/run_stage.py ocr --image examples/user_bjt_bias.jpg --out runs/ocr-first
```

## 新聊天启动语

```text
你负责 SINA 工作流的“OCR 与参数绑定”模块。当前仓库根是 SINA-Workbench。
先阅读 AGENTS.md、docs/team/START-HERE.md、docs/team/INTERFACES.md 和 docs/team/03-ocr-text.md。
只在指南规定的文件范围内优化，记录起始 Git commit，不修改前端。
先复现当前基线并展示真实错误，再逐项实施；遵守失败计入分母、保留未知字段、禁止数据泄漏。
未经对照评测不要替换选定 YOLO11m，不启动未明确授权的长时间训练或批量付费 API。
输出可运行代码、针对性测试、前后配对评估和按 EXPERIMENT-TEMPLATE.md 填写的报告。
需要其他模块改动时先列接口需求，不直接覆盖对方代码。电脑配置待用户补充。
```
