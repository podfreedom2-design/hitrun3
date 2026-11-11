@echo off
rem data validation report
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONWARNINGS=ignore
cd /d "%~dp0"
set PY=".venv\Scripts\python.exe"
%PY% run.py check
if not defined HITRUN_NO_OPEN pause
