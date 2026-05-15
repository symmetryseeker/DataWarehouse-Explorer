#!/usr/bin/env python3
"""
DataWarehouse Web Viewer — Flask-based interactive browser for DeepSeek_DataV4.

Usage:  python DataWarehouse_Web.py
        Then open http://127.0.0.1:5000 in your browser.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- auto-install flask ---
try:
    from flask import Flask, render_template_string, request, jsonify, abort, url_for
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "--quiet"])
    from flask import Flask, render_template_string, request, jsonify, abort, url_for

# --- paths ---
WAREHOUSE_ROOT = Path(__file__).resolve().parent / "My Passport" / "DataWarehouse"
# Also check E: drive
for candidate in (Path("E:/DataWarehouse"), Path("D:/DataWarehouse"), WAREHOUSE_ROOT):
    if (candidate / "metadata").is_dir():
        WAREHOUSE_ROOT = candidate
        break

METADATA_DIR = WAREHOUSE_ROOT / "metadata"
CODE_DIR = WAREHOUSE_ROOT / "code"

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_metadata() -> List[Dict[str, Any]]:
    """Load all repo metadata JSON files, sorted by quality score desc."""
    repos: List[Dict[str, Any]] = []
    if not METADATA_DIR.is_dir():
        return repos
    for mf in sorted(METADATA_DIR.glob("*.json")):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            data["slug"] = mf.stem
            repos.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    repos.sort(key=lambda r: r.get("quality_score", 0), reverse=True)
    return repos


def list_repo_files(repo_slug: str) -> List[Dict[str, Any]]:
    """Return all files in a repo's code directory."""
    repo_dir = CODE_DIR / repo_slug
    if not repo_dir.is_dir():
        return []
    files: List[Dict[str, Any]] = []
    for f in sorted(repo_dir.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            rel = str(f.relative_to(repo_dir))
            size = f.stat().st_size
            suffix = f.suffix.lower()
            preview = suffix in (".csv", ".json", ".md", ".txt", ".py", ".xml", ".yml", ".yaml")
            files.append({
                "name": f.name,
                "path": rel,
                "size": size,
                "size_human": _human_size(size),
                "suffix": suffix,
                "preview": preview,
            })
    return files


def read_file_content(repo_slug: str, file_path: str, max_lines: int = 500) -> Optional[Dict[str, Any]]:
    """Read a file from a repo directory and return parsed content."""
    full_path = CODE_DIR / repo_slug / file_path
    if not full_path.is_file():
        return None

    suffix = full_path.suffix.lower()

    try:
        if suffix == ".csv":
            return _parse_csv(full_path, max_lines)
        elif suffix == ".json":
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            try:
                parsed = json.loads(text)
                return {"type": "json", "content": json.dumps(parsed, indent=2, ensure_ascii=False)[:50000]}
            except json.JSONDecodeError:
                return {"type": "text", "content": text[:50000]}
        elif suffix in (".md", ".txt", ".py", ".yml", ".yaml", ".xml"):
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            return {"type": "text", "content": text[:50000], "language": suffix.lstrip(".")}
        else:
            return {"type": "binary", "size": _human_size(full_path.stat().st_size)}
    except (OSError, UnicodeDecodeError):
        return {"type": "binary", "size": _human_size(full_path.stat().st_size)}


def _parse_csv(path: Path, max_lines: int) -> Dict[str, Any]:
    """Parse CSV into columns + rows for table rendering."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        rows: List[List[str]] = []
        for i, row in enumerate(reader):
            if i >= max_lines:
                break
            rows.append(row)
    return {
        "type": "csv",
        "headers": headers,
        "rows": rows,
        "total_rows": len(rows),
        "truncated": len(rows) >= max_lines,
    }


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML_INDEX)


@app.route("/api/repos")
def api_repos():
    repos = load_all_metadata()
    return jsonify(repos)


@app.route("/api/repo/<slug>")
def api_repo_detail(slug: str):
    files = list_repo_files(slug)
    # load metadata
    meta_path = METADATA_DIR / f"{slug}.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return jsonify({"slug": slug, "meta": meta, "files": files})


@app.route("/api/file/<slug>/<path:filepath>")
def api_file_content(slug: str, filepath: str):
    content = read_file_content(slug, filepath)
    if content is None:
        abort(404)
    return jsonify(content)


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").lower().strip()
    if not q:
        return jsonify([])
    repos = load_all_metadata()
    results: List[Dict] = []
    for r in repos:
        text = json.dumps(r, ensure_ascii=False).lower()
        if q in text:
            results.append(r)
    return jsonify(results)


# ---------------------------------------------------------------------------
# HTML Template (single-file, no external deps)
# ---------------------------------------------------------------------------

HTML_INDEX = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DataWarehouse Explorer</title>
<style>
:root {
  --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
  --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --yellow: #d2991d; --red: #f85149;
  --purple: #a371f7;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg); color: var(--text);
  min-height: 100vh; display: flex;
}
/* Sidebar */
.sidebar {
  width: 300px; min-width: 300px; background: var(--surface);
  border-right: 1px solid var(--border); display: flex;
  flex-direction: column; height: 100vh; position: sticky; top: 0;
}
.sidebar-header {
  padding: 20px; border-bottom: 1px solid var(--border);
}
.sidebar-header h1 { font-size: 1.2rem; color: var(--accent); }
.sidebar-header .stats { font-size: .8rem; color: var(--muted); margin-top: 4px; }
.sidebar-header .links { margin-top: 8px; display: flex; gap: 10px; flex-wrap: wrap; }
.sidebar-header .links a {
  font-size: .7rem; color: var(--accent); text-decoration: none;
  padding: 3px 8px; border-radius: 4px; border: 1px solid var(--border);
  transition: background .15s;
}
.sidebar-header .links a:hover { background: rgba(88,166,255,.1); }
.search-box {
  padding: 12px 20px; border-bottom: 1px solid var(--border);
}
.search-box input {
  width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg); color: var(--text); font-size: .85rem;
  outline: none;
}
.search-box input:focus { border-color: var(--accent); }
.repo-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.repo-item {
  padding: 12px 20px; cursor: pointer; border-left: 3px solid transparent;
  transition: background .15s;
}
.repo-item:hover { background: rgba(255,255,255,.03); }
.repo-item.active { background: rgba(88,166,255,.08); border-left-color: var(--accent); }
.repo-item .name { font-size: .9rem; font-weight: 600; word-break: break-all; }
.repo-item .desc { font-size: .75rem; color: var(--muted); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.repo-item .meta-row { display: flex; gap: 10px; margin-top: 4px; font-size: .7rem; }
.score { font-weight: 700; }
.score.high { color: var(--green); } .score.mid { color: var(--yellow); } .score.low { color: var(--red); }
.stars { color: var(--muted); }
/* Main */
.main { flex: 1; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.main-header {
  padding: 16px 28px; border-bottom: 1px solid var(--border);
  background: var(--surface); display: flex; align-items: center; gap: 16px;
}
.main-header h2 { font-size: 1rem; }
.main-header .badge {
  padding: 2px 10px; border-radius: 12px; font-size: .7rem;
  background: rgba(88,166,255,.15); color: var(--accent);
}
.file-grid {
  flex: 1; overflow-y: auto; padding: 20px 28px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px; align-content: start;
}
.file-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 16px; cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.file-card:hover { border-color: var(--accent); box-shadow: 0 0 0 1px rgba(88,166,255,.2); }
.file-card .fname { font-weight: 600; font-size: .85rem; word-break: break-all; }
.file-card .fpath { font-size: .7rem; color: var(--muted); margin-top: 2px; }
.file-card .fmeta { font-size: .7rem; color: var(--muted); margin-top: 6px; }
.file-card .tag {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: .65rem; font-weight: 700; text-transform: uppercase;
  margin-right: 4px;
}
.tag.csv { background: rgba(63,185,80,.2); color: var(--green); }
.tag.json { background: rgba(163,113,247,.2); color: var(--purple); }
.tag.md, .tag.txt { background: rgba(139,148,158,.2); color: var(--muted); }
.tag.py { background: rgba(88,166,255,.2); color: var(--accent); }
/* Preview panel */
.preview-panel {
  position: fixed; right: 0; top: 0; width: 55%; height: 100vh;
  background: var(--surface); border-left: 1px solid var(--border);
  box-shadow: -4px 0 24px rgba(0,0,0,.4); z-index: 100;
  display: flex; flex-direction: column; transform: translateX(100%);
  transition: transform .25s ease;
}
.preview-panel.open { transform: translateX(0); }
.preview-header {
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.preview-header h3 { font-size: .9rem; }
.preview-close {
  background: none; border: none; color: var(--muted); font-size: 1.4rem;
  cursor: pointer; line-height: 1;
}
.preview-close:hover { color: var(--text); }
.preview-body { flex: 1; overflow: auto; padding: 0; }
.preview-body pre {
  padding: 16px 20px; font-size: .8rem; line-height: 1.5;
  white-space: pre-wrap; word-break: break-all; margin: 0;
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
}
.preview-body .csv-table {
  width: 100%; border-collapse: collapse; font-size: .78rem;
}
.preview-body .csv-table th {
  position: sticky; top: 0; background: var(--surface); padding: 8px 12px;
  text-align: left; border-bottom: 2px solid var(--border); font-weight: 700;
  white-space: nowrap;
}
.preview-body .csv-table td {
  padding: 5px 12px; border-bottom: 1px solid var(--border);
  max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.preview-body .csv-table tr:hover td { background: rgba(255,255,255,.02); }
.preview-body .csv-wrap { overflow-x: auto; padding: 0; }
.preview-body .empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; color: var(--muted); gap: 8px;
}
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 99;
  display: none; }
.overlay.show { display: block; }
.empty-main {
  display: flex; align-items: center; justify-content: center; height: 100%;
  color: var(--muted); font-size: .9rem;
}
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-header">
    <h1>DataWarehouse</h1>
    <div class="stats" id="sidebar-stats">Loading...</div>
    <div class="links">
      <a href="https://github.com/symmetryseeker/DataWarehouse-Explorer" target="_blank">GitHub</a>
      <a href="https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com" target="_blank">Live Demo</a>
    </div>
  </div>
  <div class="search-box">
    <input type="text" id="search-input" placeholder="Search repos, tags, data types..." oninput="doSearch()">
  </div>
  <div class="repo-list" id="repo-list">
    <div style="padding:20px;color:var(--muted);">Loading...</div>
  </div>
</div>

<div class="main" id="main-panel">
  <div class="main-header" id="main-header" style="display:none;">
    <h2 id="repo-title"></h2>
    <span class="badge" id="repo-score"></span>
  </div>
  <div class="file-grid" id="file-grid"></div>
  <div class="empty-main" id="empty-main">Select a repository from the sidebar</div>
</div>

<div class="overlay" id="overlay" onclick="closePreview()"></div>
<div class="preview-panel" id="preview-panel">
  <div class="preview-header">
    <h3 id="preview-title"></h3>
    <button class="preview-close" onclick="closePreview()">&times;</button>
  </div>
  <div class="preview-body" id="preview-body"></div>
</div>

<script>
let allRepos = [];
let activeSlug = null;

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
  el.innerHTML = repos.map(r => {
    const cls = r.quality_score >= 30 ? 'high' : (r.quality_score >= 15 ? 'mid' : 'low');
    return `<div class="repo-item" onclick="selectRepo('${r.slug}')" data-slug="${r.slug}">
      <div class="name">${escHtml(r.repo_name)}</div>
      <div class="desc">${escHtml((r.description||'').slice(0,80))}</div>
      <div class="meta-row">
        <span class="score ${cls}">${r.quality_score}/50</span>
        <span class="stars">★ ${(r.stars||0).toLocaleString()}</span>
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
  document.getElementById("overlay").classList.add("show");
  document.getElementById("preview-panel").classList.add("open");
  document.getElementById("preview-title").textContent = filepath;
  const body = document.getElementById("preview-body");
  body.innerHTML = '<div class="empty-state">Loading...</div>';

  try {
    const resp = await fetch("/api/file/" + slug + "/" + encodeURIComponent(filepath));
    if (!resp.ok) throw new Error("Not found");
    const data = await resp.json();

    if (data.type === "csv") {
      let html = '<div class="csv-wrap"><table class="csv-table"><thead><tr>';
      for (const h of data.headers) html += `<th>${escHtml(h)}</th>`;
      html += '</tr></thead><tbody>';
      for (const row of data.rows) {
        html += '<tr>';
        for (const cell of row) html += `<td>${escHtml(cell)}</td>`;
        html += '</tr>';
      }
      html += '</tbody></table></div>';
      if (data.truncated) html += '<div style="padding:10px 20px;color:var(--yellow);font-size:.75rem;">Showing first 500 rows</div>';
      body.innerHTML = html;
    } else if (data.type === "json") {
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

function closePreview() {
  document.getElementById("overlay").classList.remove("show");
  document.getElementById("preview-panel").classList.remove("open");
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

document.addEventListener("keydown", e => { if (e.key === "Escape") closePreview(); });
init();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _get_local_ip() -> str:
    """Detect LAN IP address."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    local_ip = _get_local_ip()
    print(f"\n  DataWarehouse Explorer")
    print(f"  Warehouse: {WAREHOUSE_ROOT}")
    print(f"  本机访问:  http://127.0.0.1:5000")
    print(f"  局域网访问: http://{local_ip}:5000")
    print(f"  按 Ctrl+C 停止服务\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
