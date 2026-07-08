@echo off
REM AV Signal Lab - run in development mode (no build required)
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
    echo Node.js is required. Install from https://nodejs.org/
    pause
    exit /b 1
)

if not exist node_modules (
    echo Installing dependencies - first run only, takes a few minutes...
    call npm install
    if errorlevel 1 (
        echo npm install failed.
        pause
        exit /b 1
    )
)

echo Starting AV Signal Lab...
call npm start
