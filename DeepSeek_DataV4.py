#!/usr/bin/env python3
"""
DeepSeek_DataV4 — Personal Offline Data Warehouse Builder
=========================================================

A fully automated, modular pipeline that:
  1. Probes GitHub mirrors for open-source data/API repos.
  2. Validates discovered projects and assigns quality scores.
  3. Stores qualified assets in a standardized local directory tree.
  4. Provides an interactive natural-language query console.

Author:  Auto-generated per specification
License: MIT
"""

from __future__ import annotations

import ast
import asyncio
import csv
import hashlib
import json
import logging
import os
import platform
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, quote_plus

# ---------------------------------------------------------------------------
# Self-healing dependency bootstrap
# ---------------------------------------------------------------------------
REQUIRED_PACKAGES: Dict[str, str] = {
    "aiohttp": "aiohttp",
    "bs4": "beautifulsoup4",
    "colorama": "colorama",
    "lxml": "lxml",
}

_missing: List[str] = []
for _mod, _pkg in REQUIRED_PACKAGES.items():
    try:
        __import__(_mod)
    except ImportError:
        _missing.append(_pkg)

if _missing:
    print(f"[BOOTSTRAP] Installing missing packages: {' '.join(_missing)}")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", *_missing],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("[BOOTSTRAP] Done. Please re-run the script if imports still fail.")
    sys.exit(0)

import aiohttp
from bs4 import BeautifulSoup

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _C = Fore  # shorthand
    _S = Style
except ImportError:
    # fallback no-op colorama
    class _FakeFore:
        def __getattr__(self, _: str) -> str: return ""
    class _FakeStyle:
        def __getattr__(self, _: str) -> str: return ""
    _C = _FakeFore()
    _S = _FakeStyle()

# ---------------------------------------------------------------------------
# Drive Detection — Locate "My Passport" external drive
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent


def detect_my_passport() -> Optional[Path]:
    """Auto-detect the 'My Passport' external drive across platforms.

    Windows:
        Iterates drive letters D: through Z:, checking volume name and/or
        the existence of a ``My Passport`` directory at the drive root.
    macOS:
        Checks ``/Volumes/My Passport``.
    Linux:
        Checks ``/media/$USER/My Passport`` and ``/mnt/My Passport``.

    Returns:
        Absolute ``Path`` to the drive root if found, otherwise ``None``.
    """
    candidates: List[Path] = []

    system = platform.system()
    drive_label = "My Passport"

    if system == "Windows":
        # Iterate available drive letters
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{letter}:\\")
            if not root.exists():
                continue
            candidate = root / drive_label
            if candidate.is_dir():
                candidates.append(candidate)
                continue
            # Also check if the volume itself is labelled "My Passport"
            try:
                result = subprocess.run(
                    ["cmd", "/c", f"vol {letter}:"],
                    capture_output=True, text=True, timeout=5,
                    encoding="utf-8", errors="ignore",
                )
                if result.returncode == 0 and result.stdout \
                        and drive_label.lower() in result.stdout.lower():
                    candidates.append(root)
            except (OSError, subprocess.TimeoutExpired):
                pass

    elif system == "Darwin":
        candidate = Path(f"/Volumes/{drive_label}")
        if candidate.is_dir():
            candidates.append(candidate)

    else:  # Linux / Unix
        for base in (f"/media/{os.environ.get('USER', '')}/{drive_label}",
                     f"/media/{drive_label}",
                     f"/mnt/{drive_label}"):
            candidate = Path(base)
            if candidate.is_dir():
                candidates.append(candidate)

    if candidates:
        print(f"[DETECT] My Passport found at: {candidates[0]}")
        return candidates[0]

    # Fallback: search the script directory and parent directories
    fallback = _SCRIPT_DIR / drive_label
    if fallback.is_dir():
        print(f"[DETECT] My Passport found (relative): {fallback}")
        return fallback

    # Check parent directories as a last resort
    for parent in _SCRIPT_DIR.parents:
        fb = parent / drive_label
        if fb.is_dir():
            print(f"[DETECT] My Passport found (up-tree): {fb}")
            return fb

    return None


def resolve_warehouse_root() -> Path:
    """Determine the warehouse root path, preferring the external drive.

    If 'My Passport' is detected, data lives at ``<drive>/DataWarehouse/``.
    Otherwise falls back to ``<script_dir>/My Passport/DataWarehouse/`` and
    prints a prominent warning.
    """
    drive_root = detect_my_passport()
    if drive_root is not None:
        wh = drive_root
    else:
        wh = _SCRIPT_DIR / "My Passport"
        print(f"\n{_C.RED}{'!' * 60}{_S.RESET_ALL}")
        print(f"{_C.RED}  WARNING: 'My Passport' external drive NOT detected.{_S.RESET_ALL}")
        print(f"{_C.RED}  Falling back to local path: {wh}{_S.RESET_ALL}")
        print(f"{_C.RED}  Data will NOT be written to your portable drive!{_S.RESET_ALL}")
        print(f"{_C.RED}{'!' * 60}{_S.RESET_ALL}\n")

    warehouse = wh / "DataWarehouse"
    # Also place config.json & logs inside the drive root for full portability
    return warehouse


# ---------------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------------
WAREHOUSE_ROOT = resolve_warehouse_root()
DRIVE_ROOT = WAREHOUSE_ROOT.parent  # e.g. D:\My Passport or _SCRIPT_DIR\My Passport
CONFIG_PATH = DRIVE_ROOT / "config.json"
METADATA_DIR = WAREHOUSE_ROOT / "metadata"
DATA_STRUCTURED_DIR = WAREHOUSE_ROOT / "data" / "structured"
DATA_UNSTRUCTURED_DIR = WAREHOUSE_ROOT / "data" / "unstructured" / "raw"
CODE_DIR = WAREHOUSE_ROOT / "code"
LOG_DIR = WAREHOUSE_ROOT / "logs"
LOG_FILE = LOG_DIR / f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"

# Sub-directories for structured data by type
STRUCTURED_SUBDIRS: Dict[str, Path] = {
    ".json": DATA_STRUCTURED_DIR / "json",
    ".csv": DATA_STRUCTURED_DIR / "csv",
    ".xml": DATA_STRUCTURED_DIR / "xml",
    ".db": DATA_STRUCTURED_DIR / "db",
    ".sqlite": DATA_STRUCTURED_DIR / "db",
}

# GitHub mirror search endpoints
MIRRORS: List[Dict[str, str]] = [
    {
        "name": "kgithub",
        "search_url": "https://kgithub.com/search",
        "repo_prefix": "https://kgithub.com",
    },
    {
        "name": "gitclone",
        "search_url": "https://gitclone.com/search",
        "repo_prefix": "https://gitclone.com",
    },
]

# Fallback: use the official GitHub REST API as well (no auth needed for public)
GITHUB_API_SEARCH = "https://api.github.com/search/repositories"

# Pool of realistic User-Agent strings rotated per-request
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Patterns that indicate structured data or API documentation
DATA_FILE_PATTERNS: List[str] = [
    r"\.json$", r"\.csv$", r"\.xml$", r"\.db$", r"\.sqlite$",
    r"\.parquet$", r"\.feather$", r"\.arrow$", r"\.avro$",
]
API_DOC_PATTERNS: List[str] = [
    r"swagger\.json$", r"openapi\.ya?ml$", r"api-docs",
    r"openapi\.json$",
]
README_API_PATTERN: re.Pattern = re.compile(
    r"(https?://[^\s]*api[^\s]*|/api/v?\d|endpoint|REST\s*API|GraphQL)",
    re.IGNORECASE,
)

# Minimum stars to consider a repo worthwhile
MIN_STARS_DEFAULT = 5

# Concurrency & rate-limiting
MAX_CONCURRENT_REQUESTS = 5
REQUEST_DELAY = 0.8  # seconds between requests to same mirror

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
for _d in (WAREHOUSE_ROOT, METADATA_DIR, LOG_DIR, CODE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
for _sd in STRUCTURED_SUBDIRS.values():
    _sd.mkdir(parents=True, exist_ok=True)
DATA_UNSTRUCTURED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("DeepSeek_DataV4")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class RepoMeta:
    """Canonical metadata record for one ingested repository."""

    repo_name: str
    repo_url: str
    mirror_name: str
    description: str = ""
    stars: int = 0
    language: str = ""
    tags: List[str] = field(default_factory=list)
    data_files: List[str] = field(default_factory=list)
    data_types: List[str] = field(default_factory=list)
    api_docs_found: bool = False
    quality_score: float = 0.0
    structure_summary: str = ""
    local_path: str = ""
    metadata_path: str = ""
    ingested_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RepoMeta":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Config Management
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "search_keywords": ["api", "crawler", "scraper", "dataset", "data-pipeline"],
    "min_stars": MIN_STARS_DEFAULT,
    "max_repos_per_keyword": 20,
    "blacklist_repos": [],
    "preferred_mirrors": ["kgithub"],
    "warehouse_root": str(WAREHOUSE_ROOT),
}


def load_config() -> Dict[str, Any]:
    """Load configuration from ``config.json``, creating a default if absent."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            # merge with defaults for any missing keys
            merged = {**DEFAULT_CONFIG, **cfg}
            logger.info("Config loaded from %s", CONFIG_PATH)
            return merged
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Config file corrupt (%s), regenerating default.", exc)
    # create default
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(DEFAULT_CONFIG, fh, indent=2, ensure_ascii=False)
    logger.info("Default config written to %s", CONFIG_PATH)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any]) -> None:
    """Persist configuration to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def random_ua() -> str:
    """Return a randomly selected User-Agent string."""
    return random.choice(USER_AGENTS)


def slugify(name: str) -> str:
    """Convert a repository full name to a safe filesystem slug."""
    return re.sub(r"[^\w\-.]", "_", name.strip().lower().replace("/", "_"))


def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def file_checksum(path: Path) -> str:
    """SHA-256 hex digest of a file, used for dedup."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ---------------------------------------------------------------------------
# Stage 1 — Ingestion
# ---------------------------------------------------------------------------

class Ingester:
    """Asynchronous search-and-fetch engine targeting GitHub mirrors."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._seen: Set[str] = set()
        self._results: List[RepoMeta] = []

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, force_close=True)
            timeout = aiohttp.ClientTimeout(total=20, connect=8)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"Accept": "text/html,application/json",
                         "Accept-Language": "en-US,en;q=0.9"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def run(self) -> List[RepoMeta]:
        """Execute the full ingestion pipeline."""
        logger.info("=" * 60)
        logger.info("STAGE 1 — Ingestion started")
        keywords = self._config.get("search_keywords", [])
        min_stars = self._config.get("min_stars", MIN_STARS_DEFAULT)
        max_per_kw = self._config.get("max_repos_per_keyword", 20)
        blacklist = set(self._config.get("blacklist_repos", []))

        tasks = []
        for kw in keywords:
            for mirror in MIRRORS:
                if mirror["name"] not in self._config.get("preferred_mirrors", []):
                    continue
                tasks.append(self._search_mirror(kw, mirror))

        # Also attempt GitHub API search for broader coverage
        tasks.append(self._search_github_api(keywords, min_stars, max_per_kw))

        mirror_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result_set in mirror_results:
            if isinstance(result_set, Exception):
                logger.error("Ingestion sub-task failed: %s", result_set)
                continue
            for repo in result_set:
                if repo.repo_url in blacklist or repo.repo_url in self._seen:
                    continue
                if repo.stars < min_stars:
                    continue
                # Only keep repos that have potential data value
                if not repo.data_files and not repo.api_docs_found:
                    continue
                self._seen.add(repo.repo_url)
                self._results.append(repo)

        # Deduplicate by URL
        unique: Dict[str, RepoMeta] = {}
        for r in self._results:
            if r.repo_url not in unique:
                unique[r.repo_url] = r
        self._results = list(unique.values())

        # Always add direct seed repos (guaranteed quality sources)
        self._results.extend(self._seed_known_repos(blacklist))

        logger.info(
            "STAGE 1 — Found %d unique candidate repos across %d keywords.",
            len(self._results),
            len(keywords),
        )
        return self._results

    @staticmethod
    def _seed_known_repos(blacklist: Set[str]) -> List[RepoMeta]:
        """Direct-seed known high-quality open-data repos — no search required.

        These are cloned directly from GitHub; they serve as a guaranteed
        fallback when mirror search / API returns nothing.
        """
        seeds: List[Dict[str, Any]] = [
            {
                "repo_name": "awesomedata/awesome-public-datasets",
                "repo_url": "https://github.com/awesomedata/awesome-public-datasets",
                "description": "A curated list of awesome open public datasets",
                "stars": 63000, "language": "Markdown",
                "tags": ["dataset", "awesome-list", "data-catalog"],
            },
            {
                "repo_name": "datasets/awesome-data",
                "repo_url": "https://github.com/datasets/awesome-data",
                "description": "Awesome data — curated list of datasets",
                "stars": 6200, "language": "Python",
                "tags": ["dataset", "awesome-list"],
            },
            {
                "repo_name": "public-apis/public-apis",
                "repo_url": "https://github.com/public-apis/public-apis",
                "description": "A collective list of free APIs",
                "stars": 330000, "language": "Python",
                "tags": ["api", "awesome-list", "open-data"],
            },
            {
                "repo_name": "jivoi/awesome-osint",
                "repo_url": "https://github.com/jivoi/awesome-osint",
                "description": "Awesome list of OSINT tools and resources",
                "stars": 21000, "language": "Markdown",
                "tags": ["osint", "data", "awesome-list"],
            },
            {
                "repo_name": "fivethirtyeight/data",
                "repo_url": "https://github.com/fivethirtyeight/data",
                "description": "Data and code behind FiveThirtyEight articles",
                "stars": 16900, "language": "Jupyter Notebook",
                "tags": ["dataset", "csv", "journalism", "statistics"],
            },
        ]

        results: List[RepoMeta] = []
        for s in seeds:
            if s["repo_url"] in blacklist:
                continue
            results.append(RepoMeta(
                repo_name=s["repo_name"],
                repo_url=s["repo_url"],
                mirror_name="direct_seed",
                description=s.get("description", ""),
                stars=s.get("stars", 0),
                language=s.get("language", ""),
                tags=s.get("tags", []),
                ingested_at=now_iso(),
            ))
        return results

    async def _search_mirror(self, keyword: str, mirror: Dict[str, str]) -> List[RepoMeta]:
        """Search a single mirror site for a keyword."""
        results: List[RepoMeta] = []
        search_url = f"{mirror['search_url']}?q={quote_plus(keyword)}&type=repositories"
        session = await self._get_session()

        text: Optional[str] = None
        try:
            async with self._semaphore:
                await asyncio.sleep(REQUEST_DELAY + random.uniform(0.1, 0.6))
                async with session.get(
                    search_url,
                    headers={"User-Agent": random_ua()},
                    allow_redirects=True,
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        logger.debug("Mirror %s returned %d for kw='%s'",
                                     mirror["name"], resp.status, keyword)
        except (aiohttp.ClientError, asyncio.TimeoutError, asyncio.TimeoutError) as exc:
            logger.debug("Mirror %s unreachable for kw='%s': %s", mirror["name"], keyword, exc)
            return results

        if text is None:
            return results

        soup = BeautifulSoup(text, "lxml")
        repo_links = soup.select("a[href*='/']")  # heuristic for repo links

        count = 0
        max_per = self._config.get("max_repos_per_keyword", 20)
        for link in repo_links:
            href = link.get("href", "")
            if not href or href in ("/", "/search"):
                continue
            # Filter to paths that look like owner/repo
            parts = [p for p in href.strip("/").split("/") if p]
            if len(parts) < 2:
                continue
            if any(p in ("search", "login", "explore", "notifications") for p in parts):
                continue

            owner, repo_name = parts[0], parts[1]
            repo_url = f"{mirror['repo_prefix']}/{owner}/{repo_name}"
            if repo_url in self._seen:
                continue

            meta = RepoMeta(
                repo_name=f"{owner}/{repo_name}",
                repo_url=repo_url,
                mirror_name=mirror["name"],
                description=link.get("title", ""),
                ingested_at=now_iso(),
            )
            results.append(meta)
            count += 1
            if count >= max_per:
                break

        logger.debug("Mirror '%s' / kw='%s' → %d repos", mirror["name"], keyword, count)
        return results

    async def _search_github_api(
        self, keywords: List[str], min_stars: int, max_per_kw: int
    ) -> List[RepoMeta]:
        """Use the official GitHub Search REST API as a fallback source."""
        results: List[RepoMeta] = []
        session = await self._get_session()

        for kw in keywords:
            params = {
                "q": f"{kw} stars:>={min_stars}",
                "sort": "stars",
                "order": "desc",
                "per_page": min(max_per_kw, 30),
            }
            data: Optional[Dict[str, Any]] = None
            try:
                async with self._semaphore:
                    await asyncio.sleep(REQUEST_DELAY + random.uniform(0.2, 0.8))
                    async with session.get(
                        GITHUB_API_SEARCH,
                        params=params,
                        headers={
                            "User-Agent": random_ua(),
                            "Accept": "application/vnd.github.v3+json",
                        },
                    ) as resp:
                        if resp.status == 403:
                            logger.warning("GitHub API rate limit hit on kw='%s'", kw)
                            return results
                        if resp.status != 200:
                            logger.debug("GitHub API returned %d for kw='%s'",
                                         resp.status, kw)
                            continue
                        data = await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
                logger.debug("GitHub API failed for kw='%s': %s", kw, exc)
                continue

            if data is None:
                continue

            for item in data.get("items", []):
                repo_url = item.get("html_url", "")
                if not repo_url:
                    continue
                meta = RepoMeta(
                    repo_name=item.get("full_name", ""),
                    repo_url=repo_url,
                    mirror_name="github_api",
                    description=item.get("description", "") or "",
                    stars=item.get("stargazers_count", 0),
                    language=item.get("language", "") or "",
                    tags=item.get("topics", []),
                    ingested_at=now_iso(),
                )
                results.append(meta)

        return results


# ---------------------------------------------------------------------------
# Stage 2 — Validation & Quality Scoring
# ---------------------------------------------------------------------------

class Validator:
    """Assess repository quality by inspecting files, code, and documentation."""

    def __init__(self, warehouse_root: Path) -> None:
        self._root = warehouse_root

    def validate(self, repo_meta: RepoMeta, project_dir: Path) -> RepoMeta:
        """Run all checks against a downloaded repo directory and update scores."""
        score = 0.0

        # 1. Check for structured data files
        data_files = self._find_data_files(project_dir)
        repo_meta.data_files = [str(p.relative_to(project_dir)) for p in data_files]
        data_types = list({p.suffix for p in data_files if p.suffix})
        repo_meta.data_types = data_types
        if data_files:
            score += min(len(data_files) * 1.5, 15)  # cap at 15

        # 2. Check for API documentation
        api_docs = self._find_api_docs(project_dir)
        repo_meta.api_docs_found = api_docs
        if api_docs:
            score += 10

        # 3. Check README for API links
        readme_path = self._find_readme(project_dir)
        if readme_path:
            try:
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                if README_API_PATTERN.search(content):
                    score += 5
            except OSError:
                pass

        # 4. Validate Python / JSON / CSV files for structural correctness
        valid_count = 0
        for f in project_dir.rglob("*.py"):
            if self._validate_python(f):
                valid_count += 1
        for f in project_dir.rglob("*.json"):
            if self._validate_json(f):
                valid_count += 1
        score += min(valid_count * 0.5, 10)

        # 5. Check if project has a dataset sample
        for pat in ["sample*", "example*", "test*", "demo*", "data*"]:
            if list(project_dir.glob(pat)):
                score += 3
                break

        # 6. Bonus for README existence and length
        if readme_path:
            size = readme_path.stat().st_size
            if size > 500:
                score += 3
            if size > 2000:
                score += 2

        repo_meta.quality_score = round(score, 1)
        repo_meta.structure_summary = self._build_summary(repo_meta, project_dir)
        return repo_meta

    @staticmethod
    def _find_data_files(root: Path) -> List[Path]:
        """Recursively locate structured data files under *root*."""
        found: List[Path] = []
        for pat in DATA_FILE_PATTERNS:
            try:
                found.extend(root.rglob(f"*{pat.replace(r'$', '').lstrip(r'\\')}"
                               if pat.endswith("$") else f"*{pat}"))
            except OSError:
                continue
        # deduplicate
        return list({p.resolve() for p in found})

    @staticmethod
    def _find_api_docs(root: Path) -> bool:
        for pat in API_DOC_PATTERNS:
            try:
                if list(root.rglob(pat)):
                    return True
            except OSError:
                continue
        return False

    @staticmethod
    def _find_readme(root: Path) -> Optional[Path]:
        for name in ("README.md", "README.rst", "README.txt", "README"):
            candidate = root / name
            if candidate.exists():
                return candidate
        # case-insensitive fallback
        for p in root.iterdir():
            if p.is_file() and p.name.lower().startswith("readme"):
                return p
        return None

    @staticmethod
    def _validate_python(path: Path) -> bool:
        """Check a Python file for syntax errors via ast.parse."""
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            ast.parse(source)
            return True
        except (SyntaxError, OSError, MemoryError):
            return False

    @staticmethod
    def _validate_json(path: Path) -> bool:
        """Check if a file is valid JSON."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                json.load(f)
            return True
        except (json.JSONDecodeError, OSError):
            return False

    @staticmethod
    def _build_summary(meta: RepoMeta, project_dir: Path) -> str:
        """Produce a human-readable structure summary."""
        parts: List[str] = []
        parts.append(f"Language: {meta.language or 'unknown'}")
        parts.append(f"Stars: {meta.stars}")
        if meta.data_types:
            parts.append(f"Data types: {', '.join(meta.data_types)}")
        if meta.data_files:
            parts.append(f"Data files ({len(meta.data_files)}): {', '.join(meta.data_files[:5])}")
        if meta.api_docs_found:
            parts.append("API docs: yes")
        parts.append(f"Quality score: {meta.quality_score}/50")
        # file count
        try:
            total = sum(1 for _ in project_dir.rglob("*") if _.is_file())
            parts.append(f"Total files: {total}")
        except OSError:
            pass
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Stage 3 — Storage
# ---------------------------------------------------------------------------

class StorageEngine:
    """Persist validated repos and their data to the warehouse directory."""

    def __init__(self, warehouse_root: Path) -> None:
        self._root = warehouse_root
        self._metadata_dir = warehouse_root / "metadata"
        self._code_dir = warehouse_root / "code"
        for d in (self._metadata_dir, self._code_dir):
            d.mkdir(parents=True, exist_ok=True)

    def store(self, repo_meta: RepoMeta, source_dir: Path) -> RepoMeta:
        """Copy/classify files from *source_dir* into the warehouse and write metadata."""
        slug = slugify(repo_meta.repo_name)
        dest_code = self._code_dir / slug
        meta_path = self._metadata_dir / f"{slug}.json"

        # --- Idempotency check ---
        if meta_path.exists():
            existing = self._load_meta(meta_path)
            if existing and existing.quality_score >= repo_meta.quality_score:
                logger.info("Skipping '%s' — already stored (score %s >= %s).",
                            repo_meta.repo_name, existing.quality_score, repo_meta.quality_score)
                return existing
            logger.info("Updating '%s' — new score %s > old %s.",
                        repo_meta.repo_name, repo_meta.quality_score,
                        existing.quality_score if existing else "N/A")

        # --- Copy project code ---
        if dest_code.exists():
            shutil.rmtree(dest_code, ignore_errors=True)
        try:
            shutil.copytree(source_dir, dest_code, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "node_modules", ".venv", "venv", ".env", "*.pyc"))
        except OSError as exc:
            logger.error("Failed to copy '%s' → '%s': %s", source_dir, dest_code, exc)

        # --- Copy structured data files into classified subdirectories ---
        for data_file_rel in repo_meta.data_files:
            src = source_dir / data_file_rel
            if not src.exists():
                continue
            suffix = src.suffix.lower()
            target_dir = STRUCTURED_SUBDIRS.get(suffix, DATA_UNSTRUCTURED_DIR)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / f"{slug}_{src.name}"
            try:
                shutil.copy2(src, target_file)
            except OSError as exc:
                logger.warning("Failed to copy data file '%s': %s", src, exc)

        # --- Write / update metadata ---
        repo_meta.local_path = str(dest_code)
        repo_meta.metadata_path = str(meta_path)
        repo_meta.updated_at = now_iso()
        if not repo_meta.ingested_at:
            repo_meta.ingested_at = now_iso()

        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(repo_meta.to_dict(), fh, indent=2, ensure_ascii=False)

        logger.info("Stored '%s' → %s (score=%.1f)", repo_meta.repo_name, dest_code, repo_meta.quality_score)
        return repo_meta

    @staticmethod
    def _load_meta(path: Path) -> Optional[RepoMeta]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return RepoMeta.from_dict(json.load(f))
        except (json.JSONDecodeError, OSError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Stage 4 — Interactive Query Interface
# ---------------------------------------------------------------------------

class QueryInterface:
    """In-memory index over warehouse metadata with natural-language search."""

    def __init__(self, metadata_dir: Path) -> None:
        self._metadata_dir = metadata_dir
        self._index: List[RepoMeta] = []
        self._keyword_map: Dict[str, List[int]] = {}  # token → list of index positions
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Scan all metadata JSON files and build an in-memory inverted index."""
        self._index.clear()
        self._keyword_map.clear()
        if not self._metadata_dir.exists():
            return
        for mf in sorted(self._metadata_dir.glob("*.json")):
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = RepoMeta.from_dict(data)
                idx = len(self._index)
                self._index.append(meta)

                # Build search tokens
                tokens: Set[str] = set()
                tokens.update(re.split(r"[\s\-_/.,]+", meta.repo_name.lower()))
                tokens.update(t.lower() for t in meta.tags)
                tokens.update(t.lower() for t in meta.data_types)
                for word in re.split(r"\W+", meta.description.lower()):
                    if len(word) > 2:
                        tokens.add(word)
                for word in re.split(r"\W+", meta.structure_summary.lower()):
                    if len(word) > 2:
                        tokens.add(word)
                for token in tokens:
                    token = token.strip()
                    if not token:
                        continue
                    self._keyword_map.setdefault(token, []).append(idx)
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                logger.debug("Skipping corrupt metadata '%s': %s", mf.name, exc)

        logger.info("Query index rebuilt — %d repos, %d unique tokens.",
                    len(self._index), len(self._keyword_map))

    def search(self, query: str, top_k: int = 10) -> List[RepoMeta]:
        """Search the index using keyword overlap scoring.

        Args:
            query: Natural-language query string.
            top_k: Maximum number of results to return.

        Returns:
            Ranked list of ``RepoMeta`` matching the query.
        """
        if not self._index:
            return []

        query_tokens = set(re.split(r"\W+", query.lower()))
        query_tokens = {t for t in query_tokens if len(t) > 1}

        # Special intent detection
        intent_types: Set[str] = set()
        if any(w in query.lower() for w in ("csv", "comma-separated", "tabular")):
            intent_types.add(".csv")
        if any(w in query.lower() for w in ("json",)):
            intent_types.add(".json")
        if any(w in query.lower() for w in ("xml",)):
            intent_types.add(".xml")
        if any(w in query.lower() for w in ("database", "db", "sqlite")):
            intent_types.add(".db")
        if any(w in query.lower() for w in ("api", "rest", "endpoint", "swagger", "openapi")):
            intent_types.add("__api__")

        scores: List[Tuple[int, float]] = []
        for i, meta in enumerate(self._index):
            score = 0.0
            for token in query_tokens:
                if token in self._keyword_map and i in self._keyword_map[token]:
                    score += 1.0
                # Fuzzy: partial substring match on repo name
                if token in meta.repo_name.lower():
                    score += 1.5
                if token in meta.description.lower():
                    score += 0.5

            # Intent boost
            if intent_types & set(meta.data_types):
                score += 2.0
            if "__api__" in intent_types and meta.api_docs_found:
                score += 2.0

            # Quality bonus so higher-quality repos surface first
            score += meta.quality_score * 0.02

            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [self._index[i] for i, _ in scores[:top_k]]

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics about the warehouse."""
        total_files = 0
        all_types: Set[str] = set()
        for meta in self._index:
            total_files += len(meta.data_files)
            all_types.update(meta.data_types)
        return {
            "total_repos": len(self._index),
            "total_data_files": total_files,
            "data_types": sorted(all_types),
            "api_docs_count": sum(1 for m in self._index if m.api_docs_found),
            "avg_quality_score": (
                round(sum(m.quality_score for m in self._index) / len(self._index), 1)
                if self._index else 0
            ),
        }


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

class Pipeline:
    """Top-level orchestrator that wires together Ingestion, Validation, Storage."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._warehouse_root = Path(config.get("warehouse_root", WAREHOUSE_ROOT))
        self._ingester = Ingester(config)
        self._validator = Validator(self._warehouse_root)
        self._storage = StorageEngine(self._warehouse_root)

    async def run(self) -> List[RepoMeta]:
        """Execute the full pipeline end-to-end."""
        stored: List[RepoMeta] = []

        # --- Stage 1 ---
        try:
            candidates = await self._ingester.run()
        except Exception as exc:
            logger.error("STAGE 1 fatal: %s\n%s", exc, traceback.format_exc())
            return stored
        finally:
            await self._ingester.close()

        if not candidates:
            logger.warning("No candidates found. Check network / config keywords.")
            return stored

        # --- Stage 2 & 3 ---
        logger.info("STAGE 2 & 3 — Validating %d candidates...", len(candidates))
        for i, repo in enumerate(candidates, 1):
            try:
                logger.info("[%d/%d] Processing '%s' ...", i, len(candidates), repo.repo_name)
                project_dir = await self._download_repo(repo)

                if project_dir is None:
                    logger.info("Skipping '%s' — download failed.", repo.repo_name)
                    continue

                # Validate
                repo = self._validator.validate(repo, project_dir)

                # Store only if above threshold
                if repo.quality_score >= 5.0:
                    repo = self._storage.store(repo, project_dir)
                    stored.append(repo)
                else:
                    logger.info("Discarding '%s' — quality too low (%.1f).", repo.repo_name, repo.quality_score)

                # Cleanup temp download
                self._rmtree_safe(project_dir)

            except Exception as exc:
                logger.error("Pipeline error on '%s': %s\n%s",
                             repo.repo_name, exc, traceback.format_exc())
                continue

        logger.info("PIPELINE COMPLETE — %d repos stored.", len(stored))
        return stored

    async def _download_repo(self, repo: RepoMeta) -> Optional[Path]:
        """Attempt to clone a repo into a temporary directory.

        Tries multiple strategies in order:
        1. git clone from GitHub directly
        2. git clone via kgithub mirror
        3. HTTP archive download from kgithub mirror (main / master branch)

        Returns the local path, or ``None`` on failure.
        """
        slug = slugify(repo.repo_name)
        temp_dir = self._warehouse_root / "tmp" / slug
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Idempotency: if already downloaded with real content, reuse.
        # We exclude stale dirs that only contain a leftover .git folder.
        entries = list(temp_dir.iterdir())
        non_git = [e for e in entries if e.name != ".git"]
        if non_git:
            logger.info("Reusing existing temp dir '%s' (%d entries)", temp_dir, len(non_git))
            return temp_dir
        if entries:
            # Only .git remains — a stale leftover from failed cleanup; remove it
            logger.debug("Removing stale temp dir '%s'", temp_dir)
            Pipeline._rmtree_safe(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

        # Derive owner/repo from URL for mirror construction
        # e.g. "https://github.com/owner/repo" → ("owner", "repo")
        parts = repo.repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            logger.warning("Cannot parse repo URL: %s", repo.repo_url)
            return None
        owner, repo_name = parts[-2], parts[-1]

        # --- Strategy 1: git clone from GitHub directly ---
        github_url = f"https://github.com/{owner}/{repo_name}.git"
        if await self._try_git_clone(github_url, temp_dir):
            return temp_dir

        # --- Strategy 2: git clone via kgithub mirror ---
        mirror_url = f"https://kgithub.com/{owner}/{repo_name}.git"
        if await self._try_git_clone(mirror_url, temp_dir):
            return temp_dir

        # --- Strategy 3: git clone via gitclone mirror ---
        mirror_url2 = f"https://gitclone.com/github.com/{owner}/{repo_name}.git"
        if await self._try_git_clone(mirror_url2, temp_dir):
            return temp_dir

        # --- Strategy 4: HTTP archive download from kgithub ---
        for branch in ("main", "master"):
            archive_url = f"https://kgithub.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
            if await self._download_archive(archive_url, temp_dir):
                return temp_dir

        # --- Strategy 5: HTTP from gitclone ---
        for branch in ("main", "master"):
            archive_url = f"https://gitclone.com/github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
            if await self._download_archive(archive_url, temp_dir):
                return temp_dir

        logger.info("All download strategies failed for '%s'", repo.repo_name)
        self._rmtree_safe(temp_dir)
        return None

    async def _try_git_clone(self, url: str, dest: Path) -> bool:
        """Attempt a shallow git clone; return True on success with real files."""
        cmd = ["git", "clone", "--depth", "1", "--quiet", url, str(dest)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
                # Verify the clone actually produced files (not just .git)
                entries = [e for e in dest.iterdir() if e.name != ".git"]
                if entries:
                    logger.info("git clone succeeded: %s (%d files)", url, len(entries))
                    return True
                logger.debug("git clone produced empty worktree: %s", url)
            else:
                logger.debug("git clone failed (rc=%d): %s", proc.returncode, url)
        except (asyncio.TimeoutError, OSError) as exc:
            logger.debug("git clone exception for '%s': %s", url, exc)
        return False

    async def _download_archive(self, archive_url: str, dest: Path) -> bool:
        """Download and unpack a ZIP archive from *archive_url*.

        Returns True on success.  Uses a short-lived session.
        """
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        connector = aiohttp.TCPConnector(limit=1, force_close=True)
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"Accept": "application/zip,*/*",
                         "Accept-Language": "en-US,en;q=0.9"},
            ) as session:
                async with session.get(
                    archive_url,
                    headers={"User-Agent": random_ua()},
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        logger.debug("Archive not found (%d): %s", resp.status, archive_url)
                        return False
                    zip_path = dest / "archive.zip"
                    with open(zip_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            f.write(chunk)
                # Unpack
                shutil.unpack_archive(str(zip_path), extract_dir=str(dest))
                zip_path.unlink(missing_ok=True)
                # The unpacked contents may be nested one level; flatten
                subdirs = [d for d in dest.iterdir() if d.is_dir()]
                if len(subdirs) == 1:
                    inner = subdirs[0]
                    for item in inner.iterdir():
                        shutil.move(str(item), str(dest / item.name))
                    inner.rmdir()
                logger.info("Archive download succeeded: %s", archive_url)
                return True
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, shutil.ReadError) as exc:
            logger.debug("Archive download failed: %s — %s", archive_url, exc)
            return False

    @staticmethod
    def _rmtree_safe(path: Path) -> None:
        """Remove a directory tree, handling Windows read-only git files."""
        if not path.exists():
            return

        def _on_error(func, subpath, exc_info):
            """Clear read-only flag then retry."""
            os.chmod(subpath, 0o777)
            try:
                func(subpath)
            except OSError:
                pass

        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(str(path), onexc=_on_error)
            else:
                shutil.rmtree(str(path), onerror=_on_error)
        except OSError:
            # Last resort: shell out to force-delete on Windows
            if platform.system() == "Windows":
                try:
                    subprocess.run(
                        ["cmd", "/c", "rd", "/s", "/q", str(path)],
                        timeout=15, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass


# ---------------------------------------------------------------------------
# Interactive Console
# ---------------------------------------------------------------------------

def interactive_loop(metadata_dir: Path) -> None:
    """Run the Stage 4 interactive query console."""
    qif = QueryInterface(metadata_dir)

    print(f"\n{_C.CYAN}{'=' * 60}{_S.RESET_ALL}")
    print(f"{_C.GREEN}  DeepSeek_DataV4 — Interactive Query Console{_S.RESET_ALL}")
    print(f"{_C.CYAN}{'=' * 60}{_S.RESET_ALL}")
    print(f"  Warehouse : {WAREHOUSE_ROOT}")
    stats = qif.stats()
    print(f"  Repos     : {stats['total_repos']}")
    print(f"  Data files: {stats['total_data_files']}")
    print(f"  Types     : {', '.join(stats['data_types']) or 'none'}")
    print(f"{_C.CYAN}{'-' * 60}{_S.RESET_ALL}")
    print(f"  Commands:")
    print(f"    /search <query>   — natural-language search")
    print(f"    /stats            — warehouse statistics")
    print(f"    /recent [n]       — show n most recently ingested repos")
    print(f"    /best [n]         — top-n by quality score")
    print(f"    /rebuild          — rebuild search index")
    print(f"    /help             — this message")
    print(f"    /quit             — exit")
    print(f"{_C.CYAN}{'=' * 60}{_S.RESET_ALL}\n")

    while True:
        try:
            raw = input(f"{_C.YELLOW}DS4>{_S.RESET_ALL} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/quit":
            print("Goodbye.")
            break
        elif cmd == "/help":
            print("Commands: /search, /stats, /recent, /best, /rebuild, /quit")
        elif cmd == "/rebuild":
            qif._rebuild_index()
            print(f"Index rebuilt. {qif.stats()['total_repos']} repos indexed.")
        elif cmd == "/stats":
            s = qif.stats()
            print(f"  Total repos      : {s['total_repos']}")
            print(f"  Total data files : {s['total_data_files']}")
            print(f"  Data types       : {', '.join(s['data_types']) or 'none'}")
            print(f"  With API docs    : {s['api_docs_count']}")
            print(f"  Avg quality score: {s['avg_quality_score']}")
        elif cmd == "/recent":
            n = int(arg) if arg.isdigit() else 10
            recent = sorted(
                qif._index,
                key=lambda m: m.ingested_at or "",
                reverse=True,
            )[:n]
            _print_results(recent)
        elif cmd == "/best":
            n = int(arg) if arg.isdigit() else 10
            best = sorted(qif._index, key=lambda m: m.quality_score, reverse=True)[:n]
            _print_results(best)
        elif cmd == "/search":
            if not arg:
                print("Usage: /search <natural language query>")
                continue
            results = qif.search(arg)
            if not results:
                print(f"  No results for '{arg}'. Try different keywords.")
            else:
                _print_results(results)
        else:
            # Treat unknown commands as implicit search
            results = qif.search(raw)
            if results:
                _print_results(results)
            else:
                print(f"  Unknown command '{cmd}'. Type /help for options.")


def _print_results(results: List[RepoMeta]) -> None:
    """Pretty-print a list of RepoMeta results."""
    for i, meta in enumerate(results, 1):
        score_color = _C.GREEN if meta.quality_score >= 30 else (
            _C.YELLOW if meta.quality_score >= 15 else _C.RED)
        print(f"\n  {_C.CYAN}[{i}]{_S.RESET_ALL} {_C.WHITE}{meta.repo_name}{_S.RESET_ALL}")
        print(f"      Score: {score_color}{meta.quality_score:.1f}{_S.RESET_ALL}  "
              f"Stars: {meta.stars}  Lang: {meta.language or '?'}")
        if meta.description:
            desc = meta.description[:120]
            print(f"      Desc: {desc}")
        if meta.data_types:
            print(f"      Types: {', '.join(meta.data_types)}")
        if meta.api_docs_found:
            print(f"      {_C.GREEN}API docs available{_S.RESET_ALL}")
        print(f"      Path: {meta.local_path or 'not stored'}")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

async def async_main() -> None:
    """Async entry point: run pipeline then drop into interactive console."""
    config = load_config()
    pipeline = Pipeline(config)

    logger.info("Starting DeepSeek_DataV4 pipeline...")
    try:
        stored = await asyncio.wait_for(pipeline.run(), timeout=600)
        logger.info("Pipeline finished. %d repos stored.", len(stored))
    except asyncio.TimeoutError:
        logger.warning("Pipeline timed out after 5 min — proceeding with partial results.")
        stored = pipeline._ingester._results  # whatever was collected so far
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)

    # Always offer the interactive console after pipeline run
    interactive_loop(METADATA_DIR)


def main() -> None:
    """Synchronous entry point for the script."""
    print(f"{_C.CYAN}")
    print(r"  ____                _     ____       _         ")
    print(r" |  _ \  ___  ___ ___| | __/ ___|  ___| | _____  ")
    print(r" | | | |/ _ \/ _ \/ _ \ |/ /\___ \ / _ \ |/ / _ \ ")
    print(r" | |_| |  __/  __/  __/   <  ___) |  __/   <  __/ ")
    print(r" |____/ \___|\___|\___|_|\_\|____/ \___|_|\_\___| ")
    print(r"     ____  __      ____   _  _   _____            ")
    print(r"    |  _ \|  \/  ||___ \ | || | |___ / _   _      ")
    print(r"    | | | | |\/| |  __) || || |_  |_ \| | | |     ")
    print(r"    | |_| | |  | | / __/ |__   _|___) | |_| |     ")
    print(r"    |____/|_|  |_||_____|   |_| |____/ \__, |     ")
    print(r"                                        |___/     ")
    print(f"{_S.RESET_ALL}")
    print(f"  Personal Offline Data Warehouse Builder")
    print(f"  Drive   root: {DRIVE_ROOT}")
    print(f"  Warehouse   : {WAREHOUSE_ROOT}")
    print(f"  Config file : {CONFIG_PATH}")
    print(f"  Log file    : {LOG_FILE}")
    print()

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)
    except Exception as exc:
        logger.critical("Unhandled top-level exception: %s\n%s", exc, traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
