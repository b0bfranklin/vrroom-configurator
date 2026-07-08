/**
 * Config backup manager.
 * Stores versioned VRROOM config backups (and any device config file)
 * in the app's user data directory with timestamps and notes.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class BackupManager {
  constructor(userDataDir) {
    this.dir = path.join(userDataDir, 'backups');
    fs.mkdirSync(this.dir, { recursive: true });
    this.indexFile = path.join(this.dir, 'index.json');
  }

  loadIndex() {
    try {
      return JSON.parse(fs.readFileSync(this.indexFile, 'utf-8'));
    } catch (_) {
      return [];
    }
  }

  saveIndex(index) {
    fs.writeFileSync(this.indexFile, JSON.stringify(index, null, 2));
  }

  /**
   * Save a backup. `content` is a string (JSON text or raw config text).
   * Returns the backup entry.
   */
  save({ deviceType, deviceName, content, note, sourceFile }) {
    const id = crypto.randomUUID();
    const timestamp = new Date().toISOString();
    const filename = `${timestamp.replace(/[:.]/g, '-')}_${deviceType || 'config'}_${id.slice(0, 8)}.json`;
    const filepath = path.join(this.dir, filename);
    fs.writeFileSync(filepath, content);

    const entry = {
      id,
      timestamp,
      device_type: deviceType || 'vrroom',
      device_name: deviceName || 'HDFury VRROOM',
      note: note || '',
      source_file: sourceFile || '',
      filename,
      size: Buffer.byteLength(content),
    };

    const index = this.loadIndex();
    index.unshift(entry);
    this.saveIndex(index);
    return entry;
  }

  list() {
    return this.loadIndex();
  }

  read(id) {
    const entry = this.loadIndex().find((e) => e.id === id);
    if (!entry) throw new Error('Backup not found');
    const content = fs.readFileSync(path.join(this.dir, entry.filename), 'utf-8');
    return { entry, content };
  }

  remove(id) {
    const index = this.loadIndex();
    const entry = index.find((e) => e.id === id);
    if (!entry) throw new Error('Backup not found');
    try {
      fs.unlinkSync(path.join(this.dir, entry.filename));
    } catch (_) {
      /* file already gone */
    }
    this.saveIndex(index.filter((e) => e.id !== id));
    return true;
  }

  /** Export a backup's content to a user-chosen path. */
  exportTo(id, destPath) {
    const { content } = this.read(id);
    fs.writeFileSync(destPath, content);
    return destPath;
  }
}

module.exports = { BackupManager };
