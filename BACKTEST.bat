@echo off
rem full backtest + AI report + dashboard
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONWARNINGS=ignore
cd /d "%~dp0"
set PY=".venv\Scripts\python.exe"
%PY% run.py backtest
if not defined HITRUN_NO_OPEN start "" "%~dp0out\dashboard.html"
if not defined HITRUN_NO_OPEN pause
