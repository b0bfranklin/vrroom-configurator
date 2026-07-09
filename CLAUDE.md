# CLAUDE.md - AV Signal Lab Project Guide

## Project Purpose

AV Signal Lab is a **self-contained Electron desktop app** for home theater signal chain
optimization:

1. **Eliminate HDMI "bonk"** - the 2-3 second black screen during HDMI format renegotiation
2. **Propose best-setup configuration** for the user's equipment chain and goals
3. **Analyze existing HDFury VRROOM configurations** (file export, plus read-only live reads)
4. **Backup device settings** with versioned local history
5. **Check firmware updates** for HDFury / AVR / projector (notify + link to official pages)
6. **Download specs and manuals** for the user's equipment

### Phases

- **Phase 1 (current)**: Windows app for ARM64 + x64. Read-only live VRROOM access.
- **Phase 2**: Write configuration changes directly to the VRROOM over IP.
- **Phase 3 (go live / public release)**: supply-chain hardening - code signing, build
  provenance/attestation + SBOM, dependency review gate, SHA-pinned actions, release checksums.
  Dependabot + lockfile + zero-native-modules are already in place; do not regress them.
- **Later**: Android, iOS, macOS, Linux (share `src/core/` + `data/`; mobile via Capacitor-style shell).

## Architecture

- **Electron** (no native modules - must stay that way so Windows ARM64 builds need no
  Visual Studio Build Tools; the user's machine is a Snapdragon Surface).
- `src/core/` - platform-agnostic logic. Keep free of Electron/browser APIs so it can be reused
  on mobile later. Covered by `test/core.test.js` (`npm test`).
- `src/main/` - Electron main process: IPC, dialogs, TCP client, backups, update checks, downloads.
- `src/renderer/` - vanilla HTML/CSS/JS dark-theme UI. Sandboxed, contextIsolation on; all
  privileged work goes through `preload.js` -> IPC.
- `data/*.json` - the knowledge base (device profiles, VRROOM settings metadata, manual URLs,
  EDID presets, goals, speaker tuning guides). Extracted from the legacy Flask app.
- `legacy/` - the previous Python/Flask web app, kept for reference only. Do not extend it.

## VRROOM IP protocol - CRITICAL SAFETY NOTES

Reference: `VRRoom_FW_63/vrroom-rs232-ip-251021.txt`

- Default IP port **2222**. Commands end with `\n`; responses end with `\r\n`.
- **Over IP/Telnet the `#vrroom` header must NOT be sent** (it is RS232-only). The legacy app
  sent the header over TCP - off-spec, suspected cause of device lockups.
- `src/main/vrroomClient.js` enforces: read-only whitelist (`get` targets only), one command in
  flight, 300ms gap, strict timeouts, circuit breaker on consecutive timeouts, socket always
  destroyed. **Never add `set` commands to the whitelist in phase 1.**
- Phase 2 write support must: keep the whitelist model, back up the config before any write,
  require explicit per-batch user confirmation, and give power-cycle guidance after changes.

## Development

```bash
npm install        # deps (electron binary skipped in CI/sandbox via ELECTRON_SKIP_BINARY_DOWNLOAD=1)
npm start          # run app
npm test           # core logic tests (node --test)
npm run dist:win   # build Windows x64 + ARM64 installers (electron-builder)
```

Windows helper scripts: `start-dev.bat`, `build-windows.bat`.

## Key domain knowledge

### Target hardware chain
- Projector: **Epson EH-LS12000b** (no native DV -> needs LLDV-to-HDR10 conversion)
- AVR: **Yamaha RX-A4A**; Source: **Nvidia Shield Pro**; Processor: **HDFury VRROOM**

### Bonk elimination essentials
1. Match pre-roll format to library content (4K HEVC HDR10 23.976fps typical)
2. EDID mode **AutoMix** (stable EDID prevents source re-reads)
3. Unmute delay ~200-250ms (balance pops vs latency)
4. Fixed 4K source output resolution on slow-handshake displays; only fps/HDR change
5. QMS (HDMI 2.1) eliminates bonk natively where supported

### LLDV for non-DV projectors
- EDID AutoMix + DV flag ON + DV mode 1 (custom/X930E LLDV string) + HDR flag ON
- Source outputs LLDV -> VRROOM converts to HDR10 with dynamic-metadata benefit
- After VRROOM config changes: **power cycle the device**

## Conventions

- Plain JS (CommonJS), no TypeScript, no frameworks in the renderer.
- Renderer never gets Node APIs; extend `preload.js` + `main.js` IPC pairs instead.
- All outbound HTTP is notify-and-link oriented: never auto-install firmware.
- New device knowledge goes in `data/devices.json` (same schema as existing entries).
