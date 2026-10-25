@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul || (echo Install uv first: https://docs.astral.sh/uv/ & exit /b 1)
uv venv --python 3.11 .venv || exit /b 1
uv pip install --python .venv\Scripts\python.exe -e ".[dev]" || exit /b 1
echo Environment ready. For NVIDIA CUDA, run install_cuda.cmd.
