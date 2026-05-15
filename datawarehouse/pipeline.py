"""Pipeline orchestrator — wires together Ingestion, Validation, and Storage."""

from __future__ import annotations

import asyncio
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from .config import load_config
from .ingestor import Ingester
from .models import RepoMeta
from .storage import StorageEngine
from .utils import slugify, random_ua
from .validator import Validator

logger = logging.getLogger("DeepSeek_DataV4")


class Pipeline:
    """Top-level orchestrator that wires together Ingestion, Validation, Storage."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._warehouse_root = Path(config.get("warehouse_root", ""))
        self._ingester = Ingester(config)
        self._validator = Validator(self._warehouse_root)
        storage_mode = config.get("storage_mode", "content_addressed")
        self._storage = StorageEngine(self._warehouse_root, storage_mode=storage_mode)

    async def run(self) -> List[RepoMeta]:
        stored: List[RepoMeta] = []

        # Stage 1
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

        # Stage 2 & 3
        logger.info("STAGE 2 & 3 — Validating %d candidates...", len(candidates))
        for i, repo in enumerate(candidates, 1):
            try:
                logger.info("[%d/%d] Processing '%s' ...", i, len(candidates), repo.repo_name)
                project_dir = await self._download_repo(repo)

                if project_dir is None:
                    logger.info("Skipping '%s' — download failed.", repo.repo_name)
                    continue

                # Validate (includes deep CSV/XML/SQLite + license detection + PII scan)
                repo = self._validator.validate(repo, project_dir)

                # PII scan for CSV files
                pii_findings: Dict[str, Dict[str, list]] = {}
                for df_rel in repo.data_files:
                    df_path = project_dir / df_rel
                    if df_path.suffix.lower() == ".csv":
                        findings = self._validator.scan_pii(df_path)
                        if findings:
                            pii_findings[df_rel] = findings
                            logger.info("PII flagged in '%s': %s", df_rel,
                                        {k: len(v) for k, v in findings.items()})

                if repo.quality_score >= 5.0:
                    repo = self._storage.store(repo, project_dir, pii_findings)
                    stored.append(repo)
                else:
                    logger.info("Discarding '%s' — quality too low (%.1f).",
                                repo.repo_name, repo.quality_score)

                StorageEngine.rmtree_safe(project_dir)

            except Exception as exc:
                logger.error("Pipeline error on '%s': %s\n%s",
                             repo.repo_name, exc, traceback.format_exc())
                continue

        logger.info("PIPELINE COMPLETE — %d repos stored.", len(stored))
        return stored

    # ------------------------------------------------------------------
    # Download strategies
    # ------------------------------------------------------------------

    async def _download_repo(self, repo: RepoMeta) -> Optional[Path]:
        slug = slugify(repo.repo_name)
        temp_dir = self._warehouse_root / "tmp" / slug
        temp_dir.mkdir(parents=True, exist_ok=True)

        entries = list(temp_dir.iterdir())
        non_git = [e for e in entries if e.name != ".git"]
        if non_git:
            logger.info("Reusing existing temp dir '%s' (%d entries)", temp_dir, len(non_git))
            return temp_dir
        if entries:
            logger.debug("Removing stale temp dir '%s'", temp_dir)
            StorageEngine.rmtree_safe(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

        parts = repo.repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            logger.warning("Cannot parse repo URL: %s", repo.repo_url)
            return None
        owner, repo_name = parts[-2], parts[-1]

        # Try 5 strategies in order
        strategies = [
            f"https://github.com/{owner}/{repo_name}.git",
            f"https://kgithub.com/{owner}/{repo_name}.git",
            f"https://gitclone.com/github.com/{owner}/{repo_name}.git",
        ]
        for url in strategies:
            if await self._try_git_clone(url, temp_dir):
                return temp_dir

        for branch in ("main", "master"):
            for mirror_host in ("kgithub.com", "gitclone.com/github.com"):
                archive_url = f"https://{mirror_host}/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
                if await self._download_archive(archive_url, temp_dir):
                    return temp_dir

        logger.info("All download strategies failed for '%s'", repo.repo_name)
        StorageEngine.rmtree_safe(temp_dir)
        return None

    async def _try_git_clone(self, url: str, dest: Path) -> bool:
        cmd = ["git", "clone", "--depth", "1", "--quiet", url, str(dest)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
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
        import shutil
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        connector = aiohttp.TCPConnector(limit=1, force_close=True)
        try:
            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout,
                headers={"Accept": "application/zip,*/*",
                         "Accept-Language": "en-US,en;q=0.9"},
            ) as session:
                async with session.get(
                    archive_url, headers={"User-Agent": random_ua()},
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        logger.debug("Archive not found (%d): %s", resp.status, archive_url)
                        return False
                    zip_path = dest / "archive.zip"
                    with open(zip_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            f.write(chunk)
                # Safe unpack with path traversal protection
                if hasattr(shutil, 'unpack_archive'):
                    shutil.unpack_archive(str(zip_path), extract_dir=str(dest), filter='data')
                else:
                    shutil.unpack_archive(str(zip_path), extract_dir=str(dest))
                zip_path.unlink(missing_ok=True)
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
