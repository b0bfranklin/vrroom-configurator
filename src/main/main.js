/**
 * AV Signal Lab - Electron main process.
 */
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');

const data = require('../core/data');
const { ConfigAnalyzer, compareWithRecommended } = require('../core/configAnalyzer');
const { RecommendationEngine } = require('../core/recommendations');
const { toSetCommands } = require('../core/commands');
const { BackupManager } = require('./backups');
const { ManualLibrary } = require('./manuals');
const updates = require('./updates');
const vrroom = require('./vrroomClient');

let mainWindow = null;
let backups = null;
let manualLibrary = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 900,
    minWidth: 980,
    minHeight: 640,
    backgroundColor: '#0d1117',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
}

app.whenReady().then(() => {
  backups = new BackupManager(app.getPath('userData'));
  manualLibrary = new ManualLibrary(app.getPath('userData'), data.deviceManuals());
  registerIpc();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

function ok(payload) {
  return { success: true, ...payload };
}

function fail(err) {
  return { success: false, error: err instanceof Error ? err.message : String(err) };
}

function registerIpc() {
  // ---------------------------------------------------------------- data
  ipcMain.handle('data:devices', () => data.devices());
  ipcMain.handle('data:goals', () => data.optimizationGoals());
  ipcMain.handle('data:edid-presets', () => data.edidPresets());
  ipcMain.handle('data:vrroom-settings-meta', () => data.vrroomSettingsMeta());
  ipcMain.handle('data:speaker-tuning', () => data.speakerTuningGuides());
  ipcMain.handle('data:manual-sources', () => data.deviceManuals());

  // ------------------------------------------------------ config analysis
  ipcMain.handle('config:open-and-analyze', async (_e, { recommendedSettings } = {}) => {
    try {
      const result = await dialog.showOpenDialog(mainWindow, {
        title: 'Open VRROOM config export',
        filters: [
          { name: 'Config files', extensions: ['json', 'txt', 'cfg'] },
          { name: 'All files', extensions: ['*'] },
        ],
        properties: ['openFile'],
      });
      if (result.canceled || !result.filePaths.length) return ok({ canceled: true });

      const filePath = result.filePaths[0];
      const raw = fs.readFileSync(filePath, 'utf-8');
      let config;
      try {
        config = JSON.parse(raw);
      } catch (_) {
        return fail('File is not valid JSON. Export the config from the VRROOM web UI (CONFIG > EXPORT).');
      }

      const analysis = new ConfigAnalyzer(config).analyze();
      const diff = recommendedSettings
        ? compareWithRecommended(config, recommendedSettings)
        : null;
      // Full config with the recommended settings merged in - safe to
      // re-import because it starts from the device's own export.
      const mergedConfig = recommendedSettings
        ? { ...config, ...recommendedSettings, _merged_by: 'AV Signal Lab', _merged_date: new Date().toISOString() }
        : null;

      // Auto-backup every config the user opens
      const backup = backups.save({
        deviceType: 'vrroom',
        deviceName: 'HDFury VRROOM',
        content: raw,
        note: 'Auto-backup on analyze',
        sourceFile: path.basename(filePath),
      });

      return ok({ file: filePath, config, analysis, diff, mergedConfig, backup });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('config:analyze-object', (_e, { config, recommendedSettings }) => {
    try {
      const analysis = new ConfigAnalyzer(config).analyze();
      const diff = recommendedSettings ? compareWithRecommended(config, recommendedSettings) : null;
      return ok({ analysis, diff });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('config:save-optimized', async (_e, { optimizedConfig }) => {
    try {
      const result = await dialog.showSaveDialog(mainWindow, {
        title: 'Save optimized VRROOM config',
        defaultPath: 'vrroom_optimized.json',
        filters: [{ name: 'JSON', extensions: ['json'] }],
      });
      if (result.canceled || !result.filePath) return ok({ canceled: true });
      fs.writeFileSync(result.filePath, JSON.stringify(optimizedConfig, null, 2));
      return ok({ file: result.filePath });
    } catch (err) {
      return fail(err);
    }
  });

  // ------------------------------------------------------ recommendations
  ipcMain.handle('recommend:generate', (_e, setup) => {
    try {
      const engine = new RecommendationEngine(setup);
      const result = engine.generate();
      result.set_commands = toSetCommands(result.vrroom_settings);
      return ok({ result });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('recommend:save-settings-file', async (_e, { settings }) => {
    try {
      const result = await dialog.showSaveDialog(mainWindow, {
        title: 'Save recommended VRROOM settings',
        defaultPath: 'vrroom_recommended_settings.json',
        filters: [{ name: 'JSON', extensions: ['json'] }],
      });
      if (result.canceled || !result.filePath) return ok({ canceled: true });
      const payload = {
        _note:
          'Recommended settings from AV Signal Lab. This is NOT a full VRROOM export - ' +
          'to build an importable file, open your device export in the Config Analyzer ' +
          'and use "Save Config With Recommended Settings".',
        _generated: new Date().toISOString(),
        ...settings,
      };
      fs.writeFileSync(result.filePath, JSON.stringify(payload, null, 2));
      return ok({ file: result.filePath });
    } catch (err) {
      return fail(err);
    }
  });

  // --------------------------------------------------------------- backups
  ipcMain.handle('backups:list', () => {
    try {
      return ok({ backups: backups.list() });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('backups:read', (_e, { id }) => {
    try {
      return ok(backups.read(id));
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('backups:delete', (_e, { id }) => {
    try {
      backups.remove(id);
      return ok({});
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('backups:export', async (_e, { id }) => {
    try {
      const { entry } = backups.read(id);
      const result = await dialog.showSaveDialog(mainWindow, {
        title: 'Export backup',
        defaultPath: entry.filename,
        filters: [{ name: 'JSON', extensions: ['json'] }],
      });
      if (result.canceled || !result.filePath) return ok({ canceled: true });
      backups.exportTo(id, result.filePath);
      return ok({ file: result.filePath });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('backups:import', async () => {
    try {
      const result = await dialog.showOpenDialog(mainWindow, {
        title: 'Import config file as backup',
        filters: [
          { name: 'Config files', extensions: ['json', 'txt', 'cfg', 'dat'] },
          { name: 'All files', extensions: ['*'] },
        ],
        properties: ['openFile'],
      });
      if (result.canceled || !result.filePaths.length) return ok({ canceled: true });
      const filePath = result.filePaths[0];
      const content = fs.readFileSync(filePath, 'utf-8');
      const entry = backups.save({
        deviceType: 'imported',
        deviceName: path.basename(filePath),
        content,
        note: 'Manually imported',
        sourceFile: path.basename(filePath),
      });
      return ok({ backup: entry });
    } catch (err) {
      return fail(err);
    }
  });

  // --------------------------------------------------------------- updates
  ipcMain.handle('updates:check-all', async () => {
    try {
      return ok({ results: await updates.checkAll() });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('updates:check', async (_e, { key }) => {
    try {
      return ok({ result: await updates.checkDevice(key) });
    } catch (err) {
      return fail(err);
    }
  });

  // --------------------------------------------------------------- manuals
  ipcMain.handle('manuals:list', () => {
    try {
      return ok({ manuals: manualLibrary.list() });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('manuals:download', async (_e, { deviceId, kind }) => {
    try {
      const result = await manualLibrary.download(deviceId, kind);
      return ok({ result });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('manuals:open-local', (_e, { localPath }) => {
    try {
      // Only open files inside our manuals directory
      const resolved = path.resolve(localPath);
      if (!resolved.startsWith(path.resolve(manualLibrary.dir))) {
        return fail('Refusing to open a file outside the manuals folder');
      }
      shell.openPath(resolved);
      return ok({});
    } catch (err) {
      return fail(err);
    }
  });

  // ------------------------------------------------------------------ live
  ipcMain.handle('vrroom:read-settings', async (_e, { host, port }) => {
    try {
      const batch = await vrroom.readBatch(host, port, vrroom.SETTINGS_TARGETS);
      const config = vrroom.parseSettingsResults(batch.results);
      return ok({ ...batch, config });
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('vrroom:read-status', async (_e, { host, port }) => {
    try {
      const batch = await vrroom.readBatch(host, port, vrroom.STATUS_TARGETS);
      return ok(batch);
    } catch (err) {
      return fail(err);
    }
  });

  // ------------------------------------------------------------------ misc
  ipcMain.handle('shell:open-external', (_e, { url }) => {
    try {
      if (!/^https?:\/\//i.test(url)) return fail('Only http(s) links can be opened');
      shell.openExternal(url);
      return ok({});
    } catch (err) {
      return fail(err);
    }
  });

  ipcMain.handle('app:info', () => {
    return ok({
      version: app.getVersion(),
      platform: process.platform,
      arch: process.arch,
      userData: app.getPath('userData'),
    });
  });
}
