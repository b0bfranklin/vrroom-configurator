#!/bin/bash

echo "============================================================"
echo "  Vrroom Configurator - HDFury Vrroom Config Analyzer"
echo "============================================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8+ using your package manager"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Create directories if they don't exist
mkdir -p uploads exports

# Check for FFprobe
if command -v ffprobe &> /dev/null; then
    echo "FFprobe found - video analysis enabled"
else
    echo "WARNING: FFprobe not found - video analysis will be disabled"
    echo "Install FFmpeg to enable pre-roll analysis"
fi

# Start the server
echo
echo "Starting server..."
echo "Open your browser to: http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo

python app.py
