# CLAUDE.md - Vrroom Configurator Project Guide

## Project Purpose

This is an HDFury Vrroom configuration tool designed to:
1. **Fix/minimize "bonk" issues** - HDMI handshake delays causing 2-3 second black screens during format changes
2. **Optimize for Dolby Vision support** on non-DV compatible devices via **LLDV (Low Latency Dolby Vision)** capability
3. **Enable custom pre-roll visibility** - Currently the user's 6-second pre-roll shows only 1 frame with audio on Emby

## Target Hardware Setup

- **Projector**: Epson EH-LS12000b (non-native DV, requires LLDV conversion)
- **AVR**: Yamaha RX-A4A
- **Source**: Nvidia Shield Pro
- **HDMI Processor**: HDFury Vrroom

## Current Pre-Roll Issue

The custom pre-roll has these properties:
- Resolution: 1280x720
- Data rate: 3114kbps
- Bitrate: 3255kbps
- Frame rate: 24.00 fps
- Format: MP4

**Problem**: Audio plays but only 1 frame of video visible on Emby (not tested with Jellyfin/Plex yet)

**Future enhancement**: Upgrade pre-roll to 4K, 60hz/120hz with Atmos test track (THX-style intro) - separate project

## Project Architecture (Planned)

### Tech Stack
- **Backend**: Python 3.8+, Flask 3.0
- **Frontend**: Vanilla HTML/CSS/JavaScript (no frameworks)
- **Video Analysis**: FFmpeg/FFprobe
- **Deployment**: Native (Windows/Linux/macOS), Docker

### Target Project Structure
```
vrroom-configurator/
├── CLAUDE.md                         # This file
├── README.md                         # User documentation
├── requirements.txt                  # Python dependencies
├── Dockerfile                        # Container build
├── docker-compose.yml                # Easy deployment
├── app.py                            # Flask web application
├── templates/
│   └── index.html                    # Web interface
├── start-windows.bat                 # Windows launcher
├── start-unix.sh                     # Linux/macOS launcher
├── uploads/                          # Temp upload storage
├── exports/                          # Generated configs
├── HDfury_EDID_collection/           # [EXISTS] EDID binary files
│   ├── Diva EDID Tables/
│   ├── Dr.HDMI EDID/
│   ├── Integral EDID Tables/
│   ├── Integral-Vizio Dolby Vision EDID/
│   ├── Linker EDID Tables/
│   ├── Linker-Vizio Dolby Vision EDID/
│   ├── Manufacturer EDID/
│   └── Older revision EDID/
└── VRRoom_FW_63/                      # [EXISTS] Firmware & docs
    ├── ReadMeFirst.txt               # Changelog & upgrade instructions
    ├── vrroom-rs232-ip-251021.txt    # RS232/IP command reference
    └── VRRoom_ir_codeset*.txt        # IR codes
```

## Existing Resources

### EDID Collection
Located in `HDfury_EDID_collection/` - includes:
- Integral EDID tables (various 4K/HDR/Atmos configurations)
- Integral-Vizio Dolby Vision EDIDs
- Linker EDID tables
- Manufacturer EDIDs (JVC, Panasonic)
- Diva EDID (includes LLDV: `LGC8-CUSTOM8-DIVA-FULLAUDIO-LLDV.bin`)

**Important EDID Notes** (from HDFury):
- DV tables not included in default firmware due to Oppo forcing DV when capability detected
- For true DV support, use AUTOMIX mode on AVR-Key, Integral, Vertex
- Linker does NOT support all DV modes

### Firmware Documentation (v0.63)
Key features relevant to this project:
- LLDV>HDR injection support under VRR signal (added in v0.51)
- DisplayID 2.0 support (384b/512b EDID) in AUTOMIX mode
- UNMUTE delay options for audio pop/crackle issues
- Config EXPORT/IMPORT functionality

### RS232/IP Commands Reference
Located at `VRRoom_FW_63/vrroom-rs232-ip-251021.txt`

**Key commands for this project**:
```bash
# EDID Mode
#vrroom set edidmode [automix / custom / fixed / copytx0 / copytx1]

# Dolby Vision EDID settings
#vrroom set ediddvflag [on / off]
#vrroom set ediddvmode [0=LG C1, 1=CUSTOM, 2=remove]

# HDR settings
#vrroom set edidhdrflag [on / off]
#vrroom set edidhdrmode [0=HDR10, 1=HDR10/HLG, 2=HDR10+, 3=HDR10+/HLG, 4=remove]

# Audio settings (for unmute delays)
# (configured via webserver)

# Custom HDR injection (disable under VRR automatically)
#vrroom set hdrcustom [on / off]

# Status checks
#vrroom get status [rx0/rx1/tx0/tx1/tx0sink/tx1sink/aud0/aud1/audout/spd0/spd1]
```

## Core Features to Implement

### 1. Config Analyzer (`VrroomWebAnalyzer` class)
Analyze Vrroom JSON config exports for:
- Audio unmute delays (critical for bonk timing)
- EDID mode issues (AutoMix vs Custom)
- Dolby Vision conversion overhead
- HDR processing delays
- LLDV configuration for non-DV displays

### 2. Pre-roll Analyzer (FFprobe integration)
- Extract video format metadata (resolution, codec, HDR info, fps)
- Identify format mismatches causing handshake delays
- Generate FFmpeg commands for re-encoding to match main content format
- Target formats:
  - HDR 4K (HEVC, BT.2020, HDR10 metadata)
  - SDR 1080p (HEVC, BT.709)
  - Match Dolby Vision profile if needed

### 3. Device Database
Pre-configured profiles for:
- **Projectors**: Epson EH-LS12000b, JVC, Sony
- **AVRs**: Yamaha RX-A4A, Denon, Marantz
- **Sources**: Nvidia Shield Pro, Apple TV, Zidoo

### 4. Web Interface
- Dark theme UI suitable for home theater use
- Drag & drop config/video upload
- Visual analysis with severity levels (Critical/Warning/Info)
- One-click optimized config download
- EDID preset reference guide

## API Endpoints (Planned)
- `POST /api/analyze/config` - Upload and analyze Vrroom config
- `POST /api/analyze/preroll` - Upload and analyze video file
- `GET /api/download/<filename>` - Download optimized config
- `GET /api/devices` - Get device profiles database
- `GET /api/edid-presets` - Get EDID documentation

## Key Technical Considerations

### LLDV (Low Latency Dolby Vision) for Epson EH-LS12000b
- The Epson projector doesn't have native DV support
- LLDV converts DV to HDR10 while preserving dynamic metadata benefits
- Vrroom can inject LLDV capability into EDID for sources to output LLDV
- Requires proper AUTOMIX configuration

### Bonk/Handshake Optimization
1. **Match pre-roll format to main content** - Prevents format switching
2. **Optimize unmute delays** - Balance between audio pops and response time
3. **Use appropriate EDID mode** - AUTOMIX typically best for mixed content
4. **Configure FRL/TMDS modes** - Based on sink capabilities

### Pre-Roll Format Recommendations
For seamless playback without bonk:
- Match resolution to most common library content (typically 4K)
- Match HDR format (HDR10 if that's what library uses)
- Match frame rate to content (23.976/24 for movies, 60 for menu/UI)
- Use HEVC codec for 4K HDR content

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Run with Docker
docker-compose up -d

# Test FFprobe integration
ffprobe -v quiet -print_format json -show_format -show_streams <video_file>
```

## Usage Workflow
1. Export Vrroom config from web interface (CONFIG → EXPORT)
2. Upload to analyzer
3. Review color-coded issues
4. Download optimized config
5. Import back to Vrroom (CONFIG → IMPORT)
6. **Power cycle Vrroom** (critical after config changes!)

## Expected Performance Improvements
- **Config optimization only**: 2-3s delay → ~500ms (50-75% improvement)
- **Config + matched pre-roll**: 2-3s delay → <200ms or zero (90-100% improvement)

## Future Enhancements
- [ ] Batch config analysis
- [ ] Config history/version tracking
- [ ] Before/after visual comparison
- [ ] Community device profile submissions
- [ ] RS232 macro builder for JVC projectors
- [ ] Home Assistant integration
- [ ] Pre-roll generator (4K/60fps/Atmos THX-style intro)

## References
- HDFury Vrroom Manual: www.hdfury.com/docs/HDfuryVRRoom.pdf
- Firmware changelog: `VRRoom_FW_63/ReadMeFirst.txt`
- RS232 commands: `VRRoom_FW_63/vrroom-rs232-ip-251021.txt`
