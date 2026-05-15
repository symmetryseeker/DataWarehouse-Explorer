"""Configuration management and path resolution."""

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
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

STRUCTURED_SUBDIRS: Dict[str, Path] = {}  # set after WAREHOUSE_ROOT resolved

DEFAULT_CONFIG: Dict[str, Any] = {
    "search_keywords": ["api", "crawler", "scraper", "dataset", "data-pipeline"],
    "min_stars": MIN_STARS_DEFAULT,
    "max_repos_per_keyword": 20,
    "blacklist_repos": [],
    "preferred_mirrors": ["kgithub"],
    "warehouse_root": "",
    "metadata_db_path": "",
    "storage_mode": "content_addressed",
    "web_auth_user": None,
    "web_auth_pass_hash": None,
    "chart_library": "chartjs",
}


# ---------------------------------------------------------------------------
# Drive Detection
# ---------------------------------------------------------------------------

def detect_my_passport() -> Optional[Path]:
    """Auto-detect the 'My Passport' external drive across platforms."""
    candidates: List[Path] = []
    system = platform.system()
    drive_label = "My Passport"
    script_dir = Path(__file__).resolve().parent.parent

    if system == "Windows":
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{letter}:\\")
            if not root.exists():
                continue
            candidate = root / drive_label
            if candidate.is_dir():
                candidates.append(candidate)
                continue
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
    else:
        for base in (f"/media/{os.environ.get('USER', '')}/{drive_label}",
                     f"/media/{drive_label}", f"/mnt/{drive_label}"):
            candidate = Path(base)
            if candidate.is_dir():
                candidates.append(candidate)

    if candidates:
        print(f"[DETECT] My Passport found at: {candidates[0]}")
        return candidates[0]

    fallback = script_dir / drive_label
    if fallback.is_dir():
        print(f"[DETECT] My Passport found (relative): {fallback}")
        return fallback

    for parent in script_dir.parents:
        fb = parent / drive_label
        if fb.is_dir():
            print(f"[DETECT] My Passport found (up-tree): {fb}")
            return fb
    return None


def resolve_warehouse_root() -> Path:
    """Determine the warehouse root path, preferring the external drive."""
    drive_root = detect_my_passport()
    if drive_root is not None:
        wh = drive_root
    else:
        wh = Path(__file__).resolve().parent.parent / "My Passport"
        print(f"\n{'!' * 60}")
        print(f"  WARNING: 'My Passport' external drive NOT detected.")
        print(f"  Falling back to local path: {wh}")
        print(f"{'!' * 60}\n")
    return wh / "DataWarehouse"


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON, creating a default if absent."""
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            merged = {**DEFAULT_CONFIG, **cfg}
            logger.info("Config loaded from %s", config_path)
            return merged
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Config file corrupt (%s), regenerating default.", exc)
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(DEFAULT_CONFIG, fh, indent=2, ensure_ascii=False)
    logger.info("Default config written to %s", config_path)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any], config_path: Path) -> None:
    """Persist configuration to disk."""
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
