# DeepSeek DataV4 — Personal Offline Data Warehouse Builder

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

> 自动化离线数据仓库构建器 + 交互式网页浏览器  
> Automated offline data warehouse builder with interactive web UI

**Live Demo**: [https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com)

---

## What is this?

A fully automated Python pipeline that:

1. **Probes** GitHub mirrors for open-source data repositories
2. **Validates** discovered projects (AST parsing, JSON schema check, quality scoring)
3. **Stores** qualified data to your external drive with a clean directory structure
4. **Serves** an interactive web UI to browse and preview all data files

Think of it as your **personal offline data warehouse** — point it at your portable drive, run it, and get a searchable, browsable catalog of real-world datasets.

---

## Quick Start

```bash
# 1. Clone this repo
git clone https://github.com/symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

# 2. Run the pipeline (downloads & indexes repos)
python DeepSeek_DataV4.py

# 3. Start the web viewer
python DataWarehouse_Web.py

# 4. Open http://127.0.0.1:5000 in your browser
```

Dependencies auto-install on first run. Requires Python 3.10+ and Git.

---

## Architecture

```
DeepSeek_DataV4.py          # CLI pipeline (4 stages)
DataWarehouse_Web.py        # Flask web viewer
config.json                 # Search keywords & settings
```

### Pipeline Stages

| Stage | Class | What it does |
|-------|-------|-------------|
| 1 — Ingestion | `Ingester` | Async search against GitHub mirrors + API. Rotates User-Agents, handles rate limits. |
| 2 — Validation | `Validator` | Finds structured data files, validates Python via `ast.parse`, JSON via `json.load`, computes 0–50 quality score. |
| 3 — Storage | `StorageEngine` | Copies code + classified data to your external drive. Fully idempotent — re-runs skip existing repos. |
| 4 — Query | `QueryInterface` | In-memory inverted index with natural-language search console. |

### Directory Structure (on your external drive)

```
My Passport/
├── config.json
└── DataWarehouse/
    ├── metadata/          # Per-repo JSON index files
    ├── code/              # Cloned repository source code
    ├── data/
    │   ├── structured/    # csv/ json/ xml/ db/
    │   └── unstructured/
    ├── logs/              # Pipeline run logs
    └── tmp/               # Temp download workspace
```

---

## Interactive Console

After the pipeline runs, you enter the `DS4>` console:

```
DS4> /search 电商价格 csv
DS4> /stats
DS4> /best 10
DS4> /recent
DS4> /quit
```

---

## Web Viewer

![Web UI](https://img.shields.io/badge/Web_UI-Flask%20%2B%20Vanilla_JS-58a6ff)

Start with `python DataWarehouse_Web.py`, then open `http://127.0.0.1:5000`.

Features:
- **Left sidebar**: browse 5 repos, search by keyword
- **File grid**: click any repo to see all its files as cards
- **CSV table preview**: side panel with interactive data table (first 500 rows)
- **JSON/text preview**: syntax-highlighted content
- **LAN sharing**: auto-detects local IP for team access
- **Public tunnel**: use `ssh -R 80:localhost:5000 serveo.net` for a public URL

---

## Demo Data

The seed list includes 5 high-quality open-data repositories:

| Repository | Stars | Score | Files |
|-----------|-------|-------|-------|
| [fivethirtyeight/data](https://github.com/fivethirtyeight/data) | 16,900 | 16.5 | 189 CSVs |
| [public-apis/public-apis](https://github.com/public-apis/public-apis) | 330,000 | 13.0 | API directory |
| [awesomedata/awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets) | 63,000 | 13.0 | Dataset catalog |
| [jivoi/awesome-osint](https://github.com/jivoi/awesome-osint) | 21,000 | 10.0 | OSINT tools |
| [datasets/awesome-data](https://github.com/datasets/awesome-data) | 6,200 | 8.0 | Dataset catalog |

---

## Configuration

Edit `config.json` to customize:

```json
{
  "search_keywords": ["api", "crawler", "scraper", "dataset", "data-pipeline"],
  "min_stars": 5,
  "max_repos_per_keyword": 20,
  "blacklist_repos": [],
  "preferred_mirrors": ["kgithub"]
}
```

---

## Dependencies

- `aiohttp` — async HTTP
- `beautifulsoup4` + `lxml` — HTML parsing
- `colorama` — terminal colors
- `flask` — web viewer

All auto-installed on first run.

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Author

**symmetryseeker** — [GitHub](https://github.com/symmetryseeker)

---

*Built with Python, aiohttp, Flask, and the desire to never search for datasets manually again.*
