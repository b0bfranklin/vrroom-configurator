Create or update my CLAUDE.MD fileI want to create a hdfury vrroom configuration tool to fix/minimise bonk issues and optimise for DV support on a non DV compatible device (Epson EH-LS12000b projector) via the LLDV capability. specifically I would like to have a custom pre-roll (which I have already made) to be visible. The pre-roll lasts 6 seconds and the audio plays but you see 1 frame of the video on emby (haven't tested with Jellyfin or plex yet). The properties of the video file (mp4) are Frame width is 1280, height is 720, data rate is 3114kbps bitrate is 3255kbps and frame rate 24.00 fps (although I would like to get that up to 4k, 60hz/120hz and redo the audio to have a longer more impressive THX style atmos test track and video ending with my custom one joined in at the same video and audio depth but that can be a separate project).
Here is what I made in claude chat so far:

# Vrroom Analyzer - Project Summary for GitHub

## **Project Overview**
Web-based and CLI toolkit for analyzing and optimizing HDFury Vrroom configurations to eliminate HDMI handshake delays ("bonk") during pre-roll playback in home theater setups.

## **Problem Solved**
- 2-3 second black screens during Plex/Jellyfin pre-rolls
- HDMI handshake delays when video format changes
- Difficult to identify optimal Vrroom settings manually
- Pre-roll format mismatches causing unnecessary format switching

## **Solution**
Dual-interface analyzer that:
1. Analyzes Vrroom JSON configs to identify timing/EDID issues
2. Generates optimized configurations with specific recommendations
3. Analyzes pre-roll video formats and suggests FFmpeg re-encoding
4. Provides device database and EDID reference documentation

## **Tech Stack**
- **Backend**: Python 3.8+, Flask 3.0
- **Frontend**: Vanilla HTML/CSS/JavaScript (no frameworks)
- **Video Analysis**: FFmpeg/FFprobe
- **Deployment**: Native (Windows/Linux/macOS), Docker

## **Key Features**
- ✅ Drag & drop config/video upload
- ✅ Visual analysis with color-coded issues (Critical/Warning/Info)
- ✅ One-click optimized config download
- ✅ Device database (projectors, AVRs, sources)
- ✅ EDID preset reference guide
- ✅ Cross-platform launchers (bat/shell scripts)
- ✅ Docker support with compose file
- ✅ FFmpeg command generation for pre-roll re-encoding

## **Project Structure**
```
vrroom-analyzer/
├── README.md                      # Main documentation
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container build
├── docker-compose.yml             # Easy deployment
├── app.py                         # Flask web application
├── templates/
│   └── index.html                # Web interface
├── start-windows.bat             # Windows launcher
├── start-unix.sh                 # Linux/macOS launcher
├── uploads/                      # Temp upload storage
└── exports/                      # Generated configs
```

## **Core Components**

### **1. Config Analyzer** (`VrroomWebAnalyzer` class)
- Parses Vrroom JSON exports
- Identifies problematic settings:
  - Audio unmute delays (critical timing)
  - EDID mode issues (AutoMix vs Custom)
  - Dolby Vision conversion overhead
  - HDR processing delays
- Generates optimized configuration
- Returns structured issue reports with severity levels

### **2. Pre-roll Analyzer** (FFprobe integration)
- Extracts video format metadata (resolution, codec, HDR, fps)
- Identifies format mismatches with typical library content
- Generates FFmpeg commands for:
  - HDR 4K (HEVC, BT.2020, HDR10 metadata)
  - SDR 1080p (HEVC, BT.709)
  - Custom scenarios

### **3. Device Database**
- Pre-configured profiles for popular hardware:
  - Projectors (Epson, JVC, Sony)
  - AVRs (Yamaha, Denon, Marantz)
  - Sources (Shield, Apple TV, Zidoo)
- Includes: handshake times, capabilities, recommended EDID

### **4. Web Interface**
- Modern dark theme UI
- Tabbed navigation (Analyzer/Pre-roll/Devices/EDID)
- Responsive design
- Real-time analysis feedback
- No external CSS/JS dependencies

## **API Endpoints**
- `POST /api/analyze/config` - Upload and analyze Vrroom config
- `POST /api/analyze/preroll` - Upload and analyze video file
- `GET /api/download/<filename>` - Download optimized config
- `GET /api/devices` - Get device profiles database
- `GET /api/edid-presets` - Get EDID documentation

## **Installation**

### **Quick Start**
```bash
# Clone repo
git clone https://github.com/yourusername/vrroom-analyzer.git
cd vrroom-analyzer

# Install dependencies
pip install -r requirements.txt

# Run server
python app.py
# OR use platform launcher
./start-unix.sh
```

### **Docker**
```bash
docker-compose up -d
```

## **Usage Example**
1. Export Vrroom config from web interface (CONFIG → EXPORT)
2. Upload to analyzer at http://localhost:5000
3. Review color-coded issues
4. Download optimized config
5. Import back to Vrroom (CONFIG → IMPORT)
6. **Power cycle Vrroom** (critical!)

## **Expected Results**
- **Config only**: 2-3s → ~500ms (50-75% improvement)
- **Config + matched pre-roll**: 2-3s → <200ms or zero (90-100% improvement)

## **Extensibility**
Designed to accept:
- Complete HDFury EDID collection (place in `docs/edid/`)
- Vrroom manual PDF (place in `docs/vrroom-manual.pdf`)
- Additional device profiles (edit `DEVICE_PROFILES` in `app.py`)
- Custom EDID presets (edit `EDID_PRESETS` in `app.py`)

## **Target Audience**
- Home theater enthusiasts using HDFury Vrroom
- Users experiencing HDMI handshake delays
- Plex/Jellyfin/Emby users with pre-roll issues
- HDFury community members

## **Dependencies**
- Python 3.8+
- Flask 3.0
- FFmpeg (optional, for pre-roll analysis)

## **License**
MIT License - Free to use, modify, distribute

## **Future Enhancements**
- [ ] Batch config analysis
- [ ] Config history tracking
- [ ] Before/after visual comparison
- [ ] Community device profile submissions
- [ ] RS232 macro builder
- [ ] Home Assistant integration
- [ ] Mobile app versions

## **Repository Keywords**
`hdfury` `vrroom` `hdmi` `home-theater` `plex` `jellyfin` `handshake` `edid` `4k` `hdr` `projector` `avr` `pre-roll` `cinema-mode` `flask` `python` `analyzer` `optimization`

## **README Sections Needed**
1. Problem description with screenshots/diagrams
2. Installation (all platforms)
3. Quick start guide
4. Detailed usage with examples
5. Configuration options
6. Troubleshooting
7. Contributing guidelines
8. Device profile format
9. API documentation
10. Deployment options (Docker, systemd, etc.)

---

**Initial Commit Message:**
```
feat: Initial release of Vrroom Analyzer

- Web-based and CLI analyzer for HDFury Vrroom configs
- Identifies HDMI handshake delay causes
- Generates optimized configurations
- Pre-roll format analyzer with FFmpeg integration
- Device database and EDID reference
- Cross-platform support (Windows/Linux/macOS/Docker)
```
