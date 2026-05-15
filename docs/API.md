# API Reference

Base URL: `http://127.0.0.1:5000`

## Repos

### `GET /api/repos`
List all indexed repositories, sorted by quality score.
```json
[{"slug": "fivethirtyeight_data", "repo_name": "fivethirtyeight/data",
  "quality_score": 16.5, "stars": 16900, "license": "MIT", ...}]
```

### `GET /api/repo/<slug>`
Get a single repo with its file listing.
```json
{"slug": "...", "meta": {...}, "files": [{"name": "...", "path": "...", "size_human": "45 KB", "suffix": ".csv"}]}
```

## File Content

### `GET /api/file/<slug>/<path>`
Get parsed file content.
- CSV → `{"type": "csv", "headers": [...], "rows": [[...]], "total_rows": 500}`
- JSON → `{"type": "json", "content": "..."}`
- Text → `{"type": "text", "content": "..."}`
- Binary → `{"type": "binary", "size": "1.2 MB"}`

### `GET /api/file/<slug>/<path>/stats`
Get per-column statistics for a CSV file.
```json
{"headers": ["name", "age"], "total_rows": 100,
 "stats": {"age": {"numeric": true, "mean": 35.2, "min": 18, "max": 72, "null_ratio": 0.01}}}
```

### `GET /api/file/<slug>/<path>/rows`
Filtered, sorted, paginated rows.
Query params: `sort`, `order` (asc/desc), `filter_col`, `filter_val`, `limit` (max 1000), `offset`

## Export

### `GET /api/export/<slug>/<path>?format=csv`
Download file as CSV attachment.

### `GET /api/export/<slug>/<path>?format=json`
Download as JSON array.

## Search

### `GET /api/search?q=<query>`
Full-text search across all repo metadata.

## Licenses

### `GET /api/licenses`
License summary for all repos.
```json
[{"repo_name": "fivethirtyeight/data", "license": "MIT", "repo_url": "..."}]
```
