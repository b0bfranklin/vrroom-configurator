/* AV Signal Lab - renderer */
/* global api */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  devices: null,
  goals: null,
  lastRecommendation: null, // full engine result
  lastAnalysis: null, // last config analysis
  liveConfig: null, // settings read live from the device
};

const STORAGE_KEY = 'avsl_setup_v2';

// ------------------------------------------------------------------ utils

function esc(s) {
  const div = document.createElement('div');
  div.textContent = String(s === undefined || s === null ? '' : s);
  return div.innerHTML;
}

function issueHtml(issue) {
  const sev = issue.severity || 'info';
  return `
    <div class="issue ${esc(sev)}">
      <span class="badge">${esc(sev)}</span>
      <span class="title">${esc(issue.title)}</span>
      <div class="desc">${esc(issue.description)}</div>
      ${issue.current_value !== undefined
        ? `<div class="values"><span class="cur">Current: ${esc(issue.current_value)}</span>
           &nbsp;&rarr;&nbsp; <span class="rec">Recommended: ${esc(issue.recommended_value)}</span></div>`
        : ''}
    </div>`;
}

function pathHtml(setting) {
  const parts = [];
  if (setting.tab) parts.push(`<span class="tab-name">${esc(setting.tab)}</span>`);
  if (setting.path || setting.menu_path) parts.push(esc(setting.path || setting.menu_path));
  if (!parts.length) return '';
  return `<div class="path">${parts.join(' &gt; ')}</div>`;
}

function saveSetup(setup) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(setup));
  } catch (_) { /* ignore */ }
}

function loadSetup() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch (_) {
    return {};
  }
}

// ------------------------------------------------------------------- nav

$$('.nav-item').forEach((item) => {
  item.addEventListener('click', () => {
    $$('.nav-item').forEach((n) => n.classList.remove('active'));
    $$('.tab-content').forEach((t) => t.classList.remove('active'));
    item.classList.add('active');
    $(`#tab-${item.dataset.tab}`).classList.add('active');
  });
});

// -------------------------------------------------------------- my setup

function populateSelect(id, devices, savedValue) {
  const select = $(id);
  for (const [key, dev] of Object.entries(devices || {})) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = dev.name || key;
    select.appendChild(opt);
  }
  if (savedValue) select.value = savedValue;
  select.addEventListener('change', persistSetup);
}

function populateChecks(containerId, items, savedList, renderLabel) {
  const container = $(containerId);
  container.innerHTML = '';
  for (const [key, item] of Object.entries(items || {})) {
    const label = document.createElement('label');
    const checked = (savedList || []).includes(key);
    if (checked) label.classList.add('checked');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = key;
    cb.checked = checked;
    cb.addEventListener('change', () => {
      label.classList.toggle('checked', cb.checked);
      persistSetup();
    });
    label.appendChild(cb);
    const span = document.createElement('span');
    span.innerHTML = renderLabel(item);
    label.appendChild(span);
    container.appendChild(label);
  }
}

function currentSetup() {
  return {
    display: $('#sel-display').value,
    hdfury_device: $('#sel-hdfury').value,
    avr: $('#sel-avr').value,
    speakers: $('#sel-speakers').value,
    screen: $('#sel-screen').value,
    sources: $$('#chk-sources input:checked').map((c) => c.value),
    media_servers: $$('#chk-servers input:checked').map((c) => c.value),
    goals: $$('#chk-goals input:checked').map((c) => c.value),
  };
}

function persistSetup() {
  saveSetup(currentSetup());
}

async function initSetupTab() {
  const saved = loadSetup();
  state.devices = await api.getDevices();
  state.goals = await api.getGoals();

  populateSelect('#sel-display', state.devices.displays, saved.display);
  populateSelect('#sel-hdfury', state.devices.hdfury_devices, saved.hdfury_device);
  populateSelect('#sel-avr', state.devices.avrs, saved.avr);
  populateSelect('#sel-speakers', state.devices.speakers, saved.speakers);
  populateSelect('#sel-screen', state.devices.screens, saved.screen);

  populateChecks('#chk-sources', state.devices.sources, saved.sources, (d) => esc(d.name));
  populateChecks('#chk-servers', state.devices.media_servers, saved.media_servers, (d) => esc(d.name));
  populateChecks('#chk-goals', state.goals, saved.goals, (g) =>
    `${esc(g.name)}<span class="goal-desc">${esc(g.description)}</span>`
  );
}

$('#btn-generate').addEventListener('click', async () => {
  const setup = currentSetup();
  if (!setup.goals.length) {
    $('#generate-status').textContent = 'Select at least one optimization goal.';
    return;
  }
  saveSetup(setup);
  $('#generate-status').innerHTML = '<span class="spinner"></span>Generating...';

  const res = await api.generateRecommendations(setup);
  $('#generate-status').textContent = '';
  if (!res.success) {
    $('#generate-status').textContent = `Error: ${res.error}`;
    return;
  }

  state.lastRecommendation = res.result;
  renderRecommendations(res.result);
  $('#analyzer-reco-note').style.display = 'block';
});

function renderRecommendations(result) {
  $('#setup-results').style.display = 'block';

  const s = result.setup_summary;
  $('#setup-summary').innerHTML = [
    ['Display', s.display],
    ['Processor', s.hdfury_device],
    ['AVR', s.avr],
    ['Sources', (s.sources || []).join(', ')],
    ['Speakers', s.speakers],
    ['Screen', s.screen],
    ['Servers', (s.media_servers || []).join(', ')],
    ['Goals', (s.goals || []).join(', ')],
  ]
    .filter(([, v]) => v && v !== 'Not specified')
    .map(([k, v]) => `<span class="chip"><b>${esc(k)}:</b> ${esc(v)}</span>`)
    .join('');

  $('#setup-recs').innerHTML =
    (result.recommendations || []).map(issueHtml).join('') ||
    '<p class="muted">No recommendations.</p>';

  const vs = result.vrroom_settings_detailed || [];
  $('#card-vrroom-settings').style.display = vs.length ? 'block' : 'none';
  $('#tbl-vrroom-settings tbody').innerHTML = vs
    .map(
      (x) => `<tr>
        <td><b>${esc(x.name)}</b>${pathHtml(x)}</td>
        <td class="value-green mono">${esc(x.display_value)}</td>
        <td class="muted">${esc(x.description)}</td>
      </tr>`
    )
    .join('');

  const src = result.source_settings || [];
  $('#card-source-settings').style.display = src.length ? 'block' : 'none';
  $('#tbl-source-settings tbody').innerHTML = src
    .map(
      (x) => `<tr>
        <td><b>${esc(x.setting)}</b>${pathHtml(x)}</td>
        <td class="value-green">${esc(x.value)}</td>
        <td style="color: var(--accent-purple);">${esc(x.device || '')}</td>
        <td class="muted">${esc(x.reason || '')}</td>
      </tr>`
    )
    .join('');

  const avr = result.avr_settings || [];
  $('#card-avr-settings').style.display = avr.length ? 'block' : 'none';
  $('#tbl-avr-settings tbody').innerHTML = avr
    .map(
      (x) => `<tr>
        <td><b>${esc(x.setting)}</b>${pathHtml(x)}</td>
        <td class="value-green">${esc(x.value)}</td>
        <td class="muted">${esc(x.reason || '')}</td>
      </tr>`
    )
    .join('');

  const disp = result.display_settings || [];
  $('#card-display-settings').style.display = disp.length ? 'block' : 'none';
  $('#tbl-display-settings tbody').innerHTML = disp
    .map(
      (x) => `<tr>
        <td><b>${esc(x.setting)}</b>${pathHtml(x)}</td>
        <td class="value-green">${esc(x.value)}</td>
        <td class="muted">${esc(x.reason || '')}</td>
      </tr>`
    )
    .join('');
}

// -------------------------------------------------------- config analyzer

$('#btn-open-config').addEventListener('click', async () => {
  $('#analyzer-status').innerHTML = '<span class="spinner"></span>Analyzing...';
  const recommended = state.lastRecommendation ? state.lastRecommendation.vrroom_settings : null;
  const res = await api.openAndAnalyzeConfig(recommended);
  $('#analyzer-status').textContent = '';

  if (!res.success) {
    $('#analyzer-status').textContent = `Error: ${res.error}`;
    return;
  }
  if (res.canceled) return;

  state.lastAnalysis = res;
  renderAnalysis(res.analysis, res.diff, res.file);
  $('#analyzer-status').textContent = `Backed up automatically (${res.backup.filename})`;
  refreshBackups();
});

function renderAnalysis(analysis, diff, fileLabel) {
  $('#analyzer-results').style.display = 'block';

  const c = analysis.issue_count;
  $('#analyzer-counts').innerHTML = `
    <div class="count-box critical"><div class="n">${c.critical}</div><div class="lbl">Critical</div></div>
    <div class="count-box warning"><div class="n">${c.warning}</div><div class="lbl">Warnings</div></div>
    <div class="count-box info"><div class="n">${c.info}</div><div class="lbl">Info</div></div>`;

  const issues = analysis.issues || [];
  const recos = analysis.recommendations || [];
  $('#analyzer-issues').innerHTML =
    (issues.map(issueHtml).join('') ||
      '<p style="color: var(--accent-green);">No issues found - this config looks good.</p>') +
    recos
      .map(
        (r) => `<div class="issue info"><span class="badge">note</span>
          <span class="title">${esc(r.title)}</span><div class="desc">${esc(r.description)}</div></div>`
      )
      .join('');

  // Diff vs recommendation
  if (diff && diff.length) {
    $('#card-diff').style.display = 'block';
    $('#tbl-diff tbody').innerHTML = diff
      .map(
        (d) => `<tr>
          <td class="${d.matches ? 'match-yes' : 'match-no'}">${d.matches ? 'OK' : 'DIFF'}</td>
          <td><b>${esc(d.name)}</b></td>
          <td class="mono">${esc(d.current_value)}</td>
          <td class="mono value-green">${esc(d.display_value)}</td>
          <td class="muted">${esc(d.tab ? d.tab + ' > ' : '')}${esc(d.menu_path)}</td>
        </tr>`
      )
      .join('');
  } else {
    $('#card-diff').style.display = 'none';
  }

  // Settings overview
  const overview = analysis.settings_overview || [];
  if (overview.length) {
    $('#card-overview').style.display = 'block';
    $('#tbl-overview tbody').innerHTML = overview
      .map(
        (o) => `<tr>
          <td><b>${esc(o.name)}</b></td>
          <td class="mono ${o.is_set ? 'value-green' : 'muted'}">${esc(o.display_value)}</td>
          <td class="muted">${esc(o.tab ? o.tab + ' > ' : '')}${esc(o.menu_path)}</td>
        </tr>`
      )
      .join('');
  } else {
    $('#card-overview').style.display = 'none';
  }

  const btn = $('#btn-save-optimized');
  if (analysis.optimized_config && (c.critical > 0 || c.warning > 0)) {
    btn.style.display = 'inline-block';
    btn.onclick = async () => {
      const res = await api.saveOptimizedConfig(analysis.optimized_config);
      if (res.success && res.file) {
        $('#analyzer-status').textContent = `Saved: ${res.file}. Import via VRROOM web UI, then power cycle.`;
      }
    };
  } else {
    btn.style.display = 'none';
  }
}

// ---------------------------------------------------------------- backups

async function refreshBackups() {
  const res = await api.listBackups();
  if (!res.success) return;
  const rows = res.backups || [];
  $('#backups-empty').style.display = rows.length ? 'none' : 'block';
  $('#tbl-backups tbody').innerHTML = rows
    .map(
      (b) => `<tr>
        <td>${esc(new Date(b.timestamp).toLocaleString())}</td>
        <td>${esc(b.device_name)}<div class="path">${esc(b.source_file || '')}</div></td>
        <td class="muted">${esc(b.note)}</td>
        <td>${(b.size / 1024).toFixed(1)} KB</td>
        <td class="row-actions">
          <button class="btn small secondary" data-act="export" data-id="${esc(b.id)}">Export</button>
          <button class="btn small secondary" data-act="analyze" data-id="${esc(b.id)}">Analyze</button>
          <button class="btn small danger" data-act="delete" data-id="${esc(b.id)}">Delete</button>
        </td>
      </tr>`
    )
    .join('');
}

$('#tbl-backups').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const { act, id } = btn.dataset;

  if (act === 'delete') {
    await api.deleteBackup(id);
    refreshBackups();
  } else if (act === 'export') {
    await api.exportBackup(id);
  } else if (act === 'analyze') {
    const res = await api.readBackup(id);
    if (!res.success) return;
    let config;
    try {
      config = JSON.parse(res.content);
    } catch (_) {
      alert('This backup is not JSON, so it cannot be analyzed as a VRROOM config.');
      return;
    }
    const recommended = state.lastRecommendation ? state.lastRecommendation.vrroom_settings : null;
    const ares = await api.analyzeConfigObject(config, recommended);
    if (ares.success) {
      // Jump to analyzer tab and show
      $$('.nav-item').forEach((n) => n.classList.remove('active'));
      $$('.tab-content').forEach((t) => t.classList.remove('active'));
      $('[data-tab="analyzer"]').classList.add('active');
      $('#tab-analyzer').classList.add('active');
      renderAnalysis(ares.analysis, ares.diff, res.entry.filename);
    }
  }
});

$('#btn-import-backup').addEventListener('click', async () => {
  await api.importBackup();
  refreshBackups();
});
$('#btn-refresh-backups').addEventListener('click', refreshBackups);

// ---------------------------------------------------------------- updates

$('#btn-check-updates').addEventListener('click', async () => {
  $('#updates-status').innerHTML = '<span class="spinner"></span>Checking manufacturer pages...';
  const res = await api.checkAllUpdates();
  $('#updates-status').textContent = '';
  if (!res.success) {
    $('#updates-status').textContent = `Error: ${res.error}`;
    return;
  }
  $('#updates-results').innerHTML = res.results
    .map((r) => {
      const version = r.parse_ok
        ? `<span class="version-pill">Latest: ${esc(r.latest_version)}</span>`
        : `<span class="version-pill unknown">Version: check page</span>`;
      const errNote = r.error
        ? `<div class="path">Could not read the page automatically (${esc(r.error)}) - use the link.</div>`
        : '';
      return `<div class="card update-card">
        <div>
          <h3>${esc(r.device)}</h3>
          <p class="muted" style="margin: 6px 0 8px; max-width: 640px;">${esc(r.notes)}</p>
          ${errNote}
          <div class="row-actions" style="margin-top: 8px;">
            <a class="link" data-url="${esc(r.download_page)}">Open download page</a>
            <a class="link" data-url="${esc(r.fallback_page)}">Alternative page</a>
          </div>
        </div>
        <div>${version}</div>
      </div>`;
    })
    .join('');
});

$('#updates-results').addEventListener('click', (e) => {
  const link = e.target.closest('a[data-url]');
  if (link) api.openExternal(link.dataset.url);
});

// ---------------------------------------------------------------- manuals

async function refreshManuals() {
  const res = await api.listManuals();
  if (!res.success) return;
  const devices = state.devices || (await api.getDevices());
  const nameOf = (id) => {
    for (const cat of Object.values(devices)) {
      if (cat[id]) return cat[id].name;
    }
    return id;
  };

  $('#tbl-manuals tbody').innerHTML = (res.manuals || [])
    .map(
      (m) => `<tr>
        <td><b>${esc(nameOf(m.device_id))}</b></td>
        <td>${esc(m.kind === 'quick_start' ? 'Quick start guide' : 'User manual')}
          <div class="path">${esc(m.url)}</div></td>
        <td>${m.local_path
          ? '<span class="value-green">Downloaded</span>'
          : '<span class="muted">Not downloaded</span>'}</td>
        <td class="row-actions">
          ${m.local_path
            ? `<button class="btn small secondary" data-act="open" data-path="${esc(m.local_path)}">Open</button>`
            : ''}
          <button class="btn small ${m.local_path ? 'secondary' : ''}" data-act="download"
            data-device="${esc(m.device_id)}" data-kind="${esc(m.kind)}">
            ${m.local_path ? 'Re-download' : 'Download'}
          </button>
          <button class="btn small secondary" data-act="visit" data-url="${esc(m.url)}">Open Link</button>
        </td>
      </tr>`
    )
    .join('');
}

$('#tbl-manuals').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const act = btn.dataset.act;
  if (act === 'open') {
    api.openLocalManual(btn.dataset.path);
  } else if (act === 'visit') {
    api.openExternal(btn.dataset.url);
  } else if (act === 'download') {
    btn.disabled = true;
    btn.textContent = 'Downloading...';
    const res = await api.downloadManual(btn.dataset.device, btn.dataset.kind);
    if (!res.success) {
      btn.disabled = false;
      btn.textContent = 'Retry';
      alert(`Download failed: ${res.error}\nUse "Open Link" to get it in your browser instead.`);
      return;
    }
    refreshManuals();
  }
});

// ------------------------------------------------------------------- live

function liveHostPort() {
  const host = $('#live-host').value.trim();
  const port = parseInt($('#live-port').value, 10) || 2222;
  if (!host) {
    $('#live-status-msg').textContent = 'Enter the VRROOM IP address.';
    return null;
  }
  localStorage.setItem('avsl_live_host', host);
  localStorage.setItem('avsl_live_port', String(port));
  return { host, port };
}

function renderLiveResults(results, errors) {
  $('#card-live-results').style.display = 'block';
  $('#tbl-live tbody').innerHTML = Object.entries(results)
    .map(
      ([target, value]) => `<tr>
        <td class="mono">get ${esc(target)}</td>
        <td class="mono ${value === null ? 'muted' : 'value-green'}">${value === null ? '(no response)' : esc(value)}</td>
      </tr>`
    )
    .join('');
  $('#live-errors').textContent = (errors || []).join(' | ');
}

$('#btn-live-settings').addEventListener('click', async () => {
  const target = liveHostPort();
  if (!target) return;
  $('#live-status-msg').innerHTML = '<span class="spinner"></span>Reading settings (paced, read-only)...';
  const res = await api.vrroomReadSettings(target.host, target.port);
  $('#live-status-msg').textContent = res.success && res.ok ? 'Done.' : 'Read failed - see below.';
  if (res.success) {
    renderLiveResults(res.results || {}, res.errors);
    if (res.ok && res.config && Object.keys(res.config).length) {
      state.liveConfig = res.config;
      $('#btn-live-analyze').style.display = 'inline-block';
    }
  } else {
    $('#live-status-msg').textContent = `Error: ${res.error}`;
  }
});

$('#btn-live-status').addEventListener('click', async () => {
  const target = liveHostPort();
  if (!target) return;
  $('#live-status-msg').innerHTML = '<span class="spinner"></span>Reading signal status...';
  const res = await api.vrroomReadStatus(target.host, target.port);
  $('#live-status-msg').textContent = res.success && res.ok ? 'Done.' : 'Read failed - see below.';
  if (res.success) renderLiveResults(res.results || {}, res.errors);
  else $('#live-status-msg').textContent = `Error: ${res.error}`;
});

$('#btn-live-analyze').addEventListener('click', async () => {
  if (!state.liveConfig) return;
  const recommended = state.lastRecommendation ? state.lastRecommendation.vrroom_settings : null;
  const res = await api.analyzeConfigObject(state.liveConfig, recommended);
  if (res.success) {
    $$('.nav-item').forEach((n) => n.classList.remove('active'));
    $$('.tab-content').forEach((t) => t.classList.remove('active'));
    $('[data-tab="analyzer"]').classList.add('active');
    $('#tab-analyzer').classList.add('active');
    renderAnalysis(res.analysis, res.diff, 'live device');
  }
});

// ---------------------------------------------------------------- support

$('#tab-support').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-url]');
  if (btn) api.openExternal(btn.dataset.url);
});

// -------------------------------------------------------------- reference

async function initReference() {
  const presets = await api.getEdidPresets();
  $('#tbl-edid-modes tbody').innerHTML = Object.values(presets || {})
    .map(
      (p) => `<tr>
        <td><b>${esc(p.name)}</b></td>
        <td class="muted">${esc(p.description)}</td>
        <td class="muted">${esc(p.use_case)}</td>
        <td class="mono">${esc(p.command)}</td>
      </tr>`
    )
    .join('');

  const dvStrings = [
    ['LG C1 (mode 0)', 'Standard DV string. Use for displays with native Dolby Vision.'],
    ['Custom / X930E LLDV (mode 1)', 'LLDV string - recommended for non-DV projectors like the Epson LS12000. Sources output LLDV which the VRROOM converts to HDR10.'],
    ['Remove DV (mode 2)', 'Strips DV capability from EDID. Sources fall back to HDR10.'],
  ];
  $('#tbl-dv-strings tbody').innerHTML = dvStrings
    .map(([name, desc]) => `<tr><td><b>${esc(name)}</b></td><td class="muted">${esc(desc)}</td></tr>`)
    .join('');
}

// -------------------------------------------------------------- bootstrap

(async function init() {
  const info = await api.appInfo();
  if (info.success) {
    $('#app-info').textContent = `v${info.version} - ${info.platform}/${info.arch}`;
  }

  $('#live-host').value = localStorage.getItem('avsl_live_host') || '';
  $('#live-port').value = localStorage.getItem('avsl_live_port') || '2222';

  await initSetupTab();
  await initReference();
  refreshBackups();
  refreshManuals();
})();
