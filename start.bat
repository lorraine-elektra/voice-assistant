@echo off
cd /d "%~dp0"
rem Use the project's own Python (.venv) when it exists, so the right packages are found.
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
echo Stopping any older copy of the assistant on port 8001...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue } | Where-Object { $_.ProcessName -like 'python*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
echo Starting the voice assistant. Keep this window open. Close it to stop.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8001"
%PY% -m uvicorn app.main:app --port 8001
pause
