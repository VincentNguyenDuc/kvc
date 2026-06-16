'use strict';

// ── Config ────────────────────────────────────────────────────────────────
const DATA_URL      = 'data/runs.json';
const VERSIONS_URL  = 'data/versions.json';

const PALETTE = [
    '#58a6ff', '#3fb950', '#d29922', '#f85149',
    '#bc8cff', '#ff7b72', '#a5d6ff', '#ffa657',
];

const PCTILE_COLORS = {
    p50_us:  '#3fb950',
    p95_us:  '#d29922',
    p99_us:  '#f85149',
    p999_us: '#bc8cff',
};

// ── State ─────────────────────────────────────────────────────────────────
const state = {
    all:        [],          // all transformed runs, sorted by timestamp
    filtered:   [],          // after sidebar filters
    versions:   [],          // [{version, description}] from versions.json
    sel: {                   // active filter sets
        version:     new Set(),
        env:         new Set(),
        connections: new Set(),
    },
    activeTab:   'about',
    charts:      {},         // { canvasId: Chart instance }
    drillId:     null,       // run_id selected in Overview drill-down
    compareIds:  new Set(),  // run_ids checked in Compare
};

// ── Formatters ────────────────────────────────────────────────────────────
const fmt    = (n, d = 0) => n != null ? (+n).toLocaleString('en', { maximumFractionDigits: d }) : '—';
const fmtDate = ts => ts ? new Date(ts).toISOString().slice(0, 16).replace('T', ' ') : '—';
const fmtUs   = n  => n != null ? fmt(n, 1) + ' µs' : '—';
const fmtPct  = n  => n != null ? (+n).toFixed(1) + '%' : '—';
const esc     = s  => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function versionColor(version) {
    const versions = [...new Set(state.all.map(r => r.version))].sort();
    return PALETTE[versions.indexOf(version) % PALETTE.length];
}

// ── Data transformation ───────────────────────────────────────────────────
function transformRun(raw) {
    const timing   = raw.timing_us  || {};
    const counters = (raw.perf?.counters) || {};
    const cfg      = raw.config     || {};
    const infra    = raw.infra      || {};
    const dur      = raw.duration_s || 0;
    const total    = raw.total      || 0;
    const clock    = counters['task-clock'];
    const ctxSw    = counters['context-switches'];

    return {
        run_id:          raw.run_id    || raw.label || String(Math.random()),
        version:         raw.version  || '—',
        label:           raw.label    || raw.run_id || '—',
        timestamp:       raw.timestamp || null,
        git_commit:      (raw.git_commit || '').slice(0, 8),
        env:             raw.env      || '—',
        connections:     raw.workers  || 1,
        total,
        errors:          raw.errors   || 0,
        duration_s:      dur,
        throughput_per_s: raw.throughput_per_s || 0,
        min_us:          timing.min   ?? null,
        p50_us:          timing.p50   ?? null,
        p95_us:          timing.p95   ?? null,
        p99_us:          timing.p99   ?? null,
        p999_us:         timing.p999  ?? null,
        max_us:          timing.max   ?? null,
        cpu_pct:         clock && dur ? +(clock / 1e9 / dur * 100).toFixed(1) : null,
        ctx_sw_per_req:  ctxSw && total ? +(ctxSw / total).toFixed(3) : null,
        task_clock_s:    clock  ? +(clock  / 1e9).toFixed(3) : null,
        context_switches: ctxSw ?? null,
        page_faults:     counters['page-faults'] ?? null,
        hostname:        infra.hostname  || '',
        cpu_model:       infra.cpu_model || '',
        os:              infra.os        || '',
        cpu_count:       infra.cpu_count ?? null,
        key_space:       cfg.key_space   ?? null,
        value_size:      cfg.value_size  ?? null,
        set_ratio:       cfg.set_ratio   ?? null,
        del_ratio:       cfg.del_ratio   ?? null,
        warmup:          cfg.warmup      ?? null,
        perf_report:     raw.perf_report  || '',
        flamegraph_url:  raw.flamegraph_url || '',
    };
}

// ── Sidebar filters ───────────────────────────────────────────────────────
function buildFilters() {
    const uniq = key => [...new Set(state.all.map(r => r[key]))].sort();
    buildCheckboxGroup('filter-version',     uniq('version'),                          state.sel.version);
    buildCheckboxGroup('filter-env',         uniq('env'),                              state.sel.env);
    buildCheckboxGroup('filter-connections', uniq('connections').map(String),          state.sel.connections);
}

function buildCheckboxGroup(id, values, selSet) {
    const el = document.getElementById(id);
    el.innerHTML = values.map(v => `
        <label>
          <input type="checkbox" value="${esc(v)}" ${selSet.has(String(v)) ? 'checked' : ''}>
          <span>${esc(v)}</span>
        </label>`).join('');
    el.querySelectorAll('input').forEach(cb => cb.addEventListener('change', onFilterChange));
}

function onFilterChange() {
    state.sel.version     = readChecked('filter-version');
    state.sel.env         = readChecked('filter-env');
    state.sel.connections = readChecked('filter-connections');
    applyFilters();
    renderActive();
}

function readChecked(id) {
    return new Set([...document.querySelectorAll(`#${id} input:checked`)].map(c => c.value));
}

function applyFilters() {
    state.filtered = state.all.filter(r =>
        state.sel.version.has(r.version) &&
        state.sel.env.has(r.env) &&
        state.sel.connections.has(String(r.connections))
    );
    document.getElementById('run-count').textContent =
        `${state.filtered.length} of ${state.all.length} runs`;
}

// ── Tab routing ───────────────────────────────────────────────────────────
function switchTab(tab) {
    state.activeTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.panel').forEach(p =>
        p.classList.toggle('active', p.id === `panel-${tab}`));
    renderActive();
}

function renderActive() {
    switch (state.activeTab) {
        case 'about':    renderAbout();    break;
        case 'overview': renderOverview(); break;
        case 'trends':   renderTrends();   break;
        case 'compare':  renderCompare();  break;
    }
}

// ── About ─────────────────────────────────────────────────────────────────
function renderAbout() {
    // Count runs per version across the full (unfiltered) dataset
    const runCounts = {};
    state.all.forEach(r => { runCounts[r.version] = (runCounts[r.version] || 0) + 1; });

    // Palette index is based on sort order of versions seen in run data
    const dataVersions = [...new Set(state.all.map(r => r.version))].sort();
    const paletteFor = v => {
        const i = dataVersions.indexOf(v);
        return i >= 0 ? PALETTE[i % PALETTE.length] : null;
    };

    // Prefer versions.json (all defined versions + descriptions);
    // fall back to whatever versions appear in the dataset.
    const knownVersions = state.versions.length
        ? state.versions
        : dataVersions.map(v => ({ version: v, description: '' }));

    const vRows = knownVersions.map(({ version, description }) => {
        const count = runCounts[version] ?? 0;
        const color = paletteFor(version);
        const dot   = color
            ? `<span class="vdot" style="background:${color}"></span>`
            : `<span class="vdot vdot-empty"></span>`;
        const runCell = count > 0 ? String(count) : '<span class="muted">—</span>';
        // Render inline backtick spans in descriptions (e.g. `SO_REUSEPORT`)
        const descHtml = esc(description).replace(/`([^`]+)`/g,
            (_, t) => `<code>${t}</code>`);
        return `
            <tr>
              <td class="col-dot">${dot}</td>
              <td class="col-version"><code>${esc(version)}</code></td>
              <td class="col-desc">${descHtml}</td>
              <td class="col-runs">${runCell}</td>
            </tr>`;
    }).join('');

    document.getElementById('panel-about').innerHTML = `
        <div class="about-content">
          <h2>kvc</h2>
          <p>An in-memory key-value store written in C/C++. Each version isolates one
             performance question; the benchmarks quantify the answer, and the next version
             picks up from there.</p>
          <h2>Protocol</h2>
          <p>Newline-delimited plain text over TCP:</p>
          <pre class="protocol-block">SET &lt;key&gt; &lt;value&gt; [&lt;ttl_seconds&gt;]
GET &lt;key&gt;
DEL &lt;key&gt;</pre>
          <h2>Versions</h2>
          <div class="table-wrap">
            <table class="data-table about-versions">
              <thead><tr>
                <th class="col-dot"></th>
                <th>Version</th>
                <th>What it measures</th>
                <th>Runs</th>
              </tr></thead>
              <tbody>${vRows}</tbody>
            </table>
          </div>
        </div>`;
}

// ── Overview ──────────────────────────────────────────────────────────────
function renderOverview() {
    const df = state.filtered;
    const panel = document.getElementById('panel-overview');

    if (!df.length) {
        panel.innerHTML = '<p class="status-msg">No runs match the current filters.</p>';
        return;
    }

    const best   = df.reduce((a, b) => b.throughput_per_s > a.throughput_per_s ? b : a);
    const latest = df[df.length - 1];

    const cards = `
        <div class="metrics-grid">
          ${card(df.length,   'Runs')}
          ${card(fmt(best.throughput_per_s)   + ' req/s', 'Best throughput',   `${esc(best.label)} · ${best.connections}c`)}
          ${card(fmt(latest.throughput_per_s) + ' req/s', 'Latest throughput', esc(latest.label))}
          ${card(fmtUs(latest.p99_us),  'Latest p99')}
          ${card(fmtPct(latest.cpu_pct),'Latest CPU%')}
        </div>`;

    const trows = df.map(r => `
        <tr data-id="${esc(r.run_id)}" class="${state.drillId === r.run_id ? 'selected' : ''}">
          <td>${esc(r.label)}</td>
          <td><span class="vdot" style="background:${versionColor(r.version)}"></span>${esc(r.version)}</td>
          <td>${fmtDate(r.timestamp)}</td>
          <td>${esc(r.env)}</td>
          <td style="text-align:right">${r.connections}</td>
          <td style="text-align:right"><strong>${fmt(r.throughput_per_s)}</strong></td>
          <td style="text-align:right">${fmtUs(r.p50_us)}</td>
          <td style="text-align:right">${fmtUs(r.p95_us)}</td>
          <td style="text-align:right">${fmtUs(r.p99_us)}</td>
          <td style="text-align:right">${fmtPct(r.cpu_pct)}</td>
          <td style="text-align:right">${r.errors}</td>
          <td><code>${esc(r.git_commit)}</code></td>
        </tr>`).join('');

    const table = `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>
              <th>Label</th><th>Version</th><th>Time</th><th>Env</th>
              <th>Conn</th><th>Throughput</th><th>p50</th><th>p95</th>
              <th>p99</th><th>CPU%</th><th>Errors</th><th>Commit</th>
            </tr></thead>
            <tbody>${trows}</tbody>
          </table>
        </div>`;

    const drill = state.drillId
        ? drillDown(df.find(r => r.run_id === state.drillId))
        : '<p style="font-size:13px;color:var(--text-muted)">Click a row to see details.</p>';

    panel.innerHTML = cards + table + drill;

    panel.querySelectorAll('.data-table tbody tr').forEach(tr =>
        tr.addEventListener('click', () => {
            state.drillId = state.drillId === tr.dataset.id ? null : tr.dataset.id;
            renderOverview();
        })
    );
}

function card(value, label, hint = '') {
    return `<div class="card">
        <div class="card-value">${value}</div>
        <div class="card-label">${label}</div>
        ${hint ? `<div class="card-hint">${hint}</div>` : ''}
    </div>`;
}

function drillDown(r) {
    if (!r) return '';
    return `
        <div class="detail-panel">
          <div class="detail-grid">
            <div class="detail-section">
              <h4>Machine</h4>
              ${drow('CPU',   r.cpu_model || '—')}
              ${drow('OS',    r.os        || '—')}
              ${drow('Host',  r.hostname  || '—')}
              ${drow('Cores', r.cpu_count ?? '—')}
            </div>
            <div class="detail-section">
              <h4>Config</h4>
              ${drow('Key space',  r.key_space  ?? '—')}
              ${drow('Value size', r.value_size != null ? r.value_size + ' B' : '—')}
              ${drow('SET ratio',  r.set_ratio  ?? '—')}
              ${drow('DEL ratio',  r.del_ratio  ?? '—')}
              ${drow('Warmup',     r.warmup     ?? '—')}
            </div>
            <div class="detail-section">
              <h4>Perf counters</h4>
              ${drow('CPU time', r.task_clock_s     != null ? r.task_clock_s + ' s' : '—')}
              ${drow('Ctx sw',   r.context_switches != null ? fmt(r.context_switches) : '—')}
              ${drow('Pg faults',r.page_faults      != null ? fmt(r.page_faults)      : '—')}
              ${drow('Ctx/req',  r.ctx_sw_per_req   ?? '—')}
            </div>
          </div>
          ${r.perf_report ? `
          <details>
            <summary>Perf report (hot functions)</summary>
            <pre class="perf-report">${esc(r.perf_report)}</pre>
          </details>` : ''}
          ${r.flamegraph_url ? `
          <p style="margin-top:10px">
            <a href="${esc(r.flamegraph_url)}" target="_blank">View flamegraph →</a>
          </p>` : ''}
        </div>`;
}

function drow(key, val) {
    return `<div class="detail-row"><span class="key">${esc(key)}</span><span>${esc(String(val))}</span></div>`;
}

// ── Trends ────────────────────────────────────────────────────────────────
function renderTrends() {
    const df    = state.filtered.filter(r => r.timestamp);
    const panel = document.getElementById('panel-trends');

    if (!df.length) {
        panel.innerHTML = '<p class="status-msg">No runs with timestamps match the filters.</p>';
        return;
    }

    const versions = [...new Set(df.map(r => r.version))].sort();
    const hasCpu   = df.some(r => r.cpu_pct != null);
    const hasCtx   = df.some(r => r.ctx_sw_per_req != null);

    panel.innerHTML = `
        <div class="chart-section">
          <h3>Throughput (req/s)</h3>
          <canvas id="c-tp" height="100"></canvas>
        </div>
        <div class="chart-section">
          <h3>Latency percentiles (µs)</h3>
          <canvas id="c-lat" height="120"></canvas>
        </div>
        ${hasCpu ? `
        <div class="col2">
          <div class="chart-section">
            <h3>CPU utilization (%)</h3>
            <canvas id="c-cpu" height="140"></canvas>
          </div>
          ${hasCtx ? `
          <div class="chart-section">
            <h3>Context switches / req</h3>
            <canvas id="c-ctx" height="140"></canvas>
          </div>` : ''}
        </div>` : ''}`;

    // Throughput — one line per version
    mkTimeChart('c-tp', 'req/s',
        versions.map((v, i) => ({
            label: v,
            data:  df.filter(r => r.version === v)
                     .map(r => ({ x: r.timestamp, y: r.throughput_per_s })),
            borderColor:     PALETTE[i % PALETTE.length],
            backgroundColor: PALETTE[i % PALETTE.length] + '30',
            tension: 0.3, pointRadius: 6, pointHoverRadius: 8,
        }))
    );

    // Latency — p50/p99 per version (keep chart readable)
    const pctiles = [
        { key: 'p50_us',  name: 'p50'  },
        { key: 'p99_us',  name: 'p99'  },
        { key: 'p999_us', name: 'p999' },
    ];
    const dashes = [[], [6, 3], [2, 2], [8, 3]];
    const latDS = [];
    pctiles.forEach(p => {
        versions.forEach((v, vi) => {
            latDS.push({
                label:           `${p.name} · ${v}`,
                data:            df.filter(r => r.version === v && r[p.key] != null)
                                   .map(r => ({ x: r.timestamp, y: r[p.key] })),
                borderColor:     PCTILE_COLORS[p.key],
                backgroundColor: PCTILE_COLORS[p.key] + '20',
                borderDash:      dashes[vi % dashes.length],
                tension: 0.3, pointRadius: 5, pointHoverRadius: 7,
            });
        });
    });
    mkTimeChart('c-lat', 'µs', latDS);

    if (hasCpu) {
        mkTimeChart('c-cpu', '%',
            versions.map((v, i) => ({
                label: v,
                data:  df.filter(r => r.version === v && r.cpu_pct != null)
                         .map(r => ({ x: r.timestamp, y: r.cpu_pct })),
                borderColor:     PALETTE[i % PALETTE.length],
                backgroundColor: PALETTE[i % PALETTE.length] + '30',
                tension: 0.3, pointRadius: 6,
            }))
        );
    }

    if (hasCtx) {
        mkTimeChart('c-ctx', 'ctx sw / req',
            versions.map((v, i) => ({
                label: v,
                data:  df.filter(r => r.version === v && r.ctx_sw_per_req != null)
                         .map(r => ({ x: r.timestamp, y: r.ctx_sw_per_req })),
                borderColor:     PALETTE[i % PALETTE.length],
                backgroundColor: PALETTE[i % PALETTE.length] + '30',
                tension: 0.3, pointRadius: 6,
            }))
        );
    }
}

function mkTimeChart(id, yLabel, datasets) {
    destroyChart(id);
    const ctx = document.getElementById(id);
    if (!ctx) return;
    state.charts[id] = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
                tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmt(c.parsed.y, 2)}` } },
            },
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'day', displayFormats: { day: 'MMM d' }, tooltipFormat: 'MMM d HH:mm' },
                    ticks: { font: { size: 11 } },
                },
                y: {
                    title: { display: true, text: yLabel, font: { size: 11 } },
                    ticks: { font: { size: 11 } },
                },
            },
        },
    });
}

// ── Compare ───────────────────────────────────────────────────────────────
function renderCompare() {
    const df    = state.filtered;
    const panel = document.getElementById('panel-compare');

    if (!df.length) {
        panel.innerHTML = '<p class="status-msg">No runs match the current filters.</p>';
        return;
    }

    // Seed defaults: last 4 filtered runs, or prune stale ids
    const validIds = new Set(df.map(r => r.run_id));
    state.compareIds = new Set([...state.compareIds].filter(id => validIds.has(id)));
    if (!state.compareIds.size) df.slice(-4).forEach(r => state.compareIds.add(r.run_id));

    const checks = df.map(r => `
        <label>
          <input type="checkbox" value="${esc(r.run_id)}" ${state.compareIds.has(r.run_id) ? 'checked' : ''}>
          <span style="border-left:3px solid ${versionColor(r.version)};padding-left:6px">
            ${esc(r.label)}
          </span>
        </label>`).join('');

    panel.innerHTML = `
        <div class="compare-picks">
          <h3>Select runs to compare</h3>
          <div class="compare-checks" id="cmp-checks">${checks}</div>
        </div>
        <div id="cmp-body"></div>`;

    panel.querySelectorAll('#cmp-checks input').forEach(cb =>
        cb.addEventListener('change', () => {
            if (cb.checked) state.compareIds.add(cb.value);
            else            state.compareIds.delete(cb.value);
            renderCompareBody();
        })
    );

    renderCompareBody();
}

function renderCompareBody() {
    const container = document.getElementById('cmp-body');
    if (!container) return;

    const sel = state.filtered.filter(r => state.compareIds.has(r.run_id));
    if (!sel.length) {
        container.innerHTML = '<p class="status-msg">Select at least one run above.</p>';
        return;
    }

    const runLabel = r => `${r.label} (${r.connections}c)`;
    const labels   = sel.map(runLabel);
    const hasCpu   = sel.some(r => r.cpu_pct      != null);
    const hasCtx   = sel.some(r => r.ctx_sw_per_req != null);

    container.innerHTML = `
        <div class="col2">
          <div class="chart-section">
            <h3>Throughput (req/s)</h3>
            <canvas id="cmp-tp"  height="220"></canvas>
          </div>
          <div class="chart-section">
            <h3>Latency distribution (µs)</h3>
            <canvas id="cmp-lat" height="220"></canvas>
          </div>
        </div>
        ${hasCpu ? `
        <div class="col2">
          <div class="chart-section">
            <h3>CPU utilization (%)</h3>
            <canvas id="cmp-cpu" height="220"></canvas>
          </div>
          ${hasCtx ? `
          <div class="chart-section">
            <h3>Context switches / req</h3>
            <canvas id="cmp-ctx" height="220"></canvas>
          </div>` : ''}
        </div>` : ''}
        <div class="chart-section">
          <h3>Summary</h3>
          ${cmpTable(sel)}
        </div>`;

    // Throughput — horizontal bar
    mkHBar('cmp-tp', 'req/s', labels,
        [{ label: 'req/s', data: sel.map(r => r.throughput_per_s),
           backgroundColor: sel.map(r => versionColor(r.version)) }]);

    // Latency — grouped bar
    destroyChart('cmp-lat');
    const latCtx = document.getElementById('cmp-lat');
    if (latCtx) {
        state.charts['cmp-lat'] = new Chart(latCtx, {
            type: 'bar',
            data: {
                labels: ['min', 'p50', 'p95', 'p99', 'p999', 'max'],
                datasets: sel.map((r, i) => ({
                    label:           runLabel(r),
                    data:            [r.min_us, r.p50_us, r.p95_us, r.p99_us, r.p999_us, r.max_us],
                    backgroundColor: PALETTE[i % PALETTE.length] + 'bb',
                    borderColor:     PALETTE[i % PALETTE.length],
                    borderWidth:     1,
                })),
            },
            options: barOptions('µs'),
        });
    }

    if (hasCpu)
        mkHBar('cmp-cpu', '%', labels,
            [{ label: 'CPU%', data: sel.map(r => r.cpu_pct),
               backgroundColor: sel.map(r => versionColor(r.version)) }]);

    if (hasCtx)
        mkHBar('cmp-ctx', 'ctx sw / req', labels,
            [{ label: 'ctx/req', data: sel.map(r => r.ctx_sw_per_req),
               backgroundColor: sel.map(r => versionColor(r.version)) }]);
}

function mkHBar(id, xLabel, labels, datasets) {
    destroyChart(id);
    const ctx = document.getElementById(id);
    if (!ctx) return;
    state.charts[id] = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => `${fmt(c.parsed.x, 1)} ${xLabel}` } },
            },
            scales: {
                x: { title: { display: true, text: xLabel }, ticks: { font: { size: 11 } } },
                y: { ticks: { font: { size: 11 } } },
            },
        },
    });
}

function barOptions(yLabel) {
    return {
        responsive: true,
        plugins: {
            legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
            tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmt(c.parsed.y, 1)} ${yLabel}` } },
        },
        scales: {
            y: { title: { display: true, text: yLabel }, ticks: { font: { size: 11 } } },
            x: { ticks: { font: { size: 11 } } },
        },
    };
}

function cmpTable(runs) {
    const rows = runs.map(r => `
        <tr>
          <td>${esc(r.label)}</td>
          <td>${esc(r.version)}</td>
          <td>${esc(r.env)}</td>
          <td style="text-align:right">${r.connections}</td>
          <td style="text-align:right"><strong>${fmt(r.throughput_per_s)}</strong></td>
          <td style="text-align:right">${fmtUs(r.p50_us)}</td>
          <td style="text-align:right">${fmtUs(r.p95_us)}</td>
          <td style="text-align:right">${fmtUs(r.p99_us)}</td>
          <td style="text-align:right">${fmtPct(r.cpu_pct)}</td>
          <td style="text-align:right">${r.errors}</td>
        </tr>`).join('');
    return `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>
              <th>Run</th><th>Version</th><th>Env</th><th>Conn</th>
              <th>Throughput</th><th>p50</th><th>p95</th><th>p99</th>
              <th>CPU%</th><th>Errors</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
}

// ── Chart helpers ─────────────────────────────────────────────────────────
function destroyChart(id) {
    if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; }
}

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
    Chart.defaults.font.family =
        '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';

    try {
        const [runsRes, versionsRes] = await Promise.all([
            fetch(DATA_URL),
            fetch(VERSIONS_URL).catch(() => null),
        ]);
        if (!runsRes.ok) throw new Error(`HTTP ${runsRes.status}`);
        const raw = await runsRes.json();

        if (versionsRes && versionsRes.ok) {
            state.versions = await versionsRes.json();
        }

        if (!Array.isArray(raw) || !raw.length) {
            document.getElementById('loading').textContent =
                'No run data yet. Add bench.json files to bench/results/ and run generate_manifest.py.';
            return;
        }

        state.all = raw
            .map(transformRun)
            .sort((a, b) => (a.timestamp || '') < (b.timestamp || '') ? -1 : 1);

        // Select all filter values by default
        state.sel.version     = new Set(state.all.map(r => r.version));
        state.sel.env         = new Set(state.all.map(r => r.env));
        state.sel.connections = new Set(state.all.map(r => String(r.connections)));

        buildFilters();
        applyFilters();

        document.getElementById('loading').classList.add('hidden');
        document.getElementById('tab-content').style.display = '';

        document.querySelectorAll('.tab-btn').forEach(btn =>
            btn.addEventListener('click', () => switchTab(btn.dataset.tab))
        );

        renderAbout();

    } catch (err) {
        const el = document.getElementById('loading');
        el.textContent = `Failed to load data/runs.json: ${err.message}. ` +
            `When running locally, serve with a web server (e.g. python3 -m http.server) instead of opening the file directly.`;
        el.classList.add('error');
    }
}

document.addEventListener('DOMContentLoaded', init);
