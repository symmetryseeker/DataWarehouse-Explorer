"""Stage 1 — Async search-and-fetch engine targeting GitHub mirrors."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup

from .config import (
    GITHUB_API_SEARCH, MAX_CONCURRENT_REQUESTS, MIN_STARS_DEFAULT,
    MIRRORS, REQUEST_DELAY,
)
from .models import RepoMeta
from .utils import now_iso, random_ua

logger = logging.getLogger("DeepSeek_DataV4")


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
            connector = aiohttp.TCPConnector(
                limit=MAX_CONCURRENT_REQUESTS, force_close=True)
            timeout = aiohttp.ClientTimeout(total=20, connect=8)
            self._session = aiohttp.ClientSession(
                connector=connector, timeout=timeout,
                headers={"Accept": "text/html,application/json",
                         "Accept-Language": "en-US,en;q=0.9"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def run(self) -> List[RepoMeta]:
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
                self._seen.add(repo.repo_url)
                self._results.append(repo)

        unique: Dict[str, RepoMeta] = {}
        for r in self._results:
            if r.repo_url not in unique:
                unique[r.repo_url] = r
        self._results = list(unique.values())
        self._results.extend(self._seed_known_repos(blacklist))

        logger.info("STAGE 1 — Found %d unique candidate repos across %d keywords.",
                    len(self._results), len(keywords))
        return self._results

    @staticmethod
    def _seed_known_repos(blacklist: Set[str]) -> List[RepoMeta]:
        seeds: List[Dict[str, Any]] = [
            {"repo_name": "awesomedata/awesome-public-datasets",
             "repo_url": "https://github.com/awesomedata/awesome-public-datasets",
             "description": "A curated list of awesome open public datasets",
             "stars": 63000, "language": "Markdown",
             "tags": ["dataset", "awesome-list", "data-catalog"]},
            {"repo_name": "datasets/awesome-data",
             "repo_url": "https://github.com/datasets/awesome-data",
             "description": "Awesome data — curated list of datasets",
             "stars": 6200, "language": "Python",
             "tags": ["dataset", "awesome-list"]},
            {"repo_name": "public-apis/public-apis",
             "repo_url": "https://github.com/public-apis/public-apis",
             "description": "A collective list of free APIs",
             "stars": 330000, "language": "Python",
             "tags": ["api", "awesome-list", "open-data"]},
            {"repo_name": "jivoi/awesome-osint",
             "repo_url": "https://github.com/jivoi/awesome-osint",
             "description": "Awesome list of OSINT tools and resources",
             "stars": 21000, "language": "Markdown",
             "tags": ["osint", "data", "awesome-list"]},
            {"repo_name": "fivethirtyeight/data",
             "repo_url": "https://github.com/fivethirtyeight/data",
             "description": "Data and code behind FiveThirtyEight articles",
             "stars": 16900, "language": "Jupyter Notebook",
             "tags": ["dataset", "csv", "journalism", "statistics"]},
        ]
        results: List[RepoMeta] = []
        for s in seeds:
            if s["repo_url"] in blacklist:
                continue
            results.append(RepoMeta(
                repo_name=s["repo_name"], repo_url=s["repo_url"],
                mirror_name="direct_seed",
                description=s.get("description", ""),
                stars=s.get("stars", 0), language=s.get("language", ""),
                tags=s.get("tags", []), ingested_at=now_iso(),
            ))
        return results

    async def _search_mirror(self, keyword: str, mirror: Dict[str, str]) -> List[RepoMeta]:
        results: List[RepoMeta] = []
        search_url = f"{mirror['search_url']}?q={quote_plus(keyword)}&type=repositories"
        session = await self._get_session()

        text: Optional[str] = None
        try:
            async with self._semaphore:
                await asyncio.sleep(REQUEST_DELAY + random.uniform(0.1, 0.6))
                async with session.get(
                    search_url, headers={"User-Agent": random_ua()}, allow_redirects=True,
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        logger.debug("Mirror %s returned %d for kw='%s'",
                                     mirror["name"], resp.status, keyword)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("Mirror %s unreachable for kw='%s': %s", mirror["name"], keyword, exc)
            return results

        if text is None:
            return results

        soup = BeautifulSoup(text, "lxml")
        count = 0
        max_per = self._config.get("max_repos_per_keyword", 20)
        for link in soup.select("a[href*='/']"):
            href = link.get("href", "")
            if not href or href in ("/", "/search"):
                continue
            parts = [p for p in href.strip("/").split("/") if p]
            if len(parts) < 2:
                continue
            if any(p in ("search", "login", "explore", "notifications") for p in parts):
                continue
            owner, repo_name = parts[0], parts[1]
            repo_url = f"{mirror['repo_prefix']}/{owner}/{repo_name}"
            if repo_url in self._seen:
                continue
            results.append(RepoMeta(
                repo_name=f"{owner}/{repo_name}", repo_url=repo_url,
                mirror_name=mirror["name"], description=link.get("title", ""),
                ingested_at=now_iso(),
            ))
            count += 1
            if count >= max_per:
                break
        logger.debug("Mirror '%s' / kw='%s' -> %d repos", mirror["name"], keyword, count)
        return results

    async def _search_github_api(
        self, keywords: List[str], min_stars: int, max_per_kw: int,
    ) -> List[RepoMeta]:
        results: List[RepoMeta] = []
        session = await self._get_session()

        for kw in keywords:
            params = {
                "q": f"{kw} stars:>={min_stars}", "sort": "stars",
                "order": "desc", "per_page": min(max_per_kw, 30),
            }
            data: Optional[Dict[str, Any]] = None
            try:
                async with self._semaphore:
                    await asyncio.sleep(REQUEST_DELAY + random.uniform(0.2, 0.8))
                    async with session.get(
                        GITHUB_API_SEARCH, params=params,
                        headers={"User-Agent": random_ua(),
                                 "Accept": "application/vnd.github.v3+json"},
                    ) as resp:
                        if resp.status == 403:
                            logger.warning("GitHub API rate limit hit on kw='%s'", kw)
                            return results
                        if resp.status != 200:
                            logger.debug("GitHub API returned %d for kw='%s'", resp.status, kw)
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
                results.append(RepoMeta(
                    repo_name=item.get("full_name", ""), repo_url=repo_url,
                    mirror_name="github_api",
                    description=item.get("description", "") or "",
                    stars=item.get("stargazers_count", 0),
                    language=item.get("language", "") or "",
                    tags=item.get("topics", []), ingested_at=now_iso(),
                ))
        return results
