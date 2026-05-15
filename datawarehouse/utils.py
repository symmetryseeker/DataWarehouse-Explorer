"""Shared utilities for the DataWarehouse pipeline."""

from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .config import USER_AGENTS


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
    """SHA-256 hex digest of a file, used for dedup and content addressing."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def checksum_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def human_size(size: int) -> str:
    """Convert byte count to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
