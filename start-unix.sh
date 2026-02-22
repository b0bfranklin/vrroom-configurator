#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================================"
echo "  AV Signal Lab - Home Theater Signal Chain Optimizer"
echo "============================================================"
echo

# ============================================================
# Initialize status variables
# ============================================================
PYTHON_OK=0
PYTHON_VER="Not installed"
PYTHON_CMD=""
FFMPEG_OK=0
GIT_OK=0
VENV_OK=0

# ============================================================
# Detect OS
# ============================================================
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS_TYPE="macos"
        PKG_MANAGER="brew"
    elif [[ -f /etc/debian_version ]]; then
        OS_TYPE="debian"
        PKG_MANAGER="apt"
    elif [[ -f /etc/redhat-release ]]; then
        OS_TYPE="redhat"
        PKG_MANAGER="dnf"
    elif [[ -f /etc/arch-release ]]; then
        OS_TYPE="arch"
        PKG_MANAGER="pacman"
    else
        OS_TYPE="unknown"
        PKG_MANAGER="unknown"
    fi
}

# ============================================================
# Check all prerequisites
# ============================================================
echo "Checking prerequisites..."
echo

detect_os

# Check Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        if python -c "import sys; exit(0 if sys.version_info[0] >= 3 else 1)" 2>/dev/null; then
            PYTHON_CMD="python"
        fi
    fi

    if [[ -n "$PYTHON_CMD" ]]; then
        if $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            PYTHON_OK=1
            PYTHON_VER=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
        else
            PYTHON_VER=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
        fi
    fi
}

# Check venv module
check_venv() {
    if [[ -n "$PYTHON_CMD" ]] && $PYTHON_CMD -c "import venv" 2>/dev/null; then
        VENV_OK=1
    fi
}

# Check FFmpeg
check_ffmpeg() {
    if command -v ffprobe &> /dev/null; then
        FFMPEG_OK=1
    fi
}

# Check Git
check_git() {
    if command -v git &> /dev/null; then
        GIT_OK=1
    fi
}

check_python
check_venv
check_ffmpeg
check_git

# ============================================================
# Display prerequisites summary
# ============================================================
echo "============================================================"
echo "  Prerequisites Summary"
echo "============================================================"
echo

if [[ $PYTHON_OK -eq 1 ]]; then
    echo -e "  ${GREEN}[OK]${NC} Python .............. $PYTHON_VER"
else
    echo -e "  ${RED}[X]${NC}  Python .............. $PYTHON_VER (3.8+ required)"
fi

if [[ $PYTHON_OK -eq 1 ]]; then
    if [[ $VENV_OK -eq 1 ]]; then
        echo -e "  ${GREEN}[OK]${NC} Python venv ......... Available"
    else
        echo -e "  ${RED}[X]${NC}  Python venv ......... Not installed (required)"
    fi
fi

if [[ $FFMPEG_OK -eq 1 ]]; then
    echo -e "  ${GREEN}[OK]${NC} FFmpeg .............. Installed"
else
    echo -e "  ${YELLOW}[--]${NC} FFmpeg .............. Not installed (optional)"
fi

if [[ $GIT_OK -eq 1 ]]; then
    echo -e "  ${GREEN}[OK]${NC} Git ................. Installed"
else
    echo -e "  ${YELLOW}[--]${NC} Git ................. Not installed (optional)"
fi

echo
echo "  Legend: [OK] = Ready  [X] = Required  [--] = Optional"
echo "  Detected OS: $OS_TYPE (package manager: $PKG_MANAGER)"
echo

# ============================================================
# Handle missing Python (required)
# ============================================================
install_python() {
    echo
    echo "============================================================"
    echo "  Python Installation Required"
    echo "============================================================"
    echo
    echo "  Python 3.8+ is REQUIRED to run AV Signal Lab."
    echo

    case $OS_TYPE in
        macos)
            echo "  Choose installation method:"
            echo
            echo "    [1] Install via Homebrew (recommended)"
            echo "    [2] Download from python.org"
            echo "    [3] Skip (I'll install it myself)"
            echo
            read -p "  Enter choice (1-3): " choice
            case $choice in
                1)
                    if command -v brew &> /dev/null; then
                        echo
                        echo "  Installing Python via Homebrew..."
                        brew install python@3.12
                        echo
                        echo "  Python installed! Please run this script again."
                        exit 0
                    else
                        echo
                        echo "  Homebrew not found. Install it first:"
                        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                        echo
                        echo "  Or download Python from python.org"
                    fi
                    ;;
                2)
                    echo
                    echo "  Opening python.org..."
                    open "https://www.python.org/downloads/macos/"
                    echo "  After installation, run this script again."
                    ;;
            esac
            ;;
        debian)
            echo "  Install Python with:"
            echo
            echo "    sudo apt update && sudo apt install python3 python3-venv python3-pip"
            echo
            read -p "  Run this command now? (y/n): " yn
            if [[ "$yn" =~ ^[Yy]$ ]]; then
                sudo apt update && sudo apt install -y python3 python3-venv python3-pip
                echo
                echo "  Python installed! Please run this script again."
                exit 0
            fi
            ;;
        redhat)
            echo "  Install Python with:"
            echo
            echo "    sudo dnf install python3 python3-pip"
            echo
            read -p "  Run this command now? (y/n): " yn
            if [[ "$yn" =~ ^[Yy]$ ]]; then
                sudo dnf install -y python3 python3-pip
                echo
                echo "  Python installed! Please run this script again."
                exit 0
            fi
            ;;
        arch)
            echo "  Install Python with:"
            echo
            echo "    sudo pacman -S python python-pip"
            echo
            read -p "  Run this command now? (y/n): " yn
            if [[ "$yn" =~ ^[Yy]$ ]]; then
                sudo pacman -S --noconfirm python python-pip
                echo
                echo "  Python installed! Please run this script again."
                exit 0
            fi
            ;;
        *)
            echo "  Please install Python 3.8+ using your package manager"
            echo "  or download from https://www.python.org/downloads/"
            ;;
    esac
    exit 1
}

install_venv() {
    echo
    echo "============================================================"
    echo "  Python venv Module Required"
    echo "============================================================"
    echo

    case $OS_TYPE in
        debian)
            echo "  The venv module is required but not installed."
            echo
            echo "  Install with: sudo apt install python3-venv"
            echo
            read -p "  Install now? (y/n): " yn
            if [[ "$yn" =~ ^[Yy]$ ]]; then
                sudo apt install -y python3-venv
                VENV_OK=1
            else
                exit 1
            fi
            ;;
        *)
            echo "  The venv module should be included with Python."
            echo "  Try reinstalling Python or installing python3-venv."
            exit 1
            ;;
    esac
}

if [[ $PYTHON_OK -eq 0 ]]; then
    install_python
fi

if [[ $VENV_OK -eq 0 ]]; then
    install_venv
fi

# ============================================================
# Offer to install optional components
# ============================================================
install_ffmpeg() {
    echo
    echo "  Installing FFmpeg..."
    case $OS_TYPE in
        macos)
            if command -v brew &> /dev/null; then
                brew install ffmpeg
                FFMPEG_OK=1
            else
                echo "  Homebrew not found. Install FFmpeg manually."
            fi
            ;;
        debian)
            sudo apt install -y ffmpeg
            FFMPEG_OK=1
            ;;
        redhat)
            sudo dnf install -y ffmpeg
            FFMPEG_OK=1
            ;;
        arch)
            sudo pacman -S --noconfirm ffmpeg
            FFMPEG_OK=1
            ;;
        *)
            echo "  Please install FFmpeg using your package manager."
            ;;
    esac
}

install_git() {
    echo
    echo "  Installing Git..."
    case $OS_TYPE in
        macos)
            if command -v brew &> /dev/null; then
                brew install git
                GIT_OK=1
            else
                echo "  Homebrew not found. Install Git manually."
            fi
            ;;
        debian)
            sudo apt install -y git
            GIT_OK=1
            ;;
        redhat)
            sudo dnf install -y git
            GIT_OK=1
            ;;
        arch)
            sudo pacman -S --noconfirm git
            GIT_OK=1
            ;;
        *)
            echo "  Please install Git using your package manager."
            ;;
    esac
}

if [[ $FFMPEG_OK -eq 0 ]]; then
    echo
    echo "============================================================"
    echo "  Optional: Install FFmpeg?"
    echo "============================================================"
    echo
    echo "  FFmpeg enables the Pre-roll Video Analyzer feature."
    echo "  Without it, you can still use Config Analyzer and My Setup."
    echo
    read -p "  Install FFmpeg now? (y/n): " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
        install_ffmpeg
    else
        echo "  Skipping FFmpeg installation."
    fi
fi

if [[ $GIT_OK -eq 0 ]]; then
    echo
    echo "============================================================"
    echo "  Optional: Install Git?"
    echo "============================================================"
    echo
    echo "  Git enables easy updates via 'git pull'."
    echo "  Without it, you can manually download updates."
    echo
    read -p "  Install Git now? (y/n): " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
        install_git
    else
        echo "  Skipping Git installation."
    fi
fi

# ============================================================
# Setup virtual environment
# ============================================================
echo
echo "============================================================"
echo "  Setting up environment..."
echo "============================================================"
echo

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv || {
        echo "ERROR: Failed to create virtual environment"
        exit 1
    }
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing Python dependencies..."
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
echo "  AV Signal Lab is ready!"
echo "============================================================"
echo
echo "  URL: http://localhost:5000"
echo
echo "  Features available:"
echo -e "    ${GREEN}[OK]${NC} My Setup - Equipment-based recommendations"
echo -e "    ${GREEN}[OK]${NC} Config Analyzer - Analyze Vrroom JSON exports"
if [[ $FFMPEG_OK -eq 1 ]]; then
    echo -e "    ${GREEN}[OK]${NC} Pre-roll Analyzer - Video format analysis"
else
    echo -e "    ${YELLOW}[--]${NC} Pre-roll Analyzer - Requires FFmpeg"
fi
echo -e "    ${GREEN}[OK]${NC} Device Database - Equipment profiles"
echo -e "    ${GREEN}[OK]${NC} EDID Reference - Command reference"
echo
echo "  Press Ctrl+C to stop the server"
echo "============================================================"
echo

python app.py
