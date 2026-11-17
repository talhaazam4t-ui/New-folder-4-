@echo off
setlocal

echo ==========================================================
echo  Teloxtech SaaS - Chrome Enforcement Launcher
echo  Strictly Enforces Google Chrome (Edge / M365 Prohibited)
echo ==========================================================

set "TARGET_URL=http://localhost:3000"

rem Detect Google Chrome path
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=C:\Program Files\Google\Chrome\Application\chrome.exe"
    goto :FOUND
)
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    goto :FOUND
)
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    goto :FOUND
)

echo [ERROR] Google Chrome was not found in standard directories.
pause
exit /b 1

:FOUND
echo [OK] Located Google Chrome: %CHROME_BIN%
echo [POLICY] Microsoft Edge and Microsoft 365 are prohibited for this application.
echo [LAUNCH] Opening %TARGET_URL% in Google Chrome...

start "" "%CHROME_BIN%" --new-window "%TARGET_URL%"

echo [SUCCESS] Teloxtech SaaS launched in Google Chrome.
exit /b 0
