/**
 * Step-by-step menu navigation paths for source device settings.
 * Ported from the legacy Flask app's _get_settings_path().
 */
const PATHS = {
  nvidia_shield_pro: {
    resolution: 'Settings > Device Preferences > Display & Sound > Resolution',
    frame_rate: 'Settings > Device Preferences > Display & Sound > Match content frame rate',
    hdr: 'Settings > Device Preferences > Display & Sound > Dynamic range > set to Auto',
    audio: 'Settings > Device Preferences > Display & Sound > Advanced sound settings > Surround sound > Auto',
    dv: 'Settings > Device Preferences > Display & Sound > Dolby Vision > set to Enabled',
  },
  apple_tv_4k: {
    resolution: 'Settings > Video and Audio > Format > 4K SDR 60Hz',
    frame_rate: 'Settings > Video and Audio > Match Content > Match Frame Rate > On',
    hdr: 'Settings > Video and Audio > Match Content > Match Dynamic Range > On',
    audio: 'Settings > Video and Audio > Audio Format > Dolby Atmos (if available)',
    dv: 'Settings > Video and Audio > Match Content > Match Dynamic Range > On (enables DV when available)',
  },
  xbox_series_x: {
    resolution: 'Settings > General > TV & Display Options > Resolution > 4K UHD',
    frame_rate: 'Settings > General > TV & Display Options > Refresh Rate > 120 Hz',
    hdr: 'Settings > General > TV & Display Options > Video Modes > Allow HDR10 > checked',
    audio: 'Settings > General > Volume & Audio Output > HDMI audio > Bitstream out > Dolby Atmos for Home Theater',
    vrr: 'Settings > General > TV & Display Options > Video Modes > Allow Variable Refresh Rate > checked',
    allm: 'Settings > General > TV & Display Options > Video Modes > Allow Auto Low Latency Mode > checked',
  },
  ps5: {
    resolution: 'Settings > Screen and Video > Video Output > Resolution > 2160p',
    frame_rate: 'Settings > Screen and Video > Video Output > Enable 120 Hz Output > Automatic',
    hdr: 'Settings > Screen and Video > Video Output > HDR > On When Supported',
    audio: 'Settings > Sound > Audio Output > Audio Format (Priority) > Bitstream (Dolby)',
    vrr: 'Settings > Screen and Video > Video Output > VRR > Automatic',
  },
  zidoo_z9x_pro: {
    resolution: 'Settings > Display > Resolution > 3840x2160p Auto',
    frame_rate: 'Settings > Display > Match Frame Rate > On',
    hdr: 'Settings > Display > HDR > Auto',
    audio: 'Settings > Audio > HDMI Audio > Auto',
    dv: 'Settings > Display > Dolby Vision > VS10 Engine',
  },
  kaleidescape_strato: {
    resolution: 'Kaleidescape App > Settings > Video > Output Resolution > Auto',
    frame_rate: 'Kaleidescape App > Settings > Video > Match Frame Rate > On',
    hdr: 'Kaleidescape App > Settings > Video > HDR > Auto',
    audio: 'Kaleidescape App > Settings > Audio > Digital Audio > Bitstream',
  },
};

function getSettingsPath(deviceId, settingType) {
  return (PATHS[deviceId] || {})[settingType] || '';
}

module.exports = { getSettingsPath };
