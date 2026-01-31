#!/usr/bin/env python3
"""
Vrroom Configurator - HDFury Vrroom Configuration Analyzer
Optimizes configs for minimal HDMI handshake delays (bonk) and LLDV support
"""

import json
import os
import subprocess
import shutil
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['EXPORT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'exports')

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)


# =============================================================================
# Device Database
# =============================================================================

DEVICE_PROFILES = {
    "projectors": {
        "epson_eh_ls12000b": {
            "name": "Epson EH-LS12000b",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 2500,
            "recommended_edid": "automix",
            "notes": "Use LLDV for Dolby Vision content. Native HDR10 support excellent."
        },
        "jvc_dla_nz8": {
            "name": "JVC DLA-NZ8",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HLG", "HDR10+"],
            "hdcp": "2.3",
            "handshake_time_ms": 3000,
            "recommended_edid": "automix",
            "notes": "Excellent tone mapping. Consider RS232 macros for lens memory."
        },
        "sony_vpl_xw7000": {
            "name": "Sony VPL-XW7000ES",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 2000,
            "recommended_edid": "automix",
            "notes": "Native 4K panel. Fast HDMI handshake."
        }
    },
    "avrs": {
        "yamaha_rx_a4a": {
            "name": "Yamaha RX-A4A",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dts_x_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 500,
            "recommended_audio_mode": "earc",
            "notes": "Good HDMI 2.1 passthrough. Use eARC for best audio."
        },
        "denon_avr_x3800h": {
            "name": "Denon AVR-X3800H",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dts_x_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 600,
            "recommended_audio_mode": "earc",
            "notes": "Excellent HDMI 2.1 implementation."
        },
        "marantz_cinema_50": {
            "name": "Marantz Cinema 50",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dts_x_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 600,
            "recommended_audio_mode": "earc",
            "notes": "Premium audio processing. Same HDMI board as Denon."
        }
    },
    "sources": {
        "nvidia_shield_pro": {
            "name": "Nvidia Shield Pro",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "hdcp": "2.3",
            "notes": "Enable match frame rate and match resolution in settings."
        },
        "apple_tv_4k": {
            "name": "Apple TV 4K (2022)",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": False,
            "hdcp": "2.3",
            "notes": "Set to 4K SDR 60Hz with match content enabled for best results."
        },
        "zidoo_z9x_pro": {
            "name": "Zidoo Z9X Pro",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "hdcp": "2.3",
            "notes": "Excellent format switching. VS10 engine for DV conversion."
        }
    }
}


# =============================================================================
# EDID Presets Documentation
# =============================================================================

EDID_PRESETS = {
    "automix": {
        "name": "AutoMix (Recommended)",
        "description": "Combines sink EDID with custom modifications. Best for mixed content.",
        "use_case": "Default choice for most setups",
        "dv_support": "Supports LLDV injection",
        "command": "#vrroom set edidmode automix"
    },
    "custom": {
        "name": "Custom EDID",
        "description": "Use one of 10 custom EDID slots. Full control over capabilities.",
        "use_case": "When sink EDID causes issues or specific caps needed",
        "dv_support": "Depends on custom EDID loaded",
        "command": "#vrroom set edidmode custom"
    },
    "copytx0": {
        "name": "Copy TX0",
        "description": "Pass through TX0 sink EDID unmodified",
        "use_case": "Troubleshooting or when full sink capabilities needed",
        "dv_support": "Depends on sink",
        "command": "#vrroom set edidmode copytx0"
    },
    "copytx1": {
        "name": "Copy TX1",
        "description": "Pass through TX1 sink EDID unmodified",
        "use_case": "Matrix setups with secondary display",
        "dv_support": "Depends on sink",
        "command": "#vrroom set edidmode copytx1"
    },
    "fixed": {
        "name": "Fixed EDID",
        "description": "Use factory default EDID",
        "use_case": "Fallback when other modes fail",
        "dv_support": "Basic HDR only",
        "command": "#vrroom set edidmode fixed"
    }
}

EDID_DV_STRINGS = {
    "lgc1": {"name": "LG C1", "mode": 0, "description": "Standard DV string compatible with most sources"},
    "custom": {"name": "Custom", "mode": 1, "description": "User-defined DV capabilities"},
    "x930e": {"name": "Sony X930E LLDV", "description": "Low latency DV for non-DV displays"},
    "z9d": {"name": "Sony Z9D Custom", "description": "Custom DV string for specific compatibility"}
}


# =============================================================================
# Vrroom Config Analyzer
# =============================================================================

class VrroomConfigAnalyzer:
    """Analyzes HDFury Vrroom configuration exports for optimization opportunities."""

    SEVERITY_CRITICAL = "critical"
    SEVERITY_WARNING = "warning"
    SEVERITY_INFO = "info"

    def __init__(self, config_data):
        self.config = config_data
        self.issues = []
        self.recommendations = []

    def analyze(self):
        """Run all analysis checks and return results."""
        self.issues = []
        self.recommendations = []

        self._check_edid_mode()
        self._check_unmute_delays()
        self._check_dv_settings()
        self._check_hdr_settings()
        self._check_hdcp_settings()
        self._check_cec_settings()
        self._check_audio_routing()

        return {
            "issues": self.issues,
            "recommendations": self.recommendations,
            "issue_count": {
                "critical": len([i for i in self.issues if i["severity"] == self.SEVERITY_CRITICAL]),
                "warning": len([i for i in self.issues if i["severity"] == self.SEVERITY_WARNING]),
                "info": len([i for i in self.issues if i["severity"] == self.SEVERITY_INFO])
            },
            "optimized_config": self._generate_optimized_config()
        }

    def _add_issue(self, severity, title, description, setting=None, current_value=None, recommended_value=None):
        """Add an issue to the analysis results."""
        issue = {
            "severity": severity,
            "title": title,
            "description": description
        }
        if setting:
            issue["setting"] = setting
        if current_value is not None:
            issue["current_value"] = current_value
        if recommended_value is not None:
            issue["recommended_value"] = recommended_value
        self.issues.append(issue)

    def _check_edid_mode(self):
        """Check EDID mode configuration."""
        edid_mode = self.config.get("edidmode", "").lower()

        if edid_mode == "fixed":
            self._add_issue(
                self.SEVERITY_WARNING,
                "Fixed EDID Mode",
                "Fixed EDID mode limits sink capabilities. Consider AutoMix for better compatibility.",
                "edidmode", edid_mode, "automix"
            )
        elif edid_mode not in ["automix", "custom", "copytx0", "copytx1"]:
            self._add_issue(
                self.SEVERITY_INFO,
                "Unknown EDID Mode",
                f"EDID mode '{edid_mode}' not recognized. AutoMix recommended for most setups.",
                "edidmode", edid_mode, "automix"
            )

        if edid_mode == "automix":
            self.recommendations.append({
                "title": "EDID Mode Optimal",
                "description": "AutoMix mode allows dynamic EDID modification for LLDV injection."
            })

    def _check_unmute_delays(self):
        """Check audio unmute delay settings - critical for bonk timing."""
        unmute_delay = self.config.get("unmutedelay", 0)
        earc_unmute = self.config.get("earcunmute", 0)

        # Convert to int if string
        try:
            unmute_delay = int(unmute_delay)
        except (ValueError, TypeError):
            unmute_delay = 0

        try:
            earc_unmute = int(earc_unmute)
        except (ValueError, TypeError):
            earc_unmute = 0

        if unmute_delay > 500:
            self._add_issue(
                self.SEVERITY_CRITICAL,
                "High Unmute Delay",
                f"Unmute delay of {unmute_delay}ms adds significant latency. "
                "Try reducing to 200-300ms if no audio pops occur.",
                "unmutedelay", unmute_delay, 250
            )
        elif unmute_delay == 0:
            self._add_issue(
                self.SEVERITY_INFO,
                "No Unmute Delay",
                "Zero unmute delay may cause audio pops on some systems. "
                "Add 100-200ms if you hear clicks/pops on format changes.",
                "unmutedelay", 0, 150
            )

        if earc_unmute > 500:
            self._add_issue(
                self.SEVERITY_WARNING,
                "High eARC Unmute Delay",
                f"eARC unmute delay of {earc_unmute}ms may cause noticeable audio lag.",
                "earcunmute", earc_unmute, 300
            )

    def _check_dv_settings(self):
        """Check Dolby Vision configuration for LLDV setups."""
        dv_flag = self.config.get("ediddvflag", "off").lower()
        dv_mode = self.config.get("ediddvmode", 0)

        if dv_flag == "off":
            self._add_issue(
                self.SEVERITY_INFO,
                "Dolby Vision Disabled",
                "DV EDID flag is off. Enable for LLDV support on non-DV displays.",
                "ediddvflag", "off", "on"
            )

        # Check for LLDV string when DV is enabled
        if dv_flag == "on":
            self.recommendations.append({
                "title": "DV Enabled",
                "description": "Ensure LLDV-compatible DV string is selected (X930E or similar) for non-DV projectors."
            })

    def _check_hdr_settings(self):
        """Check HDR configuration."""
        hdr_flag = self.config.get("edidhdrflag", "on").lower()
        hdr_mode = self.config.get("edidhdrmode", 0)
        hdr_custom = self.config.get("hdrcustom", "off").lower()

        if hdr_flag == "off":
            self._add_issue(
                self.SEVERITY_WARNING,
                "HDR Disabled in EDID",
                "HDR flag is disabled. Sources won't output HDR content.",
                "edidhdrflag", "off", "on"
            )

        if hdr_custom == "on":
            self.recommendations.append({
                "title": "Custom HDR Injection Active",
                "description": "Note: Custom HDR injection automatically disables under VRR signals."
            })

    def _check_hdcp_settings(self):
        """Check HDCP configuration."""
        hdcp_mode = self.config.get("hdcpmode", "auto").lower()

        if hdcp_mode != "auto":
            self._add_issue(
                self.SEVERITY_INFO,
                "Manual HDCP Mode",
                f"HDCP is set to '{hdcp_mode}'. Auto mode is recommended unless troubleshooting.",
                "hdcpmode", hdcp_mode, "auto"
            )

    def _check_cec_settings(self):
        """Check CEC configuration that might affect switching times."""
        cec_enabled = self.config.get("cecenabled", True)

        if cec_enabled:
            self.recommendations.append({
                "title": "CEC Enabled",
                "description": "CEC can add latency on input switches. Disable if not using TV control features."
            })

    def _check_audio_routing(self):
        """Check audio routing configuration."""
        audio_out = self.config.get("audioout", "").lower()
        earc_mode = self.config.get("earcmode", "").lower()

        if audio_out == "earc" or earc_mode in ["auto earc", "earc"]:
            self.recommendations.append({
                "title": "eARC Audio Routing",
                "description": "eARC provides best audio quality. Ensure eARC device is powered on before source."
            })

    def _generate_optimized_config(self):
        """Generate an optimized version of the config."""
        optimized = self.config.copy()

        # Apply recommended values from critical and warning issues
        for issue in self.issues:
            if issue["severity"] in [self.SEVERITY_CRITICAL, self.SEVERITY_WARNING]:
                if "setting" in issue and "recommended_value" in issue:
                    optimized[issue["setting"]] = issue["recommended_value"]

        # Add optimization metadata
        optimized["_optimized"] = True
        optimized["_optimized_date"] = datetime.now().isoformat()
        optimized["_optimized_by"] = "Vrroom Configurator"

        return optimized


# =============================================================================
# Pre-roll Video Analyzer
# =============================================================================

class PrerollAnalyzer:
    """Analyzes video files for format compatibility with main library content."""

    def __init__(self, file_path):
        self.file_path = file_path
        self.metadata = None

    def analyze(self):
        """Analyze video file using FFprobe."""
        if not self._check_ffprobe():
            return {
                "error": "FFprobe not found. Install FFmpeg to analyze video files.",
                "ffprobe_available": False
            }

        try:
            self.metadata = self._get_metadata()
            return self._analyze_metadata()
        except Exception as e:
            return {
                "error": str(e),
                "ffprobe_available": True
            }

    def _check_ffprobe(self):
        """Check if FFprobe is available."""
        return shutil.which("ffprobe") is not None

    def _get_metadata(self):
        """Extract metadata using FFprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            self.file_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"FFprobe failed: {result.stderr}")

        return json.loads(result.stdout)

    def _analyze_metadata(self):
        """Analyze extracted metadata for compatibility issues."""
        video_stream = None
        audio_stream = None

        for stream in self.metadata.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = stream

        if not video_stream:
            return {"error": "No video stream found"}

        # Extract video properties
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        codec = video_stream.get("codec_name", "unknown")

        # Parse frame rate
        fps_str = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den else 0
        except (ValueError, ZeroDivisionError):
            fps = 0

        # Color properties
        color_space = video_stream.get("color_space", "unknown")
        color_transfer = video_stream.get("color_transfer", "unknown")
        color_primaries = video_stream.get("color_primaries", "unknown")

        # HDR detection
        is_hdr = color_transfer in ["smpte2084", "arib-std-b67"] or \
                 color_primaries == "bt2020" or \
                 "hdr" in video_stream.get("profile", "").lower()

        # Dolby Vision detection
        is_dv = False
        side_data = video_stream.get("side_data_list", [])
        for sd in side_data:
            if "dovi" in sd.get("side_data_type", "").lower():
                is_dv = True
                break

        # Build analysis result
        issues = []
        recommendations = []
        ffmpeg_commands = []

        # Resolution analysis
        if width < 3840 or height < 2160:
            issues.append({
                "severity": "warning",
                "title": "Non-4K Resolution",
                "description": f"Video is {width}x{height}. Format switch to 4K content will cause handshake delay."
            })
            ffmpeg_commands.append({
                "description": "Upscale to 4K HDR10",
                "command": self._generate_ffmpeg_4k_hdr(self.file_path)
            })

        # HDR analysis
        if not is_hdr:
            issues.append({
                "severity": "info",
                "title": "SDR Content",
                "description": "Video is SDR. Switching to HDR content will trigger format change."
            })
            recommendations.append({
                "title": "Consider HDR Pre-roll",
                "description": "Encode pre-roll as HDR10 to match typical 4K HDR library content."
            })

        # Frame rate analysis
        if fps and fps not in [23.976, 24, 25, 29.97, 30, 50, 59.94, 60]:
            issues.append({
                "severity": "info",
                "title": "Non-Standard Frame Rate",
                "description": f"Frame rate {fps:.3f} fps may cause compatibility issues."
            })

        if fps and fps < 24:
            issues.append({
                "severity": "warning",
                "title": "Low Frame Rate",
                "description": f"Frame rate {fps:.3f} fps is unusual for cinema content."
            })

        # Codec analysis
        if codec not in ["hevc", "h265", "h264", "avc"]:
            issues.append({
                "severity": "info",
                "title": "Uncommon Codec",
                "description": f"Codec '{codec}' may have limited hardware support."
            })

        # Generate standard FFmpeg commands
        ffmpeg_commands.append({
            "description": "Convert to 4K HDR10 (HEVC)",
            "command": self._generate_ffmpeg_4k_hdr(self.file_path)
        })
        ffmpeg_commands.append({
            "description": "Convert to 1080p SDR (HEVC)",
            "command": self._generate_ffmpeg_1080p_sdr(self.file_path)
        })

        return {
            "ffprobe_available": True,
            "file_info": {
                "width": width,
                "height": height,
                "codec": codec,
                "fps": round(fps, 3) if fps else None,
                "color_space": color_space,
                "color_transfer": color_transfer,
                "color_primaries": color_primaries,
                "is_hdr": is_hdr,
                "is_dolby_vision": is_dv,
                "duration": float(self.metadata.get("format", {}).get("duration", 0)),
                "bitrate": int(self.metadata.get("format", {}).get("bit_rate", 0))
            },
            "audio_info": {
                "codec": audio_stream.get("codec_name") if audio_stream else None,
                "channels": audio_stream.get("channels") if audio_stream else None,
                "sample_rate": audio_stream.get("sample_rate") if audio_stream else None
            } if audio_stream else None,
            "issues": issues,
            "recommendations": recommendations,
            "ffmpeg_commands": ffmpeg_commands
        }

    def _generate_ffmpeg_4k_hdr(self, input_file):
        """Generate FFmpeg command for 4K HDR10 conversion."""
        output = os.path.splitext(os.path.basename(input_file))[0] + "_4k_hdr10.mkv"
        return (
            f'ffmpeg -i "{input_file}" '
            f'-vf "scale=3840:2160:flags=lanczos,format=yuv420p10le" '
            f'-c:v libx265 -preset slow -crf 18 '
            f'-x265-params "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:'
            f'max-cll=1000,400:master-display=G(13250,34500)B(7500,3000)R(34000,16000)'
            f'WP(15635,16450)L(10000000,1)" '
            f'-c:a copy '
            f'"{output}"'
        )

    def _generate_ffmpeg_1080p_sdr(self, input_file):
        """Generate FFmpeg command for 1080p SDR conversion."""
        output = os.path.splitext(os.path.basename(input_file))[0] + "_1080p_sdr.mkv"
        return (
            f'ffmpeg -i "{input_file}" '
            f'-vf "scale=1920:1080:flags=lanczos" '
            f'-c:v libx265 -preset slow -crf 20 '
            f'-colorspace bt709 -color_trc bt709 -color_primaries bt709 '
            f'-c:a copy '
            f'"{output}"'
        )


# =============================================================================
# API Routes
# =============================================================================

@app.route("/")
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/analyze/config", methods=["POST"])
def analyze_config():
    """Analyze uploaded Vrroom configuration."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = file.read().decode("utf-8")
        config_data = json.loads(content)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    except UnicodeDecodeError:
        return jsonify({"error": "File must be UTF-8 encoded JSON"}), 400

    analyzer = VrroomConfigAnalyzer(config_data)
    results = analyzer.analyze()

    # Save optimized config for download
    if results.get("optimized_config"):
        filename = f"vrroom_optimized_{uuid.uuid4().hex[:8]}.json"
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        with open(filepath, "w") as f:
            json.dump(results["optimized_config"], f, indent=2)
        results["download_filename"] = filename

    return jsonify(results)


@app.route("/api/analyze/preroll", methods=["POST"])
def analyze_preroll():
    """Analyze uploaded pre-roll video file."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Save uploaded file temporarily
    filename = f"preroll_{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        analyzer = PrerollAnalyzer(filepath)
        results = analyzer.analyze()
        return jsonify(results)
    finally:
        # Clean up uploaded file
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/api/download/<filename>")
def download_config(filename):
    """Download optimized configuration file."""
    # Sanitize filename
    filename = os.path.basename(filename)
    filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)

    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route("/api/devices")
def get_devices():
    """Get device profiles database."""
    return jsonify(DEVICE_PROFILES)


@app.route("/api/edid-presets")
def get_edid_presets():
    """Get EDID preset documentation."""
    return jsonify({
        "modes": EDID_PRESETS,
        "dv_strings": EDID_DV_STRINGS
    })


@app.route("/api/health")
def health_check():
    """Health check endpoint."""
    ffprobe_available = shutil.which("ffprobe") is not None
    return jsonify({
        "status": "healthy",
        "ffprobe_available": ffprobe_available,
        "version": "1.0.0"
    })


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Vrroom Configurator - HDFury Vrroom Config Analyzer")
    print("=" * 60)
    print(f"  Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"  Export folder: {app.config['EXPORT_FOLDER']}")
    print(f"  FFprobe available: {shutil.which('ffprobe') is not None}")
    print("=" * 60)
    print("  Starting server at http://localhost:5000")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=True)
