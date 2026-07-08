/**
 * Firmware / software update checker.
 * Policy: notify + link. We fetch the vendor page, best-effort parse the
 * latest version string, and always give the user the official link.
 * We never download or flash firmware automatically.
 */
const https = require('https');

const FETCH_TIMEOUT_MS = 15000;
const USER_AGENT = 'AVSignalLab/2.0 (update checker; notify-and-link only)';

function fetchPage(url, redirectsLeft = 4) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      { headers: { 'User-Agent': USER_AGENT, Accept: 'text/html,*/*' }, timeout: FETCH_TIMEOUT_MS },
      (res) => {
        if ([301, 302, 307, 308].includes(res.statusCode) && res.headers.location && redirectsLeft > 0) {
          res.resume();
          const next = new URL(res.headers.location, url).toString();
          fetchPage(next, redirectsLeft - 1).then(resolve, reject);
          return;
        }
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        let body = '';
        res.setEncoding('utf-8');
        res.on('data', (c) => {
          body += c;
          if (body.length > 3_000_000) {
            req.destroy();
            reject(new Error('Page too large'));
          }
        });
        res.on('end', () => resolve(body));
      }
    );
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timed out'));
    });
    req.on('error', reject);
  });
}

/**
 * Device update checkers. Each returns:
 * { device, current_hint, latest_version (or null), download_page, notes, checked_at }
 * Parsing vendor pages is best-effort - the download_page link is the
 * reliable part and is always present.
 */
const CHECKERS = {
  hdfury_vrroom: {
    device: 'HDFury VRROOM',
    page: 'https://www.hdfury.com/product/8k-vrroom-40gbps/',
    fallbackPage: 'https://www.hdfury.com/download/',
    notes:
      'Download the firmware ZIP from the VRROOM product page (Downloads section). ' +
      'Update via the VRROOM web UI or USB per the included ReadMeFirst instructions. ' +
      'Always power cycle after updating.',
    parse(html) {
      // Look for things like "FW 0.63", "firmware 0.63", "VRRoom_FW_63"
      const patterns = [
        /VRRoom[_\s-]*FW[_\s-]*(\d+)/i,
        /firmware[^0-9]{0,20}(\d+\.\d+)/i,
        /FW\s*(\d+\.\d+)/i,
      ];
      for (const re of patterns) {
        const m = html.match(re);
        if (m) {
          let v = m[1];
          // "FW_63" style -> 0.63
          if (!v.includes('.') && v.length <= 3) v = `0.${v}`;
          return v;
        }
      }
      return null;
    },
  },
  yamaha_rx_a4a: {
    device: 'Yamaha RX-A4A',
    page: 'https://usa.yamaha.com/support/updates/rx-a4a_avantage.html',
    fallbackPage: 'https://usa.yamaha.com/support/updates/index.html',
    notes:
      'Yamaha AVRs can update directly from the receiver: Setup > Network > Network Update. ' +
      'Or download the file from the Yamaha support page and update via USB.',
    parse(html) {
      const patterns = [
        /firmware\s*version\s*[:\s]*([\d.]+)/i,
        /version\s*([\d]+\.[\d]+)/i,
      ];
      for (const re of patterns) {
        const m = html.match(re);
        if (m) return m[1];
      }
      return null;
    },
  },
  epson_ls12000: {
    device: 'Epson EH-LS12000B',
    page: 'https://www.epson.eu/en_EU/support/sc/epson-eh-ls12000b/s/s1740',
    fallbackPage: 'https://epson.com/Support/Projectors/Home-Theater-Series/Epson-Pro-Cinema-LS12000/s/SPT_V11HA47020',
    notes:
      'Download the firmware update tool from the Epson support page for your region. ' +
      'The projector updates via USB stick or the Epson firmware updater over USB cable.',
    parse(html) {
      const patterns = [
        /firmware[^0-9]{0,40}([\d]+\.[\d]+(?:\.[\d]+)?)/i,
        /version\s*([\d]+\.[\d]+)/i,
      ];
      for (const re of patterns) {
        const m = html.match(re);
        if (m) return m[1];
      }
      return null;
    },
  },
};

async function checkDevice(key) {
  const checker = CHECKERS[key];
  if (!checker) throw new Error(`Unknown device: ${key}`);

  const result = {
    key,
    device: checker.device,
    download_page: checker.page,
    fallback_page: checker.fallbackPage,
    notes: checker.notes,
    latest_version: null,
    parse_ok: false,
    error: null,
    checked_at: new Date().toISOString(),
  };

  try {
    const html = await fetchPage(checker.page);
    result.latest_version = checker.parse(html);
    result.parse_ok = result.latest_version !== null;
  } catch (err) {
    result.error = err.message;
  }

  return result;
}

async function checkAll() {
  const keys = Object.keys(CHECKERS);
  const results = [];
  for (const key of keys) {
    // Sequential with modest pacing - be polite to vendor sites
    results.push(await checkDevice(key));
  }
  return results;
}

module.exports = { checkDevice, checkAll, CHECKERS };
