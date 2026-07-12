/**
 * VRROOM configuration analyzer.
 * Analyzes an HDFury Vrroom config export (JSON) for optimization
 * opportunities, with a focus on eliminating HDMI bonk/renegotiation.
 * Ported from the legacy Flask app's VrroomConfigAnalyzer.
 */
const data = require('./data');

const SEVERITY = { CRITICAL: 'critical', WARNING: 'warning', INFO: 'info' };

/**
 * Convert a raw setting key/value pair into a human-readable descriptor
 * using the VRROOM settings metadata (name, web UI menu path, value labels).
 */
function describeSetting(key, value) {
  const meta = data.vrroomSettingsMeta()[key] || {};
  const values = meta.values || {};
  const displayValue = values[String(value)] !== undefined ? values[String(value)] : String(value);
  const isSet = String(value).toLowerCase() !== 'off' && String(value) !== '0' && String(value) !== '';
  return {
    key,
    value,
    name: meta.name || key,
    menu_path: meta.menu_path || '',
    tab: meta.tab || '',
    description: meta.description || '',
    display_value: displayValue,
    is_set: isSet,
  };
}

class ConfigAnalyzer {
  constructor(config) {
    this.config = config || {};
    this.issues = [];
    this.recommendations = [];
  }

  analyze() {
    this.issues = [];
    this.recommendations = [];

    this.checkEdidMode();
    this.checkUnmuteDelays();
    this.checkDvSettings();
    this.checkHdrSettings();
    this.checkHdcpSettings();
    this.checkCecSettings();
    this.checkAudioRouting();

    return {
      issues: this.issues,
      recommendations: this.recommendations,
      issue_count: {
        critical: this.issues.filter((i) => i.severity === SEVERITY.CRITICAL).length,
        warning: this.issues.filter((i) => i.severity === SEVERITY.WARNING).length,
        info: this.issues.filter((i) => i.severity === SEVERITY.INFO).length,
      },
      settings_overview: this.settingsOverview(),
      optimized_config: this.generateOptimizedConfig(),
    };
  }

  addIssue(severity, title, description, setting, currentValue, recommendedValue) {
    const issue = { severity, title, description };
    if (setting) issue.setting = setting;
    if (currentValue !== undefined) issue.current_value = currentValue;
    if (recommendedValue !== undefined) issue.recommended_value = recommendedValue;
    this.issues.push(issue);
  }

  get(key, fallback = '') {
    const v = this.config[key];
    return v === undefined || v === null ? fallback : v;
  }

  getStr(key, fallback = '') {
    return String(this.get(key, fallback)).toLowerCase();
  }

  getInt(key, fallback = 0) {
    const n = parseInt(this.get(key, fallback), 10);
    return Number.isNaN(n) ? fallback : n;
  }

  checkEdidMode() {
    const edidMode = this.getStr('edidmode');

    if (edidMode === 'fixed') {
      this.addIssue(
        SEVERITY.WARNING,
        'Fixed EDID Mode',
        'Fixed EDID mode limits sink capabilities. Consider AutoMix for better compatibility.',
        'edidmode', edidMode, 'automix'
      );
    } else if (edidMode && !['automix', 'custom', 'copytx0', 'copytx1'].includes(edidMode)) {
      this.addIssue(
        SEVERITY.INFO,
        'Unknown EDID Mode',
        `EDID mode '${edidMode}' not recognized. AutoMix recommended for most setups.`,
        'edidmode', edidMode, 'automix'
      );
    }

    if (edidMode === 'automix') {
      this.recommendations.push({
        title: 'EDID Mode Optimal',
        description: 'AutoMix mode allows dynamic EDID modification for LLDV injection.',
      });
    }
  }

  checkUnmuteDelays() {
    const unmuteDelay = this.getInt('unmutedelay', 0);
    const earcUnmute = this.getInt('earcunmute', 0);

    if (unmuteDelay > 500) {
      this.addIssue(
        SEVERITY.CRITICAL,
        'High Unmute Delay',
        `Unmute delay of ${unmuteDelay}ms adds significant latency. ` +
          'Try reducing to 200-300ms if no audio pops occur.',
        'unmutedelay', unmuteDelay, 250
      );
    } else if (unmuteDelay === 0 && 'unmutedelay' in this.config) {
      this.addIssue(
        SEVERITY.INFO,
        'No Unmute Delay',
        'Zero unmute delay may cause audio pops on some systems. ' +
          'Add 100-200ms if you hear clicks/pops on format changes.',
        'unmutedelay', 0, 150
      );
    }

    if (earcUnmute > 500) {
      this.addIssue(
        SEVERITY.WARNING,
        'High eARC Unmute Delay',
        `eARC unmute delay of ${earcUnmute}ms may cause noticeable audio lag.`,
        'earcunmute', earcUnmute, 300
      );
    }
  }

  checkDvSettings() {
    const dvFlag = this.getStr('ediddvflag', 'off');

    if (dvFlag === 'off') {
      this.addIssue(
        SEVERITY.INFO,
        'Dolby Vision Disabled',
        'DV EDID flag is off. Enable for LLDV support on non-DV displays.',
        'ediddvflag', 'off', 'on'
      );
    }

    if (dvFlag === 'on') {
      this.recommendations.push({
        title: 'DV Enabled',
        description: 'Ensure LLDV-compatible DV string is selected (X930E or similar) for non-DV projectors.',
      });
    }
  }

  checkHdrSettings() {
    const hdrFlag = this.getStr('edidhdrflag', 'on');
    const hdrCustom = this.getStr('hdrcustom', 'off');

    if (hdrFlag === 'off') {
      this.addIssue(
        SEVERITY.WARNING,
        'HDR Disabled in EDID',
        "HDR flag is disabled. Sources won't output HDR content.",
        'edidhdrflag', 'off', 'on'
      );
    }

    if (hdrCustom === 'on') {
      this.recommendations.push({
        title: 'Custom HDR Injection Active',
        description: 'Note: Custom HDR injection automatically disables under VRR signals.',
      });
    }
  }

  checkHdcpSettings() {
    // Config exports use "hdcpmode"; the IP protocol uses "hdcp"
    const key = 'hdcpmode' in this.config ? 'hdcpmode' : 'hdcp';
    const hdcpMode = this.getStr(key, 'auto');

    if (hdcpMode !== 'auto') {
      this.addIssue(
        SEVERITY.INFO,
        'Manual HDCP Mode',
        `HDCP is set to '${hdcpMode}'. Auto mode is recommended unless troubleshooting.`,
        key, hdcpMode, 'auto'
      );
    }
  }

  checkCecSettings() {
    if (this.config.cecenabled || this.getStr('cec') === 'on') {
      this.recommendations.push({
        title: 'CEC Enabled',
        description: 'CEC can add latency on input switches. Disable if not using TV/AVR power control features.',
      });
    }
  }

  checkAudioRouting() {
    const audioOut = this.getStr('audioout');
    const earcMode = this.getStr('earcmode');

    if (audioOut === 'earc' || ['auto earc', 'earc'].includes(earcMode)) {
      this.recommendations.push({
        title: 'eARC Audio Routing',
        description: 'eARC provides best audio quality. Ensure eARC device is powered on before source.',
      });
    }
  }

  /** Human-readable view of every recognized setting in the config. */
  settingsOverview() {
    const meta = data.vrroomSettingsMeta();
    const overview = [];
    for (const [key, value] of Object.entries(this.config)) {
      if (key.startsWith('_')) continue;
      if (meta[key]) {
        overview.push(describeSetting(key, value));
      }
    }
    return overview;
  }

  generateOptimizedConfig() {
    const optimized = JSON.parse(JSON.stringify(this.config));

    for (const issue of this.issues) {
      if ([SEVERITY.CRITICAL, SEVERITY.WARNING].includes(issue.severity)) {
        if (issue.setting && issue.recommended_value !== undefined) {
          optimized[issue.setting] = issue.recommended_value;
        }
      }
    }

    optimized._optimized = true;
    optimized._optimized_date = new Date().toISOString();
    optimized._optimized_by = 'AV Signal Lab';
    return optimized;
  }
}

/**
 * Compare an actual VRROOM config against a recommended settings map
 * (as produced by the recommendation engine). Returns per-setting diffs.
 */
function compareWithRecommended(config, recommendedSettings) {
  const diffs = [];
  for (const [key, recommended] of Object.entries(recommendedSettings || {})) {
    const current = config[key];
    const matches =
      current !== undefined &&
      String(current).toLowerCase() === String(recommended).toLowerCase();
    diffs.push({
      ...describeSetting(key, recommended),
      recommended_value: recommended,
      current_value: current === undefined ? '(not in config)' : current,
      matches,
    });
  }
  return diffs;
}

module.exports = { ConfigAnalyzer, compareWithRecommended, describeSetting, SEVERITY };
