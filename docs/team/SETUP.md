# 其他电脑如何接手

Git仅含代码/指南/小型样例。训练数据和模型在单独的 SINA-workflow-assets.zip 中，复制到仓库外即可。

## 环境

本机验证环境Python3.13、torch2.11.0+cu128、ultralytics8.4.178、EasyOCR1.7.2；完整快照在experiments/requirements-lock.txt。
不要把别人的venv复制过来。先新建环境，再按自己的设备安装PyTorch；CPU同学无需CUDA。
以下Windows命令建立CPU环境，网络下载依赖：

```powershell
python -m venv SINA-venv
.\SINA-venv\Scripts\Activate.ps1
python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-workflow.txt
python tools/import_assets.py "D:\收到的资源\SINA-workflow-assets.zip"
python -m unittest discover -s tools -p "test_*.py"
python tools/gui_workflow.py examples/user_bjt_bias.jpg --out runs/first-local
```

资源包哈希清单在assets/manifest.json；导入器逐项校验，拒绝覆盖不同内容的文件。先创建venv再导入OCR资源。
GPU同学安装与GPU/驱动匹配的PyTorch。已验证的本机CUDA12.8安装索引为 https://download.pytorch.org/whl/cu128 ，不保证每台电脑适用；设备信息到齐后再给具体命令。
Linux激活为 `source SINA-venv/bin/activate`，本轮只验证Windows，其他平台须运行相同回归。

## 资源内容

当前微调权重 → runs/round-002/delivery/detector.pt。
上游初始权重 → SINA/Netlist Generator/IC/current_trained_model/train/weights/best.pt。
训练/验证数据 → SINA/Netlist Generator/IC/model_training/data/。
OCR两个权重 → SINA-venv/easyocr_models/。
SINA许可 → SINA/License.txt。
生产拓扑源码已经在tools/modules/topology_impl，离线识别不需要克隆上游全部历史。
历史sina_lab等研究入口可能需要完整上游快照；它们不在本资源包启动承诺内。

## 云端复核

默认不调用API。仅需要06任务时将.env.example复制为.env，填写自己的ARK_API_KEY；不要共享用户聊天中的密钥。
执行 `--allow-cloud` 将图片发送官方火山引擎接口。API额度/联网是额外条件，离线流程不依赖它。

## Git协作

无需GitHub也能先交接：仓库拥有者提供 `SINA-workflow.bundle` 与资源ZIP。接收者运行：

```powershell
git clone "D:\收到的资源\SINA-workflow.bundle" SINA-Workbench
cd SINA-Workbench
git switch -c opt/ocr-text
```

分支名按自己的模块替换。bundle带Git历史但不是可供多人推送的在线服务；建立GitHub远程后统一更换origin。资源包仍需按上面步骤导入。

当前是本地Git仓库，尚无GitHub远程。拿到远程地址后由仓库拥有者添加origin并push main，邀请组员。
组员各自clone并创建模块分支；同一电脑的多个聊天也用独立clone/worktree，避免共享工作目录冲突。
新成员设置自己的git user.name和user.email。不要复制仓库拥有者身份。当前初始提交以Codex本地代理身份记录。
大资源可通过小组共享盘或GitHub Release附件分发，文件校验以assets/manifest.json为准。
