let allRepos = [];
let activeSlug = null;
let activeFilepath = null;
let activeCsvData = null;

async function init() {
  const resp = await fetch("/api/repos");
  allRepos = await resp.json();
  document.getElementById("sidebar-stats").textContent =
    allRepos.length + " repos | " + allRepos.reduce((s,r)=>s+(r.data_files||[]).length,0) + " files";
  renderRepoList(allRepos);
  if (allRepos.length > 0) selectRepo(allRepos[0].slug);
}

function renderRepoList(repos) {
  const el = document.getElementById("repo-list");
  if (repos.length === 0) {
    el.innerHTML = '<div style="padding:20px;color:var(--muted);">No results</div>';
    return;
  }
  el.innerHTML = repos.map(r => {
    const cls = r.quality_score >= 30 ? 'high' : (r.quality_score >= 15 ? 'mid' : 'low');
    return `<div class="repo-item" onclick="selectRepo('${r.slug}')" data-slug="${r.slug}">
      <div class="name">${escHtml(r.repo_name)}</div>
      <div class="desc">${escHtml((r.description||'').slice(0,80))}</div>
      <div class="meta-row">
        <span class="score ${cls}">${r.quality_score}/50</span>
        <span class="stars">★ ${(r.stars||0).toLocaleString()}</span>
        ${r.license ? '<span style="color:var(--green);">'+escHtml(r.license)+'</span>' : ''}
      </div>
    </div>`;
  }).join("");
}

async function selectRepo(slug) {
  activeSlug = slug;
  document.querySelectorAll(".repo-item").forEach(e => e.classList.remove("active"));
  const item = document.querySelector(`[data-slug="${slug}"]`);
  if (item) item.classList.add("active");

  const resp = await fetch("/api/repo/" + slug);
  const data = await resp.json();

  document.getElementById("empty-main").style.display = "none";
  document.getElementById("main-header").style.display = "flex";
  document.getElementById("repo-title").textContent = data.meta.repo_name || slug;
  document.getElementById("repo-score").textContent = "Score " + (data.meta.quality_score||0) + "/50";

  const licBadge = document.getElementById("repo-license");
  if (data.meta.license) {
    licBadge.style.display = "inline";
    licBadge.textContent = data.meta.license;
  } else {
    licBadge.style.display = "none";
  }

  const grid = document.getElementById("file-grid");
  if (data.files.length === 0) {
    grid.innerHTML = '<div style="padding:30px;color:var(--muted);">No files found</div>';
  } else {
    grid.innerHTML = data.files.map(f => {
      const tags = f.preview
        ? `<span class="tag ${f.suffix.slice(1)}">${f.suffix}</span>`
        : `<span class="tag" style="background:rgba(248,81,73,.15);color:var(--red);">${f.suffix||'bin'}</span>`;
      return `<div class="file-card" onclick="openFile('${slug}', '${escAttr(f.path)}')">
        <div class="fname">${escHtml(f.name)}</div>
        <div class="fpath">${escHtml(f.path)}</div>
        <div class="fmeta">${tags} ${f.size_human}</div>
      </div>`;
    }).join("");
  }
}

async function openFile(slug, filepath) {
  activeSlug = slug;
  activeFilepath = filepath;
  document.getElementById("overlay").classList.add("show");
  document.getElementById("preview-panel").classList.add("open");
  document.getElementById("preview-title").textContent = filepath;

  // Hide action buttons initially
  ["btn-stats","btn-chart","btn-export-csv","btn-export-json"].forEach(id =>
    document.getElementById(id).style.display = "none");

  const body = document.getElementById("preview-body");
  body.innerHTML = '<div class="empty-state">Loading...</div>';

  try {
    const resp = await fetch("/api/file/" + slug + "/" + encodeURIComponent(filepath));
    if (!resp.ok) throw new Error("Not found");
    const data = await resp.json();

    if (data.type === "csv") {
      activeCsvData = data;
      document.getElementById("btn-stats").style.display = "inline";
      document.getElementById("btn-chart").style.display = "inline";
      document.getElementById("btn-export-csv").style.display = "inline";
      document.getElementById("btn-export-json").style.display = "inline";
      renderCsvTable(data, body);
    } else if (data.type === "json") {
      document.getElementById("btn-export-json").style.display = "inline";
      body.innerHTML = `<pre>${escHtml(data.content)}</pre>`;
    } else if (data.type === "text") {
      body.innerHTML = `<pre>${escHtml(data.content)}</pre>`;
    } else {
      body.innerHTML = `<div class="empty-state"><div>Binary file</div><div style="font-size:.8rem;">${data.size}</div></div>`;
    }
  } catch (e) {
    body.innerHTML = '<div class="empty-state">Failed to load file</div>';
  }
}

function renderCsvTable(data, body) {
  let html = '<div class="filter-row">';
  html += '<span style="font-size:.75rem;color:var(--muted);">Filter: </span>';
  html += `<input type="text" id="csv-filter-col" placeholder="Column" style="width:100px;">`;
  html += `<input type="text" id="csv-filter-val" placeholder="Value" style="width:150px;" oninput="applyCsvFilter()">`;
  html += '<span style="font-size:.7rem;color:var(--muted);">(' + data.total_rows + ' rows)</span>';
  html += '</div>';
  html += '<div class="csv-wrap"><table class="csv-table"><thead><tr>';
  for (let i = 0; i < data.headers.length; i++) {
    html += `<th onclick="sortCsv(${i}, this)">${escHtml(data.headers[i])}<span class="sort-arrow"></span></th>`;
  }
  html += '</tr></thead><tbody>';
  for (const row of data.rows) {
    html += '<tr>';
    for (const cell of row) html += `<td>${escHtml(cell)}</td>`;
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  if (data.truncated) html += '<div style="padding:10px 20px;color:var(--yellow);font-size:.75rem;">Showing first 500 rows</div>';
  body.innerHTML = html;
}

let currentSortCol = -1;
let currentSortOrder = "asc";

async function sortCsv(colIdx, thEl) {
  if (currentSortCol === colIdx) {
    currentSortOrder = currentSortOrder === "asc" ? "desc" : "asc";
  } else {
    currentSortCol = colIdx; currentSortOrder = "asc";
  }
  document.querySelectorAll(".csv-table th .sort-arrow").forEach(e => e.textContent = "");
  thEl.querySelector(".sort-arrow").textContent = currentSortOrder === "asc" ? "▲" : "▼";

  const filterCol = document.getElementById("csv-filter-col")?.value || "";
  const filterVal = document.getElementById("csv-filter-val")?.value || "";

  let url = `/api/file/${activeSlug}/${encodeURIComponent(activeFilepath)}/rows?sort=${encodeURIComponent(activeCsvData.headers[colIdx])}&order=${currentSortOrder}&limit=500`;
  if (filterCol && filterVal) url += `&filter_col=${encodeURIComponent(filterCol)}&filter_val=${encodeURIComponent(filterVal)}`;

  const resp = await fetch(url);
  const data = await resp.json();
  activeCsvData = { ...activeCsvData, headers: data.headers, rows: data.rows, total_rows: data.filtered_total };
  const body = document.getElementById("preview-body");
  renderCsvTableRaw(data.headers, data.rows, data.filtered_total, body);
}

async function applyCsvFilter() {
  const filterCol = document.getElementById("csv-filter-col")?.value || "";
  const filterVal = document.getElementById("csv-filter-val")?.value || "";
  if (!filterVal) {
    if (activeCsvData) {
      const body = document.getElementById("preview-body");
      renderCsvTableRaw(activeCsvData.headers, activeCsvData.rows, activeCsvData.total_rows, body);
    }
    return;
  }
  let url = `/api/file/${activeSlug}/${encodeURIComponent(activeFilepath)}/rows?limit=500&filter_col=${encodeURIComponent(filterCol)}&filter_val=${encodeURIComponent(filterVal)}`;
  const resp = await fetch(url);
  const data = await resp.json();
  const body = document.getElementById("preview-body");
  renderCsvTableRaw(data.headers, data.rows, data.filtered_total, body);
}

function renderCsvTableRaw(headers, rows, totalRows, body) {
  let html = '<div class="filter-row">';
  html += '<span style="font-size:.75rem;color:var(--muted);">Filter: </span>';
  html += `<input type="text" id="csv-filter-col" placeholder="Column" style="width:100px;" value="${escHtml(document.getElementById('csv-filter-col')?.value||'')}">`;
  html += `<input type="text" id="csv-filter-val" placeholder="Value" style="width:150px;" value="${escHtml(document.getElementById('csv-filter-val')?.value||'')}" oninput="applyCsvFilter()">`;
  html += '<span style="font-size:.7rem;color:var(--muted);">(' + totalRows + ' rows)</span>';
  html += '</div>';
  html += '<div class="csv-wrap"><table class="csv-table"><thead><tr>';
  for (let i = 0; i < headers.length; i++) {
    html += `<th onclick="sortCsv(${i}, this)">${escHtml(headers[i])}<span class="sort-arrow">${currentSortCol===i ? (currentSortOrder==='asc'?'▲':'▼') : ''}</span></th>`;
  }
  html += '</tr></thead><tbody>';
  for (const row of rows) {
    html += '<tr>';
    for (const cell of row) html += `<td>${escHtml(cell)}</td>`;
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  body.innerHTML = html;
}

async function showStats() {
  if (!activeFilepath) return;
  const body = document.getElementById("preview-body");
  body.innerHTML = '<div class="empty-state">Loading stats...</div>';
  try {
    const resp = await fetch(`/api/file/${activeSlug}/${encodeURIComponent(activeFilepath)}/stats`);
    const data = await resp.json();
    let html = '<div style="padding:16px 20px;font-size:.8rem;">';
    html += `<div style="margin-bottom:12px;color:var(--muted);">${data.total_rows} rows, ${data.headers.length} columns</div>`;
    html += '<table class="csv-table"><thead><tr><th>Column</th><th>Null %</th><th>Numeric</th><th>Mean</th><th>Min</th><th>Max</th></tr></thead><tbody>';
    for (const h of data.headers) {
      const s = data.stats[h] || {};
      html += `<tr>
        <td><strong>${escHtml(h)}</strong></td>
        <td>${(s.null_ratio*100).toFixed(1)}%</td>
        <td>${s.numeric ? 'Yes' : 'No'}</td>
        <td>${s.mean != null ? s.mean : '-'}</td>
        <td>${s.min != null ? s.min : '-'}</td>
        <td>${s.max != null ? s.max : '-'}</td>
      </tr>`;
    }
    html += '</tbody></table></div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<div class="empty-state">Failed to load stats</div>';
  }
}

function exportFile(format) {
  if (!activeFilepath || !activeSlug) return;
  const filterCol = document.getElementById("csv-filter-col")?.value || "";
  const filterVal = document.getElementById("csv-filter-val")?.value || "";
  let url = `/api/export/${activeSlug}/${encodeURIComponent(activeFilepath)}?format=${format}`;
  if (filterCol && filterVal) url += `&filter_col=${encodeURIComponent(filterCol)}&filter_val=${encodeURIComponent(filterVal)}`;
  window.open(url, "_blank");
}

function closePreview() {
  document.getElementById("overlay").classList.remove("show");
  document.getElementById("preview-panel").classList.remove("open");
  activeCsvData = null;
}

function doSearch() {
  const q = document.getElementById("search-input").value.trim().toLowerCase();
  if (!q) { renderRepoList(allRepos); return; }
  const filtered = allRepos.filter(r => {
    const haystack = (r.repo_name + " " + (r.description||"") + " " + (r.tags||[]).join(" ") + " " + (r.data_types||[]).join(" ")).toLowerCase();
    return haystack.includes(q);
  });
  renderRepoList(filtered);
}

function escHtml(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
function escAttr(s) {
  return s.replace(/\\/g,"\\\\").replace(/'/g,"\\'").replace(/"/g,"&quot;");
}

// ---- AI Chat ----
function toggleAiChat() {
  document.getElementById("ai-chat-panel").classList.toggle("open");
}
async function askAI() {
  const input = document.getElementById("ai-question");
  const question = input.value.trim();
  if (!question) return;

  const msgs = document.getElementById("ai-chat-messages");
  msgs.innerHTML += `<div class="ai-msg user">${escHtml(question)}</div>`;
  input.value = "";

  // Add typing indicator
  const typingId = "typing-" + Date.now();
  msgs.innerHTML += `<div class="ai-msg system" id="${typingId}">Thinking...</div>`;
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const resp = await fetch("/api/ai/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question}),
    });
    const data = await resp.json();

    // Remove typing indicator
    document.getElementById(typingId)?.remove();

    if (data.error) {
      msgs.innerHTML += `<div class="ai-msg system">Error: ${escHtml(data.error)}<br><small>Hint: Configure config/llm_config.yaml with your LLM API key</small></div>`;
    } else {
      let html = `<div class="ai-msg assistant">`;
      if (data.sql) html += `<span class="sql-block">${escHtml(data.sql)}</span>`;
      if (data.columns && data.rows) {
        html += `<div style="margin-top:6px;font-size:.7rem;color:var(--muted);">${data.row_count} rows</div>`;
        if (data.chart_type && data.chart_type !== "table") {
          html += `<div style="margin-top:4px;font-size:.7rem;color:var(--accent);">Chart: ${data.chart_type}</div>`;
        }
      }
      html += `</div>`;
      msgs.innerHTML += html;
    }
  } catch (e) {
    document.getElementById(typingId)?.remove();
    msgs.innerHTML += `<div class="ai-msg system">Network error. Is the server running?</div>`;
  }
  msgs.scrollTop = msgs.scrollHeight;
}

document.addEventListener("keydown", e => { if (e.key === "Escape") closePreview(); });
init();
