/**
 * Setup Recommendation Engine.
 * Generates tailored recommendations based on user equipment and optimization
 * goals - the "best setup for the network" engine, with HDMI bonk elimination
 * as the flagship goal. Ported from the legacy Flask app.
 */
const data = require('./data');
const { getSettingsPath } = require('./settingsPaths');
const { describeSetting } = require('./configAnalyzer');

class RecommendationEngine {
  constructor(setup) {
    const devices = data.devices();
    setup = setup || {};

    this.displayId = setup.display || '';
    this.hdfuryId = setup.hdfury_device || '';
    this.avrId = setup.avr || '';
    this.speakerId = setup.speakers || '';
    this.screenId = setup.screen || '';
    this.goals = setup.goals || [];

    // Multiple sources (Vrroom is a 4x2 matrix)
    let sourcesInput = setup.sources || [];
    if (typeof sourcesInput === 'string') sourcesInput = [sourcesInput];
    if (!sourcesInput.length && setup.source) sourcesInput = [setup.source];
    this.sourceIds = sourcesInput.filter(Boolean);
    this.sources = this.sourceIds
      .map((id) => [id, devices.sources[id]])
      .filter(([, p]) => p);
    this.sourceId = this.sourceIds[0] || '';
    this.source = this.sources.length ? this.sources[0][1] : null;

    // Multiple media servers
    let serversInput = setup.media_servers || [];
    if (typeof serversInput === 'string') serversInput = [serversInput];
    if (!serversInput.length && setup.media_server) serversInput = [setup.media_server];
    this.mediaServerIds = serversInput.filter(Boolean);
    this.mediaServers = this.mediaServerIds
      .map((id) => [id, devices.media_servers[id]])
      .filter(([, p]) => p);
    this.mediaServerId = this.mediaServerIds[0] || '';
    this.mediaServer = this.mediaServers.length ? this.mediaServers[0][1] : null;

    this.display = devices.displays[this.displayId] || null;
    this.hdfury = devices.hdfury_devices[this.hdfuryId] || null;
    this.avr = devices.avrs[this.avrId] || null;
    this.speakers = devices.speakers[this.speakerId] || null;
    this.screen = devices.screens[this.screenId] || null;
  }

  generate() {
    let recommendations = [];
    const vrroomSettings = {};
    let sourceSettings = [];

    const goalHandlers = {
      avoid_bonk: () => this.goalAvoidBonk(),
      lldv_non_dv: () => this.goalLldvNonDv(),
      best_audio: () => this.goalBestAudio(),
      gaming_low_latency: () => this.goalGamingLowLatency(),
      fix_preroll: () => this.goalFixPreroll(),
      hdr_passthrough: () => this.goalHdrPassthrough(),
      minimize_format_switch: () => this.goalMinimizeFormatSwitch(),
    };

    for (const goalId of this.goals) {
      const handler = goalHandlers[goalId];
      if (handler) {
        const result = handler();
        recommendations.push(...(result.recommendations || []));
        Object.assign(vrroomSettings, result.vrroom_settings || {});
        sourceSettings.push(...(result.source_settings || []));
      }
    }

    const general = this.generalEquipmentRecs();
    recommendations.push(...(general.recommendations || []));
    Object.assign(vrroomSettings, general.vrroom_settings || {});
    sourceSettings.push(...(general.source_settings || []));

    const avrResult = this.avrConfigRecs();
    recommendations.push(...(avrResult.recommendations || []));
    const avrSettings = avrResult.avr_settings || [];

    const displayResult = this.displayConfigRecs();
    recommendations.push(...(displayResult.recommendations || []));
    const displaySettings = displayResult.display_settings || [];

    // Deduplicate by title / (setting, device)
    const seenRecs = new Set();
    recommendations = recommendations.filter((r) => {
      if (seenRecs.has(r.title)) return false;
      seenRecs.add(r.title);
      return true;
    });
    const seenSrc = new Set();
    sourceSettings = sourceSettings.filter((s) => {
      const key = `${s.setting}|${s.device || ''}`;
      if (seenSrc.has(key)) return false;
      seenSrc.add(key);
      return true;
    });

    const goalsMeta = data.optimizationGoals();

    return {
      setup_summary: {
        display: this.display ? this.display.name : 'Not specified',
        hdfury_device: this.hdfury ? this.hdfury.name : 'Not specified',
        avr: this.avr ? this.avr.name : 'Not specified',
        sources: this.sources.length ? this.sources.map(([, s]) => s.name) : ['Not specified'],
        speakers: this.speakers ? this.speakers.name : 'Not specified',
        screen: this.screen ? this.screen.name : 'Not specified',
        media_servers: this.mediaServers.length
          ? this.mediaServers.map(([, s]) => s.name)
          : ['Not specified'],
        goals: this.goals.filter((g) => goalsMeta[g]).map((g) => goalsMeta[g].name),
      },
      recommendations,
      vrroom_settings: vrroomSettings,
      vrroom_settings_detailed: Object.entries(vrroomSettings).map(([k, v]) =>
        describeSetting(k, v)
      ),
      source_settings: sourceSettings,
      avr_settings: avrSettings,
      display_settings: displaySettings,
    };
  }

  // ---------------------------------------------------------------- goals

  goalAvoidBonk() {
    const recs = [];
    const settings = {};
    const src = [];

    recs.push({
      severity: 'critical',
      title: 'Match Pre-roll Format to Library Content',
      description:
        'The primary cause of bonk is format mismatch between pre-roll and main content. ' +
        'Encode your pre-roll at the same resolution, frame rate, HDR format, and codec as ' +
        'your most common library content (typically 4K HEVC HDR10 23.976fps).',
    });

    settings.edidmode = 'automix';

    let unmute = 200;
    if (this.avr && (this.avr.handshake_time_ms || 0) > 500) unmute = 250;
    settings.unmutedelay = unmute;
    recs.push({
      severity: 'warning',
      title: `Set Unmute Delay to ${unmute}ms`,
      description:
        'Balance between audio pop prevention and responsiveness. ' +
        `Start at ${unmute}ms and reduce if no audio pops occur.`,
    });

    if (this.display && (this.display.handshake_time_ms || 0) >= 2500) {
      recs.push({
        severity: 'warning',
        title: 'Consider Fixed Output Resolution',
        description:
          'Your display has a slow handshake. Consider setting your source to always ' +
          'output 4K to avoid resolution-change-triggered handshakes. Only frame rate ' +
          'and HDR mode should change.',
      });
      for (const [sourceId, source] of this.sources) {
        src.push({
          setting: `Output Resolution (${source.name || 'Source'})`,
          value: '4K (fixed)',
          device: source.name || 'Source',
          reason: 'Prevents resolution-change handshake delays on slow displays.',
          path: getSettingsPath(sourceId, 'resolution'),
        });
      }
    }

    if (this.mediaServer) {
      recs.push({
        severity: 'info',
        title: `Pre-roll Format for ${this.mediaServer.name || 'media server'}`,
        description:
          'Encode pre-roll as 4K HEVC HDR10 23.976fps to match typical movie content. ' +
          'This prevents the format switch that causes bonk between pre-roll and feature.',
      });
    }

    return { recommendations: recs, vrroom_settings: settings, source_settings: src };
  }

  goalLldvNonDv() {
    const recs = [];
    const settings = {};

    if (this.display && this.display.native_dv) {
      recs.push({
        severity: 'info',
        title: 'Display Has Native Dolby Vision',
        description:
          `${this.display.name || 'Your display'} already supports DV natively. ` +
          'LLDV conversion is not required, but Vrroom can still pass DV through.',
      });
      settings.ediddvflag = 'on';
      return { recommendations: recs, vrroom_settings: settings, source_settings: [] };
    }

    if (this.hdfury && !this.hdfury.lldv_support) {
      recs.push({
        severity: 'critical',
        title: 'HDFury Device Does Not Support LLDV',
        description:
          `${this.hdfury.name || 'Your HDFury device'} does not support LLDV injection. ` +
          'Consider upgrading to Vrroom or Diva for LLDV capability.',
      });
      return { recommendations: recs, vrroom_settings: {}, source_settings: [] };
    }

    settings.edidmode = 'automix';
    settings.ediddvflag = 'on';
    settings.ediddvmode = 1; // Custom mode for LLDV
    settings.edidhdrflag = 'on';
    settings.edidhdrmode = 1; // HDR10/HLG

    const displayName = this.display ? this.display.name : 'your display';
    recs.push({
      severity: 'critical',
      title: 'Enable LLDV in AutoMix Mode',
      description:
        'Set EDID to AutoMix with DV flag enabled and LLDV-compatible string (X930E). ' +
        `This tells sources to output LLDV, which Vrroom converts to HDR10 for ${displayName}.`,
    });
    recs.push({
      severity: 'warning',
      title: 'Select LLDV DV String',
      description:
        "On the Vrroom EDID page, under AutoMix > DV dropdown, select 'X930E LLDV' string. " +
        'This is the recommended LLDV string for non-DV projectors.',
    });
    recs.push({
      severity: 'info',
      title: 'LLDV Under VRR Signals',
      description:
        'LLDV>HDR injection is supported under VRR signals since firmware 0.51, ' +
        'though some Samsung TVs may have issues.',
    });

    if (this.source && this.source.lldv_output) {
      recs.push({
        severity: 'info',
        title: `${this.source.name || 'Source'} Supports LLDV Output`,
        description:
          'This source can output LLDV natively. Once EDID is configured, ' +
          'it will automatically output LLDV when DV content is played.',
      });
    } else if (this.source && !this.source.dv_output) {
      recs.push({
        severity: 'warning',
        title: 'Source Has No DV Output',
        description:
          `${this.source.name || 'Your source'} does not support Dolby Vision output. ` +
          'Content will fall back to HDR10.',
      });
    }

    return { recommendations: recs, vrroom_settings: settings, source_settings: [] };
  }

  goalBestAudio() {
    const recs = [];
    const settings = {};
    const src = [];

    const hasAtmos = this.speakers && this.speakers.atmos_capable;
    const hasEarcAvr = this.avr && this.avr.earc_support;
    const hasEarcHdfury = this.hdfury && this.hdfury.earc_support;
    const isSoundbar = this.speakers && this.speakerId.includes('soundbar');

    if (hasEarcAvr && hasEarcHdfury) {
      settings.earcmode = 'auto earc';
      recs.push({
        severity: 'critical',
        title: 'Use eARC for Audio Routing',
        description:
          "Both your AVR and HDFury device support eARC. Set eARC mode to 'Auto eARC' " +
          'for lossless Atmos/DTS:X passthrough. Ensure eARC device powers on before source.',
      });
    } else if (isSoundbar && hasEarcHdfury) {
      settings.earcmode = 'auto earc';
      recs.push({
        severity: 'warning',
        title: 'eARC for Soundbar',
        description:
          'Set eARC mode for soundbar connection. If using ARC-only soundbar, ' +
          "switch to 'Auto ARC' mode instead.",
      });
    }

    if (hasAtmos) {
      for (const [sourceId, source] of this.sources) {
        src.push({
          setting: `Audio Output (${source.name || 'Source'})`,
          value: 'Bitstream (passthrough)',
          device: source.name || 'Source',
          reason: 'Bitstream passes lossless Atmos/DTS:X to AVR for decoding.',
          path: getSettingsPath(sourceId, 'audio'),
        });
      }
      recs.push({
        severity: 'info',
        title: 'Atmos Speaker Layout Detected',
        description:
          `Your ${this.speakers.name || ''} setup supports Atmos. ` +
          'Ensure all sources are set to bitstream output for lossless audio passthrough.',
      });
    }

    if (hasEarcAvr) {
      settings.earcunmute = 200;
      recs.push({
        severity: 'info',
        title: 'eARC Unmute Delay: 200ms',
        description:
          'A small eARC unmute delay prevents audio pops when switching formats. ' +
          'Reduce to 100ms if no pops occur, increase to 300ms if they persist.',
      });
    }

    return { recommendations: recs, vrroom_settings: settings, source_settings: src };
  }

  goalGamingLowLatency() {
    const recs = [];
    const settings = {};
    const src = [];

    const displayVrr = this.display ? !!this.display.vrr_support : false;
    const displayAllm = this.display ? !!this.display.allm_support : false;
    const hdfuryVrr = this.hdfury ? !!this.hdfury.vrr_support : false;
    const hdfuryAllm = this.hdfury ? !!this.hdfury.allm_support : false;

    if (!displayVrr && this.display) {
      recs.push({
        severity: 'warning',
        title: `${this.display.name || 'Your Display'} Does Not Support VRR`,
        description:
          'Your display does not support Variable Refresh Rate (VRR). ' +
          'Gaming will work at fixed refresh rates. VRR passthrough in ' +
          'the Vrroom will have no effect for this display.',
      });
    }

    if (!displayAllm && this.display) {
      recs.push({
        severity: 'info',
        title: `${this.display.name || 'Your Display'} Does Not Support ALLM`,
        description:
          'Auto Low Latency Mode is not supported by your display. ' +
          'You may need to manually switch to game/fast mode on your display when gaming.',
      });
    }

    if (hdfuryVrr && displayVrr) {
      recs.push({
        severity: 'critical',
        title: 'Enable VRR Passthrough',
        description:
          'Both your HDFury device and display support VRR. Enable VRR passthrough ' +
          'for tear-free gaming.',
      });
      settings.edidvrrflag = 'on';
    } else if (hdfuryVrr && !displayVrr) {
      recs.push({
        severity: 'info',
        title: 'VRR Passthrough Available but Display Incompatible',
        description:
          'Your Vrroom supports VRR passthrough but your display does not accept VRR. ' +
          'VRR flag will not be added to EDID.',
      });
    }

    if (hdfuryAllm && displayAllm) {
      settings.edidallmflag = 'on';
      recs.push({
        severity: 'info',
        title: 'ALLM Passthrough Enabled',
        description:
          'ALLM will automatically switch your display to game mode when gaming content is detected.',
      });
    } else if (hdfuryAllm && !displayAllm) {
      recs.push({
        severity: 'info',
        title: 'ALLM Passthrough Available but Display Incompatible',
        description:
          'Your Vrroom supports ALLM passthrough but your display does not support it. ' +
          'Manually switch your display to game/fast mode when gaming.',
      });
    }

    settings.hdrcustom = 'off';
    recs.push({
      severity: 'warning',
      title: 'Disable Custom HDR Injection for Gaming',
      description:
        'Custom HDR injection adds processing overhead. It automatically disables under VRR ' +
        'signals, but explicitly disabling it avoids edge cases.',
    });

    for (const [sourceId, source] of this.sources) {
      if ((source.max_refresh || 0) >= 120) {
        src.push({
          setting: `Output Resolution (${source.name || 'Source'})`,
          value: '4K 120Hz',
          device: source.name || 'Source',
          reason: 'Maximum refresh rate for smoothest gaming.',
          path: getSettingsPath(sourceId, 'resolution'),
        });
      }
    }

    settings.unmutedelay = 100;
    recs.push({
      severity: 'info',
      title: 'Minimize Unmute Delay for Gaming',
      description: 'Set unmute delay to 100ms or lower to minimize audio latency during gaming.',
    });

    return { recommendations: recs, vrroom_settings: settings, source_settings: src };
  }

  goalFixPreroll() {
    const recs = [];
    const settings = {};

    recs.push({
      severity: 'critical',
      title: 'Pre-roll Format Must Match Main Content',
      description:
        'The most common cause of seeing only 1 frame with audio is the display performing an ' +
        'HDMI handshake when switching from pre-roll format to content format. During this ' +
        'handshake (2-3 seconds), the display shows nothing while audio continues from the AVR. ' +
        "Solution: re-encode pre-roll to match your library's dominant format.",
    });
    recs.push({
      severity: 'critical',
      title: 'Recommended Pre-roll Encoding',
      description:
        'Encode pre-roll as: 3840x2160 (4K), HEVC codec, HDR10 (BT.2020, SMPTE ST 2084), ' +
        '23.976fps, 10-bit. This matches the most common 4K movie format and avoids handshake.',
    });

    settings.edidmode = 'automix';

    if (this.mediaServer) {
      const serverName = this.mediaServer.name || 'Media server';
      if (this.mediaServerId === 'emby') {
        recs.push({
          severity: 'info',
          title: 'Emby Pre-roll Known Issue',
          description:
            "Emby cinema intros are known to show only 1 frame when there's a format " +
            'mismatch. Re-encoding the pre-roll to match content format resolves this.',
        });
      }
      recs.push({
        severity: 'info',
        title: `Test with Multiple ${serverName} Clients`,
        description:
          'Test pre-roll playback with different clients (web, mobile, TV app) to confirm ' +
          'the issue is HDMI handshake related and not client-specific.',
      });
    }

    return { recommendations: recs, vrroom_settings: settings, source_settings: [] };
  }

  goalHdrPassthrough() {
    const recs = [];
    const settings = {};

    settings.edidhdrflag = 'on';
    settings.edidhdrmode = 1; // HDR10/HLG
    settings.edidmode = 'automix';
    settings.hdcpmode = 'auto';

    recs.push({
      severity: 'critical',
      title: 'Enable HDR in EDID',
      description:
        'HDR flag must be enabled in EDID for sources to output HDR content. ' +
        'Set HDR mode to HDR10/HLG for broadest compatibility.',
    });

    if (this.display) {
      const hdrList = this.display.hdr_support || [];
      if (hdrList.length) {
        recs.push({
          severity: 'info',
          title: `Display HDR Support: ${hdrList.join(', ')}`,
          description:
            `${this.display.name || 'Your display'} supports ${hdrList.join(', ')}. ` +
            'EDID HDR mode has been set to match.',
        });
        if (hdrList.includes('HDR10+')) settings.edidhdrmode = 2;
      }
    }

    recs.push({
      severity: 'info',
      title: 'HDCP Set to Auto',
      description:
        'HDCP auto mode ensures proper handshake without forcing a version. ' +
        'Manual HDCP settings can cause 4K HDR content to fail.',
    });

    return { recommendations: recs, vrroom_settings: settings, source_settings: [] };
  }

  goalMinimizeFormatSwitch() {
    const recs = [];
    const settings = {};
    const src = [];

    recs.push({
      severity: 'critical',
      title: 'Set Source to Fixed Output Format',
      description:
        'Configure your source device to output a fixed resolution (4K) and let the ' +
        'Vrroom handle any necessary conversion. Only allow frame rate matching to change.',
    });

    if (this.source) {
      const sourceName = this.source.name || 'Source';
      if (this.source.match_frame_rate) {
        src.push({
          setting: 'Match Frame Rate',
          value: 'Enabled',
          device: sourceName,
          reason: 'Frame rate changes cause minimal handshake delay compared to resolution changes.',
          path: getSettingsPath(this.sourceId, 'frame_rate'),
        });
      }
      src.push({
        setting: 'Output Resolution',
        value: '4K (always)',
        device: sourceName,
        reason: 'Fixed 4K output prevents resolution-triggered handshakes.',
        path: getSettingsPath(this.sourceId, 'resolution'),
      });
      if (this.sourceId === 'apple_tv_4k') {
        src.push({
          setting: 'Video Format',
          value: '4K SDR 60Hz',
          device: sourceName,
          reason:
            'Apple TV with Match Content enabled: set base to 4K SDR, let match content handle HDR/fps.',
        });
      }
    }

    settings.edidmode = 'automix';

    recs.push({
      severity: 'info',
      title: 'AutoMix Prevents EDID Re-reads',
      description:
        'AutoMix mode provides a stable EDID to sources, preventing them from ' +
        're-reading EDID and triggering unnecessary handshakes.',
    });

    return { recommendations: recs, vrroom_settings: settings, source_settings: src };
  }

  // ------------------------------------------------------- equipment recs

  generalEquipmentRecs() {
    const recs = [];
    const settings = { hdcpmode: 'auto' };
    const sourceSettings = [];

    if (this.display) {
      const displayName = this.display.name || 'display';
      if ((this.display.handshake_time_ms || 0) >= 2500) {
        recs.push({
          severity: 'info',
          title: `${displayName} Has Slow Handshake`,
          description:
            `This display has a typical handshake time of ${this.display.handshake_time_ms}ms. ` +
            'Minimizing format changes is especially important for this device.',
        });
      }
    }

    if (this.avr && this.avr.earc_support) {
      recs.push({
        severity: 'info',
        title: 'eARC Recommended for Audio',
        description:
          `${this.avr.name || 'Your AVR'} supports eARC. Use eARC routing for ` +
          'lossless Atmos/DTS:X passthrough.',
      });
    }

    for (const [sourceId, source] of this.sources) {
      const sourceName = source.name || 'source';
      if (source.match_frame_rate) {
        sourceSettings.push({
          setting: `Match Frame Rate (${sourceName})`,
          value: 'Enabled',
          device: sourceName,
          reason: 'Prevents unnecessary refresh rate changes.',
          path: getSettingsPath(sourceId, 'frame_rate'),
        });
      }
      if (source.match_resolution) {
        sourceSettings.push({
          setting: `Match Resolution (${sourceName})`,
          value: 'Enabled',
          device: sourceName,
          reason: 'Outputs content at native resolution.',
          path: getSettingsPath(sourceId, 'resolution'),
        });
      }
    }

    return { recommendations: recs, vrroom_settings: settings, source_settings: sourceSettings };
  }

  avrConfigRecs() {
    const recs = [];
    const avrSettings = [];

    if (!this.avr || !this.speakers) return { recommendations: recs, avr_settings: avrSettings };

    const avrName = this.avr.name || 'AVR';
    const speakerLayout = this.speakers.layout || '';
    const channels = this.speakers.channels || 0;
    const overhead = this.speakers.overhead_channels || 0;
    const subs = this.speakers.sub_channels || 0;
    const hasAtmos = !!this.speakers.atmos_capable;
    const configPaths = this.avr.config_paths || {};
    const roomCorrection = this.avr.room_correction || '';

    let layoutLabel = speakerLayout || `${channels}.${subs}`;
    if (overhead > 0 && !speakerLayout) layoutLabel = `${channels}.${subs}.${overhead}`;
    const totalWithHeight = channels + overhead + subs;

    avrSettings.push({
      setting: 'Speaker Configuration',
      value: `${layoutLabel} (${totalWithHeight} total speakers)`,
      category: 'speakers',
      path: pathString(configPaths.speaker_setup),
      reason: `Set AVR to ${layoutLabel} layout to match your physical speaker arrangement.`,
    });

    let crossoverReason = '80 Hz is the THX-recommended crossover for most speakers.';
    if (subs >= 2) {
      crossoverReason += ' Dual subs provide smoother bass; 80 Hz crossover ensures seamless handoff.';
    }
    avrSettings.push({
      setting: 'Crossover Frequency (all channels)',
      value: '80 Hz',
      category: 'speakers',
      path: pathString(configPaths.crossover),
      reason: crossoverReason,
    });

    if (subs >= 2) {
      avrSettings.push({
        setting: 'Subwoofer Mode',
        value: 'LFE + Main (both subs active)',
        category: 'speakers',
        path: pathString(configPaths.speaker_setup),
        reason: 'Dual subs provide even bass distribution and reduce room mode nulls.',
      });
    }

    if (overhead > 0 && hasAtmos) {
      if (overhead === 2) {
        avrSettings.push({
          setting: 'Height Speaker Assignment',
          value: 'Front Height or Top Middle',
          category: 'speakers',
          path: pathString(configPaths.speaker_setup),
          reason:
            'With 2 height channels, Top Middle or Front Height gives the best Atmos overhead coverage. ' +
            'Top Middle preferred for ceiling-mounted; Front Height for upfiring modules.',
        });
      } else if (overhead >= 4) {
        avrSettings.push({
          setting: 'Height Speaker Assignment',
          value: 'Top Front + Top Rear (or Front Height + Rear Height)',
          category: 'speakers',
          path: pathString(configPaths.speaker_setup),
          reason:
            '4 height channels provide full Atmos hemisphere. ' +
            'Top Front + Top Rear for ceiling; Front Height + Rear Height for upfiring.',
        });
      }
    }

    if (hasAtmos) {
      avrSettings.push({
        setting: 'Surround Decode Mode',
        value: 'Dolby Atmos / DTS:X (Auto)',
        category: 'processing',
        path: pathString(configPaths.surround_decode),
        reason:
          'Auto mode decodes native Atmos/DTS:X tracks and upmixes stereo/5.1 content to height speakers.',
      });
      recs.push({
        severity: 'info',
        title: `Atmos Configuration for ${avrName}`,
        description:
          `Your ${speakerLayout} layout with ${avrName} supports Dolby Atmos and DTS:X. ` +
          'Ensure surround decode is set to Auto to engage height channels for object-based audio.',
      });
    }

    avrSettings.push({
      setting: 'HDMI Audio Output',
      value: 'AMP (decode in AVR)',
      category: 'audio_routing',
      path: pathString(configPaths.hdmi_audio),
      reason: 'Route audio decoding to AVR rather than passing through to TV/projector.',
    });

    if (this.avr.earc_support) {
      avrSettings.push({
        setting: 'eARC',
        value: 'Enabled',
        category: 'audio_routing',
        path: pathString(configPaths.earc),
        reason: 'eARC enables lossless Atmos (TrueHD MAT) and DTS:X passthrough from display or Vrroom.',
      });
    }

    if (roomCorrection) {
      avrSettings.push({
        setting: `Room Correction (${roomCorrection})`,
        value: 'Run calibration with all speakers at listening position',
        category: 'calibration',
        path: pathString(configPaths.room_correction),
        reason:
          `${roomCorrection} measures your room acoustics and applies EQ correction. ` +
          'Run at primary listening position. Use multiple measurement points if supported.',
      });
      recs.push({
        severity: 'warning',
        title: `Run ${roomCorrection} Calibration`,
        description:
          `After configuring speaker layout on ${avrName}, run ${roomCorrection} room correction. ` +
          'This compensates for room acoustics, speaker placement, and distance differences. ' +
          'Place the microphone at ear height at your primary listening position.',
      });
    }

    avrSettings.push({
      setting: 'Speaker Distances',
      value: 'Measure from each speaker to listening position',
      category: 'calibration',
      path: pathString(configPaths.distance),
      reason:
        'Correct distance settings ensure all speakers are time-aligned. ' +
        'Measure in a straight line from each speaker cone to your head position.',
    });

    avrSettings.push({
      setting: 'Speaker Levels',
      value: 'Calibrate to 75 dB SPL at listening position (use SPL meter or room correction)',
      category: 'calibration',
      path: pathString(configPaths.level),
      reason:
        'All speakers should measure the same SPL at the listening position. ' +
        'Room correction typically handles this, or use an SPL meter app with test tones.',
    });

    return { recommendations: recs, avr_settings: normalizePaths(avrSettings) };
  }

  displayConfigRecs() {
    const recs = [];
    const displaySettings = [];

    if (!this.display) return { recommendations: recs, display_settings: displaySettings };

    const displayName = this.display.name || 'Display';
    const configPaths = this.display.config_paths || {};
    const recommended = this.display.recommended_settings || {};
    const isProjector = this.display.type === 'projector';

    if (!Object.keys(configPaths).length && !Object.keys(recommended).length) {
      return { recommendations: recs, display_settings: displaySettings };
    }

    const hdmiSignalPath = configPaths.hdmi_signal || '';
    const hdmiRec = recommended.hdmi_signal_format || '';
    if (hdmiSignalPath || hdmiRec) {
      displaySettings.push({
        setting: 'HDMI Signal Format',
        value: hdmiRec || 'Enhanced / Expanded (required for 4K HDR)',
        category: 'input',
        path: pathString(hdmiSignalPath),
        reason:
          'HDMI inputs must be set to Enhanced/Expanded mode to accept 4K HDR 10-bit signals. ' +
          'Standard mode limits to 8-bit SDR.',
      });
    }

    if (recommended.color_mode_sdr) {
      displaySettings.push({
        setting: 'Picture Mode (SDR content)',
        value: recommended.color_mode_sdr,
        category: 'picture',
        path: pathString(configPaths.picture_mode),
        reason:
          'Natural or Cinema modes provide the most accurate colors for SDR content ' +
          'with proper BT.709 color space and 2.2-2.4 gamma.',
      });
    }

    if (recommended.color_mode_hdr) {
      displaySettings.push({
        setting: 'Picture Mode (HDR content)',
        value: recommended.color_mode_hdr,
        category: 'picture',
        path: pathString(configPaths.picture_mode),
        reason:
          'HDR picture mode applies appropriate tone mapping and ' +
          'BT.2020 wide color gamut processing for HDR10/HLG content.',
      });
    }

    if (recommended.hdr10_dynamic_range) {
      displaySettings.push({
        setting: 'HDR10 Dynamic Range',
        value: recommended.hdr10_dynamic_range,
        category: 'picture',
        path: pathString(configPaths.hdr_setting),
        reason:
          "Controls how HDR tone mapping maps the source brightness range to your display's capability. " +
          'Auto works for most content; a value of 16 works well in fully dark rooms.',
      });
    }

    if (recommended.color_temp) {
      displaySettings.push({
        setting: 'Color Temperature',
        value: recommended.color_temp,
        category: 'picture',
        path: pathString(configPaths.color_temp),
        reason:
          'D65 (6500K) is the reference white point for both SDR and HDR content. ' +
          'Warm/Warm2 presets on most displays approximate D65.',
      });
    }

    if (recommended.gamma_sdr) {
      displaySettings.push({
        setting: 'Gamma (SDR)',
        value: recommended.gamma_sdr,
        category: 'picture',
        path: pathString(configPaths.gamma),
        reason:
          'For a dark dedicated theater room, gamma 2.4 (BT.1886) is ideal. ' +
          'For rooms with some ambient light, use 2.2. Adjust based on viewing conditions.',
      });
    }

    if (recommended.frame_interpolation) {
      displaySettings.push({
        setting: 'Frame Interpolation / Motion Smoothing',
        value: recommended.frame_interpolation,
        category: 'processing',
        path: pathString(configPaths.frame_interp),
        reason:
          "Off preserves the filmmaker's intended 24fps cadence (no soap opera effect). " +
          'Low setting can help with judder on some displays without the soap opera look.',
      });
    }

    if (isProjector) {
      if (recommended.light_source_mode) {
        displaySettings.push({
          setting: 'Light Source Mode',
          value: recommended.light_source_mode,
          category: 'projector',
          path: pathString(configPaths.power_mode),
          reason:
            'Adjust laser/lamp output to room conditions. Lower output in fully dark rooms ' +
            'preserves contrast and extends light source life.',
        });
      }

      if (recommended.aspect_ratio) {
        displaySettings.push({
          setting: 'Aspect Ratio',
          value: recommended.aspect_ratio,
          category: 'projector',
          path: pathString(configPaths.aspect_ratio),
          reason:
            'Auto handles 16:9 and letterboxed content. Use Anamorphic/Lens Memory ' +
            'for constant image height setups with CinemaScope screens.',
        });
      }

      if (this.display.lens_memory) {
        displaySettings.push({
          setting: 'Lens Memory',
          value: 'Configure presets for 16:9 and 2.35:1 aspect ratios',
          category: 'projector',
          path: pathString(configPaths.lens_memory),
          reason:
            'Lens memory stores zoom/shift positions for different aspect ratios. ' +
            'Set one preset for 16:9 (full screen) and one for 2.35:1 (scope) if using CinemaScope screen.',
        });
      }

      if (this.screen) {
        const screenName = this.screen.name || 'screen';
        const gain = this.screen.gain !== undefined ? this.screen.gain : 1.0;
        const isAt = !!this.screen.acoustically_transparent;
        const isAlr = !!this.screen.ambient_light_rejecting;

        recs.push({
          severity: 'info',
          title: `Projector + Screen: ${displayName} on ${screenName}`,
          description:
            `Screen gain: ${gain}. ` +
            (isAt ? 'Acoustically transparent screen - place L/C/R behind screen for best imaging. ' : '') +
            (isAlr ? 'ALR screen - good for rooms with ambient light but may affect off-axis viewing. ' : '') +
            (gain >= 1.0
              ? `With ${gain} gain, no brightness compensation needed.`
              : `With ${gain} gain, increase projector brightness to compensate for light loss.`),
        });

        if (isAt) {
          recs.push({
            severity: 'info',
            title: 'Acoustically Transparent Screen Detected',
            description:
              'Place your front L/C/R speakers directly behind the screen for phantom-free ' +
              'center channel and seamless sound-to-image integration. AT screens typically ' +
              'have slightly lower gain than solid screens.',
          });
        }
      }

      recs.push({
        severity: 'info',
        title: `${displayName} Optimization Guide`,
        description:
          'Review the display settings below for recommended picture modes, HDR calibration, ' +
          'and projector-specific settings. Settings are tailored to this specific display model.',
      });
    } else {
      recs.push({
        severity: 'info',
        title: `${displayName} Settings`,
        description: 'Review the display settings below for recommended picture modes and HDR calibration.',
      });
    }

    return { recommendations: recs, display_settings: normalizePaths(displaySettings) };
  }
}

/** config_paths entries can be strings or {path, steps, tab, recommended} objects. */
function pathString(p) {
  return p || '';
}

function normalizePaths(settingsList) {
  for (const s of settingsList) {
    const p = s.path;
    if (p && typeof p === 'object') {
      s.path = p.path || '';
      s.steps = p.steps || [];
      s.tab = p.tab || '';
      if (p.recommended) s.recommended = p.recommended;
    } else if (!p) {
      s.path = '';
    }
  }
  return settingsList;
}

module.exports = { RecommendationEngine };
