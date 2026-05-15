# Configuration Guide

`config.json` is stored at the drive root (e.g., `E:\config.json`).

## All Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `search_keywords` | string[] | `["api","crawler","scraper","dataset","data-pipeline"]` | GitHub search terms |
| `min_stars` | int | `5` | Minimum GitHub stars to qualify |
| `max_repos_per_keyword` | int | `20` | Max repos to fetch per keyword |
| `blacklist_repos` | string[] | `[]` | Repo URLs to always skip |
| `preferred_mirrors` | string[] | `["kgithub"]` | Mirror priority order |
| `warehouse_root` | string | auto-detected | Path to DataWarehouse directory |
| `metadata_db_path` | string | `<warehouse_root>/metadata.db` | SQLite metadata path |
| `storage_mode` | string | `"content_addressed"` | `"content_addressed"` or `"flat"` |
| `web_auth_user` | string\|null | `null` | HTTP Basic Auth username |
| `web_auth_pass_hash` | string\|null | `null` | SHA-256 hex of password |
| `chart_library` | string | `"chartjs"` | `"chartjs"` only (for now) |

## Environment Variables

Override `config.json` values:

- `DW_WAREHOUSE_ROOT` — warehouse path
- `DW_AUTH_USER` — basic auth username
- `DW_AUTH_PASS_HASH` — SHA-256(password)
- `DW_PUBLIC_MODE` — set to `"1"` to disable auth

## Example

```json
{
  "search_keywords": ["api", "dataset", "machine-learning"],
  "min_stars": 10,
  "max_repos_per_keyword": 30,
  "storage_mode": "content_addressed"
}
```
