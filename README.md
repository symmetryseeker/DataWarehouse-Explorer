<div align="center">

# DataWarehouse-Explorer

### 把互联网变成你的随身数据仓库

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-18/18-passed-success)](tests/)
[![Modules](https://img.shields.io/badge/modules-22-orange)]()

**自动搜索 → 智能校验 → 内容寻址存储 → AI 自然语言查询 → 交互式网页浏览**
<br>
`pip install` 零手动配置 · 插移动硬盘即用 · 189 个真实数据集开箱即得

[在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com) · [快速开始](#-30-秒快速开始) · [技术架构](#-技术架构) · [为什么 Star](#-为什么值得-star)

</div>

---

## 解决什么问题？

你每次开始一个新项目——数据分析、机器学习、学术研究——都要重复做这些事：

> 打开 Kaggle → 搜索 → 下载 → 解压 → 看两眼 → 不满意 → 换一个 → 再下载 → 格式不对 → 清洗 → ...

**这个工具把上面所有步骤压缩成一条命令。** 运行一次，得到一个带 Web UI、可搜索、可导出、可 AI 查询的私有数据仓库。之后打开浏览器就能浏览所有数据。

---

## 30 秒快速开始

```bash
# 1. 克隆
git clone https://github.com/symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

# 2. 运行流水线（自动下载 5 个种子仓库）
python DeepSeek_DataV4.py

# 3. 启动网页浏览器
python DataWarehouse_Web.py
```

打开 `http://127.0.0.1:5000`，你立刻能看到 189 个真实 CSV 数据集，包括世界杯预测、美国历史天气、拳击手战绩、选民注册数据……

> 首次运行自动安装所有依赖，仅需 Python 3.10+ 和 Git。

### 30 秒不够？想搜索更多数据？

编辑 `config.json`，添加你感兴趣的关键词：

```json
{
  "search_keywords": ["healthcare dataset", "stock market csv", "climate data"],
  "min_stars": 10
}
```

重新运行 `python DeepSeek_DataV4.py`，脚本会自动从 GitHub 搜索匹配仓库、下载、校验、入库。已有数据不会被重复下载（幂等设计）。

---

## 开箱数据一览

| # | 仓库 | ⭐ | 数据量 | 内容举例 |
|---|------|-----|--------|---------|
| 1 | **fivethirtyeight/data** | 16.9k | 189 CSV | 2014 世界杯每场预测、美国 10 城市历史天气、拳击手战绩、中性名流行趋势 |
| 2 | **public-apis/public-apis** | 330k | API 目录 | 天气/金融/体育/政府/医疗等数百个分类免费 API 索引 |
| 3 | **awesomedata/awesome-public-datasets** | 63k | 数据集目录 | 金融/气候/医疗/交通等主题的高质量开源数据集链接 |
| 4 | **jivoi/awesome-osint** | 21k | 工具目录 | 社交媒体分析、网络侦察、数据泄露检测等 OSINT 工具索引 |
| 5 | **datasets/awesome-data** | 6.2k | 数据目录 | 经济/教育/气候/人口领域数据源 |

---

## 技术架构

```
                        DataWarehouse-Explorer v3.0 技术路线
══════════════════════════════════════════════════════════════════════════

 ┌─────────────────────────────────────────────────────────────┐
 │                      🔍 数据采集层                           │
 │  GitHub API  ·  kgithub/gitclone 镜像  ·  5 个种子仓库       │
 │                                                             │
 │  反爬引擎: 代理池打分轮换 · Playwright JS 渲染 · UA 伪装      │
 │  结构化 API: dlt 增量加载 + Schema 自动演化                   │
 │  容错策略: 5 路下载链路 (GitHub → 镜像 → ZIP main → ZIP      │
 │            master → 保底重试)，单点故障不影响整体               │
 └──────────────────────────┬──────────────────────────────────┘
                            │
 ┌──────────────────────────▼──────────────────────────────────┐
 │                      ✅ 数据质量层                            │
 │                                                             │
 │  ▸ CSV: 列一致性检查 + 空值比率 + 日期格式自动识别              │
 │  ▸ XML: well-formedness 校验 + 元素统计                       │
 │  ▸ SQLite: PRAGMA table_info 结构探测                        │
 │  ▸ Python: ast.parse 语法树校验                               │
 │  ▸ JSON: schema 完整性检查                                    │
 │  ▸ PII 合规: 自动扫描 email/phone/address/name/SSN/IP 列      │
 │  ▸ 许可证: MIT/Apache/GPL/CC0/BSD 自动识别                    │
 │  ▸ 综合评分: 0–50 自动化质量分，< 5 自动丢弃                   │
 └──────────────────────────┬──────────────────────────────────┘
                            │
 ┌──────────────────────────▼──────────────────────────────────┐
 │                      💾 智能存储层                            │
 │                                                             │
 │  ▸ 内容寻址: SHA-256 去重，相同文件物理只存一份                │
 │  ▸ 冷热分离: MinIO S3 (冷归档) + DuckDB (热分析)              │
 │  ▸ 数据护照: UUID + 领域标签 + 许可证 + 引用格式 + 版本哈希     │
 │  ▸ SQLite 元数据库: 3 张表 + 6 个索引，支持 10 万+ 文件        │
 │  ▸ 版本追踪: metadata/versions/ 保留每次变更历史               │
 └──────────────────────────┬──────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                                    │
 ┌────────▼────────┐                 ┌────────▼────────────┐
 │  🖥 CLI 终端      │                 │  🌐 Web 浏览器       │
 │  DS4> /search    │                 │                    │
 │  /stats /best    │                 │  📊 CSV 交互表格    │
 │  /recent         │                 │  📈 Chart.js 图表   │
 │  /export         │                 │  📥 导出 CSV/JSON  │
 │  /quit           │                 │  🤖 AI 自然语言查询 │
 └─────────────────┘                 │  🔒 HTTP Basic Auth │
                                     │  🌍 serveo 公网隧道  │
                                     └─────────────────────┘
```

### 模块一览（22 个文件）

```
datawarehouse/
├── models.py              # 4 个 dataclass 核心数据模型
├── config.py              # 配置管理 + 移动硬盘自动探测
├── pipeline.py            # 流水线编排器
│
├── ingestor.py            # 异步搜索 + 5 路下载
├── validator.py           # 深度校验 + PII + 许可证
├── storage.py             # SHA-256 内容寻址存储
├── query.py               # 倒排索引 + 自然语言搜索
├── metadb.py              # SQLite 元数据库
├── license_report.py      # LICENSES.md 自动生成
├── cli.py                 # DS4> 交互终端
│
├── ai/                    # 🆕 v3.0 AI 层
│   ├── llm_client.py      #   DeepSeek/OpenAI/GLM/Ollama
│   ├── schema_inferrer.py #   字段注释自动生成
│   └── text_to_sql.py     #   NL→SQL RAG 引擎
│
├── storage/               # 🆕 v3.0 高级存储
│   ├── duckdb_engine.py   #   OLAP 列式分析
│   └── minio_client.py    #   S3 对象存储
│
├── ingestion/             # 🆕 v3.0 高级采集
│   ├── proxy_pool.py      #   代理池 (打分/健康检查)
│   ├── playwright_fetcher.py # JS 渲染
│   └── dlt_loader.py      #   增量数据加载
│
└── web/                   # Flask Web 服务
    ├── routes.py          #   14 个 REST 端点
    ├── auth.py            #   Basic Auth
    ├── templates/         #   Jinja2 模板
    └── static/            #   Vanilla JS + Chart.js
```

---

## 为什么值得 ⭐ Star？

**1. 不是 Demo，是工程**

22 个模块化文件、18 个自动化测试、完整的 Type Hints + Google Style Docstrings。代码即文档。

**2. 硬件感知，插盘即用**

自动探测 `My Passport` 移动硬盘路径（支持 Windows/macOS/Linux）。未检测到硬盘会降级到本地目录并给出明确警告。你的数据永远跟着硬盘走，换电脑继续用。

**3. 5 路抗断网下载**

```
GitHub 直连 → kgithub 镜像 → gitclone 镜像 → ZIP(main) → ZIP(master)
```

在国内网络环境下尤为重要——一种方式挂了自动换下一种，不会因为 GitHub 间歇性超时而中断整个流水线。

**4. 内容寻址去重**

相同 SHA-256 的文件物理上只存一份。多个仓库引用同一个公共数据集（这在数据科学领域极其常见）时，你只占用一份空间。

**5. PII 合规 + 许可证追踪**

自动扫描 CSV 列头检测敏感字段，Web UI 黄色警告标记。自动检测 LICENSE 文件并生成 LICENSES.md 汇总表。学术引用和商用合规都靠它。

**6. 零成本公网分享**

不需要 nginx、不需要域名、不需要买服务器。`ssh -R` 一行命令生成公网链接，团队同事直接用浏览器访问你的数据仓库。

---

## 🤖 AI 自然语言查询（v3.0）

打开网页，点右下角蓝色 **AI** 按钮：

```
你: "Which boxer has the most wins?"
AI: 生成 SQL → SELECT name, MAX(wins) FROM ... → Jake Matlala (53 wins)

你: "Show average temperature by city"
AI: 生成 SQL + 自动推荐柱状图
```

### 配置方式

复制 `config/llm_config.yaml`，填入你的 API key（文件已加入 .gitignore，不会泄露）：

```yaml
active_provider: deepseek   # deepseek | openai | glm | ollama

providers:
  deepseek:
    api_key: "sk-your-key-here"       # https://platform.deepseek.com
    model: "deepseek-chat"

  ollama:                             # 免费本地方案
    base_url: "http://localhost:11434/v1"
    model: "qwen2.5:7b"
```

| 提供商 | 费用 | 特点 |
|--------|------|------|
| **DeepSeek** | ¥1/百万 token | 性价比最高，中文友好 |
| **GLM (智谱)** | ¥1/百万 token | 国产合规 |
| **Ollama** | **免费** | 本地运行，数据不出设备 |
| **OpenAI** | ~$5/百万 token | 推理能力最强 |

---

## 📖 使用指南

### 基础用法

```bash
# 完整流水线
python DeepSeek_DataV4.py          # 搜索 → 下载 → 校验 → 入库 → 交互终端

# 交互终端命令
DS4> /search 天气 csv              # 自然语言搜索
DS4> /stats                        # 仓库统计
DS4> /best 10                      # 质量分最高的 10 个数据集
DS4> /recent                       # 最近入库的数据集
DS4> /quit                         # 退出
```

### 网页浏览

```bash
python DataWarehouse_Web.py        # 启动 → http://127.0.0.1:5000

# 安全模式（需要认证）
python DataWarehouse_Web.py --public   # 跳过认证
DW_USER=admin DW_PASS_HASH=xxx python DataWarehouse_Web.py  # 启用 Basic Auth
```

### Web 浏览器功能

| 功能 | 操作 |
|------|------|
| **预览 CSV** | 点击任意 `.csv` 文件 → 右侧滑出交互表格 |
| **列排序** | 点击列头 → 升序 ▲ / 降序 ▼ |
| **过滤** | 输入列名 + 值 → 实时筛选行 |
| **统计** | 点 Stats 按钮 → 均值/最大最小/空值率/是否数值型 |
| **图表** | 点 Chart 按钮 → 选 X/Y 轴 → 柱状图/折线图 |
| **导出** | 点 Export CSV / Export JSON → 下载 |
| **AI 查询** | 点右下角蓝色 AI 按钮 → 自然语言提问 |
| **搜索** | 左侧搜索框 → 按仓库名/标签/数据类型过滤 |

### 分享给他人

```bash
# 局域网（自动检测 IP）
python DataWarehouse_Web.py
# → http://192.168.x.x:5000   同事直接在浏览器打开

# 公网（免费隧道，无需注册）
ssh -R 80:localhost:5000 serveo.net
# → https://xxxx.serveousercontent.com  任何人都能访问
```

---

## 扩展数据源

编辑 `config.json` 自定义搜索范围：

```json
{
  "search_keywords": [
    "machine learning dataset",
    "financial data csv",
    "open government data",
    "scientific research data"
  ],
  "min_stars": 20,
  "max_repos_per_keyword": 50,
  "storage_mode": "content_addressed"
}
```

每次修改 `search_keywords` 后重新运行 `python DeepSeek_DataV4.py`，新数据自动追加，已有数据自动跳过。

---

## 测试

```bash
pip install pytest -q
pytest tests/ -v
```

```
tests/test_validator.py::test_validate_csv_structure PASSED
tests/test_validator.py::test_validate_sqlite PASSED
tests/test_validator.py::test_detect_license PASSED
tests/test_validator.py::test_scan_pii PASSED
tests/test_web_api.py::test_api_repos PASSED
tests/test_web_api.py::test_api_file_stats PASSED
tests/test_web_api.py::test_api_export_csv PASSED
... 18 passed in 0.41s
```

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)

---

<div align="center">

### ⭐ 如果这个项目帮你省了找数据的时间，点个 Star 让更多人看到

**[在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com)** · **[GitHub](https://github.com/symmetryseeker/DataWarehouse-Explorer)** · **[API 文档](docs/API.md)** · **[配置指南](docs/CONFIGURATION.md)**

</div>
