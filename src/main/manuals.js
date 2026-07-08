/**
 * Specs & manuals downloader.
 * Downloads official manuals/spec sheets for the user's equipment into the
 * app's user data directory so they're available offline, and exposes the
 * source links.
 */
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const DOWNLOAD_TIMEOUT_MS = 60000;
const MAX_BYTES = 100 * 1024 * 1024; // 100 MB cap
const USER_AGENT = 'AVSignalLab/2.0 (manual downloader)';

function downloadFile(url, destPath, redirectsLeft = 5) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(
      url,
      { headers: { 'User-Agent': USER_AGENT }, timeout: DOWNLOAD_TIMEOUT_MS },
      (res) => {
        if ([301, 302, 307, 308].includes(res.statusCode) && res.headers.location && redirectsLeft > 0) {
          res.resume();
          const next = new URL(res.headers.location, url).toString();
          downloadFile(next, destPath, redirectsLeft - 1).then(resolve, reject);
          return;
        }
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }

        let bytes = 0;
        const tmpPath = destPath + '.part';
        const out = fs.createWriteStream(tmpPath);

        res.on('data', (chunk) => {
          bytes += chunk.length;
          if (bytes > MAX_BYTES) {
            req.destroy();
            out.destroy();
            fs.rmSync(tmpPath, { force: true });
            reject(new Error('File exceeds size limit'));
          }
        });
        res.pipe(out);
        out.on('finish', () => {
          out.close(() => {
            fs.renameSync(tmpPath, destPath);
            resolve({ path: destPath, bytes });
          });
        });
        out.on('error', (err) => {
          fs.rmSync(tmpPath, { force: true });
          reject(err);
        });
      }
    );
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Download timed out'));
    });
    req.on('error', reject);
  });
}

class ManualLibrary {
  constructor(userDataDir, deviceManuals) {
    this.dir = path.join(userDataDir, 'manuals');
    fs.mkdirSync(this.dir, { recursive: true });
    this.manuals = deviceManuals || {};
  }

  /** All known manual sources, with local availability flags. */
  list() {
    const entries = [];
    for (const [deviceId, info] of Object.entries(this.manuals)) {
      const urls = {};
      if (info.manual_url) urls.manual = info.manual_url;
      if (info.quick_start_url) urls.quick_start = info.quick_start_url;
      for (const [kind, url] of Object.entries(urls)) {
        const localName = `${deviceId}_${kind}${extensionOf(url)}`;
        const localPath = path.join(this.dir, localName);
        entries.push({
          device_id: deviceId,
          kind,
          url,
          local_path: fs.existsSync(localPath) ? localPath : null,
          local_name: localName,
        });
      }
    }
    return entries;
  }

  async download(deviceId, kind) {
    const info = this.manuals[deviceId];
    if (!info) throw new Error(`No manual sources known for ${deviceId}`);
    const url = kind === 'quick_start' ? info.quick_start_url : info.manual_url;
    if (!url) throw new Error(`No ${kind} URL for ${deviceId}`);

    const localName = `${deviceId}_${kind}${extensionOf(url)}`;
    const destPath = path.join(this.dir, localName);
    const result = await downloadFile(url, destPath);
    return { device_id: deviceId, kind, ...result };
  }
}

function extensionOf(url) {
  try {
    const p = new URL(url).pathname;
    const ext = path.extname(p);
    return ext && ext.length <= 5 ? ext : '.pdf';
  } catch (_) {
    return '.pdf';
  }
}

module.exports = { ManualLibrary, downloadFile };
