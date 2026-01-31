# Vrroom Configurator

Web-based toolkit for analyzing and optimizing HDFury Vrroom configurations to eliminate HDMI handshake delays ("bonk") during pre-roll playback in home theater setups.

## Problem Solved

- **2-3 second black screens** during Plex/Jellyfin/Emby pre-rolls
- **HDMI handshake delays** when video format changes
- **Difficult to identify** optimal Vrroom settings manually
- **Pre-roll format mismatches** causing unnecessary format switching

## Features

- **Config Analyzer** - Upload Vrroom JSON configs, identify timing/EDID issues, download optimized configs
- **Pre-roll Analyzer** - Analyze video format, get FFmpeg commands to match library content
- **Device Database** - Pre-configured profiles for popular projectors, AVRs, and sources
- **EDID Reference** - Documentation for EDID modes, DV strings, and RS232 commands

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

## Usage

### Config Analysis

1. Export your Vrroom config from the web interface (CONFIG → EXPORT)
2. Upload the JSON file to the Config Analyzer tab
3. Review color-coded issues (Critical/Warning/Info)
4. Download the optimized configuration
5. Import back to Vrroom (CONFIG → IMPORT)
6. **Power cycle your Vrroom** (critical after config changes!)

### Pre-roll Analysis

1. Upload your pre-roll video file
2. Review format analysis and identified issues
3. Copy FFmpeg commands to re-encode your pre-roll
4. Match format to your main library content to eliminate bonk

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
- **Processor**: HDFury Vrroom (Firmware 0.63+)

## LLDV (Low Latency Dolby Vision)

For projectors without native Dolby Vision support:
- Vrroom can inject LLDV capability into EDID
- Sources output LLDV which gets converted to HDR10
- Preserves dynamic metadata benefits
- Use AutoMix mode with appropriate DV string (X930E, etc.)

## Dependencies

- Python 3.8+
- Flask 3.0+
- FFmpeg/FFprobe (optional, for pre-roll analysis)

## Project Structure

```
vrroom-configurator/
├── app.py                    # Flask web application
├── templates/index.html      # Web interface
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

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze/config` | POST | Analyze Vrroom config JSON |
| `/api/analyze/preroll` | POST | Analyze pre-roll video |
| `/api/download/<filename>` | GET | Download optimized config |
| `/api/devices` | GET | Get device profiles |
| `/api/edid-presets` | GET | Get EDID documentation |
| `/api/health` | GET | Health check |

## License

MIT License

## References

- [HDFury Vrroom Manual](https://www.hdfury.com/docs/HDfuryVRRoom.pdf)
- RS232 Commands: `VRRoom_FW_63/vrroom-rs232-ip-251021.txt`
- Firmware Changelog: `VRRoom_FW_63/ReadMeFirst.txt`
