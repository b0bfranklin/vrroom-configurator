# User Guide

Complete guide to using Vrroom Configurator for optimizing your HDFury Vrroom setup.

## Table of Contents

- [Overview](#overview)
- [Understanding the Problem](#understanding-the-problem)
- [My Setup Tab](#my-setup-tab)
- [Config Analyzer Tab](#config-analyzer-tab)
- [Pre-roll Analyzer Tab](#pre-roll-analyzer-tab)
- [Device Database Tab](#device-database-tab)
- [EDID Reference Tab](#edid-reference-tab)
- [Workflow Examples](#workflow-examples)
- [FAQ](#faq)
- [Glossary](#glossary)

---

## Overview

Vrroom Configurator is a web-based tool that helps you:

1. **Eliminate "bonk"** - Those 2-3 second black screens when video format changes
2. **Enable LLDV** - Get Dolby Vision on non-DV compatible displays
3. **Fix pre-roll issues** - Ensure your cinema intros play properly
4. **Optimize audio** - Configure eARC and Atmos passthrough correctly

The tool analyzes your equipment, goals, and Vrroom configuration to provide tailored recommendations.

---

## Understanding the Problem

### What is "Bonk"?

"Bonk" is the home theater community term for HDMI handshake delays that cause:
- 2-3 second black screens when switching between content
- Visible only 1 frame of pre-roll video while audio plays
- Delays when switching from SDR to HDR content
- Interruptions when resolution or refresh rate changes

### Why Does It Happen?

When your source (Shield, Apple TV, etc.) sends video in a different format than the previous content, your display must:

1. Detect the new format
2. Negotiate HDCP (copy protection)
3. Re-sync with the new timing
4. Switch to the appropriate picture mode

This process takes 2-3 seconds on most projectors. During this time, video is black but audio continues (because your AVR handles audio separately).

### The Solution

1. **Match pre-roll format to main content** - No format switch = no handshake
2. **Use AutoMix EDID mode** - Provides stable EDID to sources
3. **Optimize unmute delays** - Prevents audio pops without adding latency
4. **Configure LLDV properly** - For Dolby Vision on non-DV displays

---

## My Setup Tab

The My Setup tab is the starting point for most users. It generates personalized recommendations based on your equipment and goals.

### Step 1: Select Your Equipment

Choose your devices from the dropdown menus:

| Field | Description |
|-------|-------------|
| **Display** | Your projector or TV (e.g., Epson EH-LS12000b) |
| **HDFury Device** | Your HDFury processor (e.g., Vrroom) |
| **AV Receiver** | Your AVR (e.g., Yamaha RX-A4A) |
| **Source Device** | Your streaming device (e.g., Nvidia Shield Pro) |
| **Speaker Setup** | Your speaker configuration (e.g., 5.2.2 Atmos) |
| **Media Server** | Your media server (e.g., Plex, Jellyfin, Emby) |

Your selections are saved in your browser, so they persist between visits.

### Step 2: Select Optimization Goals

Check the goals that apply to your situation:

| Goal | When to Select |
|------|---------------|
| **Avoid HDMI Bonk** | You experience black screens during format switches |
| **LLDV on Non-DV Display** | Your projector/TV doesn't support native Dolby Vision |
| **Best Audio Quality** | You want optimal Atmos/DTS:X passthrough |
| **Gaming / Low Latency** | You use the setup for gaming |
| **Fix Pre-roll Visibility** | Pre-roll shows only 1 frame with audio |
| **4K HDR Passthrough** | You want to ensure HDR is working correctly |
| **Minimize Format Switching** | You want the most stable output possible |

### Step 3: Generate Recommendations

Click **Generate Recommendations** to get:

1. **Setup Summary** - Confirmation of your selected equipment
2. **Recommendations** - Color-coded advice based on your setup
   - **Critical** (red) - Must-do items for your goals
   - **Warning** (yellow) - Strongly recommended
   - **Info** (blue) - Good to know
3. **Vrroom Settings** - Specific settings to apply via Vrroom web interface
4. **Source Device Settings** - Settings to configure on your source device

### Understanding Severity Levels

| Severity | Meaning | Action |
|----------|---------|--------|
| Critical | Essential for your goal to work | Apply immediately |
| Warning | Significantly improves results | Apply when possible |
| Info | Additional optimization | Apply if convenient |

---

## Config Analyzer Tab

The Config Analyzer examines your exported Vrroom configuration and identifies issues.

### How to Use

1. **Export your Vrroom config**
   - Open Vrroom web interface (usually http://192.168.x.x)
   - Navigate to CONFIG menu
   - Click EXPORT
   - Save the JSON file

2. **Upload to analyzer**
   - Drag and drop the JSON file onto the dropzone
   - Or click to browse and select the file

3. **Review issues**
   - Critical issues (red) - Likely causing problems
   - Warnings (yellow) - May cause issues
   - Info (blue) - Suggestions for improvement

4. **Download optimized config**
   - Click "Download Optimized Config"
   - The tool applies recommended fixes automatically

5. **Import to Vrroom**
   - Go to CONFIG menu in Vrroom web interface
   - Click IMPORT
   - Select the optimized config file
   - **Power cycle your Vrroom** (unplug, wait 10 seconds, plug back in)

### What It Checks

| Setting | What We Look For |
|---------|-----------------|
| EDID Mode | Should be AutoMix for most setups |
| Unmute Delay | Balance between pops and responsiveness |
| HDR Flags | Properly enabled for HDR passthrough |
| DV Flags | Configured for LLDV if needed |
| CEC | May cause unexpected power cycling |
| HDCP Mode | Should be Auto unless specific issues |

---

## Pre-roll Analyzer Tab

The Pre-roll Analyzer examines your cinema intro video and provides FFmpeg commands to re-encode it.

### How to Use

1. **Upload your pre-roll video**
   - Drag and drop your video file (MP4, MKV, MOV, AVI)
   - Or click to browse and select

2. **Review video information**
   - Resolution, codec, frame rate
   - HDR status, color space
   - Duration and bitrate

3. **Check format issues**
   - Non-4K resolution (causes resolution change handshake)
   - Non-HDR content (causes HDR mode change)
   - Wrong frame rate (causes refresh rate change)

4. **Copy FFmpeg commands**
   - Commands are provided to convert your pre-roll
   - "Convert to 4K HDR10" matches typical movie content
   - "Convert to 4K SDR" for SDR-only setups

### Why Pre-roll Format Matters

Your pre-roll should match your most common library content:

| Your Library | Recommended Pre-roll Format |
|--------------|---------------------------|
| 4K HDR movies | 4K HEVC HDR10 23.976fps |
| 4K SDR movies | 4K HEVC SDR 23.976fps |
| 1080p content | 1080p HEVC SDR 23.976fps |
| Mixed 4K/1080p | 4K HEVC HDR10 23.976fps |

### Example FFmpeg Command

```bash
ffmpeg -i your_preroll.mp4 \
  -c:v libx265 -preset slow -crf 18 \
  -vf "scale=3840:2160:flags=lanczos,format=yuv420p10le" \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \
  -c:a copy \
  preroll_4k_hdr10.mp4
```

---

## Device Database Tab

Browse pre-configured profiles for common home theater equipment.

### Categories

**Displays (Projectors/TVs)**
- Specifications: resolution, refresh rate, HDR support
- Native DV capability
- LLDV compatibility
- Typical handshake times

**HDFury Devices**
- Feature comparison (VRR, eARC, LLDV support)
- Input/output configurations
- ALLM support

**AV Receivers**
- eARC support
- Atmos/DTS:X decoding
- HDMI 2.1 features

**Source Devices**
- Output capabilities
- DV/LLDV output support
- Match frame rate features

**Speaker Setups**
- Channel configurations (5.1, 7.1, Atmos layouts)
- Recommended audio settings

**Media Servers**
- Pre-roll support
- Known issues and workarounds

### Using Device Info

Device profiles inform the recommendation engine. If your device isn't listed:
- Select the closest match
- Or select "Not specified" and rely on goal-based recommendations

---

## EDID Reference Tab

Technical reference for EDID modes, Dolby Vision strings, and common commands.

### EDID Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **AutoMix** | Combines sink and custom EDID | Recommended for most setups |
| **Custom** | Uses only custom EDID | Specific capability requirements |
| **Fixed** | Uses fixed internal EDID | Troubleshooting |
| **CopyTX0/TX1** | Copies output sink EDID | Pass-through scenarios |

### DV EDID Strings

For LLDV on non-DV displays, use one of these strings:
- **LG C1** - Good compatibility
- **X930E LLDV** - Best for projectors
- **Custom** - Advanced users

### Key Settings Reference

| Setting | Command | Values |
|---------|---------|--------|
| EDID Mode | `edidmode` | automix, custom, fixed |
| DV Flag | `ediddvflag` | on, off |
| DV Mode | `ediddvmode` | 0 (LG C1), 1 (Custom), 2 (Remove) |
| HDR Flag | `edidhdrflag` | on, off |
| HDR Mode | `edidhdrmode` | 0-4 (various HDR formats) |

---

## Workflow Examples

### Example 1: Fix Pre-roll Bonk on Emby

**Symptoms:** Pre-roll shows 1 frame, then black screen for 3 seconds while audio plays.

**Solution:**

1. Go to **My Setup** tab
2. Select your equipment
3. Check **Avoid HDMI Bonk** and **Fix Pre-roll Visibility**
4. Click **Generate Recommendations**
5. Apply Vrroom Settings via web interface
6. Go to **Pre-roll Analyzer** tab
7. Upload your current pre-roll
8. Copy the "Convert to 4K HDR10" FFmpeg command
9. Re-encode your pre-roll
10. Replace in your media server

### Example 2: Enable LLDV on Epson Projector

**Symptoms:** DV content plays as HDR10, want dynamic metadata benefits.

**Solution:**

1. Go to **My Setup** tab
2. Select your Epson projector (non-native DV)
3. Select Vrroom as HDFury device
4. Check **LLDV on Non-DV Display**
5. Click **Generate Recommendations**
6. Apply settings:
   - EDID Mode: AutoMix
   - DV Flag: On
   - DV Mode: 1 (Custom/LLDV)
7. In Vrroom EDID page, select "X930E LLDV" from DV dropdown
8. Power cycle Vrroom
9. Verify source now shows LLDV output option

### Example 3: Optimize for Gaming and Movies

**Symptoms:** Want low latency for gaming but best quality for movies.

**Solution:**

1. Go to **My Setup** tab
2. Select your equipment (include gaming source)
3. Check **Gaming / Low Latency** and **Avoid HDMI Bonk**
4. Click **Generate Recommendations**
5. Apply settings that work for both use cases
6. Note: Some optimizations conflict - low unmute delay is better for gaming, higher is better for audio quality

---

## FAQ

### General Questions

**Q: Do I need RS232/IP connection to use this tool?**

A: No. All settings can be applied via the Vrroom web interface. The tool generates recommendations; you apply them manually.

**Q: Will this work with other HDFury devices?**

A: The My Setup tab has profiles for Vrroom, Diva, Vertex, and Integral. Config Analyzer is specific to Vrroom JSON exports.

**Q: How often should I re-analyze my config?**

A: After firmware updates or if you notice new issues. Otherwise, once optimized, settings should remain stable.

### Pre-roll Questions

**Q: What resolution should my pre-roll be?**

A: Match your most common library content. For 4K HDR movies, use 4K HDR10. The goal is zero format changes.

**Q: Can I use DV for pre-roll?**

A: DV pre-rolls work but are harder to create. HDR10 is recommended for simplicity and compatibility.

**Q: My pre-roll is 6 seconds but I only see 1 frame. Why?**

A: The display is performing a 2-3 second handshake. By the time it's done, the pre-roll is almost over. Re-encode to match main content format.

### LLDV Questions

**Q: What's the difference between LLDV and regular DV?**

A: LLDV (Low Latency Dolby Vision) uses a simpler profile that can be converted to HDR10 while preserving dynamic metadata intent. It's designed for TVs/projectors without native DV support.

**Q: Will LLDV look as good as native DV?**

A: Very close. You get dynamic metadata benefits, which is the main advantage of DV over HDR10. The conversion preserves most quality.

**Q: My Shield shows DV but my projector shows HDR10. Is that right?**

A: Yes! That's LLDV working correctly. Shield outputs LLDV (a DV format), Vrroom converts it to HDR10 with optimized tone mapping for your projector.

### Troubleshooting

**Q: I applied all recommendations but still have bonk.**

A: Check:
1. Pre-roll format matches main content
2. Source is set to fixed 4K output
3. Match Frame Rate is enabled (causes minimal delay)
4. Power cycled Vrroom after config import

**Q: eARC isn't working after changes.**

A: Ensure:
1. eARC device (AVR) powers on before source
2. eARC mode is set to "Auto eARC" in Vrroom
3. eARC cable is plugged into correct HDMI port

**Q: I see purple/green artifacts with LLDV.**

A: This can indicate HDCP issues. Ensure:
1. HDCP mode is set to Auto
2. All HDMI cables are HDMI 2.1 certified
3. No incompatible splitters in chain

---

## Glossary

| Term | Definition |
|------|------------|
| **Bonk** | Community term for HDMI handshake delays causing black screens |
| **EDID** | Extended Display Identification Data - tells sources what the display supports |
| **eARC** | Enhanced Audio Return Channel - high-bandwidth audio over HDMI |
| **HDR10** | Standard HDR format with static metadata |
| **HDR10+** | HDR format with dynamic metadata (Samsung) |
| **LLDV** | Low Latency Dolby Vision - DV profile convertible to HDR10 |
| **ALLM** | Auto Low Latency Mode - automatic game mode switching |
| **VRR** | Variable Refresh Rate - for smooth gaming |
| **AutoMix** | Vrroom EDID mode combining sink capabilities with custom additions |
| **Handshake** | HDMI negotiation between source and display |
| **Pre-roll** | Cinema intro video played before movies |
| **Sink** | The receiving device (display or next device in chain) |
| **Source** | The sending device (streaming box, game console, etc.) |

---

## Need More Help?

- **HDFury Vrroom Manual**: https://www.hdfury.com/docs/HDfuryVRRoom.pdf
- **RS232 Command Reference**: See `VRRoom_FW_63/vrroom-rs232-ip-251021.txt`
- **Firmware Notes**: See `VRRoom_FW_63/ReadMeFirst.txt`
