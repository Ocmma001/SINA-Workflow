# 运行环境清单（实测记录）

本文件记录 LabPilot 及其依赖的实际安装位置、版本与验证结果。
所有数字都来自实际运行，不是估算。

更新日期：2026-10-15

---

## 1. 目录总览

```
C:\Users\lenovo\Documents\deepseek-harness\default-workspace\
├── LabPilot\                    本项目代码
│   └── build\runtime\ngspice\   ★ 仿真内核（22.13 MB，供 exe 捆绑）
├── SINA\                        SINA 检出（3.94 GB，commit a4f13885）
├── SINA-venv\                   SINA 的运行环境（1.41 GB）
├── LabPilot-venv\               LabPilot 的运行环境
├── downloads\                   安装包与模型缓存
└── tools\                       诊断与下载脚本
    └── certs\                   CA 证书（解决本机 TLS 问题）
```

⚠️ 磁盘占用已约 **6 GB**（SINA 3.94 + SINA-venv 1.41 + LabPilot-venv + ngspice 0.02）。
本机剩余空间**无法通过脚本查询**（`Get-Volume`、`Get-CimInstance Win32_LogicalDisk`、
`fsutil volume diskfree` 全部返回"拒绝访问"），请自行用文件资源管理器确认。

---

## 2. Python 环境（两个，刻意分开）

LabPilot 与 SINA 通过**子进程**交互，因此各用一套环境，互不污染。

| 用途 | 解释器 | 版本 | 说明 |
|---|---|---|---|
| LabPilot 本体 | `LabPilot-venv\Scripts\python.exe` | 3.11.0 | 界面、仿真调用、计算、打包 |
| SINA 识别 | `SINA-venv\Scripts\python.exe` | 3.11.0 | YOLO + easyocr |

> 为什么都是 3.11 而不是 SINA 官方要求的 3.12：
> **harness 自带的 Python 3.12 在"向新建子目录写文件"时必现 PermissionError**，
> 导致 pip 完全不可用。系统里的 3.11 正常。详见
> [sina_integration.md 第五节](sina_integration.md)。

### 为什么不用 harness 的 Python

已实测确认：写入已存在目录、删除、重命名都正常，但**向 `mkdtemp()` 新建的子目录写入文件**
必然失败。这不是沙箱权限问题（同目录手工操作全部正常），是那个 Python 构建自身的问题。

---

## 3. ngspice（★ 已实测可用）

| 项 | 值 |
|---|---|
| 版本 | **ngspice-41** |
| 来源 | conda-forge（`ngspice-exe` + `ngspice-lib`，win-64） |
| 位置 | `LabPilot\build\runtime\ngspice\` |
| 体积 | 22.13 MB（已删 20 MB 调试符号） |
| 控制台版 | `bin\ngspice_con.exe` ← **LabPilot 用这个** |
| GUI 版 | `bin\ngspice.exe`（**不要用在自动化里**） |

### 为什么是 41 而不是最新的 47

SourceForge 上最新的 Windows 包是 `ngspice-47_64.7z`，但：

1. SourceForge 对脚本请求全面返回 **403**（跳转页、镜像直链、API 全部被挡，
   加 Referer 也没用）——那是 Cloudflare 级反爬，脚本形态的 Python 过不去
2. conda-forge 的 Windows 包最新就是 **41**

41 完全满足需求：`.op` / `.dc` / `.ac` / `.tran` 与 `.model` 都支持。

### ⚠️ 两个必须记住的坑

**1. 必须用 `ngspice_con.exe`，不能用 `ngspice.exe`。**
`ngspice.exe` 是 GUI 版，用 `--version` 调用会**挂起**（实测 60 秒超时）。
`ngspice_con.exe` 才是控制台版。

**2. 调用时要把 `cwd` 设到 `bin\` 目录。**
ngspice 从相对路径找 `spinit` 与 `.cm` 代码模型。实测把 `cwd` 设为 `bin\`
即可正常工作。

### 实测结果（共射放大器直流工作点）

网表：分压偏置共射电路，`Vcc=12V, Rb1=100k, Rb2=33k, Rc=3k, Re=1k, Q2N3904`

```powershell
build\runtime\ngspice\bin\ngspice_con.exe -b smoke_test.cir
```

```
base = 2.653076e+00     coll = 6.127130e+00     emit = 1.970696e+00
Q1:  ic = 1.95763e-03   vbe = 0.682248   vbc = -3.47223
Total analysis time (seconds) = 0.001
Total elapsed time (seconds) = 0.005
```

**物理自洽性验算**（说明结果可信，不是"跑通了但数不对"）：

| 检查 | 计算 | 与仿真对比 |
|---|---|---|
| `Ic = (Vcc − Vc) / Rc` | (12 − 6.127) / 3k = **1.958 mA** | `ic = 1.95763e-03` ✓ |
| `Ie = Ve / Re` | 1.971 / 1k = **1.971 mA** | `ie = -0.0019707` ✓ |
| `Vbe` | 2.653 − 1.971 = **0.682 V** | `vbe = 0.682248` ✓ |
| `Vce` | 6.127 − 1.971 = **4.156 V** | 放大区 ✓ |

晶体管工作在**放大区**（Vbe≈0.68V 正偏，Vbc=−3.47V 反偏）——正是计划书
第一个演示场景「三极管静态工作点」需要的结果。

### 捆绑目录结构

```
LabPilot\build\runtime\ngspice\
├── bin\
│   ├── ngspice_con.exe      6.45 MB   ← 控制台版，LabPilot 用
│   ├── ngspice.exe          7.21 MB   GUI 版
│   └── ngspice.dll          7.33 MB   共享库
├── lib\ngspice\             XSPICE 代码模型（.cm）
│   ├── analog.cm  digital.cm  spice2poly.cm
│   └── table.cm   xtradev.cm  xtraevt.cm
├── share\ngspice\scripts\spinit        ★ 缺它会导致模型加载异常
├── include\ngspice\sharedspice.h       共享库头文件
└── info\licenses\COPYING               ngspice 许可原文
```

已删除（可安全删，省 20 MB）：`ngspice.pdb`（调试符号，20.23 MB）、
`debug.log`、`ngspice.exp`、`ngspice.lib`。

> 注意：conda 包里的是**调试版** exe，运行时会在 `bin\` 下生成 `debug.log`。
> 删掉 pdb 后实测不再生成。

### 许可

ngspice 为 BSD 类许可，`COPYING` 原文已随包保留在
`build\runtime\ngspice\info\licenses\COPYING`。正式对外发布前请自行复核。

---

## 4. Tesseract OCR（★ 已实测可用，免管理员安装）

| 项 | 值 |
|---|---|
| 版本 | **5.5.3** |
| 来源 | conda-forge（`tesseract` win-64，170.68 MB） |
| 位置 | `tools\tesseract\` |
| 体积 | **419.7 MB**（bin 79.3 MB + tessdata 339 MB） |
| 可执行 | `tools\tesseract\bin\tesseract.exe` |
| 语言数据 | `tools\tesseract\share\tessdata\`，125 种语言 |

`tesseract --version` 实测输出：

```
tesseract 5.5.3
 leptonica-1.87.0 (Dec 25 2025, 06:56:02) [MSC v.1944 LIB Release x64]
  libgif 5.2.2 : libjpeg 8d (libjpeg-turbo 3.1.2) : libpng 1.6.59
  : libtiff 4.7.2 : zlib 1.3.1 : libwebp 1.6.0 : libopenjp2 2.5.4
 Found AVX2 / AVX / FMA / SSE4.1
 Found libarchive 3.8.9 zlib/1.3.2 liblzma/5.8.3 bz2lib/1.0.8
```

### 为什么不用官方安装包

官方 `tesseract-ocr-w64-setup-5.5.3.20260724.exe`（20.90 MB）已下载到
`downloads\tesseract\`，供你在**有管理员的终端**里正规安装。

但它不能自动装：读它的 PE 清单得到

```
requestedExecutionLevel: highestAvailable
```

`highestAvailable` 会尝试提权，而本机当前用户**不是管理员**，会弹 UAC。

### ★ 最大的坑：libssh2 与 OpenSSL 版本不匹配

conda 的 tesseract 把依赖拆成很多独立包，DLL 必须手工合并到同一目录
（与 ngspice 相同的处理）。但即使把官方依赖清单里的包全下齐，
`tesseract.exe` 仍以 **`0xC0000135` (STATUS_DLL_NOT_FOUND)** 退出。

递归解析 PE 导入表后定位到根因：

| DLL | 依赖 | 问题 |
|---|---|---|
| `libssh2.dll` | `libcrypto-1_1-x64.dll` | **1.9.0 是为 OpenSSL 1.1 构建的** |
| `libcurl.dll` | `libcrypto-4-x64.dll` | 8.23 用的是 OpenSSL 3/4 |

两者对不上，且 conda-forge 已不再提供 OpenSSL 1.1 的 Windows 包。
**解法：把 libssh2 换成 1.11.1**（依赖 `openssl >=3.5.7`），立刻启动成功。

### 实测效果：Tesseract 比 easyocr 更准

对同一张运放电路图（OPA191）：

| 文本 | Tesseract | easyocr |
|---|---|---|
| `VOUT` | ✅ 0.96 | ❌ `V0UT` |
| `GND` | ✅ 0.96 | ❌ `6ND` |
| `OPA191` | ✅ 0.91 | ❌ `0PA191` |
| `10.0K` | ✅ 0.92 | ⚠️ 0.88 |
| `R1` / `R2` | ✅ 0.89 / 0.93 | ✅ |

接入 SINA 后的整体变化：

| 指标 | 仅 easyocr | 加 Tesseract |
|---|---|---|
| Tesseract 报错刷屏 | 12 次/图 | **0** |
| **提取文本项** | 44 | **106**（+141%） |
| 组件一致性校验 | 通过 | 通过 |

> ⚠️ 注意：文本项翻倍**没有**解决 `Resistor_3` 接点为 0 的问题（见
> [sina_integration.md 第八节](sina_integration.md)）——那是连通性分析的问题，
> 不是 OCR 的问题。

### 与 SINA 的对接

`tools/sina_lab.py` 在启动时调用 `setup_tesseract()` 自动发现并配置：

```python
pytesseract.pytesseract.tesseract_cmd = "<...>/tools/tesseract/bin/tesseract.exe"
os.environ["TESSDATA_PREFIX"] = "<...>/tools/tesseract/share/tessdata"
```

查找顺序：`TESSERACT_CMD` 环境变量 → `tools/tesseract/` → 系统 PATH →
常见安装位置（`C:\Program Files\Tesseract-OCR` 等）。

### 若要缩小体积

`tessdata` 有 125 种语言、339 MB，本项目只需要英文。删掉除
`eng.traineddata` 和 `osd.traineddata` 之外的文件可省约 **335 MB**：

```powershell
Get-ChildItem tools\tesseract\share\tessdata\*.traineddata |
  Where-Object { $_.Name -notin @('eng.traineddata','osd.traineddata') } |
  Remove-Item
```

（本次未执行，保留全语言以免影响你后续扩展。）

---

## 5. LabPilot 运行环境（已实测可用）

`LabPilot-venv`（Python 3.11.0），1.05 GB。12 个包全部导入验证通过：

| 包 | 版本 | 用途 |
|---|---|---|
| PySide6 | 6.12.0 | 桌面界面（QtWidgets） |
| numpy | 2.4.6 | 数值计算 |
| pandas | 3.0.6 | 数据表与实测数据处理 |
| matplotlib | 3.11.2 | 波形、伏安特性、频率响应 |
| scipy | 1.17.1 | 拟合与信号处理 |
| scikit-learn | 1.9.1 | 本地检索（RAG） |
| pypdf | 6.20.1 | 实验指导书 PDF 解析 |
| python-docx | 1.2.0 | Word 资料解析 |
| openpyxl | 3.1.5 | Excel 数据表 |
| python-dotenv | 1.2.4 | 配置与密钥加载 |
| pydantic | 2.14.1 | Structured Output 数据契约 |
| PyInstaller | 6.22.3 | 打包 exe |

另装 `zstandard` 0.25.0（解 conda 的 `.conda` 包用）。

验证结果：

- **PySide6**：`QApplication` 创建成功，平台插件 `offscreen`（说明 Qt 运行时完整）
- **中文字体**：`Microsoft YaHei`、`SimHei`、`SimSun`、`DengXian` 均可用
  —— 图表中文不会显示成方块

### ⚠️ exe 体积：PySide6 有 380 MB 是可以省的

`PySide6` 装完占 **647 MB**，但用 `QtWidgets` 做原生界面时大部分用不到。
实测各模块体积：

| 模块 | 体积 | 是否排除 |
|---|---|---|
| WebEngine | **285.9 MB** | ✅ 排除 |
| Quick/Qml | **93.8 MB** | ✅ 排除 |
| 3D | 28.7 MB | ✅ 排除 |
| Multimedia | 22.6 MB | ✅ 排除 |
| Designer | 12.3 MB | ✅ 排除 |
| Pdf | 5.8 MB | 保留（可能用于预览） |
| Network | 4.0 MB | 保留（Qt 内部可能依赖） |

单个最大的文件是 `Qt6WebEngineCore.dll`（**194.1 MB**），
另有 `qtwebengine_devtools_resources.debug.pak`（72.3 MB）。

`build/labpilot.spec` 的 `excludes` 已按此配置。**注意必须写 PySide6 的模块路径**
（`PySide6.QtWebEngineCore`），写发行包名（`PySide6_WebEngine`）或仓库名
（`Qt6WebEngineCore`）都不会生效——这正是初版 spec 没起作用的原因。

---

## 6. SINA 运行环境（已实测可用）

`SINA-venv`（Python 3.11.0），13 个包：

| 包 | 版本 | 验证 |
|---|---|---|
| torch | 2.14.1+cpu | ✅ CUDA 不可用（CPU 版） |
| ultralytics | 8.4.177 | ✅ IC 模型 10 类，推理 0.2–2.8s/张 |
| easyocr | 1.7.2 | ✅ OCR 可用，能读 `IRF9530`/`2N3904`/`47Ω` |
| cv2 | 5.0.0 | ⚠️ OpenCV 5（SINA 按 4.x 写的，未验证） |
| 其余 | — | numpy matplotlib scipy sklearn networkx dotenv pytesseract openai |

模型文件：

| 文件 | 大小 | 位置 |
|---|---|---|
| IC YOLO `best.pt` / `last.pt` | 38.6 MB ×2 | `SINA\Netlist Generator\IC\current_trained_model\train\weights\` |
| PCB YOLO `best.pt` | 50.7 MB | `SINA\Netlist Generator\PCB\all models\Final\model\` |
| easyocr `craft_mlt_25k.pth` | 79.3 MB | `SINA-venv\easyocr_models\` |
| easyocr `english_g2.pth` | 14.4 MB | 同上 |

### easyocr 三个目录都要设

`sina_runner.py` 必须设好这三个，缺一个就 `PermissionError`：

```python
os.environ["EASYOCR_MODULE_PATH"] = "<可写目录>"
reader = easyocr.Reader(lang_list, gpu=False,
                        model_storage_directory="<可写目录>",
                        user_network_directory="<可写目录>",
                        download_enabled=False)
```

---

## 7. Git 与 CA 证书（本机 TLS 故障的修复）

| 项 | 值 |
|---|---|
| Git 版本 | 2.56.0.2 |
| 位置 | `C:\Program Files\Git` |
| 安装包 | `downloads\Git-2.56.0.2-64-bit.exe`（签名有效，Johannes Schindelin） |

### 本机 TLS 故障

`%APPDATA%\Microsoft\Crypto` **不可写** → Windows Schannel 无法获取 TLS 凭据：

```
schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)
```

后果：TCP 443 可连通、HTTP 正常，但 **PowerShell / curl / winget / pip / git(默认)
的 HTTPS 全部失败**。Python 的 `ssl`（OpenSSL）不受影响。

**修复**（`tools\fix-git-tls.ps1`，在你自己终端里跑一次即全局生效）：

```powershell
git config --global http.sslBackend openssl
git config --global http.sslCAInfo <workspace>\tools\certs\windows_roots.pem
```

⚠️ **公共 CA 包不够用**：`curl.se/cacert.pem`（121 张根证书）仍报
`unable to get local issuer certificate`。**必须导 Windows 证书库**
（80 张，含本机注入的根证书）才通过。

证书文件：

| 文件 | 内容 |
|---|---|
| `tools\certs\windows_roots.pem` | 80 张（从系统证书库导出）← git 用这个 |
| `tools\certs\cacert.pem` | 121 张（Mozilla 公共 CA，不够用） |

---

## 8. 各下载源实测速率（判断"慢"时先看这个）

| 源 | 速率 | 用途 |
|---|---|---|
| 清华 PyPI 镜像 | **15–18 MB/s** | pip 装包 |
| conda-forge (anaconda.org) | 120–400 KB/s | ngspice |
| PyTorch 官方 CDN | 35 KB/s – 16 MB/s | torch |
| GitHub 仓库克隆 | **1.76 MiB/s** | SINA 2.17 GB，约 25 分钟 |
| GitHub 发行版下载 | **14.9 KB/s ～ 1.83 MB/s** | easyocr 模型 |

⚠️ **GitHub releases 速率几分钟内会剧烈波动**：同一批 URL 首次 14.9 KB/s，
重测 1830 KB/s（**123 倍**）。且国内代理镜像（ghproxy 84 KB/s、gh-proxy 146 KB/s、
ghfast 127 KB/s）**全部慢于直连**。

**结论：GitHub 下载慢时先杀掉重试，不要急着换镜像。**

---

## 9. 尚缺 / 未验证

| 项 | 状态 |
|---|---|
| OpenAI API Key | ⬜ 未配置（SINA 的 AI 环节需联网 Key） |
| SINA 主流程端到端 | ⬜ 未跑（依赖已就绪，但入口写死 `use_gpu=True` 且本机无 CUDA，行为未知） |
| OpenCV 5 与 SINA 的兼容性 | ⬜ 未验证（SINA 按 OpenCV 4.x 写的） |
| 磁盘剩余空间 | ⬜ 无法查询，需手动确认 |
