"""Assemble a portable source-and-assets handoff after an evaluated training run."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', default='round-002')
    args = p.parse_args()
    if Path(args.run).name != args.run or args.run in {'.', '..'}:
        p.error('run must be a directory name')
    run = ROOT / 'runs' / args.run
    comparison = run / 'comparison.json'
    if not comparison.is_file():
        p.error('training and evaluation must finish before packaging')
    target = run / 'delivery'
    scripts = target / 'tools'
    scripts.mkdir(exist_ok=True)
    for name in ('detect_image.py', 'local_extract.py', 'training_contract.py',
                 'test_training_contract.py', 'vision_review.py', 'test_vision_review.py',
                 'sina_ark_workflow.py', 'test_sina_prompts.py'):
        shutil.copy2(ROOT / 'tools' / name, scripts / name)
    shutil.copytree(ROOT / 'tools/modules', scripts / 'modules', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / '.env.example', target / '.env.example')
    shutil.copytree(ROOT / 'prompts', target / 'prompts', dirs_exist_ok=True)
    upstream = ROOT / 'SINA/Netlist Generator/IC/program_test/netlist_generator_algorithm_test/helper_files'
    vendor = target / 'SINA/Netlist Generator/IC/program_test/netlist_generator_algorithm_test/helper_files'
    vendor.mkdir(parents=True, exist_ok=True)
    for source in upstream.glob('*.py'):
        shutil.copy2(source, vendor / source.name)
    for name in ('LICENSE.txt', 'License.txt'):
        source = ROOT / 'SINA' / name
        if source.exists():
            shutil.copy2(source, target / ('SINA-' + name))
    models = target / 'assets/easyocr_models'
    models.mkdir(parents=True, exist_ok=True)
    for name in ('craft_mlt_25k.pth', 'english_g2.pth'):
        shutil.copy2(ROOT / 'SINA-venv/easyocr_models' / name, models / name)
    for source in (comparison, run / 'environment.json', ROOT / 'UPSTREAM.json',
                   ROOT / 'experiments/requirements-lock.txt'):
        shutil.copy2(source, target / source.name)
    (target / 'requirements-inference.txt').write_text(
        'ultralytics==8.4.178\neasyocr==1.7.2\nscikit-learn==1.9.1\n'
        'python-dotenv==1.2.4\nrequests==2.34.2\npytesseract==0.3.13\n', encoding='utf-8')
    (target / 'README.md').write_text('''# LabPilot 小组识别模块交付

包含推荐的 detector.pt、分类表、推理入口、SINA 连接分析源码及 EasyOCR 权重。
本机验证环境是 Windows + Python 3.13；完整版本见 requirements-lock.txt。
对方可创建独立 Python 环境，安装 requirements-inference.txt；PyTorch 的 CPU/GPU 版本按对方机器选择。

在本目录运行：

```powershell
python tools/detect_image.py your-circuit.png --weights detector.pt --out output-detection --device cpu
python tools/local_extract.py your-circuit.png --weights detector.pt --out output-candidates --device cpu --ocr-model-dir assets/easyocr_models --sina-root SINA
```

每次使用新的输出目录。第二条命令不需要模型 API，输出 detected.jpg、recognized.json 和 debug/。
recognized.json 中的元件位号、数值和语义引脚仍待人工确认。pin_candidates 给出有距离限制的连通区域候选，nodes 保持空数组。
本地脚本包含交叉检测，但没有合并上游完整交叉变体流水线；复杂交叉需人工复核。
字段 ready_for_simulation 固定为 false；LabPilot 必须提供确认和格式转换后才能生成仿真网表。

模型训练和对照结果见 comparison.json。官方验证集不是独立测试集；该成绩只反映元件检测，不代表 OCR、拓扑或整图正确率。
在线阶段已接入豆包 Pro；默认逐字使用 SINA 原版两段提示词：元件清点 → 位号/数值/网表命名。
第一段发送图片，第二段默认发送拓扑与 OCR 文本；--netlist-image 使用原版函数支持的附图选项。
复制 .env.example 为 .env，填写自己的 ARK_API_KEY。然后运行：

```powershell
python tools/vision_review.py your-circuit.png --candidates output-candidates/recognized.json --out output-review
```

默认输出 API_first_response.txt、raw-netlist.txt、named-netlist-response.txt、sina-draft.cir 和 sina-ark-result.json。
仅希望复用此前自定义复核提示词时，显式添加 --prompt-mode review，此模式输出 vision-review.json。
原图和识别候选会发送到火山方舟，按实际 Token 计费；不使用联网搜索。
原版提示词单图实测仍存在位号错配和缺失值，不能把 .cir 草稿直接当成可仿真文件。节点审查不代表位号正确，必须人工确认。
不要分享 .env；交付包不包含个人密钥。更换密钥只需修改本机 .env。
''', encoding='utf-8')
    print('Assembled:', target)


if __name__ == '__main__':
    main()
