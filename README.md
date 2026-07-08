# AV Signal Lab

A self-contained desktop app for optimizing your home theater signal chain — with a focus on
**eliminating HDMI bonk** (the 2–3 second black screen during format renegotiation) and getting
the best possible configuration out of an **HDFury VRROOM**, AV receiver, and projector.

Built with Electron. **Phase 1 targets Windows (ARM64 and x64)** with macOS and Linux builds
available from the same codebase; Android/iOS support is planned via a shared-core approach.

## What it does

| Feature | Status |
| --- | --- |
| Best-setup recommendations for your equipment + goals (bonk elimination, LLDV, Atmos, gaming, HDR passthrough) | Phase 1 |
| Analyze VRROOM config exports — issues, severity, comparison against your recommended setup | Phase 1 |
| Versioned local backups of device configs (auto-backup on every analyze) | Phase 1 |
| Firmware update checks for HDFury VRROOM, Yamaha RX-A4A, Epson LS12000 (notify + official link) | Phase 1 |
| Download official specs & manuals for offline reference | Phase 1 |
| **Read-only** live connection to the VRROOM over IP (spec-compliant, whitelisted `get` commands only) | Phase 1 (beta) |
| Write settings directly to the VRROOM | Phase 2 |
| Android / iOS / macOS / Linux apps | Later phases |

## Download & install (easiest)

Grab the latest installer from the repo's **[Releases page](../../releases)**:

| Your PC | File to download |
| --- | --- |
| Windows on ARM (Snapdragon / Surface) | `AV-Signal-Lab-Setup-<version>-arm64.exe` |
| Windows Intel/AMD | `AV-Signal-Lab-Setup-<version>-x64.exe` |
| No-install portable | `AV-Signal-Lab-<version>-portable-<arch>.exe` |

Double-click the Setup file — the installer runs **fully automatically**: installs per-user
(no admin prompt), creates Start Menu + Desktop shortcuts, and launches the app when done.

> The app is not code-signed yet, so Windows SmartScreen may show "Windows protected your PC".
> Click **More info → Run anyway**.

Releases are built automatically by GitHub Actions whenever a `v*` tag is pushed
(see `.github/workflows/release.yml`). You can also trigger a build manually from the
**Actions** tab (workflow_dispatch) and download the installers from the run's artifacts.

## Running from source

Requires [Node.js](https://nodejs.org/) (LTS). No Visual Studio Build Tools, no compilers —
the app has zero native modules, so it builds cleanly on Windows ARM64.

```bat
:: Windows - run in development mode
start-dev.bat

:: Windows - build installers for x64 + ARM64 (output in release\)
build-windows.bat
```

Or manually on any platform:

```bash
npm install
npm start          # run the app
npm test           # run the core logic tests
npm run dist:win   # build Windows installers (x64 + ARM64)
npm run dist       # build for the current platform
```

## Using the app

1. **My Setup** — pick your display, HDMI processor, AVR, speakers, sources, media servers and
   goals, then *Generate Recommendations*. You get prioritized recommendations plus concrete
   settings tables for the VRROOM, your sources, your AVR and your display.
2. **Config Analyzer** — export your config from the VRROOM web UI (CONFIG → EXPORT) and open it
   here. The analyzer flags issues by severity, shows every recognized setting with its web UI
   location, and — if you generated recommendations first — diffs your actual config against the
   recommended one. You can save an auto-corrected "optimized" config for re-import.
   Every opened config is automatically backed up.
3. **Backups** — versioned history of every config; export, re-analyze, or delete.
4. **Firmware Updates** — checks manufacturer pages and links you to official downloads.
   Nothing is ever flashed automatically.
5. **Specs & Manuals** — downloads official PDFs for offline reference.
6. **Live VRROOM (beta)** — reads settings and signal status straight from the device.
   Strictly read-only: only whitelisted `get` commands, sent one at a time with pacing,
   timeouts, and a circuit breaker. Per the HDFury spec, no `#vrroom` header is sent over IP
   (an off-spec header is the suspected cause of lockups with earlier tooling).

## VRROOM safety rules

The live connection can never change a setting in phase 1. It:

- only sends commands from a fixed **read-only whitelist** (`get edidmode`, `get status rx0`, ...)
- sends **one command at a time** with a 300 ms gap
- applies **strict connect/response timeouts** and aborts after 2 consecutive timeouts
- always closes the socket when done

Phase 2 (writing settings) will build on this once reads are proven stable on real hardware.

## Project layout

```
├── src/
│   ├── core/          # Platform-agnostic logic (reusable for mobile later)
│   │   ├── configAnalyzer.js    # VRROOM config analysis + recommended-vs-actual diff
│   │   ├── recommendations.js   # Best-setup engine (bonk, LLDV, audio, gaming, ...)
│   │   ├── settingsPaths.js     # Menu paths for source device settings
│   │   └── data.js              # Knowledge base loader
│   ├── main/          # Electron main process
│   │   ├── main.js              # App + IPC
│   │   ├── vrroomClient.js      # Safe read-only IP client
│   │   ├── backups.js           # Versioned config backups
│   │   ├── updates.js           # Firmware update checker (notify + link)
│   │   └── manuals.js           # Manual/spec downloader
│   └── renderer/      # UI (vanilla HTML/CSS/JS, dark theme)
├── data/              # Device database + VRROOM settings knowledge (JSON)
├── test/              # Core logic tests (node --test)
├── legacy/            # Previous Flask web app (reference)
├── HDfury_EDID_collection/   # EDID binaries (reference data)
├── VRRoom_FW_63/      # VRROOM firmware docs + RS232/IP command reference
└── docs/              # VRROOM manual and guides
```

## Target hardware

Built around (but not limited to) this chain:

- **Projector**: Epson EH-LS12000b (non-native DV → LLDV conversion)
- **AVR**: Yamaha RX-A4A
- **Source**: Nvidia Shield Pro
- **HDMI processor**: HDFury VRROOM

The device database includes 90+ profiles across displays, AVRs, sources, speakers, screens and
media servers.
