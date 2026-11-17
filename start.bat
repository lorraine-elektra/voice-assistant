@echo off
cd /d "%~dp0"
echo Starting the voice assistant. Keep this window open. Close it to stop.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8000"
python -m uvicorn app.main:app --reload
pause
