# 在工作区目录执行，或逐行设置。请替换为你实际准备的路径。
$env:SINA_ROOT = Join-Path $PSScriptRoot 'SINA'
$env:SINA_USE_GPU = '0'
$env:PYTHONIOENCODING = 'utf-8'
$env:SINA_DISABLE_THINKING = '1'
# 按实际供应方填写；必须确认模型支持所需的图片输入。
# $env:SINA_API_BASE = 'https://供应方地址'
# $env:SINA_API_MODEL = '实际模型名称'
# SINA_API_KEY 在当前进程中单独设置，不保存在可分享配置里。
# OCR 目录默认位于工作区的 SINA-venv 下；已有模型可覆盖：
# $env:EASYOCR_MODULE_PATH = 'D:\模型缓存\easyocr_module'
# $env:EASYOCR_MODEL_DIR = 'D:\模型缓存\easyocr_models'
# $env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 官方原版固定使用 OpenAI gpt-4o，读取 OPENAI_API_KEY。
# SINA_API_* 只对历史改造版生效；原版尚未支持这些选项。
# 请单独设置 OPENAI_API_KEY，不把实际密钥保存进此文件。
