@echo off
setlocal
cd /d "%~dp0"
uv pip install --python .venv\Scripts\python.exe -e ".[movie]" || exit /b 1
echo Divisualisation movie support is ready. Use --movie true.
