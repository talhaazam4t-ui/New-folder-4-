@echo off
setlocal

echo ==========================================================
echo  Teloxtech SaaS - Docker & Chrome Workflow Launcher
echo  Strictly Enforces Google Chrome (Edge / M365 Prohibited)
echo ==========================================================

rem 1. Check if Docker is available
where docker >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [DOCKER] Starting backend containers via Docker Compose...
    docker compose up -d
) else (
    echo [NOTICE] Docker CLI not found in path, skipping container startup.
)

rem 2. Detect Google Chrome
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=C:\Program Files\Google\Chrome\Application\chrome.exe"
    goto :LAUNCH
)
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    goto :LAUNCH
)
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    goto :LAUNCH
)

echo [ERROR] Google Chrome was not found. Please install Google Chrome.
pause
exit /b 1

:LAUNCH
echo [POLICY] Microsoft Edge and Microsoft 365 are prohibited for this application.
echo [LAUNCH] Enforcing Google Chrome for Teloxtech SaaS...

start "" "%CHROME_BIN%" --new-window "http://localhost:3000"

echo [SUCCESS] Teloxtech SaaS launched in Google Chrome.
exit /b 0
