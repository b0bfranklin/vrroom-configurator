@echo off
setlocal enabledelayedexpansion

REM Change to the directory containing this script
cd /d "%~dp0"

echo ============================================================
echo   Vrroom Configurator - HDFury Vrroom Config Analyzer
echo ============================================================
echo.

REM ============================================================
REM Initialize status variables
REM ============================================================
set PYTHON_OK=0
set PYTHON_VER=Not installed
set FFMPEG_OK=0
set GIT_OK=0
set NEED_INSTALL=0

REM ============================================================
REM Check all prerequisites
REM ============================================================
echo Checking prerequisites...
echo.

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    set PYTHON_VER=Not installed
    set NEED_INSTALL=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYTHON_VER=%%v
    python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if errorlevel 1 (
        set NEED_INSTALL=1
    ) else (
        set PYTHON_OK=1
    )
)

REM Check FFmpeg/FFprobe
where ffprobe >nul 2>&1
if errorlevel 1 (
    set FFMPEG_OK=0
) else (
    set FFMPEG_OK=1
)

REM Check Git (optional, for updates)
where git >nul 2>&1
if errorlevel 1 (
    set GIT_OK=0
) else (
    set GIT_OK=1
)

REM ============================================================
REM Display prerequisites summary
REM ============================================================
echo ============================================================
echo   Prerequisites Summary
echo ============================================================
echo.

if !PYTHON_OK!==1 (
    echo   [OK] Python .............. !PYTHON_VER!
) else (
    echo   [X]  Python .............. !PYTHON_VER! ^(3.8+ required^)
)

if !FFMPEG_OK!==1 (
    echo   [OK] FFmpeg .............. Installed
) else (
    echo   [--] FFmpeg .............. Not installed ^(optional^)
)

if !GIT_OK!==1 (
    echo   [OK] Git ................. Installed
) else (
    echo   [--] Git ................. Not installed ^(optional^)
)

echo.
echo   Legend: [OK] = Ready  [X] = Required  [--] = Optional
echo.

REM ============================================================
REM Handle missing Python (required)
REM ============================================================
if !PYTHON_OK!==0 (
    echo ============================================================
    echo   Python Installation Required
    echo ============================================================
    echo.
    echo   Python 3.8+ is REQUIRED to run Vrroom Configurator.
    echo.
    call :prompt_python_install
    if !PYTHON_OK!==0 (
        echo.
        echo Cannot continue without Python. Exiting.
        pause
        exit /b 1
    )
)

REM ============================================================
REM Offer to install optional components
REM ============================================================
if !FFMPEG_OK!==0 (
    echo.
    echo ============================================================
    echo   Optional: Install FFmpeg?
    echo ============================================================
    echo.
    echo   FFmpeg enables the Pre-roll Video Analyzer feature.
    echo   Without it, you can still use Config Analyzer and My Setup.
    echo.
    set /p INSTALL_FFMPEG="Install FFmpeg now? (Y/N): "
    if /i "!INSTALL_FFMPEG!"=="Y" (
        call :install_ffmpeg
    ) else (
        echo   Skipping FFmpeg installation.
    )
)

if !GIT_OK!==0 (
    echo.
    echo ============================================================
    echo   Optional: Install Git?
    echo ============================================================
    echo.
    echo   Git enables easy updates via 'git pull'.
    echo   Without it, you can manually download updates.
    echo.
    set /p INSTALL_GIT="Install Git now? (Y/N): "
    if /i "!INSTALL_GIT!"=="Y" (
        call :install_git
    ) else (
        echo   Skipping Git installation.
    )
)

REM ============================================================
REM Setup virtual environment
REM ============================================================
echo.
echo ============================================================
echo   Setting up environment...
echo ============================================================
echo.

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        echo Try: python -m pip install --upgrade pip virtualenv
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/update dependencies
echo Installing Python dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    echo Try running: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Create directories if they don't exist
if not exist "uploads" mkdir uploads
if not exist "exports" mkdir exports

REM ============================================================
REM Start the server
REM ============================================================
echo.
echo ============================================================
echo   Vrroom Configurator is ready!
echo ============================================================
echo.
echo   URL: http://localhost:5000
echo.
echo   Features available:
echo     [OK] My Setup - Equipment-based recommendations
echo     [OK] Config Analyzer - Analyze Vrroom JSON exports
if !FFMPEG_OK!==1 (
    echo     [OK] Pre-roll Analyzer - Video format analysis
) else (
    echo     [--] Pre-roll Analyzer - Requires FFmpeg
)
echo     [OK] Device Database - Equipment profiles
echo     [OK] EDID Reference - Command reference
echo.
echo   Press Ctrl+C to stop the server
echo ============================================================
echo.

python app.py
pause
exit /b 0

REM ============================================================
REM FUNCTIONS
REM ============================================================

:prompt_python_install
echo   Choose installation method:
echo.
echo     [1] Install via winget (recommended, Windows 10+)
echo     [2] Install via Microsoft Store
echo     [3] Download from python.org
echo     [4] Skip (I'll install it myself)
echo.
set /p PYCHOICE="   Enter choice (1-4): "

if "%PYCHOICE%"=="1" call :install_python_winget
if "%PYCHOICE%"=="2" call :install_python_store
if "%PYCHOICE%"=="3" call :install_python_manual
if "%PYCHOICE%"=="4" (
    echo.
    echo   Please install Python 3.8+ and run this script again.
)
goto :eof

:install_python_winget
echo.
echo   Checking for winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo   ERROR: winget is not available on this system.
    echo   Please choose another installation method.
    echo.
    call :prompt_python_install
    goto :eof
)
echo   Installing Python 3.12 via winget...
echo   This may require administrator approval.
echo.
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo   Installation may have failed. Try another method.
    call :prompt_python_install
    goto :eof
)
echo.
echo ============================================================
echo   Python installed successfully!
echo.
echo   IMPORTANT: You must restart this script for Python to be
echo   available in your PATH.
echo ============================================================
pause
exit /b 0

:install_python_store
echo.
echo   Opening Microsoft Store...
start ms-windows-store://pdp/?productid=9PJPW5LDXLZ5
echo.
echo   After installation completes:
echo     1. Close this window
echo     2. Run this script again
echo.
pause
exit /b 0

:install_python_manual
echo.
echo   Opening python.org in your browser...
start https://www.python.org/downloads/
echo.
echo   IMPORTANT: During installation, check "Add Python to PATH"
echo.
echo   After installation completes:
echo     1. Close this window
echo     2. Run this script again
echo.
pause
exit /b 0

:install_ffmpeg
echo.
echo   Checking for winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo   winget not available. Opening FFmpeg download page...
    start https://www.gyan.dev/ffmpeg/builds/
    echo.
    echo   Download FFmpeg, extract, and add the bin folder to your PATH.
    echo   Then restart this script.
    pause
    goto :eof
)
echo   Installing FFmpeg via winget (Gyan.FFmpeg)...
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo   FFmpeg installation failed or package not found.
    echo   You can install manually from: https://www.gyan.dev/ffmpeg/builds/
    echo   Download, extract, and add the bin folder to your PATH.
) else (
    where ffprobe >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   FFmpeg package installed, but ffprobe is not yet in PATH.
        echo   You may need to restart this script or add the FFmpeg bin
        echo   folder to your PATH manually.
    ) else (
        echo   FFmpeg installed and verified successfully!
    )
    set FFMPEG_OK=1
    echo.
    echo   NOTE: You may need to restart this script for FFmpeg
    echo   to be available in your PATH.
)
goto :eof

:install_git
echo.
echo   Checking for winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo   winget not available. Opening Git download page...
    start https://git-scm.com/download/win
    echo.
    echo   Download and install Git, then restart this script.
    pause
    goto :eof
)
echo   Installing Git via winget...
winget install Git.Git --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo   Git installation failed. You can install it later.
) else (
    echo   Git installed successfully!
    set GIT_OK=1
)
goto :eof
