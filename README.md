<div align="center">

# DataWarehouse-Explorer

### Personal Data Lake — Automated. AI-Powered. Portable.
### 个人数据湖 — 全自动化 · AI 驱动 · 随身携带

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-one--click%20deploy-2496ED)](docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-passing-success)](tests/)

**Search → Validate → Convert to Parquet → Store → Query with AI**
<br>
**自动搜索 → 智能校验 → Parquet 压缩 → 入库 → AI 自然语言查询**

[Live Demo 在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com) · [Quick Start 快速开始](#-quick-start-快速开始) · [Architecture 架构](#-architecture-技术架构)

</div>

---

> ⚠️ **Disclaimer / 免责声明** — This tool is intended for **personal learning and research purposes only**. Datasets downloaded via this tool retain their original licenses. You are solely responsible for complying with each dataset's license terms (CC, MIT, GPL, etc.). **Do NOT** use this tool to scrape copyrighted or proprietary data without authorization. The authors assume no liability for misuse.
>
> 本工具仅供**个人学习和研究使用**。通过本工具下载的数据集保留其原始许可证。您有责任遵守每个数据集的许可条款。**请勿**未经授权使用本工具爬取受版权保护或专有的数据。作者对滥用行为不承担任何责任。

---

## What Problem Does This Solve? / 解决什么问题？

<!-- EN -->
**Every time you start a new project** — data analysis, ML training, academic research — you spend the first hour hunting for data:

> Kaggle → search → download → unzip → "wrong format" → next → download → "too small" → next → ...

**This tool compresses that hour into one command.** Run it, and you get a queryable, AI-searchable, Parquet-compressed data lake with a web UI.

<!-- ZH -->
**每次开始一个新项目**——数据分析、机器学习、学术研究——你都要花至少一小时找数据。这个工具把这一小时压缩成一条命令。运行后得到一个可查询、AI 可搜索、Parquet 压缩的数据湖，打开浏览器就能用。

---

## Quick Start / 快速开始

### Docker (recommended / 推荐)

```bash
git clone https://github.com/symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

# Set GitHub token (optional, raises API limit from 60→5000 req/hour)
# 设置 GitHub Token（可选，API 限额从 60→5000 次/小时）
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

docker-compose up -d
# → Web UI at http://localhost:5000
# → Celery worker handles downloads in background / 后台下载
```

### Local Python / 本地运行

```bash
git clone https://github.com/symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

pip install -r requirements.txt
python DeepSeek_DataV4.py       # Pipeline / 流水线
python DataWarehouse_Web.py     # Web server / 网页服务
# → http://127.0.0.1:5000
```

> Requires Python 3.10+ and Git. Dependencies auto-install on first run.
> 需要 Python 3.10+ 和 Git。首次运行自动安装依赖。

---

## What You Get Immediately / 开箱即得

The pipeline ships with 5 high-quality seed repositories. / 流水线内置 5 个高质量种子仓库。

| Repository | Stars | Data / 数据 | Content / 内容 |
|-----------|-------|-------------|----------------|
| **fivethirtyeight/data** | 16.9k | 189 CSV | World Cup predictions, US city weather, boxer records / 世界杯预测、美国城市天气、拳击记录 |
| **public-apis/public-apis** | 330k | API index | Hundreds of categorized free APIs / 数百个分类免费 API |
| **awesomedata/awesome-public-datasets** | 63k | Dataset catalog | Finance, climate, healthcare / 金融、气候、医疗 |
| **jivoi/awesome-osint** | 21k | OSINT tools | Social media analysis, recon / 社交媒体分析、网络侦察 |
| **datasets/awesome-data** | 6.2k | Data catalog | Economics, education, demographics / 经济、教育、人口 |

> Want more? Edit `config.json` → add keywords → re-run. Existing data is never re-downloaded.
> 想要更多？编辑 `config.json` → 添加关键词 → 重新运行。已入库数据不会重复下载。

---

## Architecture / 技术架构

```
                    DataWarehouse-Explorer — Architecture / 架构
═══════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────────────────────────────────────────────────┐
 │              INGESTION LAYER / 数据采集层                         │
 │                                                                   │
 │  ▸ GitHub API + mirrors (kgithub / gitclone)                     │
 │  ▸ Proxy pool with health scoring & rotation / 代理池打分轮换     │
 │  ▸ Playwright Chromium for JS-rendered pages / JS 渲染抓取        │
 │  ▸ dlt incremental sync for structured APIs / 增量同步            │
 │  ▸ 5-strategy download chain / 5 路下载链路                       │
 └────────────────────────────┬──────────────────────────────────────┘
                              │
 ┌────────────────────────────▼──────────────────────────────────────┐
 │              QUALITY LAYER / 质量评估层                            │
 │                                                                   │
 │  ▸ CSV: column consistency, null ratios, date detection / 列校验  │
 │  ▸ XML well-formedness · SQLite PRAGMA table_info                 │
 │  ▸ ast.parse syntax · PII scan (email/phone/address/name/SSN/IP)  │
 │  ▸ License auto-detect (MIT/Apache/GPL/CC0/BSD) / 许可证自动识别  │
 │  ▸ Commit recency penalty (5yr+) / 长期未更新扣分                 │
 │  ▸ LLM evaluator: reads README → generates summary + tags         │
 └────────────────────────────┬──────────────────────────────────────┘
                              │
 ┌────────────────────────────▼──────────────────────────────────────┐
 │              STORAGE LAYER / 存储层                                │
 │                                                                   │
 │  ▸ SQLAlchemy ORM (SQLite/PostgreSQL) — O(log N) indexed queries  │
 │  ▸ SHA-256 content-addressed dedup / 内容寻址去重                  │
 │  ▸ Auto CSV/JSON → Parquet via DuckDB (5-10x compression)         │
 │  ▸ Raw / Processed / Parquet tiered storage / 冷热分层             │
 │  ▸ Data passport: UUID + domain + license + citation              │
 │  ▸ Version history per dataset / 版本历史追踪                     │
 └────────────────────────────┬──────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                                       │
 ┌────────▼──────────┐                 ┌──────────▼──────────────┐
 │  CLI Console       │                 │  Web UI (Flask)         │
 │  DS4> /search      │                 │                         │
 │  /stats /best      │                 │  ▸ Interactive table    │
 │  /recent /export   │                 │  ▸ Column sort/filter   │
 │  /ai-ask           │                 │  ▸ ECharts distribution │
 └───────────────────┘                 │  ▸ Export CSV/JSON      │
                                       │  ▸ AI NL query panel    │
                                       │  ▸ Download progress    │
                                       │  ▸ HTTP Basic Auth      │
                                       │  ▸ serveo public tunnel │
                                       └─────────────────────────┘
```

### Stack / 技术栈

| Layer / 层 | Technology / 技术 |
|-----------|-------------------|
| Orchestration / 调度 | Celery + Redis (or threading fallback / 线程回退) |
| Async HTTP / 异步请求 | aiohttp + asyncio |
| JS Rendering / JS 渲染 | Playwright (Chromium) |
| ORM | SQLAlchemy (SQLite / PostgreSQL) |
| Analytics / 分析引擎 | DuckDB (columnar, zero-config) |
| Object Store / 对象存储 | MinIO (S3-compatible, self-hosted) |
| Format / 格式 | Apache Parquet (ZSTD compression) |
| Web | Flask + AG Grid + ECharts |
| AI | DeepSeek / OpenAI / GLM / Ollama |
| Deploy / 部署 | Docker Compose |

---

## Why Star? / 为什么值得 ⭐ Star？

| # | EN | ZH |
|---|-----|-----|
| 1 | **Not a demo** — 22 modules, 18 tests, Type Hints, SQLAlchemy ORM, Docker | **不是 Demo** — 22 个模块、18 个测试、完整 Type Hints、SQLAlchemy ORM、Docker 化 |
| 2 | **Parquet-native** — Auto-converts to Parquet, 5-10x smaller, analytics-ready | **Parquet 原生** — 自动转 CSV/JSON→Parquet，体积缩 5-10 倍，分析就绪 |
| 3 | **Content-addressed dedup** — SHA-256 CAS means identical files never duplicate | **SHA-256 去重** — 相同内容物理只存一份 |
| 4 | **Async background tasks** — Celery queue, downloads run in background, Web UI shows progress | **异步后台下载** — Celery 队列，Web UI 实时显示进度 |
| 5 | **LLM-powered quality** — AI reads README, generates descriptions and tags | **LLM 智能评估** — AI 读取 README 生成中文描述和标签 |
| 6 | **No hardcoded paths** — Configurable via env vars; works on any machine | **不强绑硬盘** — 环境变量配置路径，任意机器可用 |
| 7 | **Security-first** — API keys via env vars only; PII auto-scan; legal disclaimer | **安全优先** — API 密钥仅从环境变量读取，PII 自动扫描，法律免责声明 |
| 8 | **One-click Docker** — `docker-compose up -d` brings up the full stack | **一键 Docker** — `docker-compose up -d` 启动全部服务 |

---

## AI Natural Language Query / AI 自然语言查询

Click the **AI** button (bottom-right), type a question:
点击右下角蓝色 **AI** 按钮，用自然语言提问：

```
"What are the top 5 cities by average temperature?"
"Show boxers with more than 30 wins"
"去年销售额最高的三个品类是什么？"
```

The system: **understands intent → generates SQL → executes against DuckDB → returns chart data**.
系统自动：**理解意图 → 生成 SQL → DuckDB 执行 → 返回结果 + 图表**

### LLM Setup / 配置 LLM

Copy `config/llm_config.yaml`, fill in your API key. 复制 `config/llm_config.yaml`，填入你的 API key：

```yaml
active_provider: deepseek

providers:
  deepseek:
    api_key: "sk-your-key"        # https://platform.deepseek.com
    model: "deepseek-chat"

  ollama:                          # Free, local / 免费，本地运行
    base_url: "http://localhost:11434/v1"
    model: "qwen2.5:7b"
```

| Provider / 提供商 | Cost / 费用 | Best For / 适用场景 |
|-------------------|-------------|---------------------|
| **DeepSeek** | ~¥1/M tokens | Best value, Chinese-friendly / 性价比最高 |
| **Ollama** | **Free / 免费** | Local, data never leaves device / 数据不出设备 |
| **GLM (Zhipu 智谱)** | ~¥1/M tokens | China-hosted, compliance / 国产合规 |
| **OpenAI** | ~$5/M tokens | Strongest reasoning / 最强推理能力 |

> **API keys are read from env vars or `llm_config.yaml` (gitignored). Never committed.**
> **API 密钥从环境变量或 `llm_config.yaml`（gitignored）读取。绝不提交到 Git。**

---

## Configuration / 配置

All config via `config.json` + environment variables. 通过 `config.json` + 环境变量配置：

```bash
# GitHub token (env var ONLY — NEVER in config.json)
# GitHub Token（仅环境变量，绝不写入 config.json）
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Warehouse path (configurable — no hardcoded drive letter)
# 仓库路径（完全可配，不绑定盘符）
export DW_WAREHOUSE_ROOT=/mnt/data/warehouse

# Web UI auth / 网页认证
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

Full docs / 完整文档: [Configuration Guide / 配置指南](docs/CONFIGURATION.md)

---

## API Endpoints / API 端点

| Endpoint / 端点 | Description / 描述 |
|----------|------------|
| `GET /api/repos` | List all indexed repositories / 列出所有仓库 |
| `GET /api/repo/<slug>` | Repo details + file listing / 仓库详情和文件列表 |
| `GET /api/file/<slug>/<path>` | File preview (CSV → table) / 文件预览 |
| `GET /api/file/<slug>/<path>/stats` | Column stats: mean, min, max, null% / 列统计 |
| `GET /api/file/<slug>/<path>/rows` | Sorted, filtered, paginated rows / 排序过滤分页 |
| `GET /api/export/<slug>/<path>` | Download as CSV / JSON / Parquet / 导出 |
| `POST /api/ai/ask` | Natural language → SQL → results / 自然语言查询 |
| `POST /api/ai/schema` | LLM-generated field descriptions / AI 字段描述 |
| `GET /api/licenses` | License report for all datasets / 许可证汇总 |
| `GET /api/search?q=` | Full-text search / 全文搜索 |
| `GET /api/tasks` | Background download task status / 后台任务进度 |

---

## Testing / 测试

```bash
pip install pytest -q
pytest tests/ -v
# 18 passed — validator, web API, PII scan, license detection
```

---

## License / 许可证

MIT — see [LICENSE](LICENSE)

---

<div align="center">

### ⭐ If this saved you time hunting for data, star the repo!
### ⭐ 如果这个项目帮你省了找数据的时间，点个 Star！

**[GitHub](https://github.com/symmetryseeker/DataWarehouse-Explorer)** · **[Live Demo 在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com)** · **[API Docs](docs/API.md)** · **[Config Guide 配置指南](docs/CONFIGURATION.md)**

</div>
