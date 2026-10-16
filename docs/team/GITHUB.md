# GitHub 组员接手指南

计划仓库：`Ocmma001/SINA-Workflow`。首次创建默认为私有；仓库拥有者需要在 Settings → Collaborators 为组员开通访问权限。具体发布状态以仓库实际可访问为准。

## 克隆与选择任务

```powershell
git clone https://github.com/Ocmma001/SINA-Workflow.git SINA-Workbench
cd SINA-Workbench
git switch -c opt/ocr-text
```

仓库源码很小，推荐完整克隆，随后只修改自己模块的文件。权重、数据集和虚拟环境都不会随着 git clone 下载。
先让对应新聊天读取 `AGENTS.md`、`docs/team/START-HERE.md`、`docs/team/INTERFACES.md`，再读自己的模块指南。

| 任务 | 主要工作文件 | 指南 |
|---|---|---|
| 数据与评测 | experiments/、新增数据审核/评估工具 | 01-data-evaluation.md |
| 元件检测训练 | tools/modules/detector.py、tools/train_round.py | 02-detector.md |
| OCR与文字绑定 | tools/modules/ocr.py、text_binding.py | 03-ocr-text.md |
| 导线连接 | tools/modules/topology.py、topology_impl/ | 04-topology.md |
| 引脚连接 | tools/modules/pins.py | 05-pins.md |
| 豆包复核 | tools/modules/vision.py、tools/vision_review.py | 06-vision-review.md |
| 输出校验 | tools/gui_contract.py、schemas/ | 07-contract.md |
| 集成发布 | tools/local_extract.py、gui_workflow.py、run_stage.py | 08-integration.md |

## 只检出需要的部分（可选）

由于模块共享契约与测试，以下命令保留 tools/ 公共工具，同时省略历史参考文档和图片样例。按实际任务增加其他路径。

```powershell
git clone --filter=blob:none --sparse https://github.com/Ocmma001/SINA-Workflow.git SINA-Workbench
cd SINA-Workbench
git sparse-checkout set tools docs/team prompts schemas experiments assets
```

仓库根的 README、AGENTS 和依赖清单会保留。需要实跑样例时执行 `git sparse-checkout add examples`。
“只优化某个部分”不要求创建多个互相复制公共代码的仓库；每个成员用自己的分支和工作目录即可。

## 模型和数据

发布时资源包放在 GitHub Releases 的 `workflow-v1` 发布中，附件名 `SINA-workflow-assets.zip`。
只做代码阅读、数据结构或规则开发时，可以暂不下载资源；实跑检测/OCR或训练时按 SETUP.md 建环境、下载资源并校验导入。

安装了 GitHub CLI 的组员可执行：

```powershell
gh release download workflow-v1 --repo Ocmma001/SINA-Workflow --pattern SINA-workflow-assets.zip --dir ..
python tools/import_assets.py ../SINA-workflow-assets.zip
```

本机私钥和API密钥各自配置，不通过Git或Release共享。

## 提交优化

```powershell
git add tools/modules/ocr.py tools/modules/text_binding.py
git commit -m "Improve OCR text assignment"
git push -u origin opt/ocr-text
```

随后在GitHub创建Pull Request，附实验报告、逐图对照和退化样例。未获得写权限时可由仓库拥有者添加组员权限后再推送。
组员不直接覆盖main的选定权重；集成负责人依据评测合并。高级显卡训练优先保留给用户，待每个人的配置明确后分配。
