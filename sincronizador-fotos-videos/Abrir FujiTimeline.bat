@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Instale o ambiente Python seguindo o README antes de abrir.
  pause
  exit /b 1
)
start "FujiTimeline" ".venv\Scripts\pythonw.exe" -m fujitimeline.gui
