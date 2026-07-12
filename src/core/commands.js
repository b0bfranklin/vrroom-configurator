/**
 * Convert recommended settings into VRROOM set-commands.
 *
 * Command names are verified against VRRoom_FW_63/vrroom-rs232-ip-251021.txt.
 * Some settings (unmute delays) exist only in the web UI and have no IP/RS232
 * command in FW63 - those are returned flagged as web-UI-only so the UI can
 * say so instead of emitting a command the device would ignore.
 */

/** recommended-setting key -> IP command target (null = web UI only in FW63) */
const COMMAND_MAP = {
  edidmode: 'edidmode',
  ediddvflag: 'ediddvflag',
  ediddvmode: 'ediddvmode',
  edidhdrflag: 'edidhdrflag',
  edidhdrmode: 'edidhdrmode',
  edidvrrflag: 'edidvrrflag',
  edidallmflag: 'edidallmflag',
  hdcpmode: 'hdcp',
  hdcp: 'hdcp',
  hdrcustom: 'hdrcustom',
  cec: 'cec',
  autosw: 'autosw',
  opmode: 'opmode',
  unmutedelay: null,
  earcunmute: null,
};

/** Value translations for keys whose command uses different value tokens. */
function translateValue(key, value) {
  if (key === 'earcmode') {
    const v = String(value).toLowerCase();
    if (v.includes('earc')) return 'auto';
    if (v.includes('hdmi')) return 'hdmi';
    return 'auto';
  }
  return String(value);
}

/**
 * Returns { commands: [{key, value, ip, rs232}], webUiOnly: [{key, value}] }.
 * `ip` is what you paste into a telnet session on port 2222,
 * `rs232` is the same command with the #vrroom header for serial use.
 */
function toSetCommands(settings) {
  const commands = [];
  const webUiOnly = [];

  for (const [key, value] of Object.entries(settings || {})) {
    if (key === 'earcmode') {
      const v = translateValue(key, value);
      commands.push({
        key,
        value,
        ip: `set earcforce ${v}`,
        rs232: `#vrroom set earcforce ${v}`,
      });
      continue;
    }

    const target = COMMAND_MAP[key];
    if (target === null || target === undefined) {
      webUiOnly.push({ key, value });
      continue;
    }
    commands.push({
      key,
      value,
      ip: `set ${target} ${value}`,
      rs232: `#vrroom set ${target} ${value}`,
    });
  }

  return { commands, webUiOnly };
}

module.exports = { toSetCommands, COMMAND_MAP };
