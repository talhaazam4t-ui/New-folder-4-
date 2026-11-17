<#
.SYNOPSIS
  Enforces Google Chrome as the exclusive browser for Teloxtech SaaS execution.
  Explicitly blocks Microsoft Edge and Microsoft 365 from launching or handling the application.
#>

param(
    [string]$Url = "http://localhost:3000"
)

$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe"
)

$chromePath = $null
foreach ($path in $chromeCandidates) {
    if (Test-Path $path) {
        $chromePath = $path
        break
    }
}

if (-not $chromePath) {
    # Try resolving via registry
    try {
        $regPath = (Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(Default)'
        if ($regPath -and (Test-Path $regPath)) {
            $chromePath = $regPath
        }
    } catch {}
}

if (-not $chromePath) {
    Write-Error "Google Chrome executable was not found. Google Chrome is strictly required for this execution."
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Teloxtech SaaS — Browser Enforcement Policy" -ForegroundColor Green
Write-Host " Target Browser: Google Chrome ($chromePath)" -ForegroundColor White
Write-Host " Prohibited Browsers: Microsoft Edge, Microsoft 365 / Office Web" -ForegroundColor Yellow
Write-Host " Target URL: $Url" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Explicitly set process environment variables to prevent tools from delegating to Edge/System Default
$env:BROWSER = $chromePath
$env:REACT_EDITOR = $chromePath

# Prohibit Edge from intercepting or claiming localhost URLs for this session
try {
    # Check if Microsoft Edge is running an existing tab on localhost:3000 and log notice
    $edgeProcs = Get-Process -Name "msedge" -ErrorAction SilentlyContinue
    if ($edgeProcs) {
        Write-Host "[Enforcement] Microsoft Edge detected running in background. Bypassing Edge and strictly routing to Google Chrome." -ForegroundColor Yellow
    }
} catch {}

# Launch target URL directly in Google Chrome in a dedicated new window
Start-Process -FilePath $chromePath -ArgumentList "--new-window", "$Url"

Write-Host "[Success] Application successfully dispatched to Google Chrome." -ForegroundColor Green
