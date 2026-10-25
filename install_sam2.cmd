@echo off
setlocal
cd /d "%~dp0"
set SAM2_BUILD_CUDA=0
uv pip install --python .venv\Scripts\python.exe wheel setuptools
uv pip install --python .venv\Scripts\python.exe --no-build-isolation -e ".[sam2]" || exit /b 1
echo SAM2 feature support is ready. Download weights with tools\download_models.py.
