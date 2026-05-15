"""Stage 3 — Content-addressable storage engine with deduplication."""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .models import RepoMeta
from .utils import file_checksum, human_size, slugify, now_iso

logger = logging.getLogger("DeepSeek_DataV4")

# File suffixes → classified subdirectories
STRUCTURED_SUBDIRS: Dict[str, str] = {
    ".json": "json", ".csv": "csv", ".xml": "xml",
    ".db": "db", ".sqlite": "db",
}


class StorageEngine:
    """Persist validated repos and their data to the warehouse directory.

    Uses content-addressable storage (CAS): files are stored by SHA-256 hash
    so identical content is only stored once.
    """

    def __init__(self, warehouse_root: Path, storage_mode: str = "content_addressed") -> None:
        self._root = warehouse_root
        self._metadata_dir = warehouse_root / "metadata"
        self._code_dir = warehouse_root / "code"
        self._raw_dir = warehouse_root / "raw"
        self._processed_dir = warehouse_root / "processed"
        self._versions_dir = warehouse_root / "metadata" / "versions"
        self._storage_mode = storage_mode

        for d in (self._metadata_dir, self._code_dir, self._raw_dir,
                  self._processed_dir, self._versions_dir):
            d.mkdir(parents=True, exist_ok=True)

    def store(self, repo_meta: RepoMeta, source_dir: Path,
              pii_findings: Optional[Dict[str, Dict[str, list]]] = None) -> RepoMeta:
        """Copy/classify files from *source_dir* into the warehouse with CAS."""
        slug = slugify(repo_meta.repo_name)
        dest_code = self._code_dir / slug
        meta_path = self._metadata_dir / f"{slug}.json"

        # Idempotency check
        if meta_path.exists():
            existing = self._load_meta(meta_path)
            if existing and existing.quality_score >= repo_meta.quality_score:
                logger.info("Skipping '%s' — already stored (score %s >= %s).",
                            repo_meta.repo_name, existing.quality_score, repo_meta.quality_score)
                return existing
            logger.info("Updating '%s' — new score %s > old %s.",
                        repo_meta.repo_name, repo_meta.quality_score,
                        existing.quality_score if existing else "N/A")

        # Copy project code (excluding VCS and caches)
        if dest_code.exists():
            self._rmtree_safe(dest_code)
        try:
            shutil.copytree(source_dir, dest_code, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(
                                ".git", "__pycache__", "node_modules",
                                ".venv", "venv", ".env", "*.pyc"))
        except OSError as exc:
            logger.error("Failed to copy '%s' → '%s': %s", source_dir, dest_code, exc)

        # Store data files via content-addressable storage
        for data_file_rel in repo_meta.data_files:
            src = source_dir / data_file_rel
            if not src.exists():
                continue
            suffix = src.suffix.lower()

            # Compute SHA-256 for CAS
            file_hash = file_checksum(src)

            if self._storage_mode == "content_addressed":
                hash_prefix = file_hash[:2]
                cas_dir = self._raw_dir / hash_prefix
                cas_dir.mkdir(parents=True, exist_ok=True)
                dest_file = cas_dir / f"{file_hash}_{src.name}"

                if not dest_file.exists():
                    try:
                        shutil.copy2(src, dest_file)
                    except OSError as exc:
                        logger.warning("CAS copy failed for '%s': %s", src, exc)
                        continue
                else:
                    logger.debug("CAS dedup: '%s' already stored as %s", src.name, file_hash[:12])
            else:
                # Flat mode: copy to classified directory
                target_dir = self._root / "data" / "structured" / \
                    STRUCTURED_SUBDIRS.get(suffix, "unstructured/raw")
                target_dir.mkdir(parents=True, exist_ok=True)
                dest_file = target_dir / f"{slug}_{src.name}"
                try:
                    shutil.copy2(src, dest_file)
                except OSError as exc:
                    logger.warning("Failed to copy data file '%s': %s", src, exc)

        # Write/update metadata JSON
        repo_meta.local_path = str(dest_code)
        repo_meta.metadata_path = str(meta_path)
        repo_meta.updated_at = now_iso()
        if not repo_meta.ingested_at:
            repo_meta.ingested_at = now_iso()

        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(repo_meta.to_dict(), fh, indent=2, ensure_ascii=False)

        # Track version
        self._record_version(repo_meta)

        logger.info("Stored '%s' → %s (score=%.1f, license=%s)",
                    repo_meta.repo_name, dest_code, repo_meta.quality_score,
                    repo_meta.license or "unknown")
        return repo_meta

    # ------------------------------------------------------------------
    # Version tracking
    # ------------------------------------------------------------------

    def _record_version(self, meta: RepoMeta) -> None:
        """Append a version entry for this repo."""
        slug = slugify(meta.repo_name)
        version_file = self._versions_dir / f"{slug}_versions.json"
        versions: list = []
        if version_file.exists():
            try:
                versions = json.loads(version_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        versions.append({
            "updated_at": meta.updated_at,
            "quality_score": meta.quality_score,
            "file_count": len(meta.data_files),
            "license": meta.license,
        })
        # Keep last 10 versions
        versions = versions[-10:]
        version_file.write_text(json.dumps(versions, indent=2, ensure_ascii=False),
                                encoding="utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_meta(path: Path) -> Optional[RepoMeta]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return RepoMeta.from_dict(json.load(f))
        except (json.JSONDecodeError, OSError, TypeError):
            return None

    @staticmethod
    def rmtree_safe(path: Path) -> None:
        """Remove a directory tree, handling Windows read-only git files."""
        if not path.exists():
            return

        def _on_error(func, subpath, exc_info):
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
            if platform.system() == "Windows":
                try:
                    subprocess.run(
                        ["cmd", "/c", "rd", "/s", "/q", str(path)],
                        timeout=15, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass

    _rmtree_safe = rmtree_safe  # backward-compat alias
