@echo off
setlocal
set "PYTHON=C:\Users\Marcela\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "APP=%~dp0bpa_validator_gui.py"
"%PYTHON%" "%APP%"
