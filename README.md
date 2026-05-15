# DeepSeek DataV4 — 把互联网变成你的随身数据仓库

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Web-Flask%20%2B%20Chart.js-58a6ff)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-18%20passed-brightgreen)](tests/)
[![SQLite](https://img.shields.io/badge/metadata-SQLite%20%2B%20CAS-orange)]()

**自动搜索 → 智能校验 → 内容寻址存储 → 交互式网页浏览**

[在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com) · [技术架构](#技术路线) · [快速开始](#快速开始) · [为什么值得 Star](#-为什么值得-star)

</div>

---

## 一句话说清楚

> **每次新项目都要去 Kaggle、GitHub、各大学 FTP 翻数据集？**
>
> 这个工具替你自动化了这一切。插上移动硬盘，运行一行命令，得到一个**可搜索、可预览、可导出的私有数据仓库**。自带 189 个真实 CSV 数据集让你立刻就能用。

---

## 为什么值得 ⭐ Star？

| 理由 | 一句话 |
|------|--------|
| **不是玩具** | 18 个自动化测试，12 个模块化包，完整的 Type Hints + Google Style Docstrings |
| **5 路抗断网下载** | GitHub → kgithub 镜像 → gitclone 镜像 → ZIP 主分支 → ZIP master 分支，一种挂了换下一种 |
| **内容寻址去重** | SHA-256 寻址存储，两个仓库包含同一个 CSV 只存一份，为 10 万+ 文件设计 |
| **数据护照** | 每个数据集自动生成 UUID + 领域标签 + 许可证 + 引用格式 + 兼容工具链 |
| **PII 合规扫描** | 自动检测 email/phone/address/name/SSN/IP 列，Web UI 黄色警告标记 |
| **零配置公网分享** | 无需 nginx、无需域名、无需云账单，`ssh -R` 一行命令生成公网链接 |
| **自愈安装** | 缺少依赖自动 `pip install`，Python 3.10+ 和 Git 即可运行 |
| **插盘即用** | 自动探测 `My Passport` 移动硬盘路径（Windows/macOS/Linux） |

---

## 技术路线

```
                           DeepSeek DataV4 流水线
═══════════════════════════════════════════════════════════════════

  GitHub 镜像          GitHub API          5 个种子仓库
  (kgithub/gitclone)   (REST)              (fivethirtyeight...)
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                   ┌────────▼────────┐
                   │  Stage 1         │
                   │  Ingester        │
                   │  异步 aiohttp    │
                   │  Semaphore 并发  │
                   │  User-Agent 轮换 │
                   └────────┬────────┘
                            │ 候选仓库
                   ┌────────▼────────┐
                   │  Stage 2         │
                   │  Validator       │
                   │  ▸ CSV 列一致性  │
                   │  ▸ XML 结构校验  │
                   │  ▸ SQLite 表探测 │
                   │  ▸ PII 合规扫描  │
                   │  ▸ 许可证识别    │
                   │  ▸ 0–50 质量评分 │
                   └────────┬────────┘
                            │ 合格仓库 (score ≥ 5)
                   ┌────────▼────────┐
                   │  Stage 3 + 4     │
                   │  StorageEngine   │
                   │  ▸ SHA-256 CAS   │
                   │  ▸ raw/processed │
                   │  ▸ SQLite 元数据 │
                   │  ▸ 版本历史追踪  │
                   └────────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │                           │
     ┌────────▼────────┐       ┌─────────▼────────┐
     │  CLI 终端        │       │  Web 浏览器       │
     │  DS4> /search    │       │  ▸ CSV 表格预览   │
     │  /stats /best    │       │  ▸ 排序/过滤/统计  │
     │  /recent /quit   │       │  ▸ Chart.js 图表  │
     └─────────────────┘       │  ▸ 导出 CSV/JSON  │
                               │  ▸ Basic Auth     │
                               │  ▸ serveo 公网隧道 │
                               └──────────────────┘
```

### 模块架构（v2.0）

```
datawarehouse/
├── models.py          # 4 个 dataclass: RepoMeta, DataPassport, FileRecord, ValidationReport
├── config.py          # 配置管理 + My Passport 自动探测
├── ingestor.py        # 异步搜索 + 5 路下载策略
├── validator.py       # 深度校验 + PII 扫描 + 许可证检测
├── storage.py         # SHA-256 内容寻址存储 + raw/processed 分离
├── query.py           # 内存倒排索引 + 自然语言搜索
├── metadb.py          # SQLite 元数据库 (3 tables, 6 indexes)
├── pipeline.py        # 流水线编排器
├── license_report.py  # LICENSES.md 自动生成
├── web/               # Flask 模块
│   ├── routes.py      # 11 个 REST API 端点
│   ├── auth.py        # HTTP Basic Auth (可选)
│   └── static/        # Vanilla JS + Chart.js 暗色主题 UI
└── cli.py             # DS4> 交互终端
```

---

## 快速开始

```bash
git clone git@github.com:symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

# 运行流水线（自动搜索 → 下载 → 校验 → 存储）
python DeepSeek_DataV4.py

# 启动网页浏览器
python DataWarehouse_Web.py
# → http://127.0.0.1:5000
```

> 首次运行自动安装依赖。需要 Python 3.10+ 和 Git。

---

## 预置数据：开箱即用

流水线内置 5 个高质量开源数据仓库作为种子，首跑即可获取：

| 仓库 | ⭐ Stars | 得分 | 数据 |
|------|---------|------|------|
| [fivethirtyeight/data](https://github.com/fivethirtyeight/data) | 16,900 | 16.5 | **189 个 CSV**：世界杯预测、美国天气、拳击记录、选民登记…… |
| [public-apis/public-apis](https://github.com/public-apis/public-apis) | 330,000 | 13.0 | 数百个分类免费 API 目录 |
| [awesomedata/awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets) | 63,000 | 13.0 | 按主题分类的高质量开放数据集索引 |
| [jivoi/awesome-osint](https://github.com/jivoi/awesome-osint) | 21,000 | 10.0 | 开源情报工具与资源大全 |
| [datasets/awesome-data](https://github.com/datasets/awesome-data) | 6,200 | 8.0 | 经济/气候/人口数据源 |

---

## Web 浏览器功能

```
┌──────────────────┬──────────────────────────────────────────┐
│  左侧边栏         │  主内容区                                 │
│  🔍 实时搜索      │  文件卡片网格 (按类型彩色标签)              │
│  仓库列表         │  ┌─────────┐ ┌─────────┐ ┌─────────┐    │
│  (带质量分+星标)   │  │ undefe- │ │ KCLT    │ │ KCQT    │    │
│                  │  │ ated    │ │ .csv    │ │ .csv    │    │
│  ┌────────────┐  │  │ .csv    │ │ 52 KB   │ │ 45 KB   │    │
│  │ fivethirty-│  │  └─────────┘ └─────────┘ └─────────┘    │
│  │ eight/data │  │                                          │
│  │ 16.5/50    │  │        点击任意文件 → 右侧滑出面板         │
│  │ ★ 16,900   │  │   ┌─────────────────────────────────┐   │
│  │ MIT        │  │   │ [Stats] [Chart] [Export CSV] [✕]│   │
│  └────────────┘  │   │─────────────────────────────────│   │
│  ┌────────────┐  │   │  name ▲   │ url    │ date     │   │
│  │ public-apis│  │   │  Juro...  │ boxrec │ 1941-01  │   │
│  │ 13.0/50    │  │   │  Jake...  │ boxrec │ 1943-06  │   │
│  │ ★ 330,000  │  │   │  ...      │ ...    │ ...      │   │
│  └────────────┘  │   └─────────────────────────────────┘   │
└──────────────────┴──────────────────────────────────────────┘
```

- **CSV 交互表格** — 点击列头排序（升▲/降▼）、按列值过滤、统计面板（均值/最大最小/空值率）
- **Chart.js 可视化** — 选 X/Y 轴 → 柱状图/折线图，暗色主题适配
- **导出** — 支持 CSV 和 JSON 格式，含当前过滤条件
- **许可证一览** — `/api/licenses` 展示各数据集许可证

---

## 公网分享：零配置

```bash
# 终端 1：启动 Web 服务（自动检测局域网 IP）
python DataWarehouse_Web.py
# → http://127.0.0.1:5000
# → http://10.195.169.238:5000  (LAN 自动检测)

# 终端 2：一键公网隧道（免费、无需注册）
ssh -R 80:localhost:5000 serveo.net
# → https://xxxx.serveousercontent.com  (公网链接)
```

加上 `--public` 参数可关闭认证，开启 Basic Auth 保护需配置环境变量 `DW_USER` / `DW_PASS_HASH`。

---

## 数据护照：知道你的数据从哪来

每个入库数据集自动生成身份档案：

```json
{
  "uuid": "f47ac10b-...",
  "source_repo": "fivethirtyeight/data",
  "data_domain": "sports",
  "update_frequency": "static",
  "license": "CC BY 4.0",
  "citation": "FiveThirtyEight, 2024",
  "compatible_tools": ["pandas", "jupyter", "excel"],
  "version_commit_hash": "a3f2b1c"
}
```

对于学术引用、商用合规审查、数据血缘追溯，这比任何 README 都管用。

---

## 设计原则

| 原则 | 实现 |
|------|------|
| **幂等性** | 重复运行自动跳过已入库仓库，仅增量更新 |
| **健壮性** | 网络超时、文件损坏只记日志，绝不中断主循环 |
| **PEP8 合规** | 完整 Type Hints + Google Style Docstrings + ruff 检测 |
| **自愈安装** | 缺少依赖自动 `pip install`，无需手动配置 |
| **内容寻址** | 同一文件只存一份，SHA-256 天然去重 |
| **向后兼容** | v1.0 JSON 元数据可一步迁移到 v2.0 SQLite |

---

## 配置

```json
{
  "search_keywords": ["api", "crawler", "scraper", "dataset", "data-pipeline"],
  "min_stars": 5,
  "max_repos_per_keyword": 20,
  "storage_mode": "content_addressed",
  "web_auth_user": null,
  "web_auth_pass_hash": null
}
```

完整配置项见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

---

## 测试

```bash
pytest tests/ -v
# 18 passed — 覆盖校验器、Web API、PII 扫描、许可证检测
```

---

## 技术栈

`aiohttp` · `asyncio` · `beautifulsoup4` · `lxml` · `Flask` · `Chart.js` · `SQLite` · `serveo.net`

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)

---

<div align="center">

**⭐ 如果这个项目帮你省了一下午找数据集的时间，点个 Star 支持一下**

[GitHub](https://github.com/symmetryseeker) · [在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com) · [API 文档](docs/API.md) · [配置指南](docs/CONFIGURATION.md)

</div>
