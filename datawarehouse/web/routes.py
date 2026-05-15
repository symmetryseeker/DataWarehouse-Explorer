"""Flask routes for the DataWarehouse web UI."""

from __future__ import annotations

import csv
import io
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List

from flask import (
    Blueprint, Response, abort, jsonify, render_template,
    request, send_file, current_app,
)

from .auth import requires_auth

api = Blueprint("api", __name__)
pages = Blueprint("pages", __name__)

# These are set by the app factory
_metadata_dir: Path = Path(".")
_code_dir: Path = Path(".")


def init_dirs(metadata_dir: Path, code_dir: Path) -> None:
    global _metadata_dir, _code_dir
    _metadata_dir = metadata_dir
    _code_dir = code_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_all_metadata() -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    if not _metadata_dir.is_dir():
        return repos
    for mf in sorted(_metadata_dir.glob("*.json")):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            data["slug"] = mf.stem
            repos.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    repos.sort(key=lambda r: r.get("quality_score", 0), reverse=True)
    return repos


def _list_repo_files(repo_slug: str) -> List[Dict[str, Any]]:
    repo_dir = _code_dir / repo_slug
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
                "name": f.name, "path": rel, "size": size,
                "size_human": _human_size(size), "suffix": suffix, "preview": preview,
            })
    return files


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _parse_csv(path: Path, max_lines: int = 500) -> dict:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        rows: List[List[str]] = []
        for i, row in enumerate(reader):
            if i >= max_lines:
                break
            rows.append(row)
    return {"headers": headers, "rows": rows, "total_rows": len(rows),
            "truncated": len(rows) >= max_lines}


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@pages.route("/")
@requires_auth
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@api.route("/api/repos")
@requires_auth
def api_repos():
    return jsonify(_load_all_metadata())


@api.route("/api/repo/<slug>")
@requires_auth
def api_repo_detail(slug: str):
    files = _list_repo_files(slug)
    meta_path = _metadata_dir / f"{slug}.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return jsonify({"slug": slug, "meta": meta, "files": files})


@api.route("/api/file/<slug>/<path:filepath>")
@requires_auth
def api_file_content(slug: str, filepath: str):
    full_path = _code_dir / slug / filepath
    if not full_path.is_file():
        abort(404)

    suffix = full_path.suffix.lower()
    try:
        if suffix == ".csv":
            data = _parse_csv(full_path)
            return jsonify({"type": "csv", **data})
        elif suffix == ".json":
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            try:
                parsed = json.loads(text)
                return jsonify({"type": "json", "content": json.dumps(parsed, indent=2, ensure_ascii=False)[:50000]})
            except json.JSONDecodeError:
                return jsonify({"type": "text", "content": text[:50000]})
        elif suffix in (".md", ".txt", ".py", ".yml", ".yaml", ".xml"):
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            return jsonify({"type": "text", "content": text[:50000]})
        else:
            return jsonify({"type": "binary", "size": _human_size(full_path.stat().st_size)})
    except (OSError, UnicodeDecodeError):
        return jsonify({"type": "binary", "size": _human_size(full_path.stat().st_size)})


@api.route("/api/file/<slug>/<path:filepath>/stats")
@requires_auth
def api_file_stats(slug: str, filepath: str):
    """Return per-column statistics for a CSV file."""
    full_path = _code_dir / slug / filepath
    if not full_path.is_file() or full_path.suffix.lower() != ".csv":
        abort(404)

    with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        if not headers:
            abort(400)
        col_values = {h: [] for h in headers}
        null_counts = {h: 0 for h in headers}
        total_rows = 0
        for row in reader:
            total_rows += 1
            for i, h in enumerate(headers):
                val = row[i] if i < len(row) else ""
                if val.strip() == "":
                    null_counts[h] += 1
                else:
                    col_values[h].append(val)

    stats_out = {}
    for h in headers:
        vals = col_values[h]
        nums = []
        for v in vals:
            try:
                nums.append(float(v))
            except ValueError:
                pass
        col_stat: dict = {"null_ratio": round(null_counts[h] / max(total_rows, 1), 3)}
        if nums and len(nums) > len(vals) * 0.5:
            col_stat.update({
                "numeric": True, "count": len(nums),
                "mean": round(statistics.mean(nums), 3),
                "min": round(min(nums), 3),
                "max": round(max(nums), 3),
            })
        else:
            col_stat["numeric"] = False
        stats_out[h] = col_stat

    return jsonify({"headers": headers, "total_rows": total_rows, "stats": stats_out})


@api.route("/api/file/<slug>/<path:filepath>/rows")
@requires_auth
def api_file_rows(slug: str, filepath: str):
    """Return filtered, sorted, paginated rows from a CSV."""
    full_path = _code_dir / slug / filepath
    if not full_path.is_file() or full_path.suffix.lower() != ".csv":
        abort(404)

    sort_col = request.args.get("sort")
    order = request.args.get("order", "asc")
    filter_col = request.args.get("filter_col")
    filter_val = request.args.get("filter_val", "").lower()
    limit = min(int(request.args.get("limit", 100)), 1000)
    offset = max(int(request.args.get("offset", 0)), 0)

    with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        if not headers:
            abort(400)

        rows = list(reader)
        total = len(rows)

        # Filter
        if filter_col and filter_col in headers:
            ci = headers.index(filter_col)
            rows = [r for r in rows if len(r) > ci and filter_val in r[ci].lower()]

        # Sort
        if sort_col and sort_col in headers:
            si = headers.index(sort_col)
            try:
                rows.sort(key=lambda r: float(r[si]) if si < len(r) and r[si].replace('.', '').replace('-', '').isdigit() else (r[si] if si < len(r) else ""), reverse=(order == "desc"))
            except Exception:
                pass  # fallback: unsorted

        filtered_total = len(rows)
        page = rows[offset:offset + limit]

    return jsonify({
        "headers": headers, "rows": page,
        "total": total, "filtered_total": filtered_total,
        "offset": offset, "limit": limit,
    })


@api.route("/api/export/<slug>/<path:filepath>")
@requires_auth
def api_export(slug: str, filepath: str):
    """Export a data file as CSV or JSON download."""
    full_path = _code_dir / slug / filepath
    if not full_path.is_file():
        abort(404)

    export_format = request.args.get("format", "csv")
    filter_col = request.args.get("filter_col")
    filter_val = request.args.get("filter_val", "").lower()

    if full_path.suffix.lower() == ".csv" and export_format == "json":
        with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if filter_col and filter_col in (reader.fieldnames or []):
            rows = [r for r in rows if filter_val in r.get(filter_col, "").lower()]
        return jsonify(rows)

    if full_path.suffix.lower() == ".csv" and export_format == "csv":
        return send_file(str(full_path), mimetype="text/csv",
                         as_attachment=True, download_name=full_path.name)

    # Other files: send as-is
    return send_file(str(full_path), as_attachment=True, download_name=full_path.name)


@api.route("/api/search")
@requires_auth
def api_search():
    q = request.args.get("q", "").lower().strip()
    if not q:
        return jsonify([])
    repos = _load_all_metadata()
    results = []
    for r in repos:
        text = json.dumps(r, ensure_ascii=False).lower()
        if q in text:
            results.append(r)
    return jsonify(results)


@api.route("/api/licenses")
@requires_auth
def api_licenses():
    """Return license summary for all repos."""
    repos = _load_all_metadata()
    return jsonify([{
        "repo_name": r.get("repo_name"),
        "license": r.get("license", "Unknown"),
        "repo_url": r.get("repo_url"),
    } for r in repos])
