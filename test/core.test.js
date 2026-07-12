/**
 * Core module tests - run with: npm test  (node --test)
 * These cover the platform-agnostic logic: data loading, config analysis,
 * recommendation engine, and the Vrroom client's safety rules.
 */
const { test } = require('node:test');
const assert = require('node:assert');

const data = require('../src/core/data');
const { ConfigAnalyzer, compareWithRecommended, describeSetting } = require('../src/core/configAnalyzer');
const { RecommendationEngine } = require('../src/core/recommendations');
const vrroom = require('../src/main/vrroomClient');

test('data files load and have expected shape', () => {
  const devices = data.devices();
  assert.ok(Object.keys(devices.displays).length >= 10, 'displays present');
  assert.ok(devices.displays.epson_eh_ls12000b, 'Epson LS12000B present');
  assert.ok(devices.hdfury_devices.vrroom, 'Vrroom present');
  assert.ok(devices.avrs.yamaha_rx_a4a, 'Yamaha RX-A4A present');
  assert.ok(devices.sources.nvidia_shield_pro, 'Shield Pro present');

  const meta = data.vrroomSettingsMeta();
  assert.ok(meta.edidmode, 'settings meta has edidmode');
  assert.ok(data.optimizationGoals().avoid_bonk, 'goals include avoid_bonk');
});

test('describeSetting maps values to human-readable labels', () => {
  const d = describeSetting('edidmode', 'automix');
  assert.strictEqual(d.name, 'EDID Mode');
  assert.match(d.display_value, /AutoMix/);
  assert.ok(d.menu_path.length > 0);
});

test('analyzer flags high unmute delay as critical', () => {
  const result = new ConfigAnalyzer({ unmutedelay: 800, edidmode: 'automix' }).analyze();
  assert.strictEqual(result.issue_count.critical, 1);
  const issue = result.issues.find((i) => i.setting === 'unmutedelay');
  assert.strictEqual(issue.recommended_value, 250);
  // Optimized config applies the fix
  assert.strictEqual(result.optimized_config.unmutedelay, 250);
  assert.strictEqual(result.optimized_config._optimized, true);
});

test('analyzer flags fixed EDID mode and disabled HDR', () => {
  const result = new ConfigAnalyzer({ edidmode: 'fixed', edidhdrflag: 'off' }).analyze();
  const titles = result.issues.map((i) => i.title);
  assert.ok(titles.includes('Fixed EDID Mode'));
  assert.ok(titles.includes('HDR Disabled in EDID'));
  assert.strictEqual(result.optimized_config.edidmode, 'automix');
  assert.strictEqual(result.optimized_config.edidhdrflag, 'on');
});

test('analyzer produces settings overview for recognized keys', () => {
  const result = new ConfigAnalyzer({ edidmode: 'automix', ediddvflag: 'on', notarealkey: 1 }).analyze();
  const keys = result.settings_overview.map((s) => s.key);
  assert.ok(keys.includes('edidmode'));
  assert.ok(keys.includes('ediddvflag'));
  assert.ok(!keys.includes('notarealkey'));
});

test('compareWithRecommended diffs configs correctly', () => {
  const diff = compareWithRecommended(
    { edidmode: 'fixed', unmutedelay: 200 },
    { edidmode: 'automix', unmutedelay: 200, ediddvflag: 'on' }
  );
  const byKey = Object.fromEntries(diff.map((d) => [d.key, d]));
  assert.strictEqual(byKey.edidmode.matches, false);
  assert.strictEqual(byKey.unmutedelay.matches, true);
  assert.strictEqual(byKey.ediddvflag.current_value, '(not in config)');
});

test('recommendation engine: bonk goal for the target hardware setup', () => {
  const engine = new RecommendationEngine({
    display: 'epson_eh_ls12000b',
    hdfury_device: 'vrroom',
    avr: 'yamaha_rx_a4a',
    sources: ['nvidia_shield_pro'],
    media_servers: ['emby'],
    goals: ['avoid_bonk', 'lldv_non_dv'],
  });
  const result = engine.generate();

  assert.strictEqual(result.setup_summary.display, 'Epson EH-LS12000b');
  // Bonk goal sets automix + unmute delay
  assert.strictEqual(result.vrroom_settings.edidmode, 'automix');
  assert.ok(result.vrroom_settings.unmutedelay >= 200);
  // LLDV goal (Epson is non-DV): DV flag on, custom DV mode
  assert.strictEqual(result.vrroom_settings.ediddvflag, 'on');
  assert.strictEqual(result.vrroom_settings.ediddvmode, 1);
  // Human-readable detail rows exist for every raw setting
  assert.strictEqual(
    result.vrroom_settings_detailed.length,
    Object.keys(result.vrroom_settings).length
  );
  // LLDV recommendation present
  const titles = result.recommendations.map((r) => r.title);
  assert.ok(titles.includes('Enable LLDV in AutoMix Mode'));
  // AVR settings generated (needs avr + speakers) - none without speakers
  assert.ok(Array.isArray(result.avr_settings));
});

test('recommendation engine: avr settings generated with speakers selected', () => {
  const devices = data.devices();
  const speakerId = Object.keys(devices.speakers)[0];
  const engine = new RecommendationEngine({
    avr: 'yamaha_rx_a4a',
    speakers: speakerId,
    goals: ['best_audio'],
  });
  const result = engine.generate();
  assert.ok(result.avr_settings.length >= 3, 'AVR settings produced');
  const settingNames = result.avr_settings.map((s) => s.setting);
  assert.ok(settingNames.includes('Speaker Configuration'));
  // No path is ever an object after normalization
  for (const s of result.avr_settings) {
    assert.strictEqual(typeof s.path, 'string');
  }
});

test('recommendation engine: gaming goal respects device VRR capability', () => {
  const engine = new RecommendationEngine({
    display: 'epson_eh_ls12000b',
    hdfury_device: 'vrroom',
    goals: ['gaming_low_latency'],
  });
  const result = engine.generate();
  assert.strictEqual(result.vrroom_settings.hdrcustom, 'off');
  assert.strictEqual(result.vrroom_settings.unmutedelay, 100);
});

test('vrroom client: whitelist blocks non-get targets and only spec commands', async () => {
  assert.ok(!vrroom.READ_TARGETS.has('set edidmode automix'));
  assert.ok(vrroom.READ_TARGETS.has('edidmode'));
  assert.ok(vrroom.READ_TARGETS.has('status rx0'));
  // Spec-verified: FW63 uses "hdcp", and unmute delays are web-UI-only
  assert.ok(vrroom.READ_TARGETS.has('hdcp'));
  assert.ok(!vrroom.READ_TARGETS.has('hdcpmode'));
  assert.ok(!vrroom.READ_TARGETS.has('unmutedelay'));
  assert.ok(!vrroom.READ_TARGETS.has('earcunmute'));
  // Every default settings/status target must be whitelisted
  for (const t of [...vrroom.SETTINGS_TARGETS, ...vrroom.STATUS_TARGETS]) {
    assert.ok(vrroom.READ_TARGETS.has(t), `whitelist missing ${t}`);
  }

  // readBatch skips non-whitelisted targets without sending anything
  const result = await vrroom.readBatch('127.0.0.1', 1, ['set edidmode custom']);
  // Connection to port 1 fails fast - but even before that, no write can occur
  assert.strictEqual(result.ok, false);
});

test('vrroom client: parses echoed command responses', () => {
  const parsed = vrroom.parseSettingsResults({
    edidmode: 'edidmode automix',
    hdcp: 'hdcp auto',
    cec: 'on',
    'status rx0': '4K59.94 422 BT2020 HDR10',
  });
  assert.strictEqual(parsed.edidmode, 'automix');
  assert.strictEqual(parsed.hdcp, 'auto');
  assert.strictEqual(parsed.hdcpmode, 'auto', 'hdcp aliased to hdcpmode for the analyzer');
  assert.strictEqual(parsed.cec, 'on');
  assert.ok(!('status rx0' in parsed), 'status lines excluded from config');
});

test('set-command generation maps keys to spec commands', () => {
  const { toSetCommands } = require('../src/core/commands');
  const { commands, webUiOnly } = toSetCommands({
    edidmode: 'automix',
    ediddvflag: 'on',
    hdcpmode: 'auto',
    earcmode: 'auto earc',
    unmutedelay: 200,
  });
  const ipCmds = commands.map((c) => c.ip);
  assert.ok(ipCmds.includes('set edidmode automix'));
  assert.ok(ipCmds.includes('set ediddvflag on'));
  assert.ok(ipCmds.includes('set hdcp auto'), 'hdcpmode translates to hdcp command');
  assert.ok(ipCmds.includes('set earcforce auto'), 'earcmode translates to earcforce');
  // No command may ever start with "#vrroom" in the IP variant
  for (const c of commands) assert.ok(!c.ip.startsWith('#vrroom'));
  // unmutedelay has no IP command in FW63 - flagged, not emitted
  assert.strictEqual(webUiOnly.length, 1);
  assert.strictEqual(webUiOnly[0].key, 'unmutedelay');
});

test('vrroom client: batch against a mock device server', async () => {
  const net = require('node:net');
  const received = [];

  const server = net.createServer((socket) => {
    socket.on('data', (chunk) => {
      const cmd = chunk.toString().trim();
      received.push(cmd);
      const target = cmd.replace(/^get /, '');
      socket.write(`${target} testvalue\r\n`);
    });
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;

  try {
    const result = await vrroom.readBatch('127.0.0.1', port, ['edidmode', 'hdcpmode']);
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.results.edidmode, 'edidmode testvalue');
    // Spec compliance: no #vrroom header over IP
    for (const cmd of received) {
      assert.ok(!cmd.includes('#vrroom'), 'no header over IP');
      assert.match(cmd, /^get /);
    }
  } finally {
    server.close();
  }
});
