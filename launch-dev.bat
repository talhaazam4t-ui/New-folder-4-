@echo off
setlocal

echo ==========================================================
echo  Teloxtech SaaS - Full-Stack Dev & Chrome Launcher
echo  Strictly Enforces Google Chrome (Edge / M365 Prohibited)
echo ==========================================================

rem Enforce BROWSER environment variable so next dev / npm dev never opens Edge
set "BROWSER=C:\Program Files\Google\Chrome\Application\chrome.exe"

rem Start backend uvicorn server in a separate background window if python is available
start "Teloxtech Backend" cmd /c "python -m uvicorn app.main:app --app-dir backend --reload --port 8000"

rem Start frontend Next.js server in a separate background window
start "Teloxtech Frontend" cmd /c "cd frontend && npm run dev"

echo [WAIT] Waiting 3 seconds for local servers to bind...
timeout /t 3 /nobreak >nul

rem Launch in Google Chrome
call "%~dp0launch-chrome.bat"
exit /b 0
