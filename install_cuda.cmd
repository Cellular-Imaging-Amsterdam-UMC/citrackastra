@echo off
setlocal
cd /d "%~dp0"
uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cu126 --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match torch==2.11.0+cu126 torchvision==0.26.0+cu126 || exit /b 1
.venv\Scripts\python.exe -c "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; print(torch.__version__, torch.cuda.get_device_name(0))"
