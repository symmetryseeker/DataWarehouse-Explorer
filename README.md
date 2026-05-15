#  个人离线数据仓库构建器

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Web-Flask%20%2B%20Vanilla%20JS-58a6ff)](https://flask.palletsprojects.com/)

**自动化离线数据仓库构建器 + 交互式网页浏览器**

[在线演示](https://8a2f919343bf8ef0-36-110-14-5.serveousercontent.com) · [快速开始](#快速开始) · [功能特性](#功能特性) · [架构设计](#架构设计)

</div>

---

## 这是什么？

一个完全自动化的 Python 流水线，能够：

1. **智能探测** — 从 GitHub 镜像站搜索包含 API、爬虫、数据集的开源仓库
2. **质量评估** — 自动检测项目是否"活着"：语法校验、数据结构完整性、打分
3. **本地存储** — 将合格数据保存到移动硬盘，建立科学分类的文件索引
4. **交互查询** — 提供命令行搜索终端 + Flask 网页浏览器，随时浏览预览数据

> 把你的移动硬盘变成一个**可查询、可浏览的离线数据仓库**。插上硬盘、运行脚本、获取数据集。

---

## 快速开始

```bash
# 1. 克隆仓库
git clone git@github.com:symmetryseeker/DataWarehouse-Explorer.git
cd DataWarehouse-Explorer

# 2. 运行数据流水线（自动搜索、下载、评分、存储）
python DeepSeek_DataV4.py

# 3. 启动网页浏览器
python DataWarehouse_Web.py

# 4. 浏览器打开 http://127.0.0.1:5000
```

首次运行自动安装依赖（`aiohttp`, `beautifulsoup4`, `flask` 等）。需要 Python 3.10+ 和 Git。

---

## 功能特性

### 命令行流水线（4 阶段自动化）

| 阶段 | 核心类 | 功能 |
|------|--------|------|
| **1. 探测获取** | `Ingester` | 异步搜索 kgithub/gitclone 镜像站 + GitHub API 兜底，随机轮换 User-Agent 反爬 |
| **2. 质量评估** | `Validator` | 递归发现 `.json` `.csv` `.xml` `.db` 文件，`ast.parse` 检验 Python 语法，`json.load` 校验 JSON，输出 0–50 质量分 |
| **3. 本地存储** | `StorageEngine` | 代码与分类数据写入 `My Passport/DataWarehouse/`，幂等设计——重复运行自动跳过已有内容 |
| **4. 交互查询** | `QueryInterface` | 内存倒排索引，支持自然语言检索 `/search 电商价格 csv` |

### 网页浏览器

```
┌──────────────────┬──────────────────────────────────────┐
│  左侧边栏        │  文件卡片网格                         │
│  🔍 搜索框       │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│  仓库列表         │  │ undefe- │ │ KCLT    │ │ KCQT    │ │
│  (按质量分排列)   │  │ ated    │ │ .csv    │ │ .csv    │ │
│                  │  │ .csv    │ │ 52 KB   │ │ 45 KB   │ │
│                  │  └─────────┘ └─────────┘ └─────────┘ │
│                  │              │                         │
│                  │    点击文件 → 右侧滑出预览面板          │
│                  │    ┌─────────────────────────┐        │
│                  │    │ name  │ url │ date │... │        │
│                  │    │ Juro  │ ... │ 1941 │... │        │
│                  │    │ ...   │ ... │ ...  │... │        │
│                  │    └─────────────────────────┘        │
└──────────────────┴──────────────────────────────────────┘
```

- **实时搜索** — 输入关键词即时过滤仓库
- **CSV 表格预览** — 点击 CSV 文件弹出交互式数据表格（前 500 行）
- **JSON/文本预览** — 语法高亮的 JSON，Markdown/Python/XML 源码
- **局域网共享** — 自动探测本机 IP，同事浏览器直接访问
- **公网隧道** — `ssh -R 80:localhost:5000 serveo.net` 一键生成公网链接

### 交互终端 `DS4>`

```
DS4> /search 电商价格 csv
DS4> /stats
DS4> /best 10
DS4> /recent
DS4> /rebuild
DS4> /quit
```

---

## 种子数据（预置 5 个高质量仓库）

| 仓库 | Stars | 得分 | 数据文件 | 内容 |
|------|-------|------|----------|------|
| [fivethirtyeight/data](https://github.com/fivethirtyeight/data) | 16,900 | 16.5 | 189 CSV | 世界杯预测、美国天气历史、拳击手记录、人口统计…… |
| [public-apis/public-apis](https://github.com/public-apis/public-apis) | 330,000 | 13.0 | API 目录 | 数百个分类免费 API 索引 |
| [awesomedata/awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets) | 63,000 | 13.0 | 数据集目录 | 按主题分类的高质量开放数据集清单 |
| [jivoi/awesome-osint](https://github.com/jivoi/awesome-osint) | 21,000 | 10.0 | OSINT 工具集 | 开源情报收集工具大全 |
| [datasets/awesome-data](https://github.com/datasets/awesome-data) | 6,200 | 8.0 | 数据集目录 | 经济、气候、人口等数据源链接 |

---

## 架构设计

### 项目结构

```
DataWarehouse-Explorer/
├── DeepSeek_DataV4.py          # CLI 流水线（4 阶段）
├── DataWarehouse_Web.py         # Flask 网页浏览器（单文件）
├── config.json                  # 搜索配置
├── README.md                    # 项目文档
├── LICENSE                      # MIT 协议
└── .gitignore
```

### 移动硬盘目录结构

```
My Passport/                     # 移动硬盘根目录
├── config.json                  # 运行配置
└── DataWarehouse/
    ├── metadata/                # 每个仓库的 JSON 索引
    ├── code/                    # 克隆的仓库源码
    ├── data/
    │   ├── structured/          # csv/ json/ xml/ db/ 分类存储
    │   └── unstructured/raw/
    ├── logs/                    # 运行日志
    └── tmp/                     # 临时下载目录（自动清理）
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 异步爬虫 | `aiohttp` · `asyncio` |
| HTML 解析 | `beautifulsoup4` · `lxml` |
| Python 语法校验 | `ast.parse` |
| 文件类型检测 | `pathlib` · `mimetypes` |
| Web 服务 | `Flask` |
| 前端 | Vanilla JS · CSS Grid · Fetch API |
| 网络隧道 | `serveo.net` (SSH 端口转发) |

### 设计原则

- **幂等性** — 脚本可反复运行，重复抓取时自动跳过或增量更新
- **健壮性** — 网络超时、文件损坏只记日志，绝不中断主循环
- **PEP8** — 严格遵循 Python 代码规范，完整 Type Hints
- **自愈引导** — 缺少依赖自动 `pip install`，无需手动配置

---

## 配置

编辑 `config.json` 自定义搜索行为：

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

## 公网部署

### 局域网分享

启动 Web 服务后，终端会显示本机 IP 地址，同一网络下的设备可直接访问：

```
http://10.195.169.238:5000
```

### 公网隧道（无需注册）

```bash
# 终端 1：启动网页服务
python DataWarehouse_Web.py

# 终端 2：创建公网隧道
ssh -R 80:localhost:5000 serveo.net
# 输出: https://xxxx.serveousercontent.com
```

生成的链接可发给任何人访问。serveo.net 免费、无需注册。

### 长期部署

如需长期稳定运行，建议使用 Cloudflare Tunnel 或部署到云服务器（将 `E:\DataWarehouse` 数据目录同步上去即可）。

---

## 依赖

| 包 | 用途 |
|---|------|
| `aiohttp` | 异步 HTTP 请求 |
| `beautifulsoup4` + `lxml` | HTML 页面解析 |
| `colorama` | 终端彩色输出 |
| `flask` | Web 服务 |

首次运行自动安装。

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)

---

## 作者

**symmetryseeker** — [GitHub](https://github.com/symmetryseeker)

---

<div align="center">

*用 Python、aiohttp、Flask 和「再也不想手动找数据集了」的怨念构建。*

</div>
