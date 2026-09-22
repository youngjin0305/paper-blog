@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up Python dependencies...
  python -m venv .venv
  if errorlevel 1 goto fail
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" app.py serve --open
if errorlevel 1 goto fail
exit /b 0
:fail
echo Setup or startup failed. Read the error above and README.md.
pause
exit /b 1
