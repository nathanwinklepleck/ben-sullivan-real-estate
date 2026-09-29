@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo The app is not set up yet. Double-click setup.bat first.
    pause
    exit /b 1
)
set "WEASYPRINT_DLL_DIRECTORIES=C:\msys64\mingw64\bin"
start "Sullivan CRE - API" cmd /k ".venv\Scripts\python.exe -m uvicorn cre_model.api:app --app-dir backend --host 127.0.0.1 --port 8000"
start "Sullivan CRE - Web" /d "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
timeout /t 6 /nobreak >nul
start "" "http://127.0.0.1:5173/"
