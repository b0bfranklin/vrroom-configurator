@echo off
REM AV Signal Lab - build Windows installers (x64 + ARM64)
REM Produces installers and portable exes in the release\ folder.
REM No Visual Studio Build Tools required - the app has no native modules.
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
    echo Node.js is required. Install from https://nodejs.org/
    pause
    exit /b 1
)

if not exist node_modules (
    echo Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo npm install failed.
        pause
        exit /b 1
    )
)

echo Building for Windows x64 and ARM64...
call npm run dist:win
if errorlevel 1 (
    echo Build failed. To build just for this machine's architecture try:
    echo   npm run dist:win-arm64   (Snapdragon / Surface)
    echo   npm run dist:win-x64     (Intel / AMD)
    pause
    exit /b 1
)

echo.
echo Done. Installers are in the release\ folder.
pause
