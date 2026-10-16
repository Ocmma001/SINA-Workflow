# Pro 直接检测实验路线

此路线让 Pro 只看原始图片，输出十类元件框，不向检测请求提供 YOLO、OCR 或人工标注候选。输出使用 0–1000 归一化坐标，转换为原图像素后做本地校验。

API 请求使用官方 `text.format` 严格 JSON Schema。即使请求严格格式，本地仍必须校验并拒绝不合规结果；实际实验中仍观测到格式失败，不能认为接口声明严格就一定成功。官方说明：https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh 。

## 检测单张图片

在项目根目录执行，输出目录必须不存在：

```powershell
.\SINA-Workbench\SINA-venv\Scripts\python.exe .\SINA-Workbench\tools\pro_detector.py "D:\你的图片.jpg" --out ".\SINA-Workbench\runs\my-pro-detection"
```

输出 `detection.json`、`detected.jpg`、原始回复。密钥只从本地 `.env` 或环境变量读取，不写进结果。Pro 输出没有可靠检测置信度，因此不将自评置信度当作准确率，也不与 YOLO 的 mAP 直接比较。

## 运行实验完整流程

```powershell
.\SINA-Workbench\SINA-venv\Scripts\python.exe .\SINA-Workbench\tools\run_pro_workflow.py "D:\你的图片.jpg" --out ".\SINA-Workbench\runs\my-pro-direct-workflow"
```

流程为 Pro 元件定位 → 原版 CCL 与 EasyOCR → 原版 SINA 清单与网表提示词。为确保没有隐含 YOLO 检测，关闭上游会重新调用 YOLO 的交叉检测分支。这是实验路线，未替换默认 YOLO11m。所有输出都需人工确认。

若检测框导致引脚数或连接错误，后续 Pro 整理网表不能视为可靠修复。该路线始终输出 `ready_for_simulation: false`。

## 七轮比较

用户选择每轮完整评估 66 张人工标注验证图，共七轮，462 次 Pro 检测尝试。前期普通文本输出测试不计入这七轮。每轮配置一致，人工标注只用于评分，没有发送给模型。

主指标为同类框 IoU≥0.5 的 F1，同时观察 IoU≥0.75 的定位表现。匹配时每个预测框和参考框最多使用一次；重复框计误检，失败输出计作没有可用预测，对应参考目标全部计入漏检。另存只看成功图片的指标用于排查，但最终决策以完整分母为准。

原始证据：`runs/pro-direct-schema-benchmark-20261016-001` 至 `007`。总配置与最终汇总：`runs/pro-direct-seven-trials-20261016/`。汇总脚本 `tools/summarize_detection_trials.py` 会验证七轮 YOLO 基线完全一致。

同一验证集重复七次是在观察 API 波动，不是 462 张独立测试图；不能据此声称真实电路图泛化准确率。
