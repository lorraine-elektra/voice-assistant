@echo off
cd /d "%~dp0"
echo Stopping any older copy of the assistant on port 8000...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo Starting the voice assistant. Keep this window open. Close it to stop.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8000"
python -m uvicorn app.main:app --reload
pause
