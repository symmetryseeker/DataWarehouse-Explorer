"""
Proxy pool with automatic rotation, health checking, and scoring.

Usage::

    from datawarehouse.ingestion import ProxyPool

    pool = ProxyPool()
    pool.add_proxy("http://1.2.3.4:8080")
    proxy = pool.get_proxy()  # returns the best-scored proxy
    pool.report_result(proxy, success=True)
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("DataWarehouse.Ingestion")


@dataclass
class Proxy:
    """A single proxy entry with health tracking."""

    url: str
    protocol: str = "http"  # http / https / socks5
    score: float = 10.0
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0
    last_check: float = 0.0
    latency_ms: float = 9999.0
    alive: bool = True

    @property
    def full_url(self) -> str:
        return self.url if "://" in self.url else f"{self.protocol}://{self.url}"


class ProxyPool:
    """Thread-safe proxy pool with automatic health management.

    Features:
    - Score-based selection (higher score = more likely to be picked)
    - Automatic health checks with configurable interval
    - Success/failure tracking adjusts scores in real-time
    - Support for HTTP, HTTPS, SOCKS5 proxies

    Args:
        health_check_url: URL to test proxy connectivity.
        health_interval: Seconds between health checks.
        min_score: Proxies below this score are removed from rotation.
    """

    def __init__(
        self,
        health_check_url: str = "https://httpbin.org/ip",
        health_interval: float = 300.0,
        min_score: float = 1.0,
    ) -> None:
        self._proxies: Dict[str, Proxy] = {}
        self._lock = Lock()
        self._health_url = health_check_url
        self._health_interval = health_interval
        self._min_score = min_score

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def add_proxy(self, url: str, protocol: str = "http") -> None:
        """Add a proxy to the pool."""
        with self._lock:
            if url not in self._proxies:
                self._proxies[url] = Proxy(url=url, protocol=protocol)
                logger.debug("Proxy added: %s", url)

    def add_proxies(self, urls: List[str], protocol: str = "http") -> None:
        """Batch-add proxies."""
        for url in urls:
            self.add_proxy(url, protocol)

    def remove_proxy(self, url: str) -> None:
        """Remove a proxy from the pool."""
        with self._lock:
            self._proxies.pop(url, None)
            logger.debug("Proxy removed: %s", url)

    def get_proxy(self) -> Optional[Proxy]:
        """Get the best available proxy (highest score among alive proxies).

        Returns None if no proxies are available.
        """
        with self._lock:
            alive = [p for p in self._proxies.values() if p.alive]
            if not alive:
                logger.warning("No alive proxies in pool")
                return None

            # Weighted random selection by score
            total_score = sum(p.score for p in alive)
            if total_score <= 0:
                return random.choice(alive)

            r = random.uniform(0, total_score)
            cumulative = 0.0
            for p in alive:
                cumulative += p.score
                if r <= cumulative:
                    p.last_used = time.time()
                    return p

            return alive[-1]  # fallback

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def report_success(self, proxy: Proxy, latency_ms: float = 0) -> None:
        """Report a successful request — boost score."""
        with self._lock:
            p = self._proxies.get(proxy.url)
            if p:
                p.success_count += 1
                p.score = min(p.score + 0.5, 20.0)
                p.latency_ms = latency_ms if latency_ms > 0 else p.latency_ms
                p.alive = True

    def report_failure(self, proxy: Proxy) -> None:
        """Report a failed request — reduce score."""
        with self._lock:
            p = self._proxies.get(proxy.url)
            if p:
                p.fail_count += 1
                p.score = max(p.score - 2.0, 0)
                if p.score < self._min_score:
                    p.alive = False
                    logger.info("Proxy marked dead (score=%.1f): %s", p.score, p.url)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Run health checks on all proxies.

        Returns summary: ``{"total": N, "alive": N, "dead": N}``.
        """
        now = time.time()
        alive_count = 0
        dead_count = 0

        with self._lock:
            proxies = list(self._proxies.values())

        for p in proxies:
            if now - p.last_check < self._health_interval:
                continue

            try:
                start = time.time()
                resp = requests.get(
                    self._health_url,
                    proxies={p.protocol: p.full_url},
                    timeout=10,
                )
                latency = (time.time() - start) * 1000
                if resp.status_code == 200:
                    self.report_success(p, latency)
                    alive_count += 1
                else:
                    self.report_failure(p)
                    dead_count += 1
            except requests.RequestException:
                self.report_failure(p)
                dead_count += 1

            p.last_check = now

        return {
            "total": len(proxies),
            "alive": alive_count,
            "dead": dead_count,
        }

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        with self._lock:
            proxies = list(self._proxies.values())
        alive = [p for p in proxies if p.alive]
        return {
            "total": len(proxies),
            "alive": len(alive),
            "dead": len(proxies) - len(alive),
            "avg_score": round(sum(p.score for p in alive) / max(len(alive), 1), 1),
            "top_proxy": max(alive, key=lambda p: p.score).url if alive else None,
        }

    @property
    def size(self) -> int:
        return len(self._proxies)
