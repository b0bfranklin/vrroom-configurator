# Supported Devices Database

This document lists all pre-configured devices in AV Signal Lab. Users can also add custom devices through the web interface.

## What is QMS (Quick Media Switching)?

**QMS (Quick Media Switching)** is an HDMI 2.1 feature that eliminates the "bonk" (black screen during frame rate changes) without needing an HDMI processor. When both your source AND display support QMS, frame rate switching happens seamlessly.

- **Source** (e.g., Xbox Series X, PS5) sends QMS signal
- **Display** (e.g., LG C2/C3 OLED) receives and handles it instantly
- **Result**: No black screen when switching between 24Hz movies and 60Hz menus

If your devices support QMS, you may not need an HDMI processor for bonk elimination!

## Displays

### Projectors

| Device | Type | Native DV | LLDV | Max Res | VRR | QMS | Notes |
|--------|------|-----------|------|---------|-----|-----|-------|
| Epson EH-LS12000b | Laser | No | Yes | 4K@120Hz | No | No | Use LLDV for DV content. 2700 lumens laser. |
| JVC DLA-NZ7 | Laser D-ILA | No | Yes | 4K@120Hz | No | No | E-shift 4K. Frame Adapt HDR. |
| JVC DLA-NZ8 | Laser D-ILA | No | Yes | 4K@120Hz | No | No | Native 4K D-ILA. Frame Adapt HDR. |
| JVC DLA-NZ9 | Laser D-ILA | No | Yes | 8K e-shift | No | No | Flagship JVC. Best LLDV candidate. |
| Sony VPL-XW5000ES | Laser SXRD | No | Yes | 4K@120Hz | No | No | Entry Sony native 4K laser. |
| Sony VPL-XW7000ES | Laser SXRD | No | Yes | 4K@120Hz | No | No | Fast HDMI handshake. Good HDR. |
| BenQ W5800 | Laser DLP | No | Yes | 4K@60Hz | No | No | BenQ laser projector. |
| Optoma UHZ50 | Laser DLP | No | Yes | 4K@60Hz | No | No | Budget 4K laser projector. |

### TVs

| Device | Type | Native DV | LLDV | Max Res | VRR | QMS | Notes |
|--------|------|-----------|------|---------|-----|-----|-------|
| LG C1 OLED | WOLED | Yes | Yes | 4K@120Hz | Yes | Yes | Popular gaming OLED. QMS support. |
| LG C2 OLED | WOLED evo | Yes | Yes | 4K@120Hz | Yes | **Yes** | QMS eliminates bonk natively! |
| LG C3 OLED | WOLED | Yes | Yes | 4K@120Hz | Yes | **Yes** | QMS eliminates bonk natively! |
| LG C4 OLED | WOLED | Yes | Yes | 4K@144Hz | Yes | **Yes** | 2024 C series with QMS. |
| LG G4 OLED | MLA WOLED | Yes | Yes | 4K@144Hz | Yes | **Yes** | Gallery series with QMS. |
| Samsung QN90C | Neo QLED | No | No | 4K@144Hz | Yes | Yes | No DV - use HDR10+. Has QMS. |
| Samsung QN95C | Neo QLED | No | No | 4K@144Hz | Yes | Yes | Flagship Neo QLED with QMS. |
| Samsung S95D | QD-OLED | No | No | 4K@144Hz | Yes | Samsung QD-OLED. No DV. |
| Samsung QN70F 75" | Neo QLED | No | No | 4K@144Hz | Yes | QA75QN70FAWXXY. HDR10+ support. |
| Sony A95K | QD-OLED | Yes | Yes | 4K@120Hz | Yes | Sony QD-OLED. Excellent DV. |
| Sony A95L | QD-OLED | Yes | Yes | 4K@120Hz | Yes | Latest Sony QD-OLED. |
| Sony X95L | Mini LED | Yes | Yes | 4K@120Hz | Yes | Sony flagship Mini LED. |

## HDMI Processors

### HDFury Devices

| Device | Inputs | Outputs | LLDV | VRR | eARC | Notes |
|--------|--------|---------|------|-----|------|-------|
| HDFury Vrroom | 2 | 2 | Yes | Yes | Yes | Full-featured matrix. LLDV injection. |
| HDFury Vertex2 | 2 | 2 | Yes | Yes | No | 18Gbps matrix. Dual display. |
| HDFury Diva | 4 | 2 | Yes | Yes | Yes | 4-input matrix. Dedicated LLDV EDID. |
| HDFury Integral 2 | 2 | 2 | Yes | No | No | Legacy 18Gbps. DV AUTOMIX. |
| HDFury Arcana | 1 | 1 | No | Yes | Yes | eARC adapter for non-eARC AVRs. |
| HDFury AVR-Key | 1 | 1 | Yes | No | No | Audio extractor with LLDV. |

### ESP32 / DIY Alternatives

| Device | Type | VRR | LLDV | Notes |
|--------|------|-----|------|-------|
| ESP32 VRR Injector | DIY | Yes | No | Community VRR injection project. Requires assembly. |
| ESP32 EDID Injector | DIY | No | No | EDID emulator. Low cost HDFury alternative. |
| gofanco EDID Emulator | Commercial | No | No | Budget EDID emulator. 4K60 passthrough. |

## AV Receivers

### Yamaha

| Device | Channels | Room Correction | 4K@120 | VRR | eARC | Notes |
|--------|----------|-----------------|--------|-----|------|-------|
| Yamaha RX-A4A | 9.2 | YPAO | Yes | Yes | Yes | Good HDMI 2.1 passthrough. |
| Yamaha RX-A6A | 11.2 | YPAO | Yes | Yes | Yes | Flagship Yamaha. |

### Denon

| Device | Channels | Room Correction | 4K@120 | VRR | Dirac | Notes |
|--------|----------|-----------------|--------|-----|-------|-------|
| Denon AVR-X3800H | 9.4 | Audyssey XT32 | Yes | Yes | Available | Excellent HDMI 2.1. |
| Denon AVR-X4800H | 11.4 | Audyssey XT32 | Yes | Yes | Available | 11.4ch processing. |
| Denon AVR-X6800H | 11.4 | Audyssey XT32 | Yes | Yes | Included | Flagship Denon. |

### Marantz

| Device | Channels | Room Correction | 4K@120 | VRR | Dirac | Notes |
|--------|----------|-----------------|--------|-----|-------|-------|
| Marantz Cinema 50 | 9.4 | Audyssey XT32 | Yes | Yes | Available | Premium audio processing. |
| Marantz Cinema 60 | 11.4 | Audyssey XT32 | Yes | Yes | Available | Flagship Marantz. |

### Other Brands

| Device | Channels | Room Correction | 4K@120 | VRR | Notes |
|--------|----------|-----------------|--------|-----|-------|
| Sony STR-AN1000 | 7.1.2 | D.C.A.C. IX | Yes | Yes | Budget HDMI 2.1 AVR. |
| Anthem MRX 1140 | 11.2 | ARC Genesis | Yes | Yes | Premium processor. |
| Onkyo TX-RZ70 | 11.2 | Dirac Live | Yes | Yes | THX Certified. |
| Integra DRX-8.4 | 11.4 | Dirac Live | Yes | Yes | Custom integrator focused. |

## Sources

### Gaming Consoles

| Device | Max Resolution | HDR | DV | VRR | Notes |
|--------|----------------|-----|----|----|-------|
| Xbox Series X | 4K@120Hz | HDR10 | Yes | Yes | Full-featured gaming. |
| Xbox Series S | 1440p@120Hz | HDR10 | Yes | Yes | Digital-only Xbox. |
| Xbox One X | 4K@60Hz | HDR10 | Yes | Yes | 4K capable. DV via update. |
| Xbox One S | 4K@60Hz | HDR10 | Yes | Yes | 4K media, upscaled gaming. |
| Xbox One | 1080p@60Hz | No | No | No | Original Xbox One. |
| Xbox 360 | 1080p@60Hz | No | No | No | Legacy console. |
| PlayStation 5 | 4K@120Hz | HDR10 | No | Yes | VRR via update. |
| PlayStation 4 Pro | 4K@60Hz | HDR10 | No | No | 4K upscaled gaming. |
| PlayStation 4 | 1080p@60Hz | HDR10 | No | No | HDR10 supported. |
| PlayStation 3 | 1080p@60Hz | No | No | No | Legacy console. |
| Nintendo Switch | 1080p@60Hz | No | No | No | Docked mode only. |
| Nintendo Switch OLED | 1080p@60Hz | No | No | No | Improved dock with LAN. |
| Nintendo Switch 2 | 4K@60Hz | HDR10 | No | Yes | Next-gen Nintendo. |

### Media Players

| Device | Max Resolution | DV | LLDV | HDR10+ | Notes |
|--------|----------------|----|----- |--------|-------|
| Nvidia Shield Pro | 4K@60Hz | Yes | Yes | No | Match frame rate recommended. |
| Nvidia Shield TV 2019 | 4K@60Hz | Yes | Yes | No | Tube version. |
| Nvidia Shield TV 2017 | 4K@60Hz | Yes | Yes | No | DV via software update. |
| Nvidia Shield TV 2015 | 4K@60Hz | No | No | No | Legacy. HDR10 only. |
| Apple TV 4K (2024) | 4K@60Hz | Yes | Yes | No | A15 chip. Thread support. |
| Apple TV 4K (2022) | 4K@60Hz | Yes | Yes | No | A15 chip. Match content. |
| Apple TV 4K (2021) | 4K@60Hz | Yes | Yes | No | A12 chip. |
| Apple TV HD | 1080p@60Hz | No | No | No | No HDR support. |
| Chromecast Google TV 4K | 4K@60Hz | Yes | No | Yes | Budget 4K streamer. |
| Fire TV Stick 4K Max | 4K@60Hz | Yes | No | Yes | Wi-Fi 6E. DV and HDR10+. |
| Fire TV Cube 3rd Gen | 4K@60Hz | Yes | No | Yes | Hands-free Alexa. HDMI input. |
| Roku Ultra 2024 | 4K@60Hz | Yes | No | Yes | DV and HDR10+. |

### Homatics Players

| Device | Max Resolution | DV | LLDV | HDR10+ | Processor | Notes |
|--------|----------------|----|----- |--------|-----------|-------|
| Homatics Box R 4K Plus | 4K@60Hz | Yes | Yes | Yes | S905X4-K | Certified DV. VS10 engine. Excellent for Plex. |
| Homatics Box R 4K | 4K@60Hz | Yes | Yes | Yes | S905X4 | DV certified. Wi-Fi 5. |
| Homatics Dongle G 4K | 4K@60Hz | Yes | No | No | - | Compact dongle. Google TV. |

### Zidoo Players

| Device | Max Resolution | DV | LLDV | HDR10+ | Notes |
|--------|----------------|----|----- |--------|-------|
| Zidoo Z9X Pro | 4K@60Hz | Yes | Yes | Yes | VS10 engine. Excellent format switching. |
| Zidoo Z9X | 4K@60Hz | Yes | Yes | Yes | VS10 for DV. NAS playback. |
| Zidoo Z2000 Pro | 4K@60Hz | Yes | Yes | Yes | Flagship. Internal HDD bay. |

### Other Sources

| Device | Max Resolution | DV | Notes |
|--------|----------------|----|----- |
| Raspberry Pi 5 | 4K@60Hz | No | LibreELEC/OSMC. No HDCP. |
| Raspberry Pi 4 | 4K@60Hz | No | Dual HDMI. No HDCP. |
| Panasonic UB9000 | 4K@60Hz | Yes | Reference UHD Blu-ray. HDR optimizer. |
| Sony UBP-X800M2 | 4K@60Hz | Yes | Mid-range UHD player. SACD. |
| Kaleidescape Strato | 4K@60Hz | Yes | Premium. Vrroom repeater mode. |

## Speaker Configurations

| Layout | Atmos | DTS:X | Overhead | Notes |
|--------|-------|-------|----------|-------|
| 2.0 Stereo | No | No | 0 | Basic stereo. PCM only. |
| 5.1 Surround | No | No | 0 | Standard surround. |
| 7.1 Surround | No | No | 0 | Extended surround. |
| 5.1.2 Atmos | Yes | Yes | 2 | Entry Atmos. |
| 5.2.2 Atmos | Yes | Yes | 2 | Dual subs for even bass. |
| 5.1.4 Atmos | Yes | Yes | 4 | Full height coverage. |
| 7.1.4 Atmos | Yes | Yes | 4 | Full immersive audio. |
| 7.2.4 Atmos | Yes | Yes | 4 | Reference theater. Dual subs. |
| 9.1.6 Atmos | Yes | Yes | 6 | Premium theater. |

## Projector Screens

| Brand | Material | Gain | AT | ALR | Notes |
|-------|----------|------|----|----|-------|
| Grandview Flocked Fixed Frame | Matt White | 1.0 | No | No | ISF certified. 160° viewing angle. 80mm frame. |
| Screen Innovations | Various | Varies | Available | Available | Premium screens. |
| Stewart Filmscreen | Various | Varies | Available | Available | Reference quality. |
| Elite Screens | Various | 1.0-1.3 | Available | No | Budget-friendly. |
| Silver Ticket | Grey/White | 1.0-1.1 | No | No | Value option. |

## Adding Custom Devices

Users can add their own devices through the web interface:

1. Go to **Device Database** tab
2. Click **Add Custom Device**
3. Fill in device details or paste a URL to auto-extract specs
4. Device is saved locally and persists across sessions

### Spec Extraction from URLs

When adding a device, you can provide a manufacturer URL. The system will attempt to extract:
- Resolution support (4K, 8K, 1080p)
- HDR formats (Dolby Vision, HDR10, HDR10+, HLG)
- Refresh rates (60Hz, 120Hz, 144Hz)
- Gaming features (VRR, ALLM, FreeSync, G-Sync)
- Audio support (Dolby Atmos, DTS:X)
- HDMI version
- Panel technology

**Note:** Auto-extracted specs should be verified manually.

## Community Contributions

To suggest new devices for the default database:
1. Open an issue on GitHub with device specifications
2. Include source links for verification
3. Devices will be added in future updates

## Sources

- [Samsung QN70F Specifications](https://www.samsung.com/us/tvs/neo-qled/)
- [Homatics Box R 4K Plus](https://www.homatics.com/products/box-r-4k-plus)
- [HDFury Product Documentation](https://www.hdfury.com/)
- [Rtings.com](https://www.rtings.com/) - TV and display reviews
- [FlatpanelsHD](https://www.flatpanelshd.com/) - Display database
