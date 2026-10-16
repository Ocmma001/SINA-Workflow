# 协作化交付验证（2026-10-16）

- 工作流40项unittest通过；含原32项、模块边界3项、资源导入3项、云端阶段mock2项。
- GUI原4项集成测试通过；真实QProcess识别自检5行，编辑后撤销确认且保留证据。
- 重构前后同一BJT样例的components、OCR、inference、model_sha256逐字段一致。
- 独立detector、topology、pins、OCR、contract命令均执行成功；检测框、引脚候选与OCR结果和整流程一致。
- 干净源码副本只导入1329项白名单资源：40项测试通过，离线识别输出5个器件草稿。
- 干净源码验证使用本机已有Python依赖环境；未在另一台电脑重新安装依赖，不声称所有平台都已验证。
- GUI便携ZIP包含新增modules依赖，ZIP完整性与内部SHA256清单校验通过。
- 本轮没有真实API调用、没有新训练、没有新的准确率结论。云端模块以mock验证两阶段顺序和未知值保留；此前真实Pro实测见GUI已有产物。

当前资源包：SINA-workflow-assets.zip，179.3 MiB，1329项文件。
SHA256：b907ce6726a81d7b3df2813e0e8ac356d52f6fffaaa9172d07a60a92b47fb8af。
单文件资源哈希在assets/manifest.json中，导入器对损坏/额外文件/覆盖冲突拒绝执行。

当前限制：CCL内仍有二次YOLO；引脚语义/完整拓扑仍需人工核对；66张开发集不是独立测试集。
