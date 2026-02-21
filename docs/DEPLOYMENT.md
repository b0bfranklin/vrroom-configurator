# Deployment Guide

This guide covers installation and deployment options for Vrroom Configurator.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Native Installation](#native-installation)
- [Docker Installation](#docker-installation)
- [Configuration](#configuration)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

- **Python 3.8+** (for native installation)
- **Docker & Docker Compose** (for container installation)

### Optional

- **FFmpeg/FFprobe** - Required for pre-roll video analysis
  - Without FFprobe, the Pre-roll Analyzer tab will return errors
  - Config analysis and My Setup features work without FFprobe

### Checking Prerequisites

```bash
# Check Python version
python3 --version

# Check FFprobe availability
ffprobe -version

# Check Docker (if using containers)
docker --version
docker-compose --version
```

---

## Quick Start

### Option A: Platform Launchers (Recommended for first-time users)

**Linux/macOS:**
```bash
git clone https://github.com/yourusername/vrroom-configurator.git
cd vrroom-configurator
chmod +x start-unix.sh
./start-unix.sh
```

**Windows:**
```cmd
git clone https://github.com/yourusername/vrroom-configurator.git
cd vrroom-configurator
start-windows.bat
```

The launcher scripts automatically:
1. Create a Python virtual environment
2. Install all dependencies
3. Start the Flask server on port 5000

Open your browser to **http://localhost:5000**

### Option B: Docker (Recommended for servers)

```bash
git clone https://github.com/yourusername/vrroom-configurator.git
cd vrroom-configurator
docker-compose up -d
```

Open your browser to **http://localhost:5000**

---

## Native Installation

### Step-by-Step Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/vrroom-configurator.git
   cd vrroom-configurator
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   ```

3. **Activate the virtual environment**

   Linux/macOS:
   ```bash
   source venv/bin/activate
   ```

   Windows:
   ```cmd
   venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Install FFmpeg (optional, for pre-roll analysis)**

   Ubuntu/Debian:
   ```bash
   sudo apt update && sudo apt install ffmpeg
   ```

   macOS (Homebrew):
   ```bash
   brew install ffmpeg
   ```

   Windows:
   - Download from https://ffmpeg.org/download.html
   - Add to system PATH

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the web interface**

   Open http://localhost:5000 in your browser.

### Running as a Background Service

**Linux (systemd):**

Create `/etc/systemd/system/vrroom-configurator.service`:
```ini
[Unit]
Description=Vrroom Configurator
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/vrroom-configurator
Environment=FLASK_DEBUG=0
ExecStart=/path/to/vrroom-configurator/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vrroom-configurator
sudo systemctl start vrroom-configurator
```

---

## Docker Installation

### Using Docker Compose (Recommended)

1. **Clone and start**
   ```bash
   git clone https://github.com/yourusername/vrroom-configurator.git
   cd vrroom-configurator
   docker-compose up -d
   ```

2. **View logs**
   ```bash
   docker-compose logs -f
   ```

3. **Stop the service**
   ```bash
   docker-compose down
   ```

### Using Docker Directly

1. **Build the image**
   ```bash
   docker build -t vrroom-configurator .
   ```

2. **Run the container**
   ```bash
   docker run -d \
     --name vrroom-configurator \
     -p 5000:5000 \
     -v $(pwd)/uploads:/app/uploads \
     -v $(pwd)/exports:/app/exports \
     vrroom-configurator
   ```

### Docker Compose Configuration

The default `docker-compose.yml`:

```yaml
services:
  vrroom-configurator:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./uploads:/app/uploads
      - ./exports:/app/exports
    environment:
      - FLASK_DEBUG=0
    restart: unless-stopped
```

**Customization options:**

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode (development only) |
| Port mapping | `5000:5000` | Change left side to use different host port |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_DEBUG` | `1` (dev) / `0` (Docker) | Enable Flask debug mode |
| `PORT` | `5000` | Port to listen on (native only) |

### File Storage

The application uses two directories for file storage:

| Directory | Purpose | Auto-created |
|-----------|---------|--------------|
| `uploads/` | Temporary storage for uploaded files | Yes |
| `exports/` | Generated optimized config files | Yes |

Both directories are created automatically on first run.

### Port Configuration

**Native:** Edit the last line of `app.py`:
```python
app.run(host="0.0.0.0", port=5000, debug=...)
```

**Docker:** Change port mapping in `docker-compose.yml`:
```yaml
ports:
  - "8080:5000"  # Access via port 8080
```

---

## Production Deployment

### Security Considerations

1. **Disable debug mode**
   ```bash
   export FLASK_DEBUG=0
   ```

2. **Use a reverse proxy** (nginx, Caddy, etc.)

   Example nginx configuration:
   ```nginx
   server {
       listen 80;
       server_name vrroom.yourdomain.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           client_max_body_size 100M;  # For video uploads
       }
   }
   ```

3. **Enable HTTPS** via your reverse proxy or use Caddy for automatic certificates

4. **Restrict network access** if running on home network only
   - Use firewall rules to limit access
   - Consider VPN for remote access

### Using Gunicorn (Production WSGI Server)

1. **Install Gunicorn**
   ```bash
   pip install gunicorn
   ```

2. **Run with Gunicorn**
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

3. **Add to systemd service**
   ```ini
   ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

### Resource Requirements

| Deployment | RAM | CPU | Disk |
|------------|-----|-----|------|
| Minimum | 256MB | 1 core | 100MB |
| Recommended | 512MB | 2 cores | 500MB |
| With video analysis | 1GB | 2 cores | 1GB+ |

---

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Find what's using port 5000
lsof -i :5000

# Kill the process or use a different port
```

**FFprobe not found:**
```
Error: FFprobe is not installed or not in PATH
```
Solution: Install FFmpeg package (includes ffprobe)

**Permission denied on uploads/exports:**
```bash
chmod 755 uploads exports
```

**Docker: Container exits immediately:**
```bash
# Check logs
docker-compose logs

# Common fix: ensure directories exist
mkdir -p uploads exports
```

**ModuleNotFoundError: No module named 'flask':**
```bash
# Ensure virtual environment is activated
source venv/bin/activate
pip install -r requirements.txt
```

### Verifying Installation

1. **Check the health endpoint:**
   ```bash
   curl http://localhost:5000/api/health
   ```
   Expected: `{"status": "healthy"}`

2. **Check available devices:**
   ```bash
   curl http://localhost:5000/api/devices | python -m json.tool | head -20
   ```

3. **Check optimization goals:**
   ```bash
   curl http://localhost:5000/api/goals | python -m json.tool
   ```

### Getting Help

- Check the [User Guide](USER_GUIDE.md) for usage questions
- Review [CLAUDE.md](../CLAUDE.md) for technical details
- HDFury Vrroom Manual: https://www.hdfury.com/docs/HDfuryVRRoom.pdf

---

## Updating

### Native Installation

```bash
cd vrroom-configurator
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
# Restart the application
```

### Docker

```bash
cd vrroom-configurator
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```
