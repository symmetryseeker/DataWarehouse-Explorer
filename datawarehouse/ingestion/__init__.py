"""
Advanced ingestion layer — proxy pool, JS rendering, dlt pipeline.
"""

from .proxy_pool import ProxyPool
from .playwright_fetcher import PlaywrightFetcher
from .dlt_loader import DLTLoader

__all__ = ["ProxyPool", "PlaywrightFetcher", "DLTLoader"]
