# 本次协作化实施记录

目标：在已有SINA-Workbench内建Git，保留GUI消费者调用兼容，建立能独立优化的工具边界和新聊天指南。

- [x] 提取detector/OCR/text_binding/topology/pins/vision，保留local_extract编排。
- [x] 将生产拓扑算法复制到被Git管理的模块，保留来源与MIT许可。
- [x] 提供离线run_stage入口与资源校验导入工具。
- [x] 编写8个聊天任务指南、接口契约、验收与设备建议。
- [x] 独立模块/整流程回归及干净源码资源导入验证。
- [x] 初始化仅覆盖SINA-Workbench的本地Git并保存初始提交。

不会在这一步重新训练或得出新准确率结论。GUI打包脚本仅补齐新增modules依赖，前端不纳入Git。
