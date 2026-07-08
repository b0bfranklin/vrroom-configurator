/**
 * Preload bridge - exposes a minimal, typed API surface to the renderer.
 * No Node APIs leak into the page.
 */
const { contextBridge, ipcRenderer } = require('electron');

const invoke = (channel, payload) => ipcRenderer.invoke(channel, payload);

contextBridge.exposeInMainWorld('api', {
  // data
  getDevices: () => invoke('data:devices'),
  getGoals: () => invoke('data:goals'),
  getEdidPresets: () => invoke('data:edid-presets'),
  getVrroomSettingsMeta: () => invoke('data:vrroom-settings-meta'),
  getSpeakerTuning: () => invoke('data:speaker-tuning'),
  getManualSources: () => invoke('data:manual-sources'),

  // config analysis
  openAndAnalyzeConfig: (recommendedSettings) =>
    invoke('config:open-and-analyze', { recommendedSettings }),
  analyzeConfigObject: (config, recommendedSettings) =>
    invoke('config:analyze-object', { config, recommendedSettings }),
  saveOptimizedConfig: (optimizedConfig) => invoke('config:save-optimized', { optimizedConfig }),

  // recommendations
  generateRecommendations: (setup) => invoke('recommend:generate', setup),

  // backups
  listBackups: () => invoke('backups:list'),
  readBackup: (id) => invoke('backups:read', { id }),
  deleteBackup: (id) => invoke('backups:delete', { id }),
  exportBackup: (id) => invoke('backups:export', { id }),
  importBackup: () => invoke('backups:import'),

  // updates
  checkAllUpdates: () => invoke('updates:check-all'),
  checkUpdate: (key) => invoke('updates:check', { key }),

  // manuals
  listManuals: () => invoke('manuals:list'),
  downloadManual: (deviceId, kind) => invoke('manuals:download', { deviceId, kind }),
  openLocalManual: (localPath) => invoke('manuals:open-local', { localPath }),

  // live vrroom (read-only)
  vrroomReadSettings: (host, port) => invoke('vrroom:read-settings', { host, port }),
  vrroomReadStatus: (host, port) => invoke('vrroom:read-status', { host, port }),

  // misc
  openExternal: (url) => invoke('shell:open-external', { url }),
  appInfo: () => invoke('app:info'),
});
