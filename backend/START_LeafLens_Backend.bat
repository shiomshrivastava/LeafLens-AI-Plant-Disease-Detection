@echo off
cd /d "%~dp0"
echo LeafLens local FastAPI + automatic ESP32 discovery
python run_with_discovery.py
if errorlevel 1 (
  echo.
  echo Python failed. Open PowerShell in backend and run: python run_with_discovery.py
  pause
)
