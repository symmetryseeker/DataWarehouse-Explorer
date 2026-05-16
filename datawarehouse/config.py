"""
Configuration management with environment variable support.

All sensitive values (API tokens, passwords) MUST be set via environment
variables, NEVER hardcoded in config.json or source code.

Environment Variables:
    GITHUB_TOKEN         GitHub personal access token (for higher API rate limit)
    DW_WAREHOUSE_ROOT    Override warehouse data directory
    DW_DATABASE_URL      SQLAlchemy database URL (default: sqlite:///warehouse.db)
    DW_AUTH_USER         Web UI Basic Auth username
    DW_AUTH_PASS_HASH    SHA-256 hex of Web UI password
    DW_PUBLIC_MODE       Set to "1" to disable Web UI auth
    DW_LLM_PROVIDER      Override LLM provider in llm_config.yaml
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DeepSeek_DataV4")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_STARS_DEFAULT = 5
MAX_CONCURRENT_REQUESTS = 5
REQUEST_DELAY = 0.8

GITHUB_API_SEARCH = "https://api.github.com/search/repositories"

MIRRORS: List[Dict[str, str]] = [
    {"name": "kgithub", "search_url": "https://kgithub.com/search",
     "repo_prefix": "https://kgithub.com"},
    {"name": "gitclone", "search_url": "https://gitclone.com/search",
     "repo_prefix": "https://gitclone.com"},
]

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "search_keywords": ["api", "crawler", "scraper", "dataset", "data-pipeline"],
    "min_stars": 5,
    "max_repos_per_keyword": 20,
    "blacklist_repos": [],
    "preferred_mirrors": ["kgithub"],
    "warehouse_root": "",
    "database_url": "sqlite:///warehouse.db",
    "storage_mode": "content_addressed",
    "commit_recency_weight": True,
}

# ---------------------------------------------------------------------------
# Warehouse root — configurable, NOT hardcoded to My Passport
# ---------------------------------------------------------------------------

def resolve_warehouse_root(config: Optional[Dict[str, Any]] = None) -> Path:
    """Resolve the warehouse data directory.

    Priority:
    1. ``DW_WAREHOUSE_ROOT`` environment variable
    2. ``warehouse_root`` key in config dict / config.json
    3. Auto-detect My Passport external drive (if plugged in)
    4. ``./DataWarehouse`` relative to project root

    No longer hardcoded to My Passport — works on any machine.
    """
    # 1. Environment variable (highest priority)
    env_root = os.environ.get("DW_WAREHOUSE_ROOT")
    if env_root:
        wh = Path(env_root)
        wh.mkdir(parents=True, exist_ok=True)
        return wh

    # 2. Config file
    if config and config.get("warehouse_root"):
        wh = Path(config["warehouse_root"])
        wh.mkdir(parents=True, exist_ok=True)
        return wh

    # 3. Auto-detect external drive (backward-compatible convenience)
    detected = _detect_external_drive()
    if detected:
        wh = detected / "DataWarehouse"
        wh.mkdir(parents=True, exist_ok=True)
        return wh

    # 4. Local fallback
    project_root = Path(__file__).resolve().parent.parent
    wh = project_root / "DataWarehouse"
    wh.mkdir(parents=True, exist_ok=True)
    logger.info("Warehouse root: %s (local fallback)", wh)
    return wh


def _detect_external_drive() -> Optional[Path]:
    """Auto-detect common external drive mount points."""
    system = platform.system()
    drive_label = "My Passport"

    if system == "Windows":
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{letter}:\\")
            if not root.exists():
                continue
            if (root / drive_label).is_dir():
                return root / drive_label
            try:
                result = subprocess.run(
                    ["cmd", "/c", f"vol {letter}:"],
                    capture_output=True, text=True, timeout=5,
                    encoding="utf-8", errors="ignore",
                )
                if result.returncode == 0 and result.stdout \
                        and drive_label.lower() in result.stdout.lower():
                    return root
            except (OSError, subprocess.TimeoutExpired):
                pass
    elif system == "Darwin":
        for label in (drive_label, "Untitled", "External"):
            candidate = Path(f"/Volumes/{label}")
            if candidate.is_dir():
                return candidate
    else:
        for base in (f"/media/{os.environ.get('USER', '')}/{drive_label}",
                     f"/media/{drive_label}", f"/mnt/{drive_label}"):
            candidate = Path(base)
            if candidate.is_dir():
                return candidate

    return None


# ---------------------------------------------------------------------------
# GitHub Token (NEVER from config file — env var ONLY)
# ---------------------------------------------------------------------------

def get_github_token() -> Optional[str]:
    """Get GitHub personal access token from environment variable.

    NEVER read from config.json. Raise a clear message if not set.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.debug(
            "GITHUB_TOKEN not set — GitHub API rate limit is 60 req/hour. "
            "Set 'export GITHUB_TOKEN=ghp_xxx' to increase to 5000 req/hour."
        )
    return token


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON, merging with env var overrides."""
    cfg = dict(DEFAULT_CONFIG)

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                file_cfg = json.load(fh)
            cfg.update(file_cfg)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Config file corrupt (%s), using defaults.", exc)
    else:
        # Write default config (without sensitive values)
        _safe_config = {k: v for k, v in DEFAULT_CONFIG.items()
                        if not any(s in k.lower() for s in ("token", "key", "secret", "password"))}
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(_safe_config, fh, indent=2, ensure_ascii=False)
        logger.info("Default config written to %s", config_path)

    # Env var overrides (highest priority)
    if os.environ.get("DW_WAREHOUSE_ROOT"):
        cfg["warehouse_root"] = os.environ["DW_WAREHOUSE_ROOT"]
    if os.environ.get("DW_DATABASE_URL"):
        cfg["database_url"] = os.environ["DW_DATABASE_URL"]

    return cfg


def save_config(cfg: Dict[str, Any], config_path: Path) -> None:
    """Persist configuration. Sensitive keys are stripped before writing."""
    safe = {k: v for k, v in cfg.items()
            if not any(s in k.lower() for s in ("token", "key", "secret", "password", "auth"))}
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(safe, fh, indent=2, ensure_ascii=False)
