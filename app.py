#!/usr/bin/env python3
"""
AV Signal Lab - Home Theater Signal Chain Optimizer
Optimizes HDMI signal chain for minimal handshake delays (bonk), HDR passthrough, and LLDV support
"""

import copy
import json
import os
import platform
import re
import socket
import sqlite3
import subprocess
import shutil
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, g

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['EXPORT_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')
app.config['BACKUP_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vrroom_devices.db')

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)


# =============================================================================
# SQLite Database for Custom Devices
# =============================================================================

def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database schema."""
    db = sqlite3.connect(app.config['DATABASE'])
    db.executescript('''
        CREATE TABLE IF NOT EXISTS custom_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            specs JSON NOT NULL,
            source_url TEXT,
            user_added INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS community_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            specs JSON NOT NULL,
            source_url TEXT,
            submitted_by TEXT,
            approved INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_custom_category ON custom_devices(category);
        CREATE INDEX IF NOT EXISTS idx_custom_device_id ON custom_devices(device_id);
        CREATE INDEX IF NOT EXISTS idx_community_category ON community_devices(category);
    ''')
    db.commit()
    db.close()


# Initialize database on startup
with app.app_context():
    init_db()


def get_custom_devices():
    """Get all custom devices from database."""
    db = get_db()
    devices = db.execute('SELECT * FROM custom_devices ORDER BY category, name').fetchall()
    result = {}
    for device in devices:
        category = device['category']
        if category not in result:
            result[category] = {}
        specs = json.loads(device['specs'])
        specs['name'] = device['name']
        specs['type'] = device['device_type']
        specs['user_added'] = True
        specs['source_url'] = device['source_url']
        result[category][device['device_id']] = specs
    return result


def add_custom_device(category, device_id, name, device_type, specs, source_url=None):
    """Add a custom device to the database."""
    db = get_db()
    try:
        db.execute('''
            INSERT INTO custom_devices (category, device_id, name, device_type, specs, source_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (category, device_id, name, device_type, json.dumps(specs), source_url))
        db.commit()
        return {"success": True, "device_id": device_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Device ID already exists"}


def update_custom_device(device_id, specs, source_url=None):
    """Update an existing custom device."""
    db = get_db()
    db.execute('''
        UPDATE custom_devices
        SET specs = ?, source_url = ?, updated_at = CURRENT_TIMESTAMP
        WHERE device_id = ?
    ''', (json.dumps(specs), source_url, device_id))
    db.commit()
    return {"success": True}


def delete_custom_device(device_id):
    """Delete a custom device from the database."""
    db = get_db()
    db.execute('DELETE FROM custom_devices WHERE device_id = ?', (device_id,))
    db.commit()
    return {"success": True}


# =============================================================================
# FFmpeg Path Finder (handles Windows winget installs)
# =============================================================================

def find_ffmpeg_tool(tool_name):
    """
    Find ffmpeg/ffprobe executable, checking common install locations.
    Returns the full path or None if not found.
    """
    # First try PATH
    path = shutil.which(tool_name)
    if path:
        return path

    # Windows-specific paths (winget, chocolatey, manual installs)
    if platform.system() == "Windows":
        windows_paths = [
            os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-*\bin\{tool_name}.exe"),
            os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Links\{tool_name}.exe"),
            rf"C:\ffmpeg\bin\{tool_name}.exe",
            rf"C:\Program Files\ffmpeg\bin\{tool_name}.exe",
            rf"C:\ProgramData\chocolatey\bin\{tool_name}.exe",
        ]
        import glob
        for pattern in windows_paths:
            matches = glob.glob(pattern)
            if matches:
                return matches[0]

    # macOS paths (homebrew)
    elif platform.system() == "Darwin":
        mac_paths = [
            f"/opt/homebrew/bin/{tool_name}",
            f"/usr/local/bin/{tool_name}",
        ]
        for p in mac_paths:
            if os.path.exists(p):
                return p

    # Linux paths
    else:
        linux_paths = [
            f"/usr/bin/{tool_name}",
            f"/usr/local/bin/{tool_name}",
            f"/snap/bin/{tool_name}",
        ]
        for p in linux_paths:
            if os.path.exists(p):
                return p

    return None


def get_ffprobe_path():
    """Get path to ffprobe executable."""
    return find_ffmpeg_tool("ffprobe")


def get_ffmpeg_path():
    """Get path to ffmpeg executable."""
    return find_ffmpeg_tool("ffmpeg")


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

    def set_setting(self, setting, value):
        """Set a single setting on the Vrroom."""
        response = self.send_command(f"set {setting} {value}")
        return response

    def apply_settings(self, settings_dict):
        """Apply multiple settings to the Vrroom. Returns results for each setting."""
        results = {}
        try:
            self.connect()
            for setting, value in settings_dict.items():
                try:
                    response = self.set_setting(setting, value)
                    results[setting] = {"success": True, "response": response}
                except Exception as e:
                    results[setting] = {"success": False, "error": str(e)}
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

    def backup_config(self, backup_path=None):
        """Backup all Vrroom settings to a JSON file."""
        try:
            self.connect()
            settings = self.get_all_settings()
            status = self.get_status()

            backup_data = {
                "vrroom_backup": True,
                "version": "1.0",
                "ip_address": self.ip_address,
                "timestamp": datetime.now().isoformat(),
                "settings": settings,
                "status_snapshot": status
            }

            if backup_path:
                with open(backup_path, "w") as f:
                    json.dump(backup_data, f, indent=2)

            return {"success": True, "backup": backup_data, "filepath": backup_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

    def detect_inputs(self):
        """Detect connected devices on Vrroom inputs by parsing status."""
        try:
            self.connect()
            detected = {
                "rx0": {"connected": False, "signal": None, "resolution": None},
                "rx1": {"connected": False, "signal": None, "resolution": None},
            }

            # Query input status
            for rx in ["rx0", "rx1"]:
                try:
                    response = self.send_command(f"get status {rx}")
                    if response and "no signal" not in response.lower():
                        detected[rx]["connected"] = True
                        detected[rx]["signal"] = response
                        # Try to parse resolution from response
                        # Typical format: "3840x2160p60 422 12b HDR BT2020 ..."
                        parts = response.split()
                        if parts:
                            detected[rx]["resolution"] = parts[0]
                except Exception:
                    pass

            # Also get input selection
            try:
                insel = self.send_command("get insel")
                detected["active_input"] = insel
            except Exception:
                detected["active_input"] = None

            return {"success": True, "inputs": detected}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

    def diagnose_hdr_signal_chain(self):
        """
        Diagnose HDR signal path through the Vrroom.
        Returns detailed info about HDR/DV status at each point in the chain.
        """
        try:
            self.connect()
            diagnosis = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "signal_chain": [],
                "hdr_status": {
                    "input": {"detected": False, "format": "SDR", "details": None},
                    "processing": {"lldv_active": False, "hdr_inject": False},
                    "output": {"format": "SDR", "details": None}
                },
                "settings": {},
                "issues": [],
                "recommendations": []
            }

            # 1. Query input status (what's coming from sources)
            for rx in ["rx0", "rx1"]:
                try:
                    response = self.send_command(f"get status {rx}")
                    if response and "no signal" not in response.lower():
                        signal_info = self._parse_signal_status(response, rx)
                        diagnosis["signal_chain"].append({
                            "stage": f"Input {rx.upper()}",
                            "type": "input",
                            "connected": True,
                            **signal_info
                        })
                        # Check if this input has HDR
                        if signal_info.get("hdr_format") != "SDR":
                            diagnosis["hdr_status"]["input"]["detected"] = True
                            diagnosis["hdr_status"]["input"]["format"] = signal_info.get("hdr_format", "SDR")
                            diagnosis["hdr_status"]["input"]["details"] = signal_info
                    else:
                        diagnosis["signal_chain"].append({
                            "stage": f"Input {rx.upper()}",
                            "type": "input",
                            "connected": False,
                            "raw": response
                        })
                except Exception as e:
                    diagnosis["signal_chain"].append({
                        "stage": f"Input {rx.upper()}",
                        "type": "input",
                        "error": str(e)
                    })

            # 2. Query SPD (Source Product Descriptor) info - contains HDR metadata
            for spd in ["spd0", "spd1"]:
                try:
                    response = self.send_command(f"get status {spd}")
                    if response:
                        diagnosis["signal_chain"].append({
                            "stage": f"SPD {spd[-1]}",
                            "type": "metadata",
                            "raw": response,
                            **self._parse_spd_status(response)
                        })
                except Exception:
                    pass

            # 3. Query output status (what's going to display/AVR)
            for tx in ["tx0", "tx1"]:
                try:
                    response = self.send_command(f"get status {tx}")
                    if response:
                        signal_info = self._parse_signal_status(response, tx)
                        diagnosis["signal_chain"].append({
                            "stage": f"Output {tx.upper()}",
                            "type": "output",
                            **signal_info
                        })
                        # Track output HDR format
                        if signal_info.get("hdr_format") != "SDR":
                            diagnosis["hdr_status"]["output"]["format"] = signal_info.get("hdr_format")
                            diagnosis["hdr_status"]["output"]["details"] = signal_info
                except Exception as e:
                    diagnosis["signal_chain"].append({
                        "stage": f"Output {tx.upper()}",
                        "type": "output",
                        "error": str(e)
                    })

            # 4. Query sink capabilities (what display/AVR can accept)
            for sink in ["tx0sink", "tx1sink"]:
                try:
                    response = self.send_command(f"get status {sink}")
                    if response:
                        diagnosis["signal_chain"].append({
                            "stage": f"Sink {sink[-5:-4].upper()}{sink[-4:]}",
                            "type": "sink",
                            "raw": response,
                            **self._parse_sink_capabilities(response)
                        })
                except Exception:
                    pass

            # 5. Query current EDID/HDR settings
            edid_settings = [
                "edidmode", "ediddvflag", "ediddvmode",
                "edidhdrflag", "edidhdrmode", "hdrcustom",
                "lldv", "hdrdisable"
            ]
            for setting in edid_settings:
                try:
                    value = self.get_setting(setting)
                    if value and value.lower() not in ["error", "unknown"]:
                        diagnosis["settings"][setting] = value
                except Exception:
                    pass

            # 6. Analyze the chain and generate issues/recommendations
            self._analyze_hdr_chain(diagnosis)

            return diagnosis

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ip_address": self.ip_address
            }
        finally:
            self.disconnect()

    def _parse_signal_status(self, response, port):
        """Parse signal status string to extract video format info."""
        info = {
            "raw": response,
            "resolution": None,
            "refresh_rate": None,
            "color_space": None,
            "bit_depth": None,
            "hdr_format": "SDR",
            "colorimetry": None
        }

        if not response:
            return info

        parts = response.upper().split()

        # Parse resolution (e.g., 3840x2160p60)
        for part in parts:
            res_match = re.match(r'(\d+)X(\d+)([PI])(\d+)', part)
            if res_match:
                info["resolution"] = f"{res_match.group(1)}x{res_match.group(2)}"
                info["refresh_rate"] = int(res_match.group(4))
                info["scan_type"] = "progressive" if res_match.group(3) == 'P' else "interlaced"
                break

        # Parse color space (422, 444, RGB)
        for part in parts:
            if part in ['422', '444', 'RGB', '420']:
                info["color_space"] = part
                break

        # Parse bit depth
        for part in parts:
            if re.match(r'\d+B', part):
                info["bit_depth"] = part
                break

        # Parse HDR format
        if 'DV' in parts or 'DOLBY' in response.upper():
            if 'LLDV' in response.upper():
                info["hdr_format"] = "LLDV"
            else:
                info["hdr_format"] = "Dolby Vision"
        elif 'HDR10+' in response.upper() or 'HDR10PLUS' in response.upper():
            info["hdr_format"] = "HDR10+"
        elif 'HDR10' in response.upper() or 'HDR' in parts:
            info["hdr_format"] = "HDR10"
        elif 'HLG' in parts:
            info["hdr_format"] = "HLG"
        else:
            info["hdr_format"] = "SDR"

        # Parse colorimetry (BT.2020, BT.709)
        if 'BT2020' in response.upper() or 'BT.2020' in response.upper():
            info["colorimetry"] = "BT.2020"
        elif 'BT709' in response.upper() or 'BT.709' in response.upper():
            info["colorimetry"] = "BT.709"

        return info

    def _parse_spd_status(self, response):
        """Parse SPD (Source Product Descriptor) status."""
        info = {
            "vendor": None,
            "product": None,
            "hdr_metadata": None
        }
        # SPD typically contains vendor/product info and HDR metadata
        if 'HDR' in response.upper():
            info["hdr_metadata"] = "HDR metadata present"
        if 'DV' in response.upper() or 'DOLBY' in response.upper():
            info["hdr_metadata"] = "Dolby Vision metadata"
        return info

    def _parse_sink_capabilities(self, response):
        """Parse sink (display/AVR) capabilities from status."""
        caps = {
            "hdr_capable": False,
            "dv_capable": False,
            "vrr_capable": False,
            "max_resolution": None,
            "supported_formats": []
        }

        upper = response.upper()
        if 'HDR' in upper:
            caps["hdr_capable"] = True
            caps["supported_formats"].append("HDR10")
        if 'HLG' in upper:
            caps["supported_formats"].append("HLG")
        if 'DV' in upper or 'DOLBY' in upper:
            caps["dv_capable"] = True
            caps["supported_formats"].append("Dolby Vision")
        if 'VRR' in upper:
            caps["vrr_capable"] = True

        return caps

    def _analyze_hdr_chain(self, diagnosis):
        """Analyze the HDR signal chain and generate issues/recommendations."""
        issues = []
        recommendations = []
        settings = diagnosis.get("settings", {})

        # Check if input has HDR but output is SDR
        input_hdr = diagnosis["hdr_status"]["input"]["format"]
        output_hdr = diagnosis["hdr_status"]["output"]["format"]

        if input_hdr != "SDR" and output_hdr == "SDR":
            issues.append({
                "severity": "critical",
                "title": "HDR Lost in Signal Chain",
                "description": f"Input signal is {input_hdr} but output is SDR. HDR is being stripped somewhere in the chain."
            })

            # Check EDID settings
            if settings.get("edidhdrflag", "").lower() == "off":
                recommendations.append({
                    "priority": "high",
                    "setting": "edidhdrflag",
                    "current": "off",
                    "recommended": "on",
                    "title": "Enable HDR EDID Flag",
                    "description": "The HDR flag is disabled in EDID. Enable it so sinks advertise HDR capability.",
                    "command": "#vrroom set edidhdrflag on",
                    "menu_path": "Vrroom Web UI > EDID > HDR FLAG"
                })

            if settings.get("hdrdisable", "").lower() == "on":
                recommendations.append({
                    "priority": "high",
                    "setting": "hdrdisable",
                    "current": "on",
                    "recommended": "off",
                    "title": "Disable HDR Disable Setting",
                    "description": "HDR is explicitly disabled. Turn this off to allow HDR passthrough.",
                    "command": "#vrroom set hdrdisable off",
                    "menu_path": "Vrroom Web UI > SIGNAL > HDR DISABLE"
                })

        # Check for Dolby Vision to LLDV conversion
        if input_hdr == "Dolby Vision":
            if settings.get("ediddvflag", "").lower() != "on":
                recommendations.append({
                    "priority": "medium",
                    "setting": "ediddvflag",
                    "current": settings.get("ediddvflag", "unknown"),
                    "recommended": "on",
                    "title": "Enable Dolby Vision EDID Flag",
                    "description": "DV flag should be enabled for proper LLDV conversion.",
                    "command": "#vrroom set ediddvflag on",
                    "menu_path": "Vrroom Web UI > EDID > DV FLAG"
                })

        # Check EDID mode
        edid_mode = settings.get("edidmode", "").lower()
        if edid_mode not in ["automix", "custom"]:
            recommendations.append({
                "priority": "medium",
                "setting": "edidmode",
                "current": edid_mode,
                "recommended": "automix",
                "title": "Use AutoMix EDID Mode",
                "description": "AutoMix is recommended for best compatibility with mixed HDR/SDR content.",
                "command": "#vrroom set edidmode automix",
                "menu_path": "Vrroom Web UI > EDID > MODE"
            })

        # Check for no signal issues
        no_input = all(
            s.get("connected") == False
            for s in diagnosis["signal_chain"]
            if s.get("type") == "input"
        )
        if no_input:
            issues.append({
                "severity": "warning",
                "title": "No Input Signal Detected",
                "description": "No active input signal detected. Check source connections."
            })

        diagnosis["issues"] = issues
        diagnosis["recommendations"] = recommendations

    def get_all_settings_detailed(self):
        """Get all settings with their current values and metadata for UI display."""
        try:
            self.connect()
            settings_list = []

            # Extended list of queryable settings
            all_settings = [
                "opmode", "insel", "autosw", "edidmode",
                "ediddvflag", "ediddvmode", "edidhdrflag", "edidhdrmode",
                "edidvrrflag", "edidallmflag", "edidfrlflag", "edidfrlmode",
                "hdrcustom", "hdrdisable", "vrr", "allm", "frl",
                "earc", "earcforce", "audioout", "unmutedelay",
                "downscale", "cec", "hdcp", "oled", "oledfade",
                "jvcmacro", "edidtruehdflag", "edidtruehdmode",
                "edidddflag", "edidddplusflag", "ediddtsflag", "ediddtshdflag",
                "edidpcmflag", "edidpcmchmode"
            ]

            for setting in all_settings:
                try:
                    value = self.get_setting(setting)
                    if value and value.lower() not in ["error", "unknown", ""]:
                        meta = VRROOM_SETTINGS_META.get(setting, {})
                        settings_list.append({
                            "key": setting,
                            "value": value,
                            "name": meta.get("name", setting),
                            "menu_path": meta.get("menu_path", "Vrroom Web UI"),
                            "tab": meta.get("tab", "Settings"),
                            "description": meta.get("description", ""),
                            "values": meta.get("values", {}),
                            "can_modify": True
                        })
                except Exception:
                    continue

            return {"success": True, "settings": settings_list}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()


# =============================================================================
# Device Manuals Database
# =============================================================================

DEVICE_MANUALS = {
    # Projectors
    "epson_eh_ls12000b": {
        "manual_url": "https://files.support.epson.com/docid/cpd5/cpd59971.pdf",
        "quick_start_url": "https://files.support.epson.com/docid/cpd5/cpd59972.pdf",
        "settings_screenshots": {
            "hdmi_signal": "/static/manuals/epson_ls12000b_hdmi_signal.png",
            "hdr_setting": "/static/manuals/epson_ls12000b_hdr.png"
        }
    },
    "jvc_dla_nz8": {
        "manual_url": "https://www.jvc.com/usa/projectors/instruction-manual/",
        "settings_screenshots": {}
    },
    # AVRs
    "yamaha_rx_a4a": {
        "manual_url": "https://usa.yamaha.com/files/download/other_assets/7/1324417/RX-A4A_A6A_A8A_om_U_En.pdf",
        "quick_start_url": "https://usa.yamaha.com/files/download/other_assets/7/1324418/RX-A4A_A6A_A8A_qg_U_En.pdf",
        "settings_screenshots": {
            "hdmi_enhanced": "/static/manuals/yamaha_rxa4a_hdmi_enhanced.png",
            "ypao": "/static/manuals/yamaha_rxa4a_ypao.png"
        }
    },
    "denon_avr_x3800h": {
        "manual_url": "https://manuals.denon.com/AVRX3800H/NA/EN/",
        "settings_screenshots": {}
    },
    # Sources
    "nvidia_shield_pro": {
        "manual_url": "https://www.nvidia.com/en-us/shield/support/shield-tv/",
        "settings_screenshots": {
            "display_settings": "/static/manuals/shield_display_settings.png",
            "match_content": "/static/manuals/shield_match_content.png"
        }
    },
    "apple_tv_4k": {
        "manual_url": "https://support.apple.com/guide/tv/welcome/tvos",
        "settings_screenshots": {}
    },
    "xbox_series_x": {
        "manual_url": "https://support.xbox.com/help/hardware-network/console/xbox-series-x-s-manual",
        "settings_screenshots": {
            "video_modes": "/static/manuals/xbox_video_modes.png"
        }
    },
    "ps5": {
        "manual_url": "https://manuals.playstation.net/document/en/ps5/",
        "settings_screenshots": {}
    },
    # HDMI Processors
    "vrroom": {
        "manual_url": "https://www.hdfury.com/docs/HDfuryVRRoom.pdf",
        "firmware_url": "https://www.hdfury.com/firmware/",
        "settings_screenshots": {
            "edid_tab": "/static/manuals/vrroom_edid_tab.png",
            "signal_tab": "/static/manuals/vrroom_signal_tab.png",
            "audio_tab": "/static/manuals/vrroom_audio_tab.png"
        }
    }
}


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
            "qms_support": False,  # QMS (Quick Media Switching) - HDMI 2.1 feature that eliminates bonk
            "light_source": "laser",
            "light_output_lumens": 2700,
            "native_contrast": "2500000:1",
            "panel_tech": "3LCD with 4K PRO-UHD",
            "lens_shift": True,
            "lens_memory": True,
            "lens_memory_slots": 10,
            "hdmi_inputs": 2,
            "config_paths": {
                "picture_mode": "Menu > Image > Color Mode",
                "hdr_setting": "Menu > Image > HDR > HDR10 Setting",
                "brightness": "Menu > Image > Brightness",
                "contrast": "Menu > Image > Contrast",
                "color_temp": "Menu > Image > White Balance > Color Temp.",
                "gamma": "Menu > Image > Gamma",
                "hdmi_signal": "Menu > Signal I/O > HDMI IN > EDID > Expanded",
                "frame_interp": "Menu > Image > Image Enhancement > Frame Interpolation",
                "aspect_ratio": "Menu > Signal I/O > Signal > Aspect",
                "lens_memory": "Menu > Settings > Lens Position > Memory > Load",
                "power_mode": "Menu > Settings > Operation > Light Source Mode",
                "auto_iris": "Not available (laser model)",
            },
            "recommended_settings": {
                "color_mode_sdr": "Natural",
                "color_mode_hdr": "HDR10 (Auto) or Cinema",
                "gamma_sdr": "Custom (2.2-2.4 depending on room darkness)",
                "gamma_hdr": "HDR10 auto-curves",
                "hdr10_dynamic_range": "Auto or 16 (for 100-nit room)",
                "frame_interpolation": "Off (for film purists) or Low (for smoothing)",
                "color_temp": "6500K / D65",
                "hdmi_signal_format": "Expanded (required for 4K HDR)",
                "light_source_mode": "Custom (dim for dark room, bright for some ambient)",
                "aspect_ratio": "Auto (16:9 content) or Anamorphic (with lens memory for scope)",
            },
            "notes": "Use LLDV for Dolby Vision content. Native HDR10 support excellent. Laser light source with 2700 lumens."
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
            "light_source": "laser",
            "panel_tech": "D-ILA (native 4K)",
            "lens_shift": True,
            "lens_memory": True,
            "config_paths": {
                "picture_mode": "Menu > Picture > Picture Mode",
                "hdr_setting": "Menu > Picture > HDR Setting > HDR Level",
                "gamma": "Menu > Picture > Gamma",
                "hdmi_signal": "Menu > Input/Output > HDMI > Input Level",
                "frame_interp": "Menu > Picture > Motion Enhance > Clear Motion Drive",
                "lens_memory": "Menu > Installation > Lens Control > Lens Memory",
            },
            "recommended_settings": {
                "color_mode_sdr": "Natural",
                "color_mode_hdr": "Frame Adapt HDR",
                "gamma_hdr": "Frame Adapt HDR auto-tone mapping",
                "frame_interpolation": "Off or Low",
                "hdmi_signal_format": "Auto (supports up to 48Gbps)",
            },
            "notes": "Excellent tone mapping via Frame Adapt HDR. Consider RS232 macros for lens memory."
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
            "light_source": "laser",
            "panel_tech": "D-ILA (e-Shift 4K)",
            "lens_shift": True,
            "lens_memory": True,
            "config_paths": {
                "picture_mode": "Menu > Picture > Picture Mode",
                "hdr_setting": "Menu > Picture > HDR Setting > HDR Level",
                "gamma": "Menu > Picture > Gamma",
                "hdmi_signal": "Menu > Input/Output > HDMI > Input Level",
                "frame_interp": "Menu > Picture > Motion Enhance > Clear Motion Drive",
                "lens_memory": "Menu > Installation > Lens Control > Lens Memory",
            },
            "recommended_settings": {
                "color_mode_hdr": "Frame Adapt HDR",
                "frame_interpolation": "Off or Low",
            },
            "notes": "E-shift 4K. Good candidate for LLDV via Vrroom. Frame Adapt HDR tone mapping."
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
            "light_source": "laser",
            "panel_tech": "SXRD (native 4K)",
            "lens_shift": True,
            "lens_memory": True,
            "config_paths": {
                "picture_mode": "Menu > Image > Preset",
                "hdr_setting": "Menu > Image > HDR > HDR Tone Mapping",
                "gamma": "Menu > Image > Gamma Correction",
                "hdmi_signal": "Menu > Setup > HDMI > HDMI Signal Format > Enhanced",
                "frame_interp": "Menu > Image > Motionflow",
                "lens_memory": "Menu > Installation > Lens Position",
            },
            "recommended_settings": {
                "color_mode_hdr": "Reference or Cinema Film 1",
                "frame_interpolation": "Off",
                "hdmi_signal_format": "Enhanced (required for 4K HDR)",
            },
            "notes": "Native 4K SXRD panel. Fast HDMI handshake. Good HDR tone mapping."
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
            "qms_support": True,  # QMS eliminates bonk - no HDMI processor needed for frame rate switching
            "notes": "Native DV support. QMS support eliminates bonk without HDMI processor."
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
        },
        # Samsung TVs
        "samsung_qn70f_75": {
            "name": "Samsung 75\" Neo QLED QN70F (QA75QN70FAWXXY)",
            "type": "tv",
            "native_dv": False,
            "lldv_compatible": False,
            "max_resolution": "4K",
            "max_refresh": 144,
            "hdr_support": ["HDR10", "HDR10+", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 1500,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "freesync": "FreeSync Premium Pro",
            "earc_support": True,
            "hdmi_ports": 4,
            "panel_tech": "Neo QLED Mini LED",
            "processor": "NQ4 AI Gen2",
            "speakers_watts": 20,
            "speakers_config": "2.0",
            "smart_platform": "Tizen",
            "config_paths": {
                "picture_mode": {
                    "path": "Settings > All Settings > Picture > Picture Mode",
                    "steps": [
                        "Press the Settings button (gear icon) on remote",
                        "Select 'All Settings' at bottom of Quick Settings menu",
                        "Navigate to 'Picture' tab on left sidebar",
                        "Select 'Picture Mode' at top of Picture settings",
                        "Choose: Movie, Filmmaker Mode, or Dynamic"
                    ],
                    "tab": "Picture",
                    "recommended": "Movie or Filmmaker Mode (for accurate colors)"
                },
                "hdr_tone_mapping": {
                    "path": "Settings > All Settings > Picture > Expert Settings > HDR Tone Mapping",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Picture' tab",
                        "Scroll down to 'Expert Settings'",
                        "Select 'HDR Tone Mapping'",
                        "Choose: Standard, Static, or Dynamic"
                    ],
                    "tab": "Picture > Expert Settings",
                    "recommended": "Standard (most accurate to mastering)"
                },
                "input_signal_plus": {
                    "path": "Settings > All Settings > Connection > External Device Manager > Input Signal Plus",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Connection' tab on left sidebar",
                        "Select 'External Device Manager'",
                        "Select 'Input Signal Plus'",
                        "Enable for each HDMI port you use (HDMI 1, 2, 3, 4)",
                        "This enables 4K@120Hz, HDR10, HDR10+, and VRR"
                    ],
                    "tab": "Connection > External Device Manager",
                    "recommended": "On for all HDMI ports with 4K sources",
                    "critical": True
                },
                "game_mode": {
                    "path": "Settings > All Settings > Connection > Game Mode Settings > Game Mode",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Connection' tab",
                        "Select 'Game Mode Settings'",
                        "Toggle 'Game Mode' On or Off",
                        "Or set to 'Auto' to use ALLM detection"
                    ],
                    "tab": "Connection > Game Mode Settings",
                    "recommended": "Auto (uses ALLM from gaming sources)"
                },
                "vrr": {
                    "path": "Settings > All Settings > Connection > Game Mode Settings > VRR",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Connection' tab",
                        "Select 'Game Mode Settings'",
                        "Toggle 'VRR' On",
                        "Supports FreeSync Premium Pro up to 144Hz"
                    ],
                    "tab": "Connection > Game Mode Settings",
                    "recommended": "On"
                },
                "allm": {
                    "path": "Settings > All Settings > Connection > Game Mode Settings > Auto Game Mode (ALLM)",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Connection' tab",
                        "Select 'Game Mode Settings'",
                        "Toggle 'Auto Game Mode' On",
                        "TV will auto-switch to Game Mode when console sends ALLM signal"
                    ],
                    "tab": "Connection > Game Mode Settings",
                    "recommended": "On"
                },
                "sound_output": {
                    "path": "Settings > All Settings > Sound > Sound Output",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Sound' tab on left sidebar",
                        "Select 'Sound Output' at top",
                        "Choose: TV Speaker, Soundbar, Receiver, or Bluetooth"
                    ],
                    "tab": "Sound",
                    "recommended": "TV Speaker (for standalone setup)"
                },
                "sound_mode": {
                    "path": "Settings > All Settings > Sound > Sound Mode",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Sound' tab",
                        "Select 'Sound Mode'",
                        "Choose: Standard, Adaptive Sound, Amplify, or Custom"
                    ],
                    "tab": "Sound",
                    "recommended": "Adaptive Sound (auto-adjusts to content)"
                },
                "earc": {
                    "path": "Settings > All Settings > Connection > External Device Manager > HDMI eARC Mode",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Connection' tab",
                        "Select 'External Device Manager'",
                        "Select 'HDMI eARC Mode'",
                        "Set to 'Auto' to enable eARC when soundbar/AVR connected"
                    ],
                    "tab": "Connection > External Device Manager",
                    "recommended": "Auto"
                },
                "picture_clarity": {
                    "path": "Settings > All Settings > Picture > Expert Settings > Picture Clarity Settings",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Picture' tab",
                        "Scroll to 'Expert Settings'",
                        "Select 'Picture Clarity Settings'",
                        "Adjust Blur Reduction and Judder Reduction"
                    ],
                    "tab": "Picture > Expert Settings",
                    "recommended": "Blur Reduction: Off, Judder Reduction: Off (for cinema)"
                },
                "local_dimming": {
                    "path": "Settings > All Settings > Picture > Expert Settings > Local Dimming",
                    "steps": [
                        "Press Settings button on remote",
                        "Select 'All Settings'",
                        "Go to 'Picture' tab",
                        "Scroll to 'Expert Settings'",
                        "Select 'Local Dimming'",
                        "Choose: High, Standard, or Low"
                    ],
                    "tab": "Picture > Expert Settings",
                    "recommended": "High (for best HDR contrast)"
                }
            },
            "recommended_settings": {
                "picture_mode_sdr": "Movie or Filmmaker Mode",
                "picture_mode_hdr": "HDR Movie or Filmmaker Mode",
                "game_mode": "Auto (for automatic ALLM detection)",
                "input_signal_plus": "On (REQUIRED for 4K HDR/VRR - enable per HDMI port)",
                "vrr": "On",
                "allm": "On",
                "hdr_tone_mapping": "Standard",
                "local_dimming": "High",
                "blur_reduction": "Off",
                "judder_reduction": "Off (for 24p film content)"
            },
            "standalone_settings": {
                "sound_output": "TV Speaker",
                "sound_mode": "Adaptive Sound (auto-adjusts to content type)",
                "equalizer": "Custom: Boost bass +2, Treble 0",
                "auto_volume": "On (normalizes volume between apps)",
                "dialogue_clarity": "On (if available)",
                "night_mode": "On (for late viewing - compresses dynamics)"
            },
            "media_server_settings": {
                "plex": {
                    "quality": "Maximum (for direct play)",
                    "direct_play": "Enabled",
                    "allow_insecure": "Same network only",
                    "subtitles": "Burn-in if needed (avoids transcoding)"
                },
                "emby": {
                    "playback_quality": "Direct play preferred",
                    "max_streaming_bitrate": "No limit",
                    "enable_hdr": "On"
                },
                "jellyfin": {
                    "playback_quality": "Auto",
                    "prefer_direct_play": "On",
                    "enable_hdr": "On"
                }
            },
            "notes": "No Dolby Vision support - Samsung uses HDR10+. Enable Input Signal Plus for full 4K HDR (this is CRITICAL - TV won't display HDR without it). VRR up to 4K@144Hz with FreeSync Premium Pro. For Plex/Emby/Jellyfin: ensure Direct Play is enabled to avoid transcoding.",
            "first_time_setup": [
                "1. Enable Input Signal Plus for each HDMI port (Connection > External Device Manager)",
                "2. Set Picture Mode to Movie or Filmmaker Mode",
                "3. Enable Game Mode settings (VRR, ALLM) if using gaming sources",
                "4. For standalone audio: Set Sound Mode to Adaptive Sound",
                "5. Install Plex/Emby/Jellyfin from Samsung App Store",
                "6. Configure media server app for Direct Play (no transcoding)"
            ]
        },
        "samsung_qn95c": {
            "name": "Samsung QN95C Neo QLED",
            "type": "tv",
            "native_dv": False,
            "lldv_compatible": False,
            "max_resolution": "4K",
            "max_refresh": 144,
            "hdr_support": ["HDR10", "HDR10+", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 1400,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "freesync": "FreeSync Premium Pro",
            "earc_support": True,
            "panel_tech": "Neo QLED Mini LED",
            "notes": "Flagship Neo QLED. No DV - use HDR10+. One Connect Box separates inputs."
        },
        "samsung_s95d_oled": {
            "name": "Samsung S95D QD-OLED",
            "type": "tv",
            "native_dv": False,
            "lldv_compatible": False,
            "max_resolution": "4K",
            "max_refresh": 144,
            "hdr_support": ["HDR10", "HDR10+", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 1300,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "panel_tech": "QD-OLED",
            "notes": "Samsung QD-OLED. Excellent HDR peak brightness. No DV support."
        },
        # LG TVs
        "lg_c4_oled": {
            "name": "LG C4 OLED",
            "type": "tv",
            "native_dv": True,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 144,
            "hdr_support": ["HDR10", "HLG", "Dolby Vision"],
            "hdcp": "2.3",
            "handshake_time_ms": 1400,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "earc_support": True,
            "panel_tech": "WOLED",
            "notes": "Native DV support. VRR up to 4K@144Hz. webOS smart platform."
        },
        "lg_c2_oled": {
            "name": "LG C2 OLED",
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
            "qms_support": True,  # QMS eliminates bonk natively
            "earc_support": True,
            "panel_tech": "WOLED evo",
            "notes": "Native DV. QMS support. Popular gaming OLED with 4x HDMI 2.1 ports."
        },
        "lg_c1_oled": {
            "name": "LG C1 OLED",
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
            "earc_support": True,
            "panel_tech": "WOLED",
            "notes": "Native DV. Older but still excellent OLED. Good HDFury EDID reference."
        },
        "lg_g4_oled": {
            "name": "LG G4 OLED",
            "type": "tv",
            "native_dv": True,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 144,
            "hdr_support": ["HDR10", "HLG", "Dolby Vision"],
            "hdcp": "2.3",
            "handshake_time_ms": 1300,
            "recommended_edid": "automix",
            "vrr_support": True,
            "allm_support": True,
            "earc_support": True,
            "panel_tech": "MLA WOLED",
            "notes": "LG Gallery OLED with MLA technology. Brightest LG OLED. Native DV."
        },
        # Sony TVs
        "sony_a95k_oled": {
            "name": "Sony A95K QD-OLED",
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
            "earc_support": True,
            "panel_tech": "QD-OLED",
            "notes": "Sony QD-OLED with Cognitive Processor XR. Excellent DV tone mapping."
        },
        "sony_x95l": {
            "name": "Sony X95L Mini LED",
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
            "panel_tech": "Mini LED LCD",
            "notes": "Sony flagship Mini LED. Native DV. Google TV platform."
        },
        # More projectors
        "benq_w5800": {
            "name": "BenQ W5800",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "hdr_support": ["HDR10", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 2800,
            "recommended_edid": "automix",
            "vrr_support": False,
            "allm_support": False,
            "light_source": "laser",
            "panel_tech": "DLP",
            "notes": "BenQ laser projector. Use LLDV for DV content."
        },
        "optoma_uhz50": {
            "name": "Optoma UHZ50",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "hdr_support": ["HDR10", "HLG"],
            "hdcp": "2.3",
            "handshake_time_ms": 2500,
            "recommended_edid": "automix",
            "vrr_support": False,
            "allm_support": False,
            "light_source": "laser",
            "panel_tech": "DLP",
            "notes": "Optoma laser 4K projector. Good for LLDV conversion."
        },
        "sony_vpl_xw5000": {
            "name": "Sony VPL-XW5000ES",
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
            "light_source": "laser",
            "panel_tech": "SXRD (native 4K)",
            "notes": "Entry Sony native 4K laser. Excellent for LLDV."
        },
        "jvc_dla_nz9": {
            "name": "JVC DLA-NZ9",
            "type": "projector",
            "native_dv": False,
            "lldv_compatible": True,
            "max_resolution": "8K",
            "max_refresh": 60,
            "hdr_support": ["HDR10", "HLG", "HDR10+"],
            "hdcp": "2.3",
            "handshake_time_ms": 3200,
            "recommended_edid": "automix",
            "vrr_support": False,
            "allm_support": False,
            "light_source": "laser",
            "panel_tech": "D-ILA (8K e-shift)",
            "lens_memory": True,
            "notes": "JVC flagship with 8K e-shift. Frame Adapt HDR. Best candidate for LLDV."
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
        },
        # ========== ESP32 / DIY HDMI Alternatives ==========
        "esp32_vrr_injector": {
            "name": "ESP32 VRR Injector",
            "type": "diy_hdmi",
            "inputs": 1,
            "outputs": 1,
            "lldv_support": False,
            "vrr_support": True,
            "allm_support": True,
            "earc_support": False,
            "edid_modes": ["custom"],
            "custom_edid_slots": 1,
            "max_resolution": "4K",
            "max_refresh": 120,
            "project_url": "https://github.com/Mrcuve0/VRR-Mod",
            "notes": "DIY VRR injection for non-VRR displays. Requires soldering/assembly. Community project."
        },
        "esp32_edid_injector": {
            "name": "ESP32 EDID Injector",
            "type": "diy_hdmi",
            "inputs": 1,
            "outputs": 1,
            "lldv_support": False,
            "vrr_support": False,
            "allm_support": False,
            "earc_support": False,
            "edid_modes": ["custom"],
            "custom_edid_slots": 1,
            "max_resolution": "4K",
            "max_refresh": 60,
            "project_url": "https://github.com/topics/edid-emulator",
            "notes": "DIY EDID emulator. Fixes EDID handshake issues. Low cost alternative to HDFury."
        },
        "thinklogical_tldp": {
            "name": "Thinklogical EDID Emulator",
            "type": "edid_emulator",
            "inputs": 1,
            "outputs": 1,
            "lldv_support": False,
            "vrr_support": False,
            "allm_support": False,
            "earc_support": False,
            "edid_modes": ["custom"],
            "notes": "Commercial EDID emulator. Stores custom EDID. Simpler than HDFury."
        },
        "gofanco_edid_emulator": {
            "name": "gofanco EDID Emulator",
            "type": "edid_emulator",
            "inputs": 1,
            "outputs": 1,
            "lldv_support": False,
            "vrr_support": False,
            "allm_support": False,
            "earc_support": False,
            "edid_modes": ["custom", "passthrough"],
            "notes": "Budget EDID emulator. 4K60 passthrough. Stores 1 custom EDID."
        },
        "avr_key": {
            "name": "HDFury AVR-Key",
            "type": "hdfury",
            "inputs": 1,
            "outputs": 1,
            "lldv_support": True,
            "vrr_support": False,
            "allm_support": False,
            "earc_support": False,
            "edid_modes": ["automix", "custom"],
            "custom_edid_slots": 10,
            "notes": "HDMI audio extractor with LLDV injection. Good for older AVRs."
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
            "max_channels": "9.2",
            "amplifier_channels": 9,
            "room_correction": "YPAO",
            "room_correction_mic": "YPAO microphone (included)",
            "dirac_support": False,
            "config_paths": {
                "speaker_setup": {
                    "path": "Setup > Speaker > Manual Setup > Configuration",
                    "steps": [
                        "Press SETUP button on remote or front panel",
                        "Navigate to 'Speaker' using arrow keys",
                        "Select 'Manual Setup'",
                        "Select 'Configuration'",
                        "Set each speaker position: Front L/R, Center, Surround L/R, etc.",
                        "Options: Large, Small, or None for each position"
                    ],
                    "menu_button": "SETUP",
                    "tab": "Speaker > Manual Setup",
                    "recommended": "Set based on speaker size - Small for bookshelf, Large for floorstanders"
                },
                "crossover": {
                    "path": "Setup > Speaker > Manual Setup > Crossover",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'Speaker' > 'Manual Setup'",
                        "Select 'Crossover'",
                        "Set crossover frequency for each speaker set to 'Small'",
                        "Options: 40Hz, 60Hz, 80Hz, 90Hz, 100Hz, 110Hz, 120Hz, 150Hz, 200Hz"
                    ],
                    "menu_button": "SETUP",
                    "tab": "Speaker > Manual Setup",
                    "recommended": "80Hz for most bookshelf speakers, 60Hz for larger speakers"
                },
                "distance": {
                    "path": "Setup > Speaker > Manual Setup > Distance",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'Speaker' > 'Manual Setup'",
                        "Select 'Distance'",
                        "Measure distance from each speaker to listening position",
                        "Enter distance for each speaker (in feet or meters)",
                        "Use a tape measure for accuracy"
                    ],
                    "menu_button": "SETUP",
                    "tab": "Speaker > Manual Setup",
                    "recommended": "Measure accurately - this affects time alignment"
                },
                "level": {
                    "path": "Setup > Speaker > Manual Setup > Level",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'Speaker' > 'Manual Setup'",
                        "Select 'Level'",
                        "Use test tones and SPL meter",
                        "Adjust each speaker to same level (75dB reference)",
                        "Range: -10.0dB to +10.0dB in 0.5dB steps"
                    ],
                    "menu_button": "SETUP",
                    "tab": "Speaker > Manual Setup",
                    "recommended": "Use SPL meter app, aim for 75dB at listening position"
                },
                "ypao": {
                    "path": "Setup > Speaker > YPAO",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'Speaker'",
                        "Select 'YPAO'",
                        "Connect YPAO microphone to front panel YPAO jack",
                        "Place microphone at ear height at listening position",
                        "Select 'Start' and leave the room",
                        "Wait for measurement to complete (several minutes)",
                        "Review and save results"
                    ],
                    "menu_button": "SETUP",
                    "tab": "Speaker",
                    "recommended": "Run YPAO for automatic room correction. See Speaker Tuning guide."
                },
                "surround_decode": {
                    "path": "Sound > Surround Decoder",
                    "steps": [
                        "Press SOUND button on remote",
                        "Navigate to 'Surround Decoder'",
                        "Select decoder mode for stereo content",
                        "Options: DTS Neural:X, Dolby Surround, CINEMA DSP, etc."
                    ],
                    "menu_button": "SOUND",
                    "tab": "Surround Decoder",
                    "recommended": "DTS Neural:X or Dolby Surround for upmixing stereo to surround"
                },
                "hdmi_audio": {
                    "path": "Setup > HDMI > Audio Output",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'HDMI'",
                        "Select 'Audio Output'",
                        "Options: Amp (receiver speakers), TV (TV speakers), or TV+Amp (both)"
                    ],
                    "menu_button": "SETUP",
                    "tab": "HDMI",
                    "recommended": "Amp (processes audio through receiver)"
                },
                "earc": {
                    "path": "Setup > HDMI > HDMI Control > ARC",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'HDMI'",
                        "Select 'HDMI Control'",
                        "Enable 'HDMI Control' first",
                        "Set 'ARC' to On",
                        "Connect TV to HDMI OUT (ARC) port on receiver",
                        "Enable eARC/ARC on TV as well"
                    ],
                    "menu_button": "SETUP",
                    "tab": "HDMI > HDMI Control",
                    "recommended": "On - enables eARC for lossless audio from TV apps"
                },
                "4k_passthrough": {
                    "path": "Setup > HDMI > 4K Signal Format",
                    "steps": [
                        "Press SETUP button on remote",
                        "Navigate to 'HDMI'",
                        "Select '4K Signal Format'",
                        "Set to 'Mode 1' for 4K/60Hz 4:4:4 and 4K/120Hz",
                        "Or 'Mode 2' for maximum compatibility"
                    ],
                    "menu_button": "SETUP",
                    "tab": "HDMI",
                    "recommended": "Mode 1 (8K/4K 120Hz) for full HDMI 2.1 features"
                }
            },
            "recommended_settings": {
                "speaker_config": "Set based on actual speakers (Small with crossover for most)",
                "crossover": "80Hz for bookshelf, 60Hz for floorstanders",
                "ypao": "Run YPAO automatic calibration",
                "4k_signal_format": "Mode 1 (for 4K@120Hz, VRR)",
                "hdmi_control": "On (enables CEC/ARC)",
                "arc": "On (for TV audio return)",
                "audio_output": "Amp"
            },
            "notes": "Good HDMI 2.1 passthrough. Use eARC for best audio from TV apps. YPAO room correction included - run after speaker setup."
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
            "max_channels": "11.2",
            "amplifier_channels": 11,
            "room_correction": "YPAO",
            "room_correction_mic": "YPAO microphone (included)",
            "dirac_support": False,
            "config_paths": {
                "speaker_setup": "Setup > Speaker > Manual Setup > Configuration",
                "crossover": "Setup > Speaker > Manual Setup > Crossover",
                "distance": "Setup > Speaker > Manual Setup > Distance",
                "level": "Setup > Speaker > Manual Setup > Level",
                "room_correction": "Setup > Speaker > YPAO",
                "surround_decode": "Sound > Surround Decoder",
                "hdmi_audio": "Setup > HDMI > Audio Output",
                "earc": "Setup > HDMI > HDMI Control > ARC",
            },
            "notes": "Flagship Yamaha. 11.2ch processing with HDMI 2.1. YPAO room correction."
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
            "max_channels": "9.4",
            "amplifier_channels": 9,
            "room_correction": "Audyssey MultEQ XT32",
            "room_correction_mic": "Audyssey microphone (included)",
            "dirac_support": True,
            "config_paths": {
                "speaker_setup": "Setup > Speakers > Manual Setup > Speaker Config",
                "crossover": "Setup > Speakers > Manual Setup > Crossovers",
                "distance": "Setup > Speakers > Manual Setup > Distances",
                "level": "Setup > Speakers > Manual Setup > Levels",
                "room_correction": "Setup > Speakers > Audyssey Setup",
                "surround_decode": "Setup > Surround Parameter > Surround Parameter",
                "hdmi_audio": "Setup > HDMI Setup > Audio Output",
                "earc": "Setup > HDMI Setup > eARC",
            },
            "notes": "Excellent HDMI 2.1. Audyssey XT32 room correction. Dirac Live upgrade available."
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
            "max_channels": "11.4",
            "amplifier_channels": 11,
            "room_correction": "Audyssey MultEQ XT32",
            "room_correction_mic": "Audyssey microphone (included)",
            "dirac_support": True,
            "config_paths": {
                "speaker_setup": "Setup > Speakers > Manual Setup > Speaker Config",
                "crossover": "Setup > Speakers > Manual Setup > Crossovers",
                "distance": "Setup > Speakers > Manual Setup > Distances",
                "level": "Setup > Speakers > Manual Setup > Levels",
                "room_correction": "Setup > Speakers > Audyssey Setup",
                "surround_decode": "Setup > Surround Parameter > Surround Parameter",
                "hdmi_audio": "Setup > HDMI Setup > Audio Output",
                "earc": "Setup > HDMI Setup > eARC",
            },
            "notes": "11.4ch processing. Dirac Live ready. Audyssey XT32 included."
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
            "max_channels": "9.4",
            "amplifier_channels": 9,
            "room_correction": "Audyssey MultEQ XT32",
            "room_correction_mic": "Audyssey microphone (included)",
            "dirac_support": True,
            "config_paths": {
                "speaker_setup": "Setup > Speakers > Manual Setup > Speaker Config",
                "crossover": "Setup > Speakers > Manual Setup > Crossovers",
                "distance": "Setup > Speakers > Manual Setup > Distances",
                "level": "Setup > Speakers > Manual Setup > Levels",
                "room_correction": "Setup > Speakers > Audyssey Setup",
                "surround_decode": "Setup > Surround Parameter > Surround Parameter",
                "hdmi_audio": "Setup > HDMI Setup > Audio Output",
                "earc": "Setup > HDMI Setup > eARC",
            },
            "notes": "Premium audio processing. Same HDMI board as Denon. Audyssey XT32 + Dirac available."
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
            "max_channels": "15.2",
            "amplifier_channels": 7,
            "room_correction": "ARC Genesis",
            "room_correction_mic": "ARC Genesis microphone (included)",
            "dirac_support": False,
            "config_paths": {
                "speaker_setup": "Settings > Speaker Configuration > Speaker Setup",
                "crossover": "Settings > Speaker Configuration > Bass Management",
                "distance": "Settings > Speaker Configuration > Speaker Distances",
                "level": "Settings > Speaker Configuration > Speaker Levels",
                "room_correction": "Settings > ARC Genesis > Run ARC",
                "surround_decode": "Settings > Decoder Settings",
                "hdmi_audio": "Settings > Audio > HDMI Audio",
                "earc": "Settings > Audio > eARC",
            },
            "notes": "Premium processor with ARC Genesis room correction. Excellent measurement-based EQ."
        },
        "sony_str_an1000": {
            "name": "Sony STR-AN1000",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 550,
            "recommended_audio_mode": "earc",
            "max_channels": "7.1.2",
            "amplifier_channels": 7,
            "room_correction": "D.C.A.C. IX",
            "room_correction_mic": "Sony measurement microphone (included)",
            "notes": "Sony budget HDMI 2.1 AVR. 360 Spatial Sound Mapping available. Good value."
        },
        "denon_avr_x6800h": {
            "name": "Denon AVR-X6800H",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 550,
            "recommended_audio_mode": "earc",
            "max_channels": "11.4",
            "amplifier_channels": 11,
            "room_correction": "Audyssey MultEQ XT32",
            "dirac_support": True,
            "notes": "Flagship Denon. 11 channels of amplification. Dirac Live included."
        },
        "marantz_cinema_60": {
            "name": "Marantz Cinema 60",
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
            "max_channels": "11.4",
            "amplifier_channels": 9,
            "room_correction": "Audyssey MultEQ XT32",
            "dirac_support": True,
            "notes": "Premium Marantz. Audiophile sound quality. Audyssey XT32 + Dirac."
        },
        "onkyo_tx_rz70": {
            "name": "Onkyo TX-RZ70",
            "type": "avr",
            "earc_support": True,
            "atmos_support": True,
            "dtsx_support": True,
            "passthrough_4k120": True,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "handshake_time_ms": 650,
            "recommended_audio_mode": "earc",
            "max_channels": "11.2",
            "amplifier_channels": 11,
            "room_correction": "Dirac Live",
            "notes": "Flagship Onkyo. THX Certified. Dirac Live included."
        },
        "integra_drx_8_4": {
            "name": "Integra DRX-8.4",
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
            "max_channels": "11.4",
            "amplifier_channels": 11,
            "room_correction": "Dirac Live",
            "notes": "Premium Integra. Custom integrator focused. Dirac Live included."
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
            "qms_support": True,  # Supports QMS for seamless refresh rate switching
            "vrr_support": True,
            "allm_support": True,
            "notes": "Gaming source with QMS. Enable VRR/ALLM for best gaming experience."
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
            "qms_support": True,  # Supports QMS for seamless refresh rate switching
            "vrr_support": True,
            "allm_support": True,
            "notes": "HDR10 gaming with QMS. No DV support. VRR available."
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
        },
        # ========== Gaming Consoles ==========
        "xbox_series_s": {
            "name": "Xbox Series S",
            "type": "console",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "1440p",
            "max_refresh": 120,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "notes": "Digital-only Xbox. 1440p max but can output 4K signal. VRR capable."
        },
        "xbox_one_x": {
            "name": "Xbox One X",
            "type": "console",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.2",
            "notes": "4K capable Xbox One. DV support added via update. VRR support added."
        },
        "xbox_one_s": {
            "name": "Xbox One S",
            "type": "console",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "vrr_support": True,
            "allm_support": False,
            "hdcp": "2.2",
            "notes": "4K media playback, upscaled 4K gaming. HDR10 and DV supported."
        },
        "xbox_one": {
            "name": "Xbox One",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": False,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "2.0",
            "notes": "Original Xbox One. 1080p only, no HDR."
        },
        "xbox_360": {
            "name": "Xbox 360",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": False,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "1.4",
            "notes": "Legacy console. 1080p max. Component or HDMI output."
        },
        "ps4_pro": {
            "name": "PlayStation 4 Pro",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "2.2",
            "notes": "4K upscaled gaming. HDR10 supported. Enable 4K in settings."
        },
        "ps4": {
            "name": "PlayStation 4",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "2.2",
            "notes": "1080p gaming with HDR10 support."
        },
        "ps3": {
            "name": "PlayStation 3",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": False,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "1.4",
            "notes": "Legacy console. 1080p max. Also plays Blu-ray discs."
        },
        "nintendo_switch": {
            "name": "Nintendo Switch",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": False,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "1.4",
            "notes": "1080p docked mode only. Requires dock for HDMI output."
        },
        "nintendo_switch_oled": {
            "name": "Nintendo Switch OLED",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": False,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "vrr_support": False,
            "allm_support": False,
            "hdcp": "1.4",
            "notes": "1080p docked mode. Improved dock with LAN port."
        },
        "nintendo_switch_2": {
            "name": "Nintendo Switch 2",
            "type": "console",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "vrr_support": True,
            "allm_support": True,
            "hdcp": "2.3",
            "notes": "Next-gen Nintendo. 4K docked output with HDR10. DLSS upscaling."
        },
        # ========== Media Players ==========
        "nvidia_shield_2019": {
            "name": "Nvidia Shield TV (2019)",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "hdcp": "2.2",
            "notes": "Tube version. Slightly less powerful than Pro but same video output."
        },
        "nvidia_shield_2017": {
            "name": "Nvidia Shield TV (2017)",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "hdcp": "2.2",
            "notes": "Older Shield. Still excellent. DV added via software update."
        },
        "nvidia_shield_2015": {
            "name": "Nvidia Shield TV (2015)",
            "type": "source",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "hdcp": "2.2",
            "notes": "First Shield. No DV support but HDR10 works. Legacy device."
        },
        "apple_tv_4k_2021": {
            "name": "Apple TV 4K (2021)",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": False,
            "hdcp": "2.2",
            "notes": "A12 chip. Set to 4K SDR 60Hz with match content enabled."
        },
        "apple_tv_4k_2024": {
            "name": "Apple TV 4K (2024)",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": False,
            "hdcp": "2.3",
            "notes": "Latest Apple TV. A15 chip. Thread support. Match content recommended."
        },
        "apple_tv_hd": {
            "name": "Apple TV HD",
            "type": "source",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": False,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": False,
            "hdcp": "1.4",
            "notes": "1080p only Apple TV. No HDR support."
        },
        "chromecast_google_tv_4k": {
            "name": "Chromecast with Google TV (4K)",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "2.2",
            "notes": "Budget 4K streamer. DV and HDR10+ support. Google TV interface."
        },
        "chromecast_google_tv_hd": {
            "name": "Chromecast with Google TV (HD)",
            "type": "source",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "1080p",
            "max_refresh": 60,
            "hdcp": "1.4",
            "notes": "Budget 1080p streamer. HDR10 only."
        },
        "fire_tv_stick_4k_max": {
            "name": "Fire TV Stick 4K Max",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "2.2",
            "notes": "Amazon 4K streamer. DV and HDR10+ support. Wi-Fi 6E."
        },
        "fire_tv_cube": {
            "name": "Fire TV Cube (3rd Gen)",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "2.2",
            "notes": "Premium Amazon streamer. Hands-free Alexa. HDMI input for cable boxes."
        },
        "roku_ultra": {
            "name": "Roku Ultra (2024)",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "hdcp": "2.2",
            "notes": "Premium Roku. DV and HDR10+ support. Ethernet port."
        },
        # Homatics Players
        "homatics_box_r_4k_plus": {
            "name": "Homatics Box R 4K Plus",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "2.2",
            "atmos_passthrough": True,
            "dtsx_passthrough": True,
            "processor": "Amlogic S905X4-K",
            "ram_gb": 4,
            "storage_gb": 32,
            "wifi": "Wi-Fi 6",
            "os": "Android TV 12",
            "notes": "Certified DV/HDR10+ streamer. VS10 engine. Netflix/Disney+ certified. Excellent for Plex."
        },
        "homatics_box_r_4k": {
            "name": "Homatics Box R 4K",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "2.2",
            "atmos_passthrough": True,
            "processor": "Amlogic S905X4",
            "ram_gb": 4,
            "storage_gb": 32,
            "wifi": "Wi-Fi 5",
            "os": "Android TV 11",
            "notes": "DV certified streamer. Good budget option for HDR streaming."
        },
        "homatics_dongle_g": {
            "name": "Homatics Dongle G 4K",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "hdcp": "2.2",
            "os": "Google TV",
            "notes": "Compact 4K dongle. Google TV certified. DV support."
        },
        # Zidoo Players
        "zidoo_z2000_pro": {
            "name": "Zidoo Z2000 Pro",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "atmos_passthrough": True,
            "dtsx_passthrough": True,
            "hdcp": "2.3",
            "notes": "Flagship Zidoo. VS10 engine for DV. Internal HDD bay. Excellent for local playback."
        },
        "zidoo_z9x": {
            "name": "Zidoo Z9X",
            "type": "source",
            "dv_output": True,
            "lldv_output": True,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "match_resolution": True,
            "atmos_passthrough": True,
            "hdcp": "2.2",
            "notes": "Popular Zidoo. VS10 for DV. Good for NAS/local media playback."
        },
        # Raspberry Pi
        "raspberry_pi_5": {
            "name": "Raspberry Pi 5",
            "type": "source",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "None",
            "notes": "DIY media player. LibreELEC/OSMC for Kodi. 4K60 HDR10 capable. No HDCP."
        },
        "raspberry_pi_4": {
            "name": "Raspberry Pi 4",
            "type": "source",
            "dv_output": False,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "match_frame_rate": True,
            "hdcp": "None",
            "notes": "Popular DIY player. LibreELEC/OSMC. Dual HDMI outputs. No HDCP."
        },
        # Blu-ray Players
        "panasonic_ub9000": {
            "name": "Panasonic UB9000",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "hdr10plus_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "hdcp": "2.3",
            "notes": "Reference UHD Blu-ray player. DV and HDR10+. Excellent HDR optimizer."
        },
        "sony_ubp_x800m2": {
            "name": "Sony UBP-X800M2",
            "type": "source",
            "dv_output": True,
            "lldv_output": False,
            "hdr10_output": True,
            "max_resolution": "4K",
            "max_refresh": 60,
            "hdcp": "2.2",
            "notes": "Mid-range UHD player. DV support. SACD/DVD-Audio playback."
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
    "screens": {
        "grandview_105_fixed": {
            "name": "Grandview 105\" Flocked Fixed Frame",
            "type": "screen",
            "size_inches": 105,
            "image_area_mm": "2324x1307",
            "frame_size_mm": "2484x1467",
            "aspect_ratio": "16:9",
            "material": "Matt White ISF Certified Multi-Layer PVC",
            "gain": 1.0,
            "viewing_angle": 160,
            "half_gain_angle": 80,
            "frame_width_mm": 80,
            "frame_finish": "Black velvet (light absorbing)",
            "tension_system": "4-sided steel bar tension",
            "resolution_support": "4K (1 micron diamond optical microgrooves)",
            "viewing_distance_recommended": "10-14 ft",
            "acoustically_transparent": False,
            "ambient_light_rejecting": False,
            "notes": "ISF certified 4K screen with 1.0 gain matte white surface. 80mm beveled frame with black velvet finish absorbs stray light. Wide 160° viewing angle ideal for multiple seating positions."
        },
        "grandview_120_fixed": {
            "name": "Grandview 120\" Flocked Fixed Frame",
            "type": "screen",
            "size_inches": 120,
            "image_area_mm": "2657x1494",
            "frame_size_mm": "2817x1654",
            "aspect_ratio": "16:9",
            "material": "Matt White ISF Certified Multi-Layer PVC",
            "gain": 1.0,
            "viewing_angle": 160,
            "half_gain_angle": 80,
            "frame_width_mm": 80,
            "frame_finish": "Black velvet (light absorbing)",
            "tension_system": "4-sided steel bar tension",
            "resolution_support": "4K (1 micron diamond optical microgrooves)",
            "viewing_distance_recommended": "12-16 ft",
            "acoustically_transparent": False,
            "ambient_light_rejecting": False,
            "notes": "Larger format ISF certified 4K screen for rooms with 12ft+ seating distance. Same matte white surface as 105\"."
        },
        "screen_100_alr": {
            "name": "100\" ALR (Ambient Light Rejecting)",
            "type": "screen",
            "size_inches": 100,
            "aspect_ratio": "16:9",
            "material": "ALR grey",
            "gain": 0.8,
            "viewing_distance_recommended": "8-12 ft",
            "acoustically_transparent": False,
            "ambient_light_rejecting": True,
            "notes": "ALR material rejects ambient light for rooms without full light control. May reduce off-axis brightness."
        },
        "screen_120_at": {
            "name": "120\" Acoustically Transparent",
            "type": "screen",
            "size_inches": 120,
            "aspect_ratio": "16:9",
            "material": "woven AT",
            "gain": 0.9,
            "viewing_distance_recommended": "12-16 ft",
            "acoustically_transparent": True,
            "ambient_light_rejecting": False,
            "notes": "Woven acoustically transparent material. Place L/C/R speakers behind screen for phantom-free center channel."
        },
        "screen_135_cinemascope": {
            "name": "135\" CinemaScope 2.35:1",
            "type": "screen",
            "size_inches": 135,
            "aspect_ratio": "2.35:1",
            "material": "white",
            "gain": 1.0,
            "viewing_distance_recommended": "12-16 ft",
            "acoustically_transparent": False,
            "ambient_light_rejecting": False,
            "notes": "CinemaScope aspect ratio for scope movies without letterboxing. Use lens memory or anamorphic lens."
        },
        "screen_motorized_110": {
            "name": "110\" Motorized Drop-Down",
            "type": "screen",
            "size_inches": 110,
            "aspect_ratio": "16:9",
            "material": "white",
            "gain": 1.0,
            "viewing_distance_recommended": "10-14 ft",
            "acoustically_transparent": False,
            "ambient_light_rejecting": False,
            "notes": "Motorized screen for multi-purpose rooms. Can be triggered via RS232 or 12V trigger."
        }
    },
    "media_servers": {
        "plex": {
            "name": "Plex",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "preroll_paths": {
                "windows": r"C:\Users\<username>\AppData\Local\Plex Media Server\Extras\preroll.mp4",
                "linux": "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/preroll.mp4",
                "macos": "~/Library/Application Support/Plex Media Server/preroll.mp4",
                "docker": "/config/Library/Application Support/Plex Media Server/preroll.mp4"
            },
            "preroll_config_path": "Settings > Extras > Cinema Trailers Pre-roll Video",
            "preroll_config_notes": "Enter the full path to your pre-roll video. Multiple pre-rolls can be separated with semicolons (random) or commas (sequential).",
            "optimization_settings": {
                "direct_play": {"path": "Settings > Server > Network > Direct Play", "recommended": "Enabled", "reason": "Avoids transcoding which can change format"},
                "direct_stream": {"path": "Settings > Server > Network > Direct Stream", "recommended": "Enabled", "reason": "Allows remuxing without transcoding video"},
                "transcoder_quality": {"path": "Settings > Server > Transcoder > Transcoder Quality", "recommended": "Maximum", "reason": "If transcoding is needed, use highest quality"},
                "video_quality": {"path": "Settings > Quality (client) > Video Quality", "recommended": "Maximum / Original", "reason": "Ensures client requests original quality"}
            },
            "notes": "Set pre-roll in Settings > Extras. No automatic format matching. Use full file path."
        },
        "jellyfin": {
            "name": "Jellyfin",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "preroll_paths": {
                "windows": r"C:\ProgramData\Jellyfin\Server\data\intros\preroll.mp4",
                "linux": "/var/lib/jellyfin/data/intros/preroll.mp4",
                "macos": "~/.local/share/jellyfin/data/intros/preroll.mp4",
                "docker": "/config/data/intros/preroll.mp4"
            },
            "preroll_config_path": "Dashboard > Plugins > Intros > Configure",
            "preroll_config_notes": "Install the Intros plugin from the plugin catalog. Point it to a folder containing your pre-roll videos.",
            "optimization_settings": {
                "playback_transcoding": {"path": "Dashboard > Playback > Transcoding", "recommended": "Hardware acceleration enabled if available", "reason": "Reduces CPU load, maintains quality"},
                "direct_play": {"path": "Client Settings > Playback > Direct Play", "recommended": "Enabled / Forced", "reason": "Prevents unnecessary transcoding"},
                "max_streaming_bitrate": {"path": "Client Settings > Playback > Maximum Streaming Bitrate", "recommended": "Auto or Maximum", "reason": "Allows full quality streaming"}
            },
            "notes": "Pre-roll via Intros plugin. Free and open source. Create an 'intros' folder and configure the plugin."
        },
        "emby": {
            "name": "Emby",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "preroll_paths": {
                "windows": r"C:\ProgramData\Emby-Server\programdata\intros\preroll.mp4",
                "linux": "/var/lib/emby/intros/preroll.mp4",
                "macos": "~/.emby-server/intros/preroll.mp4",
                "docker": "/config/intros/preroll.mp4"
            },
            "preroll_config_path": "Settings > Advanced > Cinema Mode Intros",
            "preroll_config_notes": "Enable Cinema Mode and set the intro folder path. Videos in this folder play before movies.",
            "optimization_settings": {
                "cinema_mode": {"path": "Settings > Advanced > Cinema Mode", "recommended": "Enabled", "reason": "Required for pre-roll functionality"},
                "direct_play": {"path": "Settings > Playback > Direct Play", "recommended": "Enabled", "reason": "Prevents format changes that cause bonk"},
                "direct_stream": {"path": "Settings > Playback > Direct Stream", "recommended": "Enabled", "reason": "Allows container changes without re-encoding"},
                "transcoding_bitrate": {"path": "Settings > Playback > Transcoding Bitrate", "recommended": "Maximum / Original", "reason": "If transcoding needed, maintain quality"}
            },
            "notes": "Cinema intros feature. IMPORTANT: Pre-roll format MUST match movie format to avoid 1-frame display bug."
        },
        "kodi": {
            "name": "Kodi",
            "type": "media_server",
            "preroll_support": True,
            "preroll_format_match": False,
            "preroll_paths": {
                "windows": "C:\\Users\\<username>\\AppData\\Roaming\\Kodi\\userdata\\addon_data\\script.cinemavision\\",
                "linux": "~/.kodi/userdata/addon_data/script.cinemavision/",
                "macos": "~/Library/Application Support/Kodi/userdata/addon_data/script.cinemavision/",
                "libreelec": "/storage/.kodi/userdata/addon_data/script.cinemavision/"
            },
            "preroll_config_path": "Add-ons > CinemaVision > Settings > Sequences",
            "preroll_config_notes": "Install CinemaVision addon. Create a sequence with your pre-roll video as a 'Trivia' or 'Trailer' element.",
            "optimization_settings": {
                "adjust_refresh": {"path": "Settings > Player > Videos > Adjust display refresh rate", "recommended": "On start/stop", "reason": "Matches display to content frame rate"},
                "sync_playback": {"path": "Settings > Player > Videos > Sync playback to display", "recommended": "Enabled", "reason": "Reduces judder"},
                "passthrough": {"path": "Settings > System > Audio > Allow Passthrough", "recommended": "Enabled for Atmos/DTS:X", "reason": "Passes lossless audio to AVR"},
                "gui_resolution": {"path": "Settings > System > Display > Resolution", "recommended": "Match content or 4K", "reason": "Reduces mode switches"}
            },
            "notes": "CinemaVision addon for pre-roll. Local playback. Best for HTPC setups with direct display connection."
        }
    }
}


# =============================================================================
# VRROOM Settings Metadata (human-readable names and menu paths)
# =============================================================================

VRROOM_SETTINGS_META = {
    "edidmode": {
        "name": "EDID Mode",
        "menu_path": "Vrroom Web UI > EDID > MODE",
        "tab": "EDID",
        "values": {
            "automix": "AutoMix (Recommended)",
            "custom": "Custom EDID",
            "fixed": "Fixed",
            "copytx0": "Copy TX0",
            "copytx1": "Copy TX1"
        },
        "description": "How EDID is generated for connected sources"
    },
    "ediddvflag": {
        "name": "Dolby Vision EDID Flag",
        "menu_path": "Vrroom Web UI > EDID > DV FLAG",
        "tab": "EDID",
        "values": {"on": "Enabled", "off": "Disabled"},
        "description": "Include Dolby Vision capability in EDID"
    },
    "ediddvmode": {
        "name": "Dolby Vision Mode",
        "menu_path": "Vrroom Web UI > EDID > DV MODE",
        "tab": "EDID",
        "values": {"0": "LG C1 (Standard)", "1": "Custom", "2": "Remove DV"},
        "description": "Which DV profile to advertise"
    },
    "edidhdrflag": {
        "name": "HDR EDID Flag",
        "menu_path": "Vrroom Web UI > EDID > HDR FLAG",
        "tab": "EDID",
        "values": {"on": "Enabled", "off": "Disabled"},
        "description": "Include HDR capability in EDID"
    },
    "edidhdrmode": {
        "name": "HDR Mode",
        "menu_path": "Vrroom Web UI > EDID > HDR MODE",
        "tab": "EDID",
        "values": {
            "0": "HDR10 only",
            "1": "HDR10 + HLG",
            "2": "HDR10+",
            "3": "HDR10+ + HLG",
            "4": "Remove HDR"
        },
        "description": "Which HDR formats to advertise in EDID"
    },
    "hdrcustom": {
        "name": "Custom HDR Injection",
        "menu_path": "Vrroom Web UI > SIGNAL > HDR CUSTOM",
        "tab": "SIGNAL",
        "values": {"on": "Enabled", "off": "Disabled"},
        "description": "Inject custom HDR metadata (auto-disables under VRR)"
    },
    "lldv": {
        "name": "LLDV (Low Latency DV)",
        "menu_path": "Vrroom Web UI > EDID > LLDV",
        "tab": "EDID",
        "values": {"on": "Enabled", "off": "Disabled"},
        "description": "Enable LLDV conversion for non-DV displays"
    },
    "unmutedelay": {
        "name": "Audio Unmute Delay",
        "menu_path": "Vrroom Web UI > AUDIO > UNMUTE DELAY",
        "tab": "AUDIO",
        "values": "0-20 (x100ms, e.g., 5 = 500ms)",
        "description": "Delay before unmuting audio after format change to prevent pops"
    },
    "vrr": {
        "name": "VRR (Variable Refresh Rate)",
        "menu_path": "Vrroom Web UI > SIGNAL > VRR",
        "tab": "SIGNAL",
        "values": {"on": "Enabled", "off": "Disabled", "force": "Force On"},
        "description": "Variable Refresh Rate passthrough or injection"
    },
    "allm": {
        "name": "ALLM (Auto Low Latency Mode)",
        "menu_path": "Vrroom Web UI > SIGNAL > ALLM",
        "tab": "SIGNAL",
        "values": {"on": "Enabled", "off": "Disabled", "force": "Force On"},
        "description": "Auto Low Latency Mode passthrough or injection"
    },
    "downscale": {
        "name": "Downscale Output",
        "menu_path": "Vrroom Web UI > SIGNAL > DOWNSCALE",
        "tab": "SIGNAL",
        "values": {"off": "Disabled (native)", "1080p": "1080p", "4k": "4K"},
        "description": "Downscale output resolution"
    },
    "frl": {
        "name": "Fixed Rate Link (HDMI 2.1)",
        "menu_path": "Vrroom Web UI > SIGNAL > FRL MODE",
        "tab": "SIGNAL",
        "values": {"auto": "Auto", "off": "Disabled (TMDS only)"},
        "description": "HDMI 2.1 FRL mode for high bandwidth"
    },
    "earc": {
        "name": "eARC Mode",
        "menu_path": "Vrroom Web UI > AUDIO > eARC",
        "tab": "AUDIO",
        "values": {"on": "Enabled", "off": "Disabled"},
        "description": "Enhanced Audio Return Channel"
    },
    "audioout": {
        "name": "Audio Output Mode",
        "menu_path": "Vrroom Web UI > AUDIO > OUTPUT",
        "tab": "AUDIO",
        "values": {"off": "Disabled", "spdif": "S/PDIF", "analog": "Analog", "all": "All"},
        "description": "Audio extraction output"
    }
}


def get_vrroom_setting_display(setting_key, value):
    """Convert RS232 setting to human-readable format."""
    meta = VRROOM_SETTINGS_META.get(setting_key, {})
    if not meta:
        return {
            "name": setting_key,
            "value": str(value),
            "display_value": str(value),
            "menu_path": "Vrroom Web UI",
            "tab": "Settings",
            "is_set": True
        }

    # Get human-readable value
    values_map = meta.get("values", {})
    if isinstance(values_map, dict):
        display_value = values_map.get(str(value), str(value))
    else:
        display_value = f"{value} ({values_map})"

    # Determine if this is "enabled/on" state
    is_enabled = str(value).lower() in ["on", "enabled", "1", "true", "yes", "automix"]

    return {
        "name": meta.get("name", setting_key),
        "value": value,
        "display_value": display_value,
        "menu_path": meta.get("menu_path", "Vrroom Web UI"),
        "tab": meta.get("tab", "Settings"),
        "description": meta.get("description", ""),
        "is_set": is_enabled
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


# =============================================================================
# Speaker Tuning Guides
# =============================================================================

SPEAKER_TUNING_GUIDES = {
    "yamaha_ypao": {
        "name": "Yamaha YPAO (Yamaha Parametric Room Acoustic Optimizer)",
        "manufacturer": "Yamaha",
        "description": "Automatic room calibration system included with Yamaha AV receivers.",
        "equipment_needed": [
            "YPAO microphone (included with receiver)",
            "Microphone stand or tripod",
            "Quiet room during measurement"
        ],
        "steps": [
            {
                "step": 1,
                "title": "Prepare the Room",
                "instructions": [
                    "Turn off fans, AC, and other noise sources",
                    "Close windows and doors",
                    "Remove obstacles between speakers and listening position",
                    "Ensure all speakers are connected and powered"
                ]
            },
            {
                "step": 2,
                "title": "Position the Microphone",
                "instructions": [
                    "Place microphone at ear height when seated (typically 3-4 feet)",
                    "Position at main listening position (center of couch)",
                    "Use tripod or mic stand - don't hold by hand",
                    "Point microphone straight up (not toward any speaker)",
                    "Keep at least 3 feet from walls"
                ]
            },
            {
                "step": 3,
                "title": "Connect Microphone",
                "instructions": [
                    "Plug YPAO microphone into YPAO jack on front of receiver",
                    "Ensure secure connection",
                    "Wait for receiver to detect microphone"
                ]
            },
            {
                "step": 4,
                "title": "Run YPAO",
                "instructions": [
                    "Navigate to: Setup > Speaker > YPAO",
                    "Select 'Start' to begin measurement",
                    "Leave the room during measurement (sounds can affect results)",
                    "Wait for all test tones to complete (several minutes)",
                    "Receiver will measure each speaker individually"
                ]
            },
            {
                "step": 5,
                "title": "Review Results",
                "instructions": [
                    "Check for any error messages (speaker wiring, phase issues)",
                    "Review detected speaker configuration",
                    "Verify distances seem reasonable for your room",
                    "Check that no speakers show 'None' unless intentional"
                ]
            },
            {
                "step": 6,
                "title": "Apply Settings",
                "instructions": [
                    "Select the YPAO result to apply (Flat, Front, Natural)",
                    "'Flat' = neutral frequency response (recommended for movies)",
                    "'Natural' = slightly warmer sound",
                    "'Front' = matches surround to front speakers",
                    "Save and exit"
                ]
            },
            {
                "step": 7,
                "title": "Optional: Multi-Position Measurement",
                "instructions": [
                    "For better coverage, run YPAO Multi-Point",
                    "Move microphone to 8 different positions around seating area",
                    "Follow on-screen prompts for each position",
                    "This averages the room response for multiple listeners"
                ]
            }
        ],
        "common_issues": {
            "Speaker Phase Error": "Check speaker wire polarity (+/- connections). Swap if necessary.",
            "No Speaker Detected": "Verify speaker is connected and working. Check wire connections.",
            "Distance Seems Wrong": "YPAO measures acoustic distance, not physical. Some variation is normal.",
            "Subwoofer Issues": "Ensure sub is powered on, volume at 50%, crossover set to LFE or highest setting."
        },
        "tips": [
            "Run YPAO after any room changes (furniture, acoustic treatments)",
            "For subwoofers, set the sub's volume to 50% before calibration",
            "Use YPAO-RSC (Reflected Sound Control) if available for room reflections",
            "Consider the Yamaha YPAO app for more detailed results",
            "Manual fine-tuning after YPAO is acceptable for personal preference"
        ]
    },
    "audyssey": {
        "name": "Audyssey MultEQ",
        "manufacturer": "Denon / Marantz",
        "description": "Automatic room calibration system for Denon and Marantz receivers.",
        "equipment_needed": [
            "Audyssey microphone (included with receiver)",
            "Microphone stand",
            "Audyssey app (optional, recommended for XT32)"
        ],
        "steps": [
            {
                "step": 1,
                "title": "Prepare the Room",
                "instructions": [
                    "Minimize ambient noise",
                    "Position speakers in final locations",
                    "Set subwoofer volume to 75% (Audyssey will adjust)",
                    "Set subwoofer crossover to maximum/LFE"
                ]
            },
            {
                "step": 2,
                "title": "Position Microphone",
                "instructions": [
                    "Place at primary listening position first",
                    "Ear height when seated",
                    "Use included stand - microphone facing up",
                    "Keep away from surfaces and walls"
                ]
            },
            {
                "step": 3,
                "title": "Run Audyssey Setup",
                "instructions": [
                    "Navigate to: Setup > Speakers > Audyssey Setup",
                    "Select measurement positions (3-8 positions available)",
                    "More positions = better averaging",
                    "Follow prompts to move microphone between measurements"
                ]
            },
            {
                "step": 4,
                "title": "Review and Apply",
                "instructions": [
                    "Check speaker configuration detection",
                    "Apply results",
                    "Choose Audyssey mode: Reference, L/R Bypass, Flat, or Off"
                ]
            }
        ],
        "common_issues": {
            "Sub too loud/quiet": "Use Dynamic EQ or adjust sub trim after calibration",
            "Dialogue unclear": "Try Audyssey Dynamic Volume or increase center level +2dB",
            "Bass lacking": "Enable Dynamic EQ at -15dB reference level"
        },
        "tips": [
            "Use Audyssey app (MultEQ-X) for curve customization",
            "Dynamic EQ compensates for low-volume listening",
            "Consider Dirac Live upgrade for XT32 receivers",
            "Run calibration when room is at typical viewing temperature"
        ]
    },
    "dirac_live": {
        "name": "Dirac Live",
        "manufacturer": "Dirac Research",
        "description": "Premium room correction available as upgrade for many receivers.",
        "equipment_needed": [
            "Dirac Live calibration microphone (UMIK-1 or UMIK-2 recommended)",
            "Computer running Dirac Live software",
            "USB cable for microphone",
            "Measurement stand/tripod"
        ],
        "steps": [
            {
                "step": 1,
                "title": "Setup Software",
                "instructions": [
                    "Download Dirac Live from dirac.com",
                    "Connect USB microphone to computer",
                    "Ensure receiver is on same network as computer",
                    "Launch Dirac Live and detect receiver"
                ]
            },
            {
                "step": 2,
                "title": "Measure Room",
                "instructions": [
                    "Follow app prompts for microphone positions",
                    "9-17 positions around listening area recommended",
                    "Keep microphone at ear height",
                    "Stay out of room during measurements"
                ]
            },
            {
                "step": 3,
                "title": "Design Target Curve",
                "instructions": [
                    "Use default Dirac target or customize",
                    "Adjust bass, treble, and house curve to taste",
                    "Preview before applying",
                    "Save multiple filter slots for different preferences"
                ]
            },
            {
                "step": 4,
                "title": "Apply Filters",
                "instructions": [
                    "Upload filters to receiver",
                    "Select active filter slot on receiver",
                    "A/B test with Dirac on/off"
                ]
            }
        ],
        "tips": [
            "Dirac Live is considered superior to Audyssey/YPAO by many enthusiasts",
            "The UMIK-2 microphone is calibrated and provides better accuracy",
            "Bass Control (separate license) allows independent sub correction",
            "Create multiple filter slots for movies vs music"
        ]
    },
    "arc_genesis": {
        "name": "Anthem ARC Genesis",
        "manufacturer": "Anthem",
        "description": "Room correction system for Anthem AV equipment.",
        "equipment_needed": [
            "ARC Genesis microphone (included)",
            "Computer running ARC Genesis software",
            "USB cable for microphone"
        ],
        "steps": [
            {
                "step": 1,
                "title": "Install Software",
                "instructions": [
                    "Download ARC Genesis from anthemav.com",
                    "Connect microphone via USB",
                    "Connect computer to same network as receiver"
                ]
            },
            {
                "step": 2,
                "title": "Run Measurements",
                "instructions": [
                    "Place microphone at 5 positions minimum",
                    "Cover primary listening area",
                    "ARC calculates room response and corrections"
                ]
            },
            {
                "step": 3,
                "title": "Review and Apply",
                "instructions": [
                    "Examine frequency response graphs",
                    "Adjust target curve if desired",
                    "Upload corrections to receiver"
                ]
            }
        ],
        "tips": [
            "ARC Genesis provides detailed measurement graphs",
            "One of the most transparent room correction systems",
            "Quick Measure option for simple setups"
        ]
    },
    "manual_speaker_setup": {
        "name": "Manual Speaker Setup (No Room Correction)",
        "manufacturer": "Universal",
        "description": "Basic speaker setup without automatic room correction.",
        "equipment_needed": [
            "Tape measure",
            "SPL meter (phone app works: NIOSH SLM, Sound Meter)",
            "Test tones (pink noise, available on YouTube or streaming)"
        ],
        "steps": [
            {
                "step": 1,
                "title": "Measure Distances",
                "instructions": [
                    "Measure from each speaker to primary listening position",
                    "Use straight-line distance (not along floor)",
                    "Enter distances in receiver's speaker setup menu",
                    "This ensures proper time alignment for all channels"
                ]
            },
            {
                "step": 2,
                "title": "Set Crossover Frequencies",
                "instructions": [
                    "Small bookshelf speakers: 80-100Hz crossover",
                    "Floor-standing speakers: 40-80Hz (or set to Large)",
                    "Center channel: Usually 80Hz",
                    "Subwoofer: Set sub's crossover to LFE/max, let receiver manage"
                ]
            },
            {
                "step": 3,
                "title": "Level Matching",
                "instructions": [
                    "Use receiver's test tone generator",
                    "Measure each speaker with SPL meter at listening position",
                    "Adjust trim so all speakers read same level (75dB reference)",
                    "Do NOT adjust subwoofer by ear - use meter"
                ]
            },
            {
                "step": 4,
                "title": "Subwoofer Phase",
                "instructions": [
                    "Play bass-heavy content",
                    "Flip sub phase between 0° and 180°",
                    "Choose setting with MORE bass at listening position",
                    "Some subs have variable phase (0-180°) for fine tuning"
                ]
            }
        ],
        "tips": [
            "Reference level for movies is 85dB (main channels) / 95dB (LFE)",
            "Phone SPL apps are adequate for level matching",
            "Trust measurements over your ears for setup",
            "Reposition speakers before adding acoustic treatment"
        ]
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
        self.screen_id = setup.get("screen", "")
        self.goals = setup.get("goals", [])

        # Support multiple media servers
        media_servers_input = setup.get("media_servers", [])
        # Backwards compat: single media_server string
        if not media_servers_input:
            single = setup.get("media_server", "")
            media_servers_input = [single] if single else []
        elif isinstance(media_servers_input, str):
            media_servers_input = [media_servers_input]

        self.media_server_ids = [s for s in media_servers_input if s]
        self.media_servers = []
        for sid in self.media_server_ids:
            profile = DEVICE_PROFILES["media_servers"].get(sid, {})
            if profile:
                self.media_servers.append((sid, profile))

        # Keep first media server as primary for backwards compat
        self.media_server_id = self.media_server_ids[0] if self.media_server_ids else ""
        self.media_server = self.media_servers[0][1] if self.media_servers else {}

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
        self.screen = DEVICE_PROFILES["screens"].get(self.screen_id, {})
        # media_server already set above from media_servers array

    def generate(self):
        """Generate full recommendation set."""
        recommendations = []
        vrroom_settings = {}
        source_settings = []
        avr_settings = []
        display_settings = []

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

        # Generate AVR config recommendations
        avr_result = self._avr_config_recs()
        recommendations.extend(avr_result.get("recommendations", []))
        avr_settings = avr_result.get("avr_settings", [])

        # Generate display/projector config recommendations
        display_result = self._display_config_recs()
        recommendations.extend(display_result.get("recommendations", []))
        display_settings = display_result.get("display_settings", [])

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

        # Convert vrroom_settings to detailed format with human-readable names
        vrroom_settings_detailed = []
        for key, value in vrroom_settings.items():
            detailed = get_vrroom_setting_display(key, value)
            vrroom_settings_detailed.append(detailed)

        # Fix avr_settings paths - extract string from object if needed
        for setting in avr_settings:
            path = setting.get("path", "")
            if isinstance(path, dict):
                # Extract path string and add steps if available
                setting["path"] = path.get("path", "")
                setting["steps"] = path.get("steps", [])
                setting["tab"] = path.get("tab", "")
                setting["recommended"] = path.get("recommended", "")
            elif not path:
                setting["path"] = ""

        # Fix display_settings paths too
        for setting in display_settings:
            path = setting.get("path", "")
            if isinstance(path, dict):
                setting["path"] = path.get("path", "")
                setting["steps"] = path.get("steps", [])
                setting["tab"] = path.get("tab", "")
                setting["recommended"] = path.get("recommended", "")
            elif not path:
                setting["path"] = ""

        return {
            "setup_summary": {
                "display": self.display.get("name", "Not specified"),
                "hdfury_device": self.hdfury.get("name", "Not specified"),
                "avr": self.avr.get("name", "Not specified"),
                "sources": [s[1].get("name", "Unknown") for s in self.sources] if self.sources else ["Not specified"],
                "speakers": self.speakers.get("name", "Not specified"),
                "screen": self.screen.get("name", "Not specified"),
                "media_servers": [s[1].get("name", "Unknown") for s in self.media_servers] if self.media_servers else ["Not specified"],
                "goals": [OPTIMIZATION_GOALS[g]["name"] for g in self.goals if g in OPTIMIZATION_GOALS]
            },
            "recommendations": unique_recs,
            "vrroom_settings": vrroom_settings,  # Raw settings for apply function
            "vrroom_settings_detailed": vrroom_settings_detailed,  # Human-readable for display
            "source_settings": unique_src,
            "avr_settings": avr_settings,
            "display_settings": display_settings,
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

    def _avr_config_recs(self):
        """Generate AVR configuration recommendations based on speaker layout."""
        recs = []
        avr_settings = []

        if not self.avr or not self.speakers:
            return {"recommendations": recs, "avr_settings": avr_settings}

        avr_name = self.avr.get("name", "AVR")
        speaker_layout = self.speakers.get("layout", "")
        channels = self.speakers.get("channels", 0)
        overhead = self.speakers.get("overhead_channels", 0)
        subs = self.speakers.get("sub_channels", 0)
        has_atmos = self.speakers.get("atmos_capable", False)
        config_paths = self.avr.get("config_paths", {})
        room_correction = self.avr.get("room_correction", "")

        # Speaker configuration
        total_bed = channels + subs
        total_with_height = channels + overhead + subs
        layout_label = speaker_layout or f"{channels}.{subs}"
        if overhead > 0:
            layout_label = f"{channels}.{subs}.{overhead}"

        avr_settings.append({
            "setting": "Speaker Configuration",
            "value": f"{layout_label} ({total_with_height} total speakers)",
            "category": "speakers",
            "path": config_paths.get("speaker_setup", ""),
            "reason": f"Set AVR to {layout_label} layout to match your physical speaker arrangement."
        })

        # Crossover settings
        crossover_main = "80 Hz"
        crossover_reason = "80 Hz is the THX-recommended crossover for most speakers."
        if subs >= 2:
            crossover_reason += " Dual subs provide smoother bass; 80 Hz crossover ensures seamless handoff."

        avr_settings.append({
            "setting": "Crossover Frequency (all channels)",
            "value": crossover_main,
            "category": "speakers",
            "path": config_paths.get("crossover", ""),
            "reason": crossover_reason
        })

        # Subwoofer mode
        if subs >= 2:
            avr_settings.append({
                "setting": "Subwoofer Mode",
                "value": "LFE + Main (both subs active)",
                "category": "speakers",
                "path": config_paths.get("speaker_setup", ""),
                "reason": "Dual subs provide even bass distribution and reduce room mode nulls."
            })

        # Height/Atmos channels
        if overhead > 0 and has_atmos:
            height_type = "Top" if overhead == 4 else "Top"
            if overhead == 2:
                height_label = "2 height channels (Front Height or Top Middle)"
                avr_settings.append({
                    "setting": "Height Speaker Assignment",
                    "value": "Front Height or Top Middle",
                    "category": "speakers",
                    "path": config_paths.get("speaker_setup", ""),
                    "reason": "With 2 height channels, Top Middle or Front Height gives the best Atmos overhead coverage. "
                              "Top Middle preferred for ceiling-mounted; Front Height for upfiring modules."
                })
            elif overhead == 4:
                height_label = "4 height channels (Top Front + Top Rear)"
                avr_settings.append({
                    "setting": "Height Speaker Assignment",
                    "value": "Top Front + Top Rear (or Front Height + Rear Height)",
                    "category": "speakers",
                    "path": config_paths.get("speaker_setup", ""),
                    "reason": "4 height channels provide full Atmos hemisphere. "
                              "Top Front + Top Rear for ceiling; Front Height + Rear Height for upfiring."
                })

        # Surround decode mode
        if has_atmos:
            avr_settings.append({
                "setting": "Surround Decode Mode",
                "value": "Dolby Atmos / DTS:X (Auto)",
                "category": "processing",
                "path": config_paths.get("surround_decode", ""),
                "reason": "Auto mode decodes native Atmos/DTS:X tracks and upmixes stereo/5.1 content to height speakers."
            })
            recs.append({
                "severity": "info",
                "title": f"Atmos Configuration for {avr_name}",
                "description": f"Your {speaker_layout} layout with {avr_name} supports Dolby Atmos and DTS:X. "
                               "Ensure surround decode is set to Auto to engage height channels for object-based audio."
            })

        # HDMI audio output
        avr_settings.append({
            "setting": "HDMI Audio Output",
            "value": "AMP (decode in AVR)",
            "category": "audio_routing",
            "path": config_paths.get("hdmi_audio", ""),
            "reason": "Route audio decoding to AVR rather than passing through to TV/projector."
        })

        # eARC
        if self.avr.get("earc_support"):
            avr_settings.append({
                "setting": "eARC",
                "value": "Enabled",
                "category": "audio_routing",
                "path": config_paths.get("earc", ""),
                "reason": "eARC enables lossless Atmos (TrueHD MAT) and DTS:X passthrough from display or Vrroom."
            })

        # Room correction
        if room_correction:
            avr_settings.append({
                "setting": f"Room Correction ({room_correction})",
                "value": "Run calibration with all speakers at listening position",
                "category": "calibration",
                "path": config_paths.get("room_correction", ""),
                "reason": f"{room_correction} measures your room acoustics and applies EQ correction. "
                          "Run at primary listening position. Use multiple measurement points if supported."
            })
            recs.append({
                "severity": "warning",
                "title": f"Run {room_correction} Calibration",
                "description": f"After configuring speaker layout on {avr_name}, run {room_correction} room correction. "
                               "This compensates for room acoustics, speaker placement, and distance differences. "
                               "Place the microphone at ear height at your primary listening position."
            })

        # Speaker distance calibration note
        avr_settings.append({
            "setting": "Speaker Distances",
            "value": "Measure from each speaker to listening position",
            "category": "calibration",
            "path": config_paths.get("distance", ""),
            "reason": "Correct distance settings ensure all speakers are time-aligned. "
                      "Measure in a straight line from each speaker cone to your head position."
        })

        # Speaker levels
        avr_settings.append({
            "setting": "Speaker Levels",
            "value": "Calibrate to 75 dB SPL at listening position (use SPL meter or room correction)",
            "category": "calibration",
            "path": config_paths.get("level", ""),
            "reason": "All speakers should measure the same SPL at the listening position. "
                      "Room correction typically handles this, or use an SPL meter app with test tones."
        })

        return {"recommendations": recs, "avr_settings": avr_settings}

    def _display_config_recs(self):
        """Generate display/projector configuration recommendations."""
        recs = []
        display_settings = []

        if not self.display:
            return {"recommendations": recs, "display_settings": display_settings}

        display_name = self.display.get("name", "Display")
        display_type = self.display.get("type", "")
        config_paths = self.display.get("config_paths", {})
        recommended = self.display.get("recommended_settings", {})
        is_projector = display_type == "projector"

        if not config_paths and not recommended:
            # No detailed config available for this display
            return {"recommendations": recs, "display_settings": display_settings}

        # HDMI signal format (critical for 4K HDR)
        hdmi_signal_path = config_paths.get("hdmi_signal", "")
        hdmi_rec = recommended.get("hdmi_signal_format", "")
        if hdmi_signal_path or hdmi_rec:
            display_settings.append({
                "setting": "HDMI Signal Format",
                "value": hdmi_rec or "Enhanced / Expanded (required for 4K HDR)",
                "category": "input",
                "path": hdmi_signal_path,
                "reason": "HDMI inputs must be set to Enhanced/Expanded mode to accept 4K HDR 10-bit signals. "
                          "Standard mode limits to 8-bit SDR."
            })

        # Picture mode for SDR
        sdr_mode = recommended.get("color_mode_sdr", "")
        if sdr_mode:
            display_settings.append({
                "setting": "Picture Mode (SDR content)",
                "value": sdr_mode,
                "category": "picture",
                "path": config_paths.get("picture_mode", ""),
                "reason": "Natural or Cinema modes provide the most accurate colors for SDR content "
                          "with proper BT.709 color space and 2.2-2.4 gamma."
            })

        # Picture mode for HDR
        hdr_mode = recommended.get("color_mode_hdr", "")
        if hdr_mode:
            display_settings.append({
                "setting": "Picture Mode (HDR content)",
                "value": hdr_mode,
                "category": "picture",
                "path": config_paths.get("picture_mode", ""),
                "reason": "HDR picture mode applies appropriate tone mapping and "
                          "BT.2020 wide color gamut processing for HDR10/HLG content."
            })

        # HDR-specific settings
        hdr_range = recommended.get("hdr10_dynamic_range", "")
        if hdr_range:
            display_settings.append({
                "setting": "HDR10 Dynamic Range",
                "value": hdr_range,
                "category": "picture",
                "path": config_paths.get("hdr_setting", ""),
                "reason": "Controls how HDR tone mapping maps the source brightness range to your display's capability. "
                          "Auto works for most content; a value of 16 works well in fully dark rooms."
            })

        # Color temperature
        color_temp = recommended.get("color_temp", "")
        if color_temp:
            display_settings.append({
                "setting": "Color Temperature",
                "value": color_temp,
                "category": "picture",
                "path": config_paths.get("color_temp", ""),
                "reason": "D65 (6500K) is the reference white point for both SDR and HDR content. "
                          "Warm/Warm2 presets on most displays approximate D65."
            })

        # Gamma
        gamma_sdr = recommended.get("gamma_sdr", "")
        if gamma_sdr:
            display_settings.append({
                "setting": "Gamma (SDR)",
                "value": gamma_sdr,
                "category": "picture",
                "path": config_paths.get("gamma", ""),
                "reason": "For a dark dedicated theater room, gamma 2.4 (BT.1886) is ideal. "
                          "For rooms with some ambient light, use 2.2. Adjust based on viewing conditions."
            })

        # Frame interpolation
        fi = recommended.get("frame_interpolation", "")
        if fi:
            display_settings.append({
                "setting": "Frame Interpolation / Motion Smoothing",
                "value": fi,
                "category": "processing",
                "path": config_paths.get("frame_interp", ""),
                "reason": "Off preserves the filmmaker's intended 24fps cadence (no soap opera effect). "
                          "Low setting can help with judder on some displays without the soap opera look."
            })

        # Projector-specific settings
        if is_projector:
            # Light source mode
            light_mode = recommended.get("light_source_mode", "")
            if light_mode:
                display_settings.append({
                    "setting": "Light Source Mode",
                    "value": light_mode,
                    "category": "projector",
                    "path": config_paths.get("power_mode", ""),
                    "reason": "Adjust laser/lamp output to room conditions. Lower output in fully dark rooms "
                              "preserves contrast and extends light source life."
                })

            # Aspect ratio
            aspect = recommended.get("aspect_ratio", "")
            if aspect:
                display_settings.append({
                    "setting": "Aspect Ratio",
                    "value": aspect,
                    "category": "projector",
                    "path": config_paths.get("aspect_ratio", ""),
                    "reason": "Auto handles 16:9 and letterboxed content. Use Anamorphic/Lens Memory "
                              "for constant image height setups with CinemaScope screens."
                })

            # Lens memory
            if self.display.get("lens_memory"):
                display_settings.append({
                    "setting": "Lens Memory",
                    "value": "Configure presets for 16:9 and 2.35:1 aspect ratios",
                    "category": "projector",
                    "path": config_paths.get("lens_memory", ""),
                    "reason": "Lens memory stores zoom/shift positions for different aspect ratios. "
                              "Set one preset for 16:9 (full screen) and one for 2.35:1 (scope) if using CinemaScope screen."
                })

            # Screen-specific projector recommendations
            if self.screen:
                screen_name = self.screen.get("name", "screen")
                gain = self.screen.get("gain", 1.0)
                is_at = self.screen.get("acoustically_transparent", False)
                is_alr = self.screen.get("ambient_light_rejecting", False)

                recs.append({
                    "severity": "info",
                    "title": f"Projector + Screen: {display_name} on {screen_name}",
                    "description": f"Screen gain: {gain}. "
                                   + ("Acoustically transparent screen - place L/C/R behind screen for best imaging. " if is_at else "")
                                   + ("ALR screen - good for rooms with ambient light but may affect off-axis viewing. " if is_alr else "")
                                   + (f"With {gain} gain, no brightness compensation needed." if gain >= 1.0
                                      else f"With {gain} gain, increase projector brightness to compensate for light loss.")
                })

                if is_at:
                    recs.append({
                        "severity": "info",
                        "title": "Acoustically Transparent Screen Detected",
                        "description": "Place your front L/C/R speakers directly behind the screen for phantom-free "
                                       "center channel and seamless sound-to-image integration. AT screens typically "
                                       "have slightly lower gain than solid screens."
                    })

            recs.append({
                "severity": "info",
                "title": f"{display_name} Optimization Guide",
                "description": f"Review the display settings below for recommended picture modes, HDR calibration, "
                               "and projector-specific settings. Settings are tailored to this specific display model."
            })

        else:
            # TV-specific
            recs.append({
                "severity": "info",
                "title": f"{display_name} Settings",
                "description": "Review the display settings below for recommended picture modes and HDR calibration."
            })

        return {"recommendations": recs, "display_settings": display_settings}

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
        optimized["_optimized_by"] = "AV Signal Lab"

        return optimized


# =============================================================================
# Pre-roll Video Analyzer
# =============================================================================

class PrerollAnalyzer:
    """Analyzes video files for format compatibility with main library content."""

    # Common library content formats
    TARGET_FORMATS = {
        "4k_hdr10_24": {
            "name": "4K HDR10 23.976fps (Movies)",
            "width": 3840, "height": 2160, "fps": 23.976,
            "hdr": True, "color_transfer": "smpte2084",
            "description": "Most common format for 4K HDR movies"
        },
        "4k_hdr10_60": {
            "name": "4K HDR10 60fps (Gaming/UI)",
            "width": 3840, "height": 2160, "fps": 60,
            "hdr": True, "color_transfer": "smpte2084",
            "description": "For gaming or menu/UI content"
        },
        "4k_sdr_24": {
            "name": "4K SDR 23.976fps (Movies)",
            "width": 3840, "height": 2160, "fps": 23.976,
            "hdr": False, "color_transfer": "bt709",
            "description": "For 4K SDR movie libraries"
        },
        "1080p_sdr_24": {
            "name": "1080p SDR 23.976fps (Movies)",
            "width": 1920, "height": 1080, "fps": 23.976,
            "hdr": False, "color_transfer": "bt709",
            "description": "For 1080p movie libraries"
        },
        "1080p_hdr10_24": {
            "name": "1080p HDR10 23.976fps (Movies)",
            "width": 1920, "height": 1080, "fps": 23.976,
            "hdr": True, "color_transfer": "smpte2084",
            "description": "Rare, but some content is mastered this way"
        }
    }

    def __init__(self, file_path):
        self.file_path = file_path
        self.metadata = None
        self.ffprobe_path = get_ffprobe_path()
        self.ffmpeg_path = get_ffmpeg_path()

    def analyze(self, target_format=None):
        """Analyze video file using FFprobe."""
        if not self.ffprobe_path:
            # Provide more helpful error with install instructions
            install_hint = ""
            if platform.system() == "Windows":
                install_hint = " Run: winget install -e --id Gyan.FFmpeg then restart your terminal."
            elif platform.system() == "Darwin":
                install_hint = " Run: brew install ffmpeg"
            else:
                install_hint = " Run: sudo apt install ffmpeg (Debian/Ubuntu) or equivalent."

            return {
                "error": f"FFprobe not found. Install FFmpeg to analyze video files.{install_hint}",
                "ffprobe_available": False,
                "ffprobe_path": None,
                "install_hint": install_hint.strip()
            }

        try:
            self.metadata = self._get_metadata()
            return self._analyze_metadata(target_format)
        except Exception as e:
            return {
                "error": str(e),
                "ffprobe_available": True,
                "ffprobe_path": self.ffprobe_path
            }

    def _get_metadata(self):
        """Extract metadata using FFprobe."""
        cmd = [
            self.ffprobe_path,
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

    def _analyze_metadata(self, target_format=None):
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

        # Get target format details if specified
        target = self.TARGET_FORMATS.get(target_format) if target_format else None

        # Resolution analysis
        is_4k = width >= 3840 and height >= 2160
        if target:
            if width != target["width"] or height != target["height"]:
                issues.append({
                    "severity": "warning",
                    "title": "Resolution Mismatch",
                    "description": f"Pre-roll is {width}x{height} but target is {target['width']}x{target['height']}. This WILL cause HDMI bonk."
                })
        elif not is_4k:
            issues.append({
                "severity": "warning",
                "title": "Non-4K Resolution",
                "description": f"Video is {width}x{height}. Format switch to 4K content will cause handshake delay."
            })

        # HDR analysis
        if target:
            if target["hdr"] and not is_hdr:
                issues.append({
                    "severity": "critical",
                    "title": "HDR Mismatch",
                    "description": "Pre-roll is SDR but target library is HDR. This WILL cause HDMI bonk."
                })
            elif not target["hdr"] and is_hdr:
                issues.append({
                    "severity": "warning",
                    "title": "HDR Mismatch",
                    "description": "Pre-roll is HDR but target library is SDR. This may cause display mode switch."
                })
        elif not is_hdr:
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
        target_fps = target["fps"] if target else 23.976
        if fps and abs(fps - target_fps) > 0.5:
            issues.append({
                "severity": "info",
                "title": "Frame Rate Mismatch",
                "description": f"Pre-roll is {fps:.3f}fps, target is {target_fps}fps. May trigger refresh rate change."
            })

        if fps and fps not in [23.976, 24, 25, 29.97, 30, 50, 59.94, 60]:
            issues.append({
                "severity": "info",
                "title": "Non-Standard Frame Rate",
                "description": f"Frame rate {fps:.3f} fps may cause compatibility issues."
            })

        # Codec analysis
        if codec not in ["hevc", "h265", "h264", "avc"]:
            issues.append({
                "severity": "info",
                "title": "Uncommon Codec",
                "description": f"Codec '{codec}' may have limited hardware support."
            })

        # Check if already matches target
        matches_target = False
        if target:
            res_match = width == target["width"] and height == target["height"]
            hdr_match = is_hdr == target["hdr"]
            fps_match = abs(fps - target["fps"]) < 0.5 if fps else False
            matches_target = res_match and hdr_match and fps_match
            if matches_target:
                recommendations.append({
                    "title": "Pre-roll Already Matches Target!",
                    "description": f"Your pre-roll already matches {target['name']}. No re-encoding needed."
                })

        # Generate FFmpeg commands for all target formats
        for fmt_key, fmt in self.TARGET_FORMATS.items():
            is_recommended = (fmt_key == target_format) or (not target_format and fmt_key == "4k_hdr10_24")
            ffmpeg_commands.append({
                "format_id": fmt_key,
                "description": fmt["name"] + (" (RECOMMENDED)" if is_recommended else ""),
                "target_description": fmt["description"],
                "command": self._generate_ffmpeg_command(self.file_path, fmt),
                "recommended": is_recommended
            })

        return {
            "ffprobe_available": True,
            "ffprobe_path": self.ffprobe_path,
            "ffmpeg_path": self.ffmpeg_path,
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
            "target_format": target,
            "matches_target": matches_target,
            "issues": issues,
            "recommendations": recommendations,
            "ffmpeg_commands": ffmpeg_commands,
            "available_target_formats": self.TARGET_FORMATS
        }

    def _generate_ffmpeg_command(self, input_file, target_format):
        """Generate FFmpeg command for converting to target format."""
        width = target_format["width"]
        height = target_format["height"]
        fps = target_format["fps"]
        is_hdr = target_format["hdr"]

        # Build output filename
        suffix = f"_{width}x{height}_{'hdr10' if is_hdr else 'sdr'}_{fps}fps"
        output = os.path.splitext(os.path.basename(input_file))[0] + suffix + ".mkv"

        ffmpeg = self.ffmpeg_path or "ffmpeg"

        if is_hdr:
            # HDR10 encoding with proper metadata
            return (
                f'"{ffmpeg}" -i "{input_file}" '
                f'-vf "scale={width}:{height}:flags=lanczos,fps={fps},format=yuv420p10le" '
                f'-c:v libx265 -preset slow -crf 18 '
                f'-x265-params "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:'
                f'max-cll=1000,400:master-display=G(13250,34500)B(7500,3000)R(34000,16000)'
                f'WP(15635,16450)L(10000000,1)" '
                f'-c:a copy '
                f'"{output}"'
            )
        else:
            # SDR encoding with BT.709 color space
            return (
                f'"{ffmpeg}" -i "{input_file}" '
                f'-vf "scale={width}:{height}:flags=lanczos,fps={fps}" '
                f'-c:v libx265 -preset slow -crf 20 '
                f'-colorspace bt709 -color_trc bt709 -color_primaries bt709 '
                f'-c:a copy '
                f'"{output}"'
            )

    def _generate_ffmpeg_4k_hdr(self, input_file):
        """Generate FFmpeg command for 4K HDR10 conversion (legacy)."""
        return self._generate_ffmpeg_command(input_file, self.TARGET_FORMATS["4k_hdr10_24"])

    def _generate_ffmpeg_1080p_sdr(self, input_file):
        """Generate FFmpeg command for 1080p SDR conversion (legacy)."""
        return self._generate_ffmpeg_command(input_file, self.TARGET_FORMATS["1080p_sdr_24"])


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


@app.route("/api/vrroom/diagnose", methods=["POST"])
def vrroom_diagnose_hdr():
    """Diagnose HDR signal chain through Vrroom."""
    data = request.get_json()
    if not data or "ip" not in data:
        return jsonify({"error": "IP address required"}), 400

    ip = data.get("ip")
    port = data.get("port", VrroomConnection.DEFAULT_PORT)

    try:
        connection = VrroomConnection(ip, int(port))
        result = connection.diagnose_hdr_signal_chain()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/vrroom/settings", methods=["POST"])
def vrroom_get_all_settings():
    """Get all Vrroom settings with metadata for UI display."""
    data = request.get_json()
    if not data or "ip" not in data:
        return jsonify({"error": "IP address required"}), 400

    ip = data.get("ip")
    port = data.get("port", VrroomConnection.DEFAULT_PORT)

    try:
        connection = VrroomConnection(ip, int(port))
        result = connection.get_all_settings_detailed()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/vrroom/set", methods=["POST"])
def vrroom_set_setting():
    """Set a single Vrroom setting."""
    data = request.get_json()
    if not data or "ip" not in data or "setting" not in data or "value" not in data:
        return jsonify({"error": "IP, setting, and value required"}), 400

    ip = data.get("ip")
    port = data.get("port", VrroomConnection.DEFAULT_PORT)
    setting = data.get("setting")
    value = data.get("value")

    try:
        connection = VrroomConnection(ip, int(port))
        connection.connect()
        response = connection.set_setting(setting, value)
        connection.disconnect()

        return jsonify({
            "success": True,
            "setting": setting,
            "value": value,
            "response": response
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/manuals")
def get_device_manuals():
    """Get device manual links and references."""
    return jsonify(DEVICE_MANUALS)


@app.route("/api/manuals/<device_id>")
def get_device_manual(device_id):
    """Get manual info for a specific device."""
    manual = DEVICE_MANUALS.get(device_id)
    if not manual:
        return jsonify({"error": "Manual not found"}), 404
    return jsonify(manual)


@app.route("/api/analyze/preroll", methods=["POST"])
def analyze_preroll():
    """Analyze uploaded pre-roll video file."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Get optional target format (e.g., "4k_hdr10_24")
    target_format = request.form.get("target_format")

    filename = f"preroll_{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        analyzer = PrerollAnalyzer(filepath)
        results = analyzer.analyze(target_format=target_format)
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
    """Get device profiles database including custom devices."""
    # Start with built-in profiles
    all_devices = {}
    for category, devices in DEVICE_PROFILES.items():
        all_devices[category] = dict(devices)

    # Merge custom devices from database
    try:
        custom = get_custom_devices()
        for category, devices in custom.items():
            if category not in all_devices:
                all_devices[category] = {}
            all_devices[category].update(devices)
    except Exception:
        pass  # Database might not be available in all contexts

    return jsonify(all_devices)


@app.route("/api/devices/custom", methods=["GET"])
def get_custom_devices_api():
    """Get only custom user-added devices."""
    try:
        return jsonify(get_custom_devices())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/custom", methods=["POST"])
def add_custom_device_api():
    """Add a new custom device."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ["category", "device_id", "name", "device_type"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    specs = data.get("specs", {})
    source_url = data.get("source_url")

    result = add_custom_device(
        category=data["category"],
        device_id=data["device_id"],
        name=data["name"],
        device_type=data["device_type"],
        specs=specs,
        source_url=source_url
    )

    if result["success"]:
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@app.route("/api/devices/custom/<device_id>", methods=["PUT"])
def update_custom_device_api(device_id):
    """Update an existing custom device."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    specs = data.get("specs", {})
    source_url = data.get("source_url")

    result = update_custom_device(device_id, specs, source_url)
    return jsonify(result)


@app.route("/api/devices/custom/<device_id>", methods=["DELETE"])
def delete_custom_device_api(device_id):
    """Delete a custom device."""
    result = delete_custom_device(device_id)
    return jsonify(result)


@app.route("/api/devices/fetch-specs", methods=["POST"])
def fetch_device_specs():
    """Fetch device specifications from a URL (basic scraping)."""
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "URL required"}), 400

    url = data["url"]
    device_type = data.get("device_type", "unknown")

    try:
        import urllib.request
        import urllib.error
        from html.parser import HTMLParser

        # Simple HTML parser to extract text and find specs
        class SpecParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_content = []
                self.in_body = False
                self.current_tag = None
                self.specs = {}

            def handle_starttag(self, tag, attrs):
                self.current_tag = tag
                if tag == 'body':
                    self.in_body = True

            def handle_endtag(self, tag):
                if tag == 'body':
                    self.in_body = False
                self.current_tag = None

            def handle_data(self, data):
                if self.in_body and data.strip():
                    self.text_content.append(data.strip())

        # Fetch the URL
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; VrroomConfigurator/1.0)'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')

        parser = SpecParser()
        parser.feed(html)
        text = ' '.join(parser.text_content)

        # Extract common specs using patterns
        extracted_specs = {
            "source_url": url,
            "extracted": True
        }

        # Resolution patterns
        if '8K' in text or '8k' in text or '7680' in text:
            extracted_specs["max_resolution"] = "8K"
        elif '4K' in text or '4k' in text or '3840' in text or '2160p' in text:
            extracted_specs["max_resolution"] = "4K"
        elif '1440p' in text or '2560' in text:
            extracted_specs["max_resolution"] = "1440p"
        elif '1080p' in text or '1920' in text:
            extracted_specs["max_resolution"] = "1080p"

        # HDR patterns
        hdr_support = []
        if 'Dolby Vision' in text or 'DolbyVision' in text:
            hdr_support.append("Dolby Vision")
        if 'HDR10+' in text or 'HDR10 Plus' in text:
            hdr_support.append("HDR10+")
        if 'HDR10' in text and 'HDR10+' not in text:
            hdr_support.append("HDR10")
        if 'HLG' in text:
            hdr_support.append("HLG")
        if hdr_support:
            extracted_specs["hdr_support"] = hdr_support

        # Refresh rate
        if '144Hz' in text or '144 Hz' in text:
            extracted_specs["max_refresh"] = 144
        elif '120Hz' in text or '120 Hz' in text:
            extracted_specs["max_refresh"] = 120
        elif '60Hz' in text or '60 Hz' in text:
            extracted_specs["max_refresh"] = 60

        # Features
        if 'VRR' in text or 'Variable Refresh Rate' in text:
            extracted_specs["vrr_support"] = True
        if 'ALLM' in text or 'Auto Low Latency' in text:
            extracted_specs["allm_support"] = True
        if 'eARC' in text:
            extracted_specs["earc_support"] = True
        if 'FreeSync' in text:
            extracted_specs["freesync"] = True
        if 'G-Sync' in text or 'G-SYNC' in text:
            extracted_specs["gsync"] = True

        # Audio features
        if 'Dolby Atmos' in text:
            extracted_specs["atmos_support"] = True
        if 'DTS:X' in text or 'DTS-X' in text:
            extracted_specs["dtsx_support"] = True

        # HDMI
        if 'HDMI 2.1' in text:
            extracted_specs["hdmi_version"] = "2.1"
        elif 'HDMI 2.0' in text:
            extracted_specs["hdmi_version"] = "2.0"

        # Panel type
        if 'OLED' in text:
            extracted_specs["panel_tech"] = "OLED"
        elif 'Mini LED' in text or 'MiniLED' in text:
            extracted_specs["panel_tech"] = "Mini LED"
        elif 'QLED' in text:
            extracted_specs["panel_tech"] = "QLED"
        elif 'LED' in text:
            extracted_specs["panel_tech"] = "LED LCD"

        return jsonify({
            "success": True,
            "url": url,
            "specs": extracted_specs,
            "note": "Specs extracted automatically. Please verify accuracy."
        })

    except urllib.error.HTTPError as e:
        return jsonify({"error": f"HTTP error: {e.code}"}), 400
    except urllib.error.URLError as e:
        return jsonify({"error": f"URL error: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to fetch: {str(e)}"}), 500


@app.route("/api/speaker-tuning")
def get_speaker_tuning_guides():
    """Get all speaker tuning guides."""
    return jsonify(SPEAKER_TUNING_GUIDES)


@app.route("/api/speaker-tuning/<guide_id>")
def get_speaker_tuning_guide(guide_id):
    """Get a specific speaker tuning guide."""
    guide = SPEAKER_TUNING_GUIDES.get(guide_id)
    if not guide:
        return jsonify({"error": "Guide not found"}), 404
    return jsonify(guide)


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


@app.route("/api/vrroom/backup", methods=["POST"])
def vrroom_backup():
    """Backup Vrroom settings to a JSON file."""
    data = request.get_json()
    if not data or "ip_address" not in data:
        return jsonify({"error": "IP address required"}), 400

    ip = data["ip_address"]
    port = data.get("port", 2222)

    # Create backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vrroom_backup_{timestamp}.json"
    filepath = os.path.join(app.config['BACKUP_FOLDER'], filename)

    vrroom = VrroomConnection(ip, port)
    result = vrroom.backup_config(filepath)

    if result.get("success"):
        return jsonify({
            "success": True,
            "filename": filename,
            "download_url": f"/api/download/backup/{filename}",
            "backup": result["backup"]
        })
    else:
        return jsonify(result), 500


@app.route("/api/vrroom/apply", methods=["POST"])
def vrroom_apply_settings():
    """Apply settings to Vrroom via IP connection."""
    data = request.get_json()
    if not data or "ip_address" not in data:
        return jsonify({"error": "IP address required"}), 400

    ip = data["ip_address"]
    port = data.get("port", 2222)
    settings = data.get("settings", {})

    if not settings:
        return jsonify({"error": "No settings provided"}), 400

    vrroom = VrroomConnection(ip, port)
    result = vrroom.apply_settings(settings)
    return jsonify(result)


@app.route("/api/vrroom/detect", methods=["POST"])
def vrroom_detect_inputs():
    """Detect connected devices on Vrroom inputs."""
    data = request.get_json()
    if not data or "ip_address" not in data:
        return jsonify({"error": "IP address required"}), 400

    ip = data["ip_address"]
    port = data.get("port", 2222)

    vrroom = VrroomConnection(ip, port)
    result = vrroom.detect_inputs()
    return jsonify(result)


@app.route("/api/download/backup/<filename>")
def download_backup(filename):
    """Download a backup file."""
    filename = os.path.basename(filename)
    filepath = os.path.join(app.config['BACKUP_FOLDER'], filename)

    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route("/api/preroll/encode", methods=["POST"])
def encode_preroll():
    """Re-encode pre-roll to target format (runs FFmpeg on server)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    target_format = request.form.get("target_format", "4k_hdr10_24")

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return jsonify({
            "error": "FFmpeg not found on server. Cannot re-encode.",
            "ffmpeg_available": False
        }), 500

    # Save uploaded file
    input_filename = f"preroll_input_{uuid.uuid4().hex[:8]}_{file.filename}"
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    file.save(input_path)

    # Get target format
    target = PrerollAnalyzer.TARGET_FORMATS.get(target_format)
    if not target:
        os.remove(input_path)
        return jsonify({"error": f"Unknown target format: {target_format}"}), 400

    # Build output path
    suffix = f"_{target['width']}x{target['height']}_{'hdr10' if target['hdr'] else 'sdr'}"
    output_filename = os.path.splitext(file.filename)[0] + suffix + ".mkv"
    output_path = os.path.join(app.config['EXPORT_FOLDER'], output_filename)

    try:
        # Build FFmpeg command
        analyzer = PrerollAnalyzer(input_path)
        cmd = analyzer._generate_ffmpeg_command(input_path, target)

        # Replace output filename in command
        cmd = cmd.rsplit('"', 2)[0] + f'"{output_path}"'

        # Run FFmpeg (this can take a while)
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode != 0:
            return jsonify({
                "error": f"FFmpeg encoding failed: {result.stderr}",
                "command": cmd
            }), 500

        return jsonify({
            "success": True,
            "output_filename": output_filename,
            "download_url": f"/api/download/{output_filename}",
            "target_format": target
        })

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Encoding timed out (10 minute limit)"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)


@app.route("/api/preroll/targets")
def get_preroll_targets():
    """Get available pre-roll target formats."""
    return jsonify(PrerollAnalyzer.TARGET_FORMATS)


@app.route("/api/media-server/<server_id>/preroll-paths")
def get_preroll_paths(server_id):
    """Get pre-roll paths for a specific media server."""
    server = DEVICE_PROFILES["media_servers"].get(server_id)
    if not server:
        return jsonify({"error": f"Unknown media server: {server_id}"}), 404

    return jsonify({
        "server": server_id,
        "name": server["name"],
        "paths": server.get("preroll_paths", {}),
        "config_path": server.get("preroll_config_path", ""),
        "config_notes": server.get("preroll_config_notes", "")
    })


@app.route("/api/media-server/<server_id>/optimizations")
def get_server_optimizations(server_id):
    """Get optimization recommendations for a media server."""
    server = DEVICE_PROFILES["media_servers"].get(server_id)
    if not server:
        return jsonify({"error": f"Unknown media server: {server_id}"}), 404

    return jsonify({
        "server": server_id,
        "name": server["name"],
        "optimization_settings": server.get("optimization_settings", {}),
        "preroll_paths": server.get("preroll_paths", {}),
        "preroll_config_path": server.get("preroll_config_path", ""),
        "preroll_config_notes": server.get("preroll_config_notes", ""),
        "notes": server.get("notes", "")
    })


@app.route("/api/media-servers/all-optimizations")
def get_all_server_optimizations():
    """Get optimization recommendations for all media servers."""
    result = {}
    for server_id, server in DEVICE_PROFILES["media_servers"].items():
        result[server_id] = {
            "name": server["name"],
            "optimization_settings": server.get("optimization_settings", {}),
            "preroll_paths": server.get("preroll_paths", {}),
            "preroll_config_path": server.get("preroll_config_path", ""),
            "preroll_config_notes": server.get("preroll_config_notes", "")
        }
    return jsonify(result)


@app.route("/api/health")
def health_check():
    """Health check endpoint."""
    ffprobe_path = get_ffprobe_path()
    ffmpeg_path = get_ffmpeg_path()
    return jsonify({
        "status": "healthy",
        "ffprobe_available": ffprobe_path is not None,
        "ffprobe_path": ffprobe_path,
        "ffmpeg_available": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path,
        "platform": platform.system(),
        "version": "1.2.0"
    })


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"

    print("\n" + "=" * 60)
    print("  AV Signal Lab - Home Theater Signal Chain Optimizer")
    print("=" * 60)
    print(f"  Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"  Export folder: {app.config['EXPORT_FOLDER']}")
    print(f"  FFprobe available: {shutil.which('ffprobe') is not None}")
    print(f"  Debug mode: {debug}")
    print("=" * 60)
    print("  Starting server at http://localhost:5000")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=debug)
