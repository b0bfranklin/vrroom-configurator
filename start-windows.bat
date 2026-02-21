@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   Vrroom Configurator - HDFury Vrroom Config Analyzer
echo ============================================================
echo.

REM ============================================================
REM Check for Python
REM ============================================================
echo Checking prerequisites...
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python is NOT installed or not in PATH
    echo.
    goto :install_python
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo [OK] Python !PYVER! found
)

REM Check Python version is 3.8+
python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [X] Python 3.8 or higher is required
    echo     Your version: !PYVER!
    echo.
    goto :install_python
)

REM ============================================================
REM Check for FFmpeg (optional)
REM ============================================================
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo [!] FFprobe not found - Pre-roll video analysis will be disabled
    echo     To enable video analysis, install FFmpeg
    set FFMPEG_MISSING=1
) else (
    echo [OK] FFprobe found - Video analysis enabled
    set FFMPEG_MISSING=0
)
echo.

REM ============================================================
REM Setup virtual environment
REM ============================================================
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
echo Installing dependencies...
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
echo   Server starting...
echo   Open your browser to: http://localhost:5000
echo   Press Ctrl+C to stop the server
echo ============================================================
echo.

if !FFMPEG_MISSING!==1 (
    echo NOTE: Install FFmpeg to enable pre-roll video analysis
    echo       winget install FFmpeg.FFmpeg
    echo.
)

python app.py
pause
exit /b 0

REM ============================================================
REM Python Installation Helper
REM ============================================================
:install_python
echo ============================================================
echo   Python Installation Required
echo ============================================================
echo.
echo Python 3.8 or higher is required to run Vrroom Configurator.
echo.
echo Choose an installation method:
echo.
echo   [1] Install via winget (recommended, requires Windows 10+)
echo   [2] Install via Microsoft Store
echo   [3] Download from python.org (manual)
echo   [4] Exit
echo.

set /p CHOICE="Enter choice (1-4): "

if "%CHOICE%"=="1" goto :install_winget
if "%CHOICE%"=="2" goto :install_store
if "%CHOICE%"=="3" goto :install_manual
if "%CHOICE%"=="4" exit /b 1
goto :install_python

:install_winget
echo.
echo Checking for winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo ERROR: winget is not available on this system
    echo Please use Microsoft Store or download from python.org
    echo.
    pause
    goto :install_python
)
echo.
echo Installing Python via winget...
echo This may take a few minutes and require administrator approval.
echo.
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo Installation may have failed. Please try another method.
    pause
    goto :install_python
)
echo.
echo ============================================================
echo   Python installed successfully!
echo   IMPORTANT: Please close this window and run the script again
echo   to ensure Python is in your PATH.
echo ============================================================
pause
exit /b 0

:install_store
echo.
echo Opening Microsoft Store to Python page...
start ms-windows-store://pdp/?productid=9PJPW5LDXLZ5
echo.
echo After installing Python from the Store:
echo   1. Close this window
echo   2. Run this script again
echo.
pause
exit /b 0

:install_manual
echo.
echo Opening Python download page in your browser...
start https://www.python.org/downloads/
echo.
echo Installation instructions:
echo   1. Download Python 3.12 or later
echo   2. Run the installer
echo   3. IMPORTANT: Check "Add Python to PATH" during installation
echo   4. Complete the installation
echo   5. Close this window and run this script again
echo.
pause
exit /b 0
