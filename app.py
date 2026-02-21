#!/usr/bin/env python3
"""
Vrroom Configurator - HDFury Vrroom Configuration Analyzer
Optimizes configs for minimal HDMI handshake delays (bonk) and LLDV support
"""

import copy
import json
import os
import socket
import subprocess
import shutil
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['EXPORT_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)


# =============================================================================
# Vrroom IP Connection
# =============================================================================

class VrroomConnection:
    """Connect to Vrroom via TCP/Telnet to query settings."""

    DEFAULT_PORT = 2222
    TIMEOUT = 5  # seconds

    # Settings to query from Vrroom
    SETTINGS_TO_QUERY = [
        "opmode", "insel", "dhcp", "ipaddr", "autosw",
        "edidmode", "edidfrlflag", "edidfrlmode", "edidvrrflag", "edidallmflag",
        "edidhdrflag", "edidhdrmode", "ediddvflag", "ediddvmode",
        "edidtruehdflag", "edidtruehdmode", "edidddflag", "edidddplusflag",
        "ediddtsflag", "ediddtshdflag", "edidpcmflag", "edidpcmchmode",
        "hdcp", "hdrcustom", "hdrdisable", "cec",
        "earcforce", "jvcmacro", "oled", "oledfade"
    ]

    STATUS_QUERIES = ["rx0", "tx0", "tx1", "tx0sink", "tx1sink", "aud0", "audout"]

    def __init__(self, ip_address, port=None):
        self.ip_address = ip_address
        self.port = port or self.DEFAULT_PORT
        self.socket = None

    def connect(self):
        """Establish TCP connection to Vrroom."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.TIMEOUT)
            self.socket.connect((self.ip_address, self.port))
            return True
        except socket.timeout:
            raise ConnectionError(f"Connection to {self.ip_address}:{self.port} timed out")
        except socket.error as e:
            raise ConnectionError(f"Failed to connect to {self.ip_address}:{self.port}: {e}")

    def disconnect(self):
        """Close the connection."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

    def send_command(self, command):
        """Send a command and receive response."""
        if not self.socket:
            raise ConnectionError("Not connected")

        try:
            # IP mode doesn't need #vrroom prefix
            cmd = f"{command}\r\n"
            self.socket.sendall(cmd.encode('utf-8'))

            # Read response
            response = b""
            while True:
                try:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    # Check if we have a complete response (ends with \r\n)
                    if response.endswith(b"\r\n"):
                        break
                except socket.timeout:
                    break

            return response.decode('utf-8').strip()
        except socket.error as e:
            raise ConnectionError(f"Communication error: {e}")

    def get_setting(self, setting):
        """Query a single setting."""
        response = self.send_command(f"get {setting}")
        # Response format is typically "setting value" or just "value"
        parts = response.split()
        if len(parts) >= 2:
            return parts[-1]  # Return last part as value
        return response

    def get_all_settings(self):
        """Query all relevant settings from Vrroom."""
        settings = {}

        for setting in self.SETTINGS_TO_QUERY:
            try:
                value = self.get_setting(setting)
                if value and value.lower() not in ["error", "unknown"]:
                    settings[setting] = value
            except Exception:
                continue  # Skip settings that fail

        return settings

    def get_status(self):
        """Get current signal status."""
        status = {}

        for query in self.STATUS_QUERIES:
            try:
                response = self.send_command(f"get status {query}")
                if response:
                    status[query] = response
            except Exception:
                continue

        return status

    def fetch_config(self):
        """Fetch complete configuration from Vrroom."""
        try:
            self.connect()
            settings = self.get_all_settings()
            status = self.get_status()

            return {
                "success": True,
                "ip_address": self.ip_address,
                "settings": settings,
                "status": status,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ip_address": self.ip_address
            }
        finally:
            self.disconnect()


# =============================================================================
# Device Database
# =============================================================================

DEVICE_PROFILES = {
    "displays": {
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
            "vrr_support": False,
            "allm_support": False,
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
            "vrr_support": False,
            "allm_support": False,
            "notes": "Excellent tone mapping. Consider RS232 macros for lens memory."
        },
        "jvc_dla_nz7": {
            "name": "JVC DLA-NZ7",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 3000,
            "recommended_edid": "automix",
            "vrr_support": False,
            "allm_support": False,
            "notes": "E-shift 4K. Good candidate for LLDV via Vrroom."
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
            "vrr_support": False,
            "allm_support": False,
            "notes": "Native 4K panel. Fast HDMI handshake."
        },
        "lg_c3_oled": {
            "name": "LG C3 OLED",
            "type": "tv",
            "native_dv": True,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HLG", "Dolby Vision"],
            "hdcp": "2.3",
            "handshake_time_ms": 1500,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "notes": "Native DV support. LLDV not required but Vrroom can still optimize handshake."
        },
        "samsung_qn90c": {
            "name": "Samsung QN90C",
            "type": "tv",
            "native_dv": False,
            "lldv_compatible": False,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HDR10+", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 1800,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "notes": "No DV support. Use HDR10+ when available, HDR10 fallback."
        },
        "sony_a95l_oled": {
            "name": "Sony A95L QD-OLED",
            "type": "tv",
            "native_dv": True,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "hdr_support": ["HDR10", "HLG", "Dolby Vision"],
            "hdcp": "2.3",
            "handshake_time_ms": 1600,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "notes": "Native DV with excellent QD-OLED HDR."
        }
    },
    "hdfury_devices": {
        "vrroom": {
            "name": "HDFury Vrroom",
            "type": "hdfury",
            "inputs": 2,
            "outputs": 2,
            "lldv_support": True,
            "vrr_support": True,
            "allm_support": True,
            "earc_support": True,
            "edid_modes": ["automix", "custom", "fixed", "copytx0", "copytx1"],
            "custom_edid_slots": 10,
            "max_frl": True,
            "downscale": True,
            "current_firmware": "0.63",
            "notes": "Full-featured HDMI matrix with LLDV injection and eARC support."
        },
        "vertex2": {
            "name": "HDFury Vertex2",
            "type": "hdfury",
            "inputs": 2,
            "outputs": 2,
            "lldv_support": True,
            "vrr_support": True,
            "allm_support": True,
            "earc_support": False,
            "edid_modes": ["automix", "custom", "fixed", "copytx0", "copytx1"],
            "custom_edid_slots": 10,
            "max_frl": True,
            "downscale": True,
            "current_firmware": "N/A",
            "notes": "18Gbps matrix. Good for dual-display setups without eARC needs."
        },
        "diva": {
            "name": "HDFury Diva",
            "type": "hdfury",
            "inputs": 4,
            "outputs": 2,
            "lldv_support": True,
            "vrr_support": True,
            "allm_support": True,
            "earc_support": True,
            "edid_modes": ["automix", "custom", "fixed", "copytx0", "copytx1"],
            "custom_edid_slots": 10,
            "max_frl": True,
            "downscale": True,
            "current_firmware": "N/A",
            "notes": "4-input matrix with LLDV. Has dedicated LLDV EDID: LGC8-CUSTOM8-DIVA-FULLAUDIO-LLDV.bin"
        },
        "integral_2": {
            "name": "HDFury Integral 2",
            "type": "hdfury",
            "inputs": 2,
            "outputs": 2,
            "lldv_support": True,
            "vrr_support": False,
            "allm_support": False,
            "earc_support": False,
            "edid_modes": ["automix", "custom", "fixed", "copytx0", "copytx1"],
            "custom_edid_slots": 10,
            "max_frl": False,
            "downscale": True,
            "current_firmware": "N/A",
            "notes": "Legacy 18Gbps device. DV AUTOMIX supported."
        },
        "arcana": {
            "name": "HDFury Arcana",
            "type": "hdfury",
            "inputs": 1,
            "outputs": 1,
            "lldv_support": False,
            "vrr_support": True,
            "allm_support": True,
            "earc_support": True,
            "edid_modes": ["automix"],
            "custom_edid_slots": 0,
            "max_frl": True,
            "downscale": False,
            "current_firmware": "N/A",
            "notes": "eARC adapter. Adds eARC to non-eARC AVRs/soundbars."
        }
    },
    "avrs": {
        "yamaha_rx_a4a": {
            "name": "Yamaha RX-A4A",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 500,
            "recommended_audio_mode": "earc",
            "notes": "Good HDMI 2.1 passthrough. Use eARC for best audio."
        },
        "yamaha_rx_a6a": {
            "name": "Yamaha RX-A6A",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 500,
            "recommended_audio_mode": "earc",
            "notes": "Flagship Yamaha. 11.2ch processing with HDMI 2.1."
        },
        "denon_avr_x3800h": {
            "name": "Denon AVR-X3800H",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 600,
            "recommended_audio_mode": "earc",
            "notes": "Excellent HDMI 2.1 implementation."
        },
        "denon_avr_x4800h": {
            "name": "Denon AVR-X4800H",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 600,
            "recommended_audio_mode": "earc",
            "notes": "11.4ch processing. Dirac Live ready."
        },
        "marantz_cinema_50": {
            "name": "Marantz Cinema 50",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 600,
            "recommended_audio_mode": "earc",
            "notes": "Premium audio processing. Same HDMI board as Denon."
        },
        "anthem_mrx_1140": {
            "name": "Anthem MRX 1140",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 700,
            "recommended_audio_mode": "earc",
            "notes": "Premium processor with ARC Genesis room correction."
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
        },
        "xbox_series_x": {
            "name": "Xbox Series X",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "match_frame_rate": False,
            "match_resolution": False,
            "hdcp": "2.3",
            "notes": "Gaming source. Enable VRR/ALLM for best gaming experience."
        },
        "ps5": {
            "name": "PlayStation 5",
            "type": "source",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 120,
            "match_frame_rate": False,
            "match_resolution": False,
            "hdcp": "2.3",
            "notes": "HDR10 gaming. No DV support. VRR available."
        },
        "kaleidescape_strato": {
            "name": "Kaleidescape Strato",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "hdcp": "2.3",
            "notes": "Premium media player. Known compatibility with Vrroom repeater mode."
        }
    },
    "speakers": {
        "stereo_2_0": {
            "name": "2.0 Stereo",
            "type": "speaker",
            "layout": "2.0",
            "atmos_capable": False,
            "dtsx_capable": False,
            "channels": 2,
            "overhead_channels": 0,
            "sub_channels": 0,
            "recommended_audio_format": "pcm",
            "notes": "Basic stereo. PCM or compressed stereo only."
        },
        "surround_5_1": {
            "name": "5.1 Surround",
            "type": "speaker",
            "layout": "5.1",
            "atmos_capable": False,
            "dtsx_capable": False,
            "channels": 5,
            "overhead_channels": 0,
            "sub_channels": 1,
            "recommended_audio_format": "bitstream",
            "notes": "Standard surround. Supports DD/DTS via bitstream."
        },
        "surround_7_1": {
            "name": "7.1 Surround",
            "type": "speaker",
            "layout": "7.1",
            "atmos_capable": False,
            "dtsx_capable": False,
            "channels": 7,
            "overhead_channels": 0,
            "sub_channels": 1,
            "recommended_audio_format": "bitstream",
            "notes": "Extended surround. Supports DD/DTS/TrueHD/DTS-HD via bitstream."
        },
        "atmos_5_1_2": {
            "name": "5.1.2 Atmos",
            "type": "speaker",
            "layout": "5.1.2",
            "atmos_capable": True,
            "dtsx_capable": True,
            "channels": 5,
            "overhead_channels": 2,
            "sub_channels": 1,
            "recommended_audio_format": "bitstream",
            "notes": "Entry Atmos. 2 overhead channels for height effects."
        },
        "atmos_5_2_2": {
            "name": "5.2.2 Atmos",
            "type": "speaker",
            "layout": "5.2.2",
            "atmos_capable": True,
            "dtsx_capable": True,
            "channels": 5,
            "overhead_channels": 2,
            "sub_channels": 2,
            "recommended_audio_format": "bitstream",
            "notes": "Atmos with dual subs and 2 overhead channels. Dual subs provide even bass distribution."
        },
        "atmos_5_1_4": {
            "name": "5.1.4 Atmos",
            "type": "speaker",
            "layout": "5.1.4",
            "atmos_capable": True,
            "dtsx_capable": True,
            "channels": 5,
            "overhead_channels": 4,
            "sub_channels": 1,
            "recommended_audio_format": "bitstream",
            "notes": "Full Atmos with 4 overhead channels. Recommended minimum for immersive audio."
        },
        "atmos_7_1_4": {
            "name": "7.1.4 Atmos",
            "type": "speaker",
            "layout": "7.1.4",
            "atmos_capable": True,
            "dtsx_capable": True,
            "channels": 7,
            "overhead_channels": 4,
            "sub_channels": 1,
            "recommended_audio_format": "bitstream",
            "notes": "Reference Atmos layout. 7 ear-level + 4 overhead + subwoofer."
        },
        "atmos_7_2_4": {
            "name": "7.2.4 Atmos",
            "type": "speaker",
            "layout": "7.2.4",
            "atmos_capable": True,
            "dtsx_capable": True,
            "channels": 7,
            "overhead_channels": 4,
            "sub_channels": 2,
            "recommended_audio_format": "bitstream",
            "notes": "Reference Atmos with dual subs for even bass distribution."
        },
        "soundbar_atmos": {
            "name": "Soundbar (Atmos)",
            "type": "speaker",
            "layout": "varies",
            "atmos_capable": True,
            "dtsx_capable": False,
            "channels": 0,
            "overhead_channels": 0,
            "sub_channels": 0,
            "recommended_audio_format": "bitstream",
            "notes": "Soundbar via eARC/ARC. Ensure eARC mode is set correctly on Vrroom."
        },
        "soundbar_basic": {
            "name": "Soundbar (Basic)",
            "type": "speaker",
            "layout": "varies",
            "atmos_capable": False,
            "dtsx_capable": False,
            "channels": 0,
            "overhead_channels": 0,
            "sub_channels": 0,
            "recommended_audio_format": "pcm",
            "notes": "Basic soundbar via ARC. May need ARC mode (not eARC) on Vrroom."
        }
    },
    "media_servers": {
        "plex": {
            "name": "Plex",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "notes": "Set pre-roll in Settings > Extras. No automatic format matching."
        },
        "jellyfin": {
            "name": "Jellyfin",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "notes": "Pre-roll via Intros plugin. Free and open source."
        },
        "emby": {
            "name": "Emby",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "notes": "Cinema intros feature. Known issue: may only show 1 frame if format mismatch."
        },
        "kodi": {
            "name": "Kodi",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "notes": "CinemaVision addon for pre-roll. Local playback only."
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
# Optimization Goals
# =============================================================================

OPTIMIZATION_GOALS = {
    "avoid_bonk": {
        "id": "avoid_bonk",
        "name": "Avoid HDMI Bonk / Blank Screen",
        "description": "Minimize or eliminate black screen delays during format changes between pre-roll and main content.",
        "category": "video"
    },
    "lldv_non_dv": {
        "id": "lldv_non_dv",
        "name": "Dolby Vision on Non-DV Display (LLDV)",
        "description": "Enable Dolby Vision content on displays without native DV support via Low Latency Dolby Vision conversion.",
        "category": "video"
    },
    "best_audio": {
        "id": "best_audio",
        "name": "Best Audio Quality (Atmos/DTS:X)",
        "description": "Optimize audio routing for highest quality lossless surround sound passthrough.",
        "category": "audio"
    },
    "gaming_low_latency": {
        "id": "gaming_low_latency",
        "name": "Gaming / Low Latency",
        "description": "Enable VRR, ALLM, and minimize processing for the lowest input lag gaming experience.",
        "category": "video"
    },
    "fix_preroll": {
        "id": "fix_preroll",
        "name": "Fix Pre-roll Visibility",
        "description": "Fix issues where pre-roll video shows only 1 frame or black screen while audio plays.",
        "category": "video"
    },
    "hdr_passthrough": {
        "id": "hdr_passthrough",
        "name": "4K HDR Passthrough",
        "description": "Ensure clean 4K HDR10/HLG passthrough with correct color space and metadata.",
        "category": "video"
    },
    "minimize_format_switch": {
        "id": "minimize_format_switch",
        "name": "Minimize Format Switching",
        "description": "Reduce the number of HDMI re-negotiations by standardizing output format across content types.",
        "category": "video"
    }
}


def _get_settings_path(device_id, setting_type):
    """Get step-by-step navigation path for a device setting."""
    paths = {
        "nvidia_shield_pro": {
            "resolution": "Settings > Device Preferences > Display & Sound > Resolution",
            "frame_rate": "Settings > Device Preferences > Display & Sound > Match content frame rate",
            "hdr": "Settings > Device Preferences > Display & Sound > Dynamic range > set to Auto",
            "audio": "Settings > Device Preferences > Display & Sound > Advanced sound settings > Surround sound > Auto",
            "dv": "Settings > Device Preferences > Display & Sound > Dolby Vision > set to Enabled"
        },
        "apple_tv_4k": {
            "resolution": "Settings > Video and Audio > Format > 4K SDR 60Hz",
            "frame_rate": "Settings > Video and Audio > Match Content > Match Frame Rate > On",
            "hdr": "Settings > Video and Audio > Match Content > Match Dynamic Range > On",
            "audio": "Settings > Video and Audio > Audio Format > Dolby Atmos (if available)",
            "dv": "Settings > Video and Audio > Match Content > Match Dynamic Range > On (enables DV when available)"
        },
        "xbox_series_x": {
            "resolution": "Settings > General > TV & Display Options > Resolution > 4K UHD",
            "frame_rate": "Settings > General > TV & Display Options > Refresh Rate > 120 Hz",
            "hdr": "Settings > General > TV & Display Options > Video Modes > Allow HDR10 > checked",
            "audio": "Settings > General > Volume & Audio Output > HDMI audio > Bitstream out > Dolby Atmos for Home Theater",
            "vrr": "Settings > General > TV & Display Options > Video Modes > Allow Variable Refresh Rate > checked",
            "allm": "Settings > General > TV & Display Options > Video Modes > Allow Auto Low Latency Mode > checked"
        },
        "ps5": {
            "resolution": "Settings > Screen and Video > Video Output > Resolution > 2160p",
            "frame_rate": "Settings > Screen and Video > Video Output > Enable 120 Hz Output > Automatic",
            "hdr": "Settings > Screen and Video > Video Output > HDR > On When Supported",
            "audio": "Settings > Sound > Audio Output > Audio Format (Priority) > Bitstream (Dolby)",
            "vrr": "Settings > Screen and Video > Video Output > VRR > Automatic"
        },
        "zidoo_z9x_pro": {
            "resolution": "Settings > Display > Resolution > 3840x2160p Auto",
            "frame_rate": "Settings > Display > Match Frame Rate > On",
            "hdr": "Settings > Display > HDR > Auto",
            "audio": "Settings > Audio > HDMI Audio > Auto",
            "dv": "Settings > Display > Dolby Vision > VS10 Engine"
        },
        "kaleidescape_strato": {
            "resolution": "Kaleidescape App > Settings > Video > Output Resolution > Auto",
            "frame_rate": "Kaleidescape App > Settings > Video > Match Frame Rate > On",
            "hdr": "Kaleidescape App > Settings > Video > HDR > Auto",
            "audio": "Kaleidescape App > Settings > Audio > Digital Audio > Bitstream"
        }
    }
    device_paths = paths.get(device_id, {})
    return device_paths.get(setting_type, "")


# =============================================================================
# Setup Recommendation Engine
# =============================================================================

class SetupRecommendationEngine:
    """Generates tailored recommendations based on user equipment and optimization goals."""

    def __init__(self, setup):
        self.display_id = setup.get("display", "")
        self.hdfury_id = setup.get("hdfury_device", "")
        self.avr_id = setup.get("avr", "")
        self.speaker_id = setup.get("speakers", "")
        self.media_server_id = setup.get("media_server", "")
        self.goals = setup.get("goals", [])

        # Support multiple sources (Vrroom is a 4x2 matrix)
        sources_input = setup.get("sources", [])
        # Backwards compat: single source string
        if not sources_input:
            single = setup.get("source", "")
            sources_input = [single] if single else []
        elif isinstance(sources_input, str):
            sources_input = [sources_input]

        self.source_ids = [s for s in sources_input if s]
        self.sources = []
        for sid in self.source_ids:
            profile = DEVICE_PROFILES["sources"].get(sid, {})
            if profile:
                self.sources.append((sid, profile))

        # Keep first source as primary for backwards compat
        self.source_id = self.source_ids[0] if self.source_ids else ""
        self.source = self.sources[0][1] if self.sources else {}

        self.display = DEVICE_PROFILES["displays"].get(self.display_id, {})
        self.hdfury = DEVICE_PROFILES["hdfury_devices"].get(self.hdfury_id, {})
        self.avr = DEVICE_PROFILES["avrs"].get(self.avr_id, {})
        self.speakers = DEVICE_PROFILES["speakers"].get(self.speaker_id, {})
        self.media_server = DEVICE_PROFILES["media_servers"].get(self.media_server_id, {})

    def generate(self):
        """Generate full recommendation set."""
        recommendations = []
        vrroom_settings = {}
        source_settings = []

        for goal_id in self.goals:
            handler = getattr(self, f"_goal_{goal_id}", None)
            if handler:
                result = handler()
                recommendations.extend(result.get("recommendations", []))
                vrroom_settings.update(result.get("vrroom_settings", {}))
                source_settings.extend(result.get("source_settings", []))

        # Add general recommendations based on equipment
        general = self._general_equipment_recs()
        recommendations.extend(general.get("recommendations", []))
        vrroom_settings.update(general.get("vrroom_settings", {}))
        source_settings.extend(general.get("source_settings", []))

        # Deduplicate
        seen_recs = set()
        unique_recs = []
        for rec in recommendations:
            key = rec["title"]
            if key not in seen_recs:
                seen_recs.add(key)
                unique_recs.append(rec)

        seen_src = set()
        unique_src = []
        for s in source_settings:
            key = (s["setting"], s.get("device", ""))
            if key not in seen_src:
                seen_src.add(key)
                unique_src.append(s)

        # Generate downloadable Vrroom config file
        config_filename = None
        if vrroom_settings:
            config_data = {**vrroom_settings}
            config_filename = f"vrroom_recommended_{uuid.uuid4().hex[:8]}.json"
            filepath = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'exports', config_filename
            )
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(config_data, f, indent=2)

        return {
            "setup_summary": {
                "display": self.display.get("name", "Not specified"),
                "hdfury_device": self.hdfury.get("name", "Not specified"),
                "avr": self.avr.get("name", "Not specified"),
                "sources": [s[1].get("name", "Unknown") for s in self.sources] if self.sources else ["Not specified"],
                "speakers": self.speakers.get("name", "Not specified"),
                "media_server": self.media_server.get("name", "Not specified"),
                "goals": [OPTIMIZATION_GOALS[g]["name"] for g in self.goals if g in OPTIMIZATION_GOALS]
            },
            "recommendations": unique_recs,
            "vrroom_settings": vrroom_settings,
            "source_settings": unique_src,
            "download_filename": config_filename
        }

    def _general_equipment_recs(self):
        """Recommendations based purely on the equipment selected."""
        recs = []
        settings = {}
        source_settings = []

        # HDCP always auto
        settings["hdcpmode"] = "auto"

        if self.display:
            display_name = self.display.get("name", "display")
            if self.display.get("handshake_time_ms", 0) >= 2500:
                recs.append({
                    "severity": "info",
                    "title": f"{display_name} Has Slow Handshake",
                    "description": f"This display has a typical handshake time of {self.display['handshake_time_ms']}ms. "
                                   "Minimizing format changes is especially important for this device."
                })

        if self.avr:
            if self.avr.get("earc_support"):
                recs.append({
                    "severity": "info",
                    "title": "eARC Recommended for Audio",
                    "description": f"{self.avr.get('name', 'Your AVR')} supports eARC. Use eARC routing for "
                                   "lossless Atmos/DTS:X passthrough."
                })

        for source_id, source in self.sources:
            source_name = source.get("name", "source")
            if source.get("match_frame_rate"):
                source_settings.append({
                    "setting": f"Match Frame Rate ({source_name})",
                    "value": "Enabled",
                    "device": source_name,
                    "reason": "Prevents unnecessary refresh rate changes.",
                    "path": _get_settings_path(source_id, "frame_rate")
                })
            if source.get("match_resolution"):
                source_settings.append({
                    "setting": f"Match Resolution ({source_name})",
                    "value": "Enabled",
                    "device": source_name,
                    "reason": "Outputs content at native resolution.",
                    "path": _get_settings_path(source_id, "resolution")
                })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": source_settings}

    def _goal_avoid_bonk(self):
        """Recommendations for avoiding HDMI bonk/blank screen."""
        recs = []
        settings = {}
        src = []

        recs.append({
            "severity": "critical",
            "title": "Match Pre-roll Format to Library Content",
            "description": "The primary cause of bonk is format mismatch between pre-roll and main content. "
                           "Encode your pre-roll at the same resolution, frame rate, HDR format, and codec as "
                           "your most common library content (typically 4K HEVC HDR10 23.976fps)."
        })

        settings["edidmode"] = "automix"

        unmute = 200
        if self.avr and self.avr.get("handshake_time_ms", 0) > 500:
            unmute = 250
        settings["unmutedelay"] = unmute
        recs.append({
            "severity": "warning",
            "title": f"Set Unmute Delay to {unmute}ms",
            "description": "Balance between audio pop prevention and responsiveness. "
                           f"Start at {unmute}ms and reduce if no audio pops occur."
        })

        if self.display and self.display.get("handshake_time_ms", 0) >= 2500:
            recs.append({
                "severity": "warning",
                "title": "Consider Fixed Output Resolution",
                "description": "Your display has a slow handshake. Consider setting your source to always "
                               "output 4K to avoid resolution-change-triggered handshakes. Only frame rate "
                               "and HDR mode should change."
            })
            for source_id, source in self.sources:
                source_name = source.get("name", "Source")
                if self.display and self.display.get("handshake_time_ms", 0) >= 2500:
                    src.append({
                        "setting": f"Output Resolution ({source_name})",
                        "value": "4K (fixed)",
                        "device": source_name,
                        "reason": "Prevents resolution-change handshake delays on slow displays.",
                        "path": _get_settings_path(source_id, "resolution")
                    })

        if self.media_server:
            server_name = self.media_server.get("name", "media server")
            recs.append({
                "severity": "info",
                "title": f"Pre-roll Format for {server_name}",
                "description": "Encode pre-roll as 4K HEVC HDR10 23.976fps to match typical movie content. "
                               "This prevents the format switch that causes bonk between pre-roll and feature."
            })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": src}

    def _goal_lldv_non_dv(self):
        """Recommendations for LLDV on non-DV displays."""
        recs = []
        settings = {}

        if self.display and self.display.get("native_dv"):
            recs.append({
                "severity": "info",
                "title": "Display Has Native Dolby Vision",
                "description": f"{self.display.get('name', 'Your display')} already supports DV natively. "
                               "LLDV conversion is not required, but Vrroom can still pass DV through."
            })
            settings["ediddvflag"] = "on"
            return {"recommendations": recs, "vrroom_settings": settings, "source_settings": []}

        if self.hdfury and not self.hdfury.get("lldv_support"):
            recs.append({
                "severity": "critical",
                "title": "HDFury Device Does Not Support LLDV",
                "description": f"{self.hdfury.get('name', 'Your HDFury device')} does not support LLDV injection. "
                               "Consider upgrading to Vrroom or Diva for LLDV capability."
            })
            return {"recommendations": recs, "vrroom_settings": {}, "source_settings": []}

        settings["edidmode"] = "automix"
        settings["ediddvflag"] = "on"
        settings["ediddvmode"] = 1  # Custom mode for LLDV
        settings["edidhdrflag"] = "on"
        settings["edidhdrmode"] = 1  # HDR10/HLG

        display_name = self.display.get("name", "your display") if self.display else "your display"
        recs.append({
            "severity": "critical",
            "title": "Enable LLDV in AutoMix Mode",
            "description": f"Set EDID to AutoMix with DV flag enabled and LLDV-compatible string (X930E). "
                           f"This tells sources to output LLDV, which Vrroom converts to HDR10 for {display_name}."
        })
        recs.append({
            "severity": "warning",
            "title": "Select LLDV DV String",
            "description": "On the Vrroom EDID page, under AutoMix > DV dropdown, select 'X930E LLDV' string. "
                           "This is the recommended LLDV string for non-DV projectors."
        })
        recs.append({
            "severity": "info",
            "title": "LLDV Under VRR Signals",
            "description": "LLDV>HDR injection is supported under VRR signals since firmware 0.51, "
                           "though some Samsung TVs may have issues."
        })

        if self.source and self.source.get("lldv_output"):
            recs.append({
                "severity": "info",
                "title": f"{self.source.get('name', 'Source')} Supports LLDV Output",
                "description": "This source can output LLDV natively. Once EDID is configured, "
                               "it will automatically output LLDV when DV content is played."
            })
        elif self.source and not self.source.get("dv_output"):
            recs.append({
                "severity": "warning",
                "title": "Source Has No DV Output",
                "description": f"{self.source.get('name', 'Your source')} does not support Dolby Vision output. "
                               "Content will fall back to HDR10."
            })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": []}

    def _goal_best_audio(self):
        """Recommendations for best audio quality."""
        recs = []
        settings = {}
        src = []

        has_atmos = self.speakers and self.speakers.get("atmos_capable")
        has_earc_avr = self.avr and self.avr.get("earc_support")
        has_earc_hdfury = self.hdfury and self.hdfury.get("earc_support")
        is_soundbar = self.speakers and "soundbar" in self.speaker_id

        if has_earc_avr and has_earc_hdfury:
            settings["earcmode"] = "auto earc"
            recs.append({
                "severity": "critical",
                "title": "Use eARC for Audio Routing",
                "description": "Both your AVR and HDFury device support eARC. Set eARC mode to 'Auto eARC' "
                               "for lossless Atmos/DTS:X passthrough. Ensure eARC device powers on before source."
            })
        elif is_soundbar and has_earc_hdfury:
            settings["earcmode"] = "auto earc"
            recs.append({
                "severity": "warning",
                "title": "eARC for Soundbar",
                "description": "Set eARC mode for soundbar connection. If using ARC-only soundbar, "
                               "switch to 'Auto ARC' mode instead."
            })

        if has_atmos:
            for source_id, source in self.sources:
                src.append({
                    "setting": f"Audio Output ({source.get('name', 'Source')})",
                    "value": "Bitstream (passthrough)",
                    "device": source.get("name", "Source"),
                    "reason": "Bitstream passes lossless Atmos/DTS:X to AVR for decoding.",
                    "path": _get_settings_path(source_id, "audio")
                })
            recs.append({
                "severity": "info",
                "title": "Atmos Speaker Layout Detected",
                "description": f"Your {self.speakers.get('name', '')} setup supports Atmos. "
                               "Ensure all sources are set to bitstream output for lossless audio passthrough."
            })

        # Unmute delay for audio
        if has_earc_avr:
            settings["earcunmute"] = 200
            recs.append({
                "severity": "info",
                "title": "eARC Unmute Delay: 200ms",
                "description": "A small eARC unmute delay prevents audio pops when switching formats. "
                               "Reduce to 100ms if no pops occur, increase to 300ms if they persist."
            })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": src}

    def _goal_gaming_low_latency(self):
        """Recommendations for gaming / low latency."""
        recs = []
        settings = {}
        src = []

        # Check display VRR/ALLM support
        display_vrr = self.display.get("vrr_support", False) if self.display else False
        display_allm = self.display.get("allm_support", False) if self.display else False
        hdfury_vrr = self.hdfury.get("vrr_support", False) if self.hdfury else False
        hdfury_allm = self.hdfury.get("allm_support", False) if self.hdfury else False

        if not display_vrr and self.display:
            recs.append({
                "severity": "warning",
                "title": f"{self.display.get('name', 'Your Display')} Does Not Support VRR",
                "description": "Your display does not support Variable Refresh Rate (VRR). "
                               "Gaming will work at fixed refresh rates. VRR passthrough in "
                               "the Vrroom will have no effect for this display."
            })

        if not display_allm and self.display:
            recs.append({
                "severity": "info",
                "title": f"{self.display.get('name', 'Your Display')} Does Not Support ALLM",
                "description": "Auto Low Latency Mode is not supported by your display. "
                               "You may need to manually switch to game/fast mode on your display when gaming."
            })

        if hdfury_vrr and display_vrr:
            recs.append({
                "severity": "critical",
                "title": "Enable VRR Passthrough",
                "description": "Both your HDFury device and display support VRR. Enable VRR passthrough "
                               "for tear-free gaming."
            })
            settings["edidvrrflag"] = "on"
        elif hdfury_vrr and not display_vrr:
            recs.append({
                "severity": "info",
                "title": "VRR Passthrough Available but Display Incompatible",
                "description": "Your Vrroom supports VRR passthrough but your display does not accept VRR. "
                               "VRR flag will not be added to EDID."
            })

        if hdfury_allm and display_allm:
            settings["edidallmflag"] = "on"
            recs.append({
                "severity": "info",
                "title": "ALLM Passthrough Enabled",
                "description": "ALLM will automatically switch your display to game mode when gaming content is detected."
            })
        elif hdfury_allm and not display_allm:
            recs.append({
                "severity": "info",
                "title": "ALLM Passthrough Available but Display Incompatible",
                "description": "Your Vrroom supports ALLM passthrough but your display does not support it. "
                               "Manually switch your display to game/fast mode when gaming."
            })

        settings["hdrcustom"] = "off"
        recs.append({
            "severity": "warning",
            "title": "Disable Custom HDR Injection for Gaming",
            "description": "Custom HDR injection adds processing overhead. It automatically disables under VRR "
                           "signals, but explicitly disabling it avoids edge cases."
        })

        # Generate source settings for ALL gaming-capable sources
        for source_id, source in self.sources:
            source_name = source.get("name", "Source")
            if source.get("max_refresh", 0) >= 120:
                src.append({
                    "setting": f"Output Resolution ({source_name})",
                    "value": "4K 120Hz",
                    "device": source_name,
                    "reason": "Maximum refresh rate for smoothest gaming.",
                    "path": _get_settings_path(source_id, "resolution")
                })

        settings["unmutedelay"] = 100
        recs.append({
            "severity": "info",
            "title": "Minimize Unmute Delay for Gaming",
            "description": "Set unmute delay to 100ms or lower to minimize audio latency during gaming."
        })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": src}

    def _goal_fix_preroll(self):
        """Recommendations for fixing pre-roll visibility issues."""
        recs = []
        settings = {}
        src = []

        recs.append({
            "severity": "critical",
            "title": "Pre-roll Format Must Match Main Content",
            "description": "The most common cause of seeing only 1 frame with audio is the display performing an "
                           "HDMI handshake when switching from pre-roll format to content format. During this "
                           "handshake (2-3 seconds), the display shows nothing while audio continues from the AVR. "
                           "Solution: re-encode pre-roll to match your library's dominant format."
        })
        recs.append({
            "severity": "critical",
            "title": "Recommended Pre-roll Encoding",
            "description": "Encode pre-roll as: 3840x2160 (4K), HEVC codec, HDR10 (BT.2020, SMPTE ST 2084), "
                           "23.976fps, 10-bit. This matches the most common 4K movie format and avoids handshake."
        })
        recs.append({
            "severity": "warning",
            "title": "Use the Pre-roll Analyzer Tab",
            "description": "Upload your current pre-roll video in the Pre-roll Analyzer tab to get specific "
                           "FFmpeg commands for re-encoding it to the optimal format."
        })

        settings["edidmode"] = "automix"

        if self.media_server:
            server_name = self.media_server.get("name", "Media server")
            if self.media_server_id == "emby":
                recs.append({
                    "severity": "info",
                    "title": "Emby Pre-roll Known Issue",
                    "description": "Emby cinema intros are known to show only 1 frame when there's a format "
                                   "mismatch. Re-encoding the pre-roll to match content format resolves this."
                })
            recs.append({
                "severity": "info",
                "title": f"Test with Multiple {server_name} Clients",
                "description": "Test pre-roll playback with different clients (web, mobile, TV app) to confirm "
                               "the issue is HDMI handshake related and not client-specific."
            })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": src}

    def _goal_hdr_passthrough(self):
        """Recommendations for 4K HDR passthrough."""
        recs = []
        settings = {}

        settings["edidhdrflag"] = "on"
        settings["edidhdrmode"] = 1  # HDR10/HLG
        settings["edidmode"] = "automix"
        settings["hdcpmode"] = "auto"

        recs.append({
            "severity": "critical",
            "title": "Enable HDR in EDID",
            "description": "HDR flag must be enabled in EDID for sources to output HDR content. "
                           "Set HDR mode to HDR10/HLG for broadest compatibility."
        })

        if self.display:
            hdr_list = self.display.get("hdr_support", [])
            if hdr_list:
                recs.append({
                    "severity": "info",
                    "title": f"Display HDR Support: {', '.join(hdr_list)}",
                    "description": f"{self.display.get('name', 'Your display')} supports {', '.join(hdr_list)}. "
                                   "EDID HDR mode has been set to match."
                })
                if "HDR10+" in hdr_list:
                    settings["edidhdrmode"] = 2  # HDR10+

        recs.append({
            "severity": "info",
            "title": "HDCP Set to Auto",
            "description": "HDCP auto mode ensures proper handshake without forcing a version. "
                           "Manual HDCP settings can cause 4K HDR content to fail."
        })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": []}

    def _goal_minimize_format_switch(self):
        """Recommendations for minimizing format switching."""
        recs = []
        settings = {}
        src = []

        recs.append({
            "severity": "critical",
            "title": "Set Source to Fixed Output Format",
            "description": "Configure your source device to output a fixed resolution (4K) and let the "
                           "Vrroom handle any necessary conversion. Only allow frame rate matching to change."
        })

        if self.source:
            source_name = self.source.get("name", "Source")
            if self.source.get("match_frame_rate"):
                src.append({
                    "setting": "Match Frame Rate",
                    "value": "Enabled",
                    "device": source_name,
                    "reason": "Frame rate changes cause minimal handshake delay compared to resolution changes."
                })
            src.append({
                "setting": "Output Resolution",
                "value": "4K (always)",
                "device": source_name,
                "reason": "Fixed 4K output prevents resolution-triggered handshakes."
            })
            if self.source_id == "apple_tv_4k":
                src.append({
                    "setting": "Video Format",
                    "value": "4K SDR 60Hz",
                    "device": source_name,
                    "reason": "Apple TV with Match Content enabled: set base to 4K SDR, let match content handle HDR/fps."
                })

        settings["edidmode"] = "automix"

        recs.append({
            "severity": "info",
            "title": "AutoMix Prevents EDID Re-reads",
            "description": "AutoMix mode provides a stable EDID to sources, preventing them from "
                           "re-reading EDID and triggering unnecessary handshakes."
        })

        return {"recommendations": recs, "vrroom_settings": settings, "source_settings": src}


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
        elif edid_mode and edid_mode not in ["automix", "custom", "copytx0", "copytx1"]:
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

        if dv_flag == "off":
            self._add_issue(
                self.SEVERITY_INFO,
                "Dolby Vision Disabled",
                "DV EDID flag is off. Enable for LLDV support on non-DV displays.",
                "ediddvflag", "off", "on"
            )

        if dv_flag == "on":
            self.recommendations.append({
                "title": "DV Enabled",
                "description": "Ensure LLDV-compatible DV string is selected (X930E or similar) for non-DV projectors."
            })

    def _check_hdr_settings(self):
        """Check HDR configuration."""
        hdr_flag = self.config.get("edidhdrflag", "on").lower()
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
        if "cecenabled" in self.config and self.config["cecenabled"]:
            self.recommendations.append({
                "title": "CEC Enabled",
                "description": "CEC can add latency on input switches. Disable if not using TV/AVR power control features."
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
        optimized = copy.deepcopy(self.config)

        for issue in self.issues:
            if issue["severity"] in [self.SEVERITY_CRITICAL, self.SEVERITY_WARNING]:
                if "setting" in issue and "recommended_value" in issue:
                    optimized[issue["setting"]] = issue["recommended_value"]

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

        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        codec = video_stream.get("codec_name", "unknown")

        fps_str = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den else 0
        except (ValueError, ZeroDivisionError):
            fps = 0

        color_space = video_stream.get("color_space", "unknown")
        color_transfer = video_stream.get("color_transfer", "unknown")
        color_primaries = video_stream.get("color_primaries", "unknown")

        is_hdr = color_transfer in ["smpte2084", "arib-std-b67"] or \
                 color_primaries == "bt2020" or \
                 "hdr" in video_stream.get("profile", "").lower()

        is_dv = False
        side_data = video_stream.get("side_data_list", [])
        for sd in side_data:
            if "dovi" in sd.get("side_data_type", "").lower():
                is_dv = True
                break

        issues = []
        recommendations = []
        ffmpeg_commands = []

        # Resolution analysis
        is_4k = width >= 3840 and height >= 2160
        if not is_4k:
            issues.append({
                "severity": "warning",
                "title": "Non-4K Resolution",
                "description": f"Video is {width}x{height}. Format switch to 4K content will cause handshake delay."
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

        # Always provide both conversion commands
        ffmpeg_commands.append({
            "description": "Convert to 4K HDR10 (HEVC) - Recommended for movie pre-rolls",
            "command": self._generate_ffmpeg_4k_hdr(self.file_path)
        })
        ffmpeg_commands.append({
            "description": "Convert to 1080p SDR (HEVC) - For SDR-only setups",
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

    if results.get("optimized_config"):
        filename = f"vrroom_optimized_{uuid.uuid4().hex[:8]}.json"
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        with open(filepath, "w") as f:
            json.dump(results["optimized_config"], f, indent=2)
        results["download_filename"] = filename

    return jsonify(results)


@app.route("/api/vrroom/connect", methods=["POST"])
def vrroom_connect():
    """Connect to Vrroom by IP and fetch current configuration."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    ip_address = data.get("ip_address", "").strip()
    port = data.get("port", VrroomConnection.DEFAULT_PORT)

    if not ip_address:
        return jsonify({"error": "IP address is required"}), 400

    # Basic IP validation
    parts = ip_address.split(".")
    if len(parts) != 4:
        return jsonify({"error": "Invalid IP address format"}), 400
    try:
        for part in parts:
            num = int(part)
            if num < 0 or num > 255:
                raise ValueError()
    except ValueError:
        return jsonify({"error": "Invalid IP address"}), 400

    try:
        port = int(port)
    except (ValueError, TypeError):
        port = VrroomConnection.DEFAULT_PORT

    connection = VrroomConnection(ip_address, port)
    result = connection.fetch_config()

    if result["success"]:
        # Also run analysis on the fetched settings
        settings = result.get("settings", {})
        status = result.get("status", {})

        # Build a config-like structure for analysis
        config_data = {**settings}

        # Add status info
        result["analysis"] = {
            "settings_count": len(settings),
            "status_count": len(status),
            "edid_mode": settings.get("edidmode", "unknown"),
            "dv_enabled": settings.get("ediddvflag", "off") == "on",
            "hdr_enabled": settings.get("edidhdrflag", "off") == "on",
            "cec_enabled": settings.get("cec", "off") == "on",
        }

        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/api/vrroom/command", methods=["POST"])
def vrroom_command():
    """Send a command to Vrroom (for applying settings)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    ip_address = data.get("ip_address", "").strip()
    command = data.get("command", "").strip()
    port = data.get("port", VrroomConnection.DEFAULT_PORT)

    if not ip_address:
        return jsonify({"error": "IP address is required"}), 400
    if not command:
        return jsonify({"error": "Command is required"}), 400

    # Security: only allow 'get' and 'set' commands
    cmd_lower = command.lower()
    if not (cmd_lower.startswith("get ") or cmd_lower.startswith("set ")):
        return jsonify({"error": "Only 'get' and 'set' commands are allowed"}), 400

    try:
        connection = VrroomConnection(ip_address, int(port))
        connection.connect()
        response = connection.send_command(command)
        connection.disconnect()

        return jsonify({
            "success": True,
            "command": command,
            "response": response
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/analyze/preroll", methods=["POST"])
def analyze_preroll():
    """Analyze uploaded pre-roll video file."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = f"preroll_{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        analyzer = PrerollAnalyzer(filepath)
        results = analyzer.analyze()
        return jsonify(results)
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/api/download/<filename>")
def download_config(filename):
    """Download optimized configuration file."""
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


@app.route("/api/goals")
def get_goals():
    """Get available optimization goals."""
    return jsonify(OPTIMIZATION_GOALS)


@app.route("/api/setup/recommend", methods=["POST"])
def setup_recommend():
    """Generate recommendations based on user setup and goals."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No setup data provided"}), 400

    engine = SetupRecommendationEngine(data)
    results = engine.generate()
    return jsonify(results)


@app.route("/api/health")
def health_check():
    """Health check endpoint."""
    ffprobe_available = shutil.which("ffprobe") is not None
    return jsonify({
        "status": "healthy",
        "ffprobe_available": ffprobe_available,
        "version": "1.1.0"
    })


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"

    print("\n" + "=" * 60)
    print("  Vrroom Configurator - HDFury Vrroom Config Analyzer")
    print("=" * 60)
    print(f"  Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"  Export folder: {app.config['EXPORT_FOLDER']}")
    print(f"  FFprobe available: {shutil.which('ffprobe') is not None}")
    print(f"  Debug mode: {debug}")
    print("=" * 60)
    print("  Starting server at http://localhost:5000")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=debug)
