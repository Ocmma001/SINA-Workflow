# SINA 多模态 API 候选

核对日期：2026-10-16。此表用于候选筛选，尚未完成电路识别实测。

| 候选 | 短请求输入 / 输出，人民币每百万 Token | 计划角色 |
|---|---|---|
| Qwen3-VL-Flash | 0.15 / 1.5 | 日常调用，优先候选 |
| Qwen3-VL-Plus | 1 / 10 | 难例复核，与 Flash 对照 |
| Doubao Seed-1.6-Flash | 0.15 / 1.5 | 第二供应方对照 |

具体模型版本、地域、长上下文阶梯与当前可用性以服务控制台为准。图片会折算成输入 Token；思考输出、重试和多次请求计入成本。

假定单次输入合计 10,000 Token、输出 2,000 Token：Flash 约 0.0045 元，Plus 约 0.03 元。不是每张图片固定报价。

建议先固定 20–30 张人工核对难例，比较位号、数值、语义引脚、连接、完整 JSON 通过率、耗时和费用。不能把通用模型排行榜当作电路拓扑准确率。

官方来源：

- https://help.aliyun.com/zh/model-studio/model-pricing?source=5176.29345612&userCode=iqy5u8og
- https://docs.volcengine.com/docs/Largemodelofimagegeneration/Packagebillinginstructions?lang=zh

当前原版 SINA 使用写死的 OpenAI 端点和 gpt-4o，尚不能仅靠替换密钥接入上述模型。须统一配置 API 地址、模型 ID、图片格式和响应解析；不要把个人密钥打包给小组。
