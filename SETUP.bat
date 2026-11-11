@echo off
rem first-time setup: create .venv and install requirements
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONWARNINGS=ignore
cd /d "%~dp0"
set PY=".venv\Scripts\python.exe"
py -3.11 -m venv .venv
%PY% -m pip install -r requirements.txt
if not defined HITRUN_NO_OPEN pause
