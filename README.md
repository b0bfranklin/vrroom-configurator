# Vrroom Configurator

Web-based toolkit for analyzing and optimizing HDFury Vrroom configurations to eliminate HDMI handshake delays ("bonk") during pre-roll playback in home theater setups.

## Problem Solved

- **2-3 second black screens** during Plex/Jellyfin/Emby pre-rolls
- **HDMI handshake delays** when video format changes
- **Dolby Vision on non-DV displays** via LLDV conversion
- **Pre-roll format mismatches** causing unnecessary format switching

## Features

- **My Setup** - Select your equipment and optimization goals, get tailored recommendations
- **Config Analyzer** - Upload Vrroom JSON configs, identify issues, download optimized configs
- **Pre-roll Analyzer** - Analyze video format, get FFmpeg commands to match library content
- **Device Database** - Pre-configured profiles for displays, AVRs, sources, and speakers
- **EDID Reference** - Documentation for EDID modes and DV strings

## Quick Start

### Native (Python)

```bash
# Clone and enter directory
git clone https://github.com/yourusername/vrroom-configurator.git
cd vrroom-configurator

# Run the launcher (creates venv, installs deps)
./start-unix.sh      # Linux/macOS
start-windows.bat    # Windows

# Open browser to http://localhost:5000
```

### Docker

```bash
docker-compose up -d
# Open browser to http://localhost:5000
```

## Documentation

- **[Deployment Guide](docs/DEPLOYMENT.md)** - Installation, configuration, and production deployment
- **[User Guide](docs/USER_GUIDE.md)** - Complete usage instructions and workflow examples

## Usage Overview

### My Setup (Recommended Starting Point)

1. Select your equipment (display, AVR, source, speakers, media server)
2. Choose optimization goals (Avoid Bonk, LLDV, Best Audio, etc.)
3. Click **Generate Recommendations**
4. Apply Vrroom Settings via web interface
5. Configure Source Settings on your streaming device

### Config Analysis

1. Export your Vrroom config (CONFIG → EXPORT)
2. Upload the JSON file to the Config Analyzer
3. Review color-coded issues (Critical/Warning/Info)
4. Download the optimized configuration
5. Import back to Vrroom (CONFIG → IMPORT)
6. **Power cycle your Vrroom** (critical!)

### Pre-roll Analysis

1. Upload your pre-roll video
2. Review format analysis
3. Copy FFmpeg commands to re-encode
4. Match format to main library content

## Expected Results

| Optimization | Before | After | Improvement |
|-------------|--------|-------|-------------|
| Config only | 2-3s delay | ~500ms | 50-75% |
| Config + matched pre-roll | 2-3s delay | <200ms | 90-100% |

## Target Hardware

Originally developed for:
- **Projector**: Epson EH-LS12000b (non-native DV, LLDV compatible)
- **AVR**: Yamaha RX-A4A
- **Source**: Nvidia Shield Pro
- **Speakers**: 5.2.2 Atmos
- **Processor**: HDFury Vrroom (Firmware 0.63+)

Supports additional devices including JVC projectors, Denon/Marantz AVRs, Apple TV, and more.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze/config` | POST | Analyze Vrroom config JSON |
| `/api/analyze/preroll` | POST | Analyze pre-roll video |
| `/api/download/<filename>` | GET | Download optimized config |
| `/api/devices` | GET | Get device profiles |
| `/api/goals` | GET | Get optimization goals |
| `/api/setup/recommend` | POST | Generate setup recommendations |
| `/api/edid-presets` | GET | Get EDID documentation |
| `/api/health` | GET | Health check |

## Dependencies

- Python 3.8+
- Flask 3.0+
- FFmpeg/FFprobe (optional, for pre-roll analysis)

## Project Structure

```
vrroom-configurator/
├── app.py                    # Flask web application
├── templates/index.html      # Web interface
├── docs/
│   ├── DEPLOYMENT.md        # Deployment guide
│   └── USER_GUIDE.md        # User guide
├── requirements.txt          # Python dependencies
├── Dockerfile               # Container build
├── docker-compose.yml       # Easy deployment
├── start-windows.bat        # Windows launcher
├── start-unix.sh           # Linux/macOS launcher
├── uploads/                 # Temp upload storage
├── exports/                 # Generated configs
├── HDfury_EDID_collection/  # EDID binary files
└── VRRoom_FW_63/           # Firmware documentation
```

## License

MIT License

## References

- [HDFury Vrroom Manual](https://www.hdfury.com/docs/HDfuryVRRoom.pdf)
- RS232 Commands: `VRRoom_FW_63/vrroom-rs232-ip-251021.txt`
- Firmware Changelog: `VRRoom_FW_63/ReadMeFirst.txt`
