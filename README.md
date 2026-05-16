<div align="center">

# DataWarehouse-Explorer

### Personal Data Lake — Automated. AI-Powered. Portable.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-one--click%20deploy-2496ED)](docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-passing-success)](tests/)

**Search → Validate → Convert to Parquet → Store → Query with AI**

[Live Demo](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com) · [Quick Start](#-quick-start) · [Architecture](#-architecture) · [Why Star](#-why-star)

</div>

---

> ⚠️ **Disclaimer** — This tool is intended for **personal learning and research purposes only**. Datasets downloaded via this tool retain their original licenses. You are solely responsible for complying with each dataset's license terms (CC, MIT, GPL, etc.). **Do NOT** use this tool to scrape copyrighted or proprietary data without authorization. The authors assume no liability for misuse.

---

## What Problem Does This Solve?

You start a new project — data analysis, ML training, academic research — and spend the first hour hunting for data:

> Kaggle → search → download → unzip → "wrong format" → next → download → "too small" → next → ...

**This tool compresses that hour into one command.** Run it, and you get a queryable, AI-searchable, Parquet-compressed data lake with a web UI. After that, you just open your browser.

---

## Quick Start

### Option 1: Docker (recommended)

```bash
git clone https://github.com/symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

# Set GitHub token for higher API rate limit (optional but recommended)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# One command
docker-compose up -d
# → Web UI at http://localhost:5000
# → Celery worker handles downloads in background
```

### Option 2: Local Python

```bash
git clone https://github.com/symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

pip install -r requirements.txt

# Run pipeline
python DeepSeek_DataV4.py

# Start web server
python DataWarehouse_Web.py
# → http://127.0.0.1:5000
```

> Requires Python 3.10+ and Git. Dependencies auto-install on first run.

---

## What You Get Immediately

The pipeline ships with 5 high-quality seed repositories. Open the web UI and you'll see:

| Repository | Stars | Data | Preview |
|-----------|-------|------|---------|
| **fivethirtyeight/data** | 16.9k | 189 CSV | World Cup predictions, US city weather, boxer records, voter registration |
| **public-apis/public-apis** | 330k | API index | Hundreds of categorized free APIs |
| **awesomedata/awesome-public-datasets** | 63k | Dataset catalog | Finance, climate, healthcare, transportation |
| **jivoi/awesome-osint** | 21k | OSINT tools | Social media analysis, recon, leak detection |
| **datasets/awesome-data** | 6.2k | Data catalog | Economics, education, demographics |

Want more? Edit config.json → add keywords → re-run. Existing data is never re-downloaded.

---

## Architecture

```
                    DataWarehouse-Explorer — Technical Architecture
═══════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────────────────────────────────────────────────┐
 │                     DATA INGESTION LAYER                          │
 │                                                                   │
 │  ▸ GitHub API + mirrors (kgithub / gitclone)                     │
 │  ▸ Proxy pool with health scoring & automatic rotation            │
 │  ▸ Playwright headless Chromium for JS-rendered pages             │
 │  ▸ dlt (Data Load Tool) for structured API incremental sync       │
 │  ▸ 5-strategy download: GitHub → mirror → mirror2 → ZIP → retry  │
 └────────────────────────────┬──────────────────────────────────────┘
                              │
 ┌────────────────────────────▼──────────────────────────────────────┐
 │                     QUALITY ASSESSMENT LAYER                       │
 │                                                                   │
 │  ▸ CSV: column consistency, null ratios, date format detection    │
 │  ▸ XML: well-formedness + element diversity                       │
 │  ▸ SQLite: PRAGMA table_info structure probe                      │
 │  ▸ Python: ast.parse syntax validation                            │
 │  ▸ PII scan: email, phone, address, name, SSN, IP auto-detect     │
 │  ▸ License: MIT / Apache / GPL / CC0 / BSD auto-identification    │
 │  ▸ Commit recency: penalize repos untouched for 5+ years          │
 │  ▸ LLM evaluator: reads README → generates Chinese summary + tags │
 └────────────────────────────┬──────────────────────────────────────┘
                              │
 ┌────────────────────────────▼──────────────────────────────────────┐
 │                     STORAGE LAYER                                  │
 │                                                                   │
 │  ▸ SQLAlchemy ORM (SQLite/PostgreSQL) — O(log N) indexed queries  │
 │  ▸ SHA-256 content-addressed dedup — same file stored once        │
 │  ▸ Auto CSV/JSON → Parquet via DuckDB (5-10x compression)         │
 │  ▸ Raw / Processed / Parquet directory separation                  │
 │  ▸ Data passport: UUID + domain + license + citation + commit hash│
 │  ▸ Version history tracking per dataset                           │
 └────────────────────────────┬──────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                                       │
 ┌────────▼──────────┐                 ┌──────────▼──────────────┐
 │  CLI Console       │                 │  Web UI (Flask)         │
 │  DS4> /search      │                 │                         │
 │  /stats /best      │                 │  ▸ AG Grid table        │
 │  /recent /export   │                 │  ▸ ECharts distribution │
 │  /ai-ask           │                 │  ▸ Column sort/filter   │
 └───────────────────┘                 │  ▸ Export CSV/JSON      │
                                       │  ▸ AI NL query panel    │
                                       │  ▸ Download progress bar│
                                       │  ▸ HTTP Basic Auth      │
                                       │  ▸ serveo public tunnel │
                                       └─────────────────────────┘
```

### Stack

| Layer | Technology |
|-------|-----------|
| **Orchestration** | Celery + Redis (or threading fallback) |
| **Async HTTP** | aiohttp + asyncio |
| **JS Rendering** | Playwright (Chromium) |
| **ORM** | SQLAlchemy (SQLite / PostgreSQL) |
| **Analytics Engine** | DuckDB (columnar, zero-config) |
| **Object Store** | MinIO (S3-compatible, self-hosted) |
| **Format** | Apache Parquet (ZSTD compression) |
| **Web** | Flask + AG Grid + ECharts |
| **AI** | DeepSeek / OpenAI / GLM / Ollama |
| **Deploy** | Docker Compose |

---

## Why Star?

| # | Reason |
|---|--------|
| 1 | **Not a demo** — 22 modules, 18 tests, full Type Hints, SQLAlchemy ORM, Docker |
| 2 | **Parquet-native** — Auto-converts downloaded data to Parquet, 5-10x smaller, analytical-ready |
| 3 | **Content-addressed dedup** — SHA-256 CAS means identical files from different repos never duplicate |
| 4 | **Async background tasks** — Celery queue, downloads run in background, Web UI shows progress |
| 5 | **LLM-powered quality** — AI reads README, generates descriptions, tags, and use-case summaries |
| 6 | **No hardcoded paths** — Configurable via env vars; Docker volume; works on any machine, not tied to `E:\` |
| 7 | **Security-first** — API keys via env vars only; PII auto-scan; license compliance report; legal disclaimer |
| 8 | **One-click Docker** — `docker-compose up -d` brings up Flask + Redis + Celery worker |

---

## AI Natural Language Query (v3.0)

Click the **AI** button (bottom-right), type a question:

```
"What are the top 5 cities by average temperature?"
"Show boxers with more than 30 wins"
```

The system: **understands intent → generates SQL → executes against DuckDB → returns chart data**.

### LLM Setup

Copy `config/llm_config.yaml`, fill in your API key:

```yaml
active_provider: deepseek

providers:
  deepseek:
    api_key: "sk-your-key"        # https://platform.deepseek.com
    model: "deepseek-chat"

  ollama:                          # Free, local
    base_url: "http://localhost:11434/v1"
    model: "qwen2.5:7b"
```

| Provider | Cost | Best For |
|----------|------|----------|
| **DeepSeek** | ~¥1/M tokens | Best value, Chinese-friendly |
| **Ollama** | **Free** | Local, data never leaves device |
| **GLM (Zhipu)** | ~¥1/M tokens | China-hosted, compliance |
| **OpenAI** | ~$5/M tokens | Strongest reasoning |

> API keys are read from env vars or `llm_config.yaml` (gitignored). Never committed.

---

## Configuration

All config via `config.json` + environment variables:

```bash
# GitHub token (env var only — NEVER in config.json)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Warehouse path (configurable — no hardcoded E:\ drive)
export DW_WAREHOUSE_ROOT=/mnt/data/warehouse

# Web UI auth
export DW_AUTH_USER=admin
export DW_AUTH_PASS_HASH=$(echo -n "password" | sha256sum | cut -d' ' -f1)
```

```json
// config.json
{
  "search_keywords": ["climate data csv", "financial dataset", "healthcare analytics"],
  "min_stars": 10,
  "max_repos_per_keyword": 30,
  "storage_mode": "content_addressed",
  "commit_recency_weight": true
}
```

Full docs: [Configuration Guide](docs/CONFIGURATION.md)

---

## API Endpoints

| Endpoint | Description |
|----------|------------|
| `GET /api/repos` | List all indexed repositories |
| `GET /api/repo/<slug>` | Repo details + file listing |
| `GET /api/file/<slug>/<path>` | File preview (CSV → table, JSON → formatted) |
| `GET /api/file/<slug>/<path>/stats` | Column stats: mean, min, max, null% |
| `GET /api/file/<slug>/<path>/rows` | Sorted, filtered, paginated rows |
| `GET /api/export/<slug>/<path>` | Download as CSV / JSON / Parquet |
| `POST /api/ai/ask` | Natural language → SQL → results |
| `POST /api/ai/schema` | LLM-generated field descriptions |
| `GET /api/licenses` | License report for all datasets |
| `GET /api/search?q=` | Full-text search across repos |
| `GET /api/tasks` | Background download task status |

---

## Testing

```bash
pip install pytest -q
pytest tests/ -v
# 18 passed — validator, web API, PII scan, license detection
```

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

### ⭐ If this saved you an afternoon of digging for data, star the repo

**[GitHub](https://github.com/symmetryseeker/DataWarehouse-Explorer)** · **[Live Demo](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com)** · **[API Docs](docs/API.md)** · **[Config Guide](docs/CONFIGURATION.md)**

</div>
