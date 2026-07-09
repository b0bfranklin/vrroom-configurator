/**
 * Safe, read-only VRROOM IP client.
 *
 * Designed after the official spec (VRRoom_FW_63/vrroom-rs232-ip-251021.txt):
 *  - Over IP/Telnet, commands must NOT include the "#vrroom" header
 *    (the legacy client sent the header over TCP, which is off-spec and the
 *    likely cause of device lockups).
 *  - Each command ends with \n; each response ends with \r\n.
 *  - Default IP port is 2222.
 *
 * Safety rules enforced here:
 *  - READ ONLY: only "get <target>" commands from a fixed whitelist are sent.
 *  - One command in flight at a time, with a minimum gap between commands.
 *  - Strict connect and response timeouts.
 *  - Circuit breaker: consecutive timeouts abort the whole batch.
 *  - Socket is always destroyed when the batch completes or fails.
 */
const net = require('net');

const DEFAULT_PORT = 2222;
const CONNECT_TIMEOUT_MS = 4000;
const RESPONSE_TIMEOUT_MS = 2500;
const COMMAND_GAP_MS = 300;
const MAX_CONSECUTIVE_TIMEOUTS = 2;

/**
 * Only these read targets may ever be queried. No "set" commands exist here.
 * Every entry is verified against VRRoom_FW_63/vrroom-rs232-ip-251021.txt
 * ("current set-values can be read with the get-command"). Note: the web UI
 * settings "unmute delay" / "eARC unmute" are NOT exposed over IP in FW63,
 * and the HDCP command is "hdcp" (not "hdcpmode").
 */
const READ_TARGETS = new Set([
  // routing / mode
  'opmode', 'insel', 'inseltx0', 'inseltx1', 'autosw',
  // network
  'ipaddr', 'dhcp',
  // EDID block
  'edidmode', 'ediddvflag', 'ediddvmode', 'edidhdrflag', 'edidhdrmode',
  'edidvrrflag', 'edidvrrmode', 'edidallmflag', 'edidallmmode',
  'edidfrlflag', 'edidfrlmode',
  // HDCP / HDR / AVI
  'hdcp', 'hdrcustom', 'hdrdisable', 'avicustom', 'avidisable',
  // CEC / audio / eARC
  'cec', 'earcforce', 'mutetx0audio', 'mutetx1audio',
  'audiochtx0', 'audiochtx1', 'audiochaudout',
  'audiomodetx0', 'audiomodetx1', 'audiomodeaudout',
  // signal status
  'status rx0', 'status rx1', 'status tx0', 'status tx1',
  'status tx0sink', 'status tx1sink', 'status aud0', 'status aud1',
  'status audout', 'status spd0', 'status spd1',
]);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class VrroomClient {
  constructor(host, port = DEFAULT_PORT) {
    this.host = host;
    this.port = port;
    this.socket = null;
    this.buffer = '';
    this.pending = null; // { resolve, reject, timer }
  }

  connect() {
    return new Promise((resolve, reject) => {
      const socket = new net.Socket();
      socket.setNoDelay(true);

      const connectTimer = setTimeout(() => {
        socket.destroy();
        reject(new Error(`Connection to ${this.host}:${this.port} timed out after ${CONNECT_TIMEOUT_MS}ms`));
      }, CONNECT_TIMEOUT_MS);

      socket.once('error', (err) => {
        clearTimeout(connectTimer);
        socket.destroy();
        reject(new Error(`Connection failed: ${err.message}`));
      });

      socket.connect(this.port, this.host, () => {
        clearTimeout(connectTimer);
        this.socket = socket;

        socket.on('data', (chunk) => this.onData(chunk));
        socket.on('error', (err) => this.failPending(new Error(`Socket error: ${err.message}`)));
        socket.on('close', () => this.failPending(new Error('Connection closed by device')));

        resolve();
      });
    });
  }

  onData(chunk) {
    this.buffer += chunk.toString('utf-8');
    // Responses are terminated with \r\n
    const idx = this.buffer.indexOf('\n');
    if (idx !== -1 && this.pending) {
      const line = this.buffer.slice(0, idx).replace(/\r$/, '').trim();
      this.buffer = this.buffer.slice(idx + 1);
      const { resolve, timer } = this.pending;
      clearTimeout(timer);
      this.pending = null;
      resolve(line);
    }
  }

  failPending(err) {
    if (this.pending) {
      const { reject, timer } = this.pending;
      clearTimeout(timer);
      this.pending = null;
      reject(err);
    }
  }

  /**
   * Send a single whitelisted read command. Target must be in READ_TARGETS.
   * Per spec: no "#vrroom" header over IP, terminate with \n.
   */
  sendGet(target) {
    if (!READ_TARGETS.has(target)) {
      return Promise.reject(new Error(`Refusing non-whitelisted command: get ${target}`));
    }
    if (!this.socket) {
      return Promise.reject(new Error('Not connected'));
    }
    if (this.pending) {
      return Promise.reject(new Error('A command is already in flight'));
    }

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending = null;
        reject(new Error(`Timeout waiting for response to "get ${target}"`));
      }, RESPONSE_TIMEOUT_MS);

      this.pending = { resolve, reject, timer };
      this.buffer = '';
      this.socket.write(`get ${target}\n`);
    });
  }

  disconnect() {
    if (this.socket) {
      try {
        this.socket.destroy();
      } catch (_) {
        /* already closed */
      }
      this.socket = null;
    }
    this.failPending(new Error('Disconnected'));
  }
}

/**
 * Run a batch of read commands against a Vrroom with all safety rules applied.
 * Returns { ok, results: {target: value|null}, errors: [..] }.
 */
async function readBatch(host, port, targets) {
  const client = new VrroomClient(host, port || DEFAULT_PORT);
  const results = {};
  const errors = [];
  let consecutiveTimeouts = 0;

  try {
    await client.connect();
  } catch (err) {
    return { ok: false, results, errors: [err.message] };
  }

  try {
    for (const target of targets) {
      if (!READ_TARGETS.has(target)) {
        errors.push(`Skipped non-whitelisted target: ${target}`);
        continue;
      }
      try {
        const response = await client.sendGet(target);
        results[target] = response;
        consecutiveTimeouts = 0;
      } catch (err) {
        results[target] = null;
        errors.push(`${target}: ${err.message}`);
        if (err.message.startsWith('Timeout')) {
          consecutiveTimeouts += 1;
          if (consecutiveTimeouts >= MAX_CONSECUTIVE_TIMEOUTS) {
            errors.push(
              `Aborting batch: ${consecutiveTimeouts} consecutive timeouts. ` +
                'The device may be busy - wait a moment before retrying.'
            );
            break;
          }
        } else {
          // Socket-level failure: stop immediately
          break;
        }
      }
      await sleep(COMMAND_GAP_MS);
    }
  } finally {
    client.disconnect();
  }

  const gotAny = Object.values(results).some((v) => v !== null);
  return { ok: gotAny, results, errors };
}

/** Standard settings snapshot used by the Live tab and config analysis. */
const SETTINGS_TARGETS = [
  'edidmode', 'ediddvflag', 'ediddvmode', 'edidhdrflag', 'edidhdrmode',
  'edidvrrflag', 'edidallmflag', 'hdcp', 'hdrcustom',
  'cec', 'earcforce', 'autosw', 'opmode',
];

const STATUS_TARGETS = [
  'status rx0', 'status tx0', 'status tx0sink', 'status audout', 'audiomodeaudout',
];

/** Live command names that differ from the config-export key the analyzer uses. */
const CONFIG_KEY_ALIASES = { hdcp: 'hdcpmode' };

/**
 * Parse "get X" responses into a config-like object.
 * Responses typically echo the command name: "edidmode automix".
 */
function parseSettingsResults(results) {
  const config = {};
  for (const [target, raw] of Object.entries(results)) {
    if (raw === null || target.startsWith('status ')) continue;
    let value = raw;
    // Strip echoed command name prefix if present
    const prefix = target + ' ';
    if (raw.toLowerCase().startsWith(prefix)) {
      value = raw.slice(prefix.length);
    } else if (raw.toLowerCase().startsWith(target)) {
      value = raw.slice(target.length).trim();
    }
    value = value.trim();
    config[target] = value;
    if (CONFIG_KEY_ALIASES[target]) config[CONFIG_KEY_ALIASES[target]] = value;
  }
  return config;
}

module.exports = {
  readBatch,
  parseSettingsResults,
  SETTINGS_TARGETS,
  STATUS_TARGETS,
  READ_TARGETS,
  DEFAULT_PORT,
};
