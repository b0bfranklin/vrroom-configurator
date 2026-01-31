@echo off
echo ============================================================
echo   Vrroom Configurator - HDFury Vrroom Config Analyzer
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/update dependencies
echo Installing dependencies...
pip install -r requirements.txt -q

REM Create directories if they don't exist
if not exist "uploads" mkdir uploads
if not exist "exports" mkdir exports

REM Start the server
echo.
echo Starting server...
echo Open your browser to: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
python app.py

pause
