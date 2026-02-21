#!/bin/bash

set -e

echo "============================================================"
echo "  Vrroom Configurator - HDFury Vrroom Config Analyzer"
echo "============================================================"
echo

# ============================================================
# Check for Python
# ============================================================
echo "Checking prerequisites..."
echo

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        # Check if 'python' is Python 3
        if python -c "import sys; exit(0 if sys.version_info[0] >= 3 else 1)" 2>/dev/null; then
            PYTHON_CMD="python"
        else
            return 1
        fi
    else
        return 1
    fi

    # Check version is 3.8+
    if ! $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
        echo "[X] Python 3.8 or higher is required"
        echo "    Your version: $($PYTHON_CMD --version 2>&1)"
        return 1
    fi

    PYVER=$($PYTHON_CMD --version 2>&1)
    echo "[OK] $PYVER found"
    return 0
}

install_python_help() {
    echo
    echo "============================================================"
    echo "  Python Installation Required"
    echo "============================================================"
    echo
    echo "Python 3.8 or higher is required to run Vrroom Configurator."
    echo

    # Detect OS and provide specific instructions
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macOS detected. Install Python using one of these methods:"
        echo
        echo "  Option 1 - Homebrew (recommended):"
        echo "    brew install python@3.12"
        echo
        echo "  Option 2 - Official installer:"
        echo "    Download from https://www.python.org/downloads/macos/"
        echo
        if command -v brew &> /dev/null; then
            echo "Homebrew is installed. Install Python now? (y/n)"
            read -r response
            if [[ "$response" =~ ^[Yy]$ ]]; then
                echo "Installing Python via Homebrew..."
                brew install python@3.12
                echo
                echo "Python installed! Please run this script again."
                exit 0
            fi
        fi
    elif [[ -f /etc/debian_version ]]; then
        echo "Debian/Ubuntu detected. Install Python with:"
        echo
        echo "  sudo apt update && sudo apt install python3 python3-venv python3-pip"
        echo
    elif [[ -f /etc/redhat-release ]]; then
        echo "RHEL/Fedora detected. Install Python with:"
        echo
        echo "  sudo dnf install python3 python3-pip"
        echo
    elif [[ -f /etc/arch-release ]]; then
        echo "Arch Linux detected. Install Python with:"
        echo
        echo "  sudo pacman -S python python-pip"
        echo
    else
        echo "Install Python 3.8+ using your system's package manager,"
        echo "or download from https://www.python.org/downloads/"
        echo
    fi

    exit 1
}

if ! check_python; then
    install_python_help
fi

# ============================================================
# Check for FFmpeg (optional)
# ============================================================
if command -v ffprobe &> /dev/null; then
    echo "[OK] FFprobe found - Video analysis enabled"
    FFMPEG_MISSING=0
else
    echo "[!] FFprobe not found - Pre-roll video analysis will be disabled"
    FFMPEG_MISSING=1
fi
echo

# ============================================================
# Setup virtual environment
# ============================================================
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv || {
        echo "ERROR: Failed to create virtual environment"
        echo
        echo "You may need to install the venv module:"
        if [[ -f /etc/debian_version ]]; then
            echo "  sudo apt install python3-venv"
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  Python from Homebrew includes venv by default"
            echo "  Try: brew reinstall python@3.12"
        fi
        exit 1
    }
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q || {
    echo "ERROR: Failed to install dependencies"
    echo "Try running: pip install -r requirements.txt"
    exit 1
}

# Create directories if they don't exist
mkdir -p uploads exports

# ============================================================
# Start the server
# ============================================================
echo
echo "============================================================"
echo "  Server starting..."
echo "  Open your browser to: http://localhost:5000"
echo "  Press Ctrl+C to stop the server"
echo "============================================================"
echo

if [ "$FFMPEG_MISSING" -eq 1 ]; then
    echo "NOTE: Install FFmpeg to enable pre-roll video analysis"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "      brew install ffmpeg"
    elif [[ -f /etc/debian_version ]]; then
        echo "      sudo apt install ffmpeg"
    elif [[ -f /etc/redhat-release ]]; then
        echo "      sudo dnf install ffmpeg"
    elif [[ -f /etc/arch-release ]]; then
        echo "      sudo pacman -S ffmpeg"
    fi
    echo
fi

python app.py
