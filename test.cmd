@echo off
setlocal
cd /d "%~dp0"
if not exist work mkdir work
.venv\Scripts\python.exe -m pytest -q --basetemp=work\pt %*
