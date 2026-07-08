/**
 * Data loader - reads the JSON knowledge base extracted from the legacy app.
 * Platform-agnostic: only depends on Node fs/path, reusable in a Capacitor
 * shell later by swapping the loader.
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', '..', 'data');

const cache = {};

function load(name) {
  if (!(name in cache)) {
    const file = path.join(DATA_DIR, `${name}.json`);
    cache[name] = JSON.parse(fs.readFileSync(file, 'utf-8'));
  }
  return cache[name];
}

module.exports = {
  devices: () => load('devices'),
  vrroomSettingsMeta: () => load('vrroom-settings-meta'),
  deviceManuals: () => load('device-manuals'),
  edidPresets: () => load('edid-presets'),
  optimizationGoals: () => load('optimization-goals'),
  speakerTuningGuides: () => load('speaker-tuning-guides'),
};
