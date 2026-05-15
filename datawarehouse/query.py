"""Stage 4 — In-memory inverted index with natural-language search."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from .models import RepoMeta

logger = logging.getLogger("DeepSeek_DataV4")


class QueryInterface:
    """In-memory index over warehouse metadata with keyword search."""

    def __init__(self, metadata_dir: Path) -> None:
        self._metadata_dir = metadata_dir
        self._index: List[RepoMeta] = []
        self._keyword_map: Dict[str, List[int]] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Scan all metadata JSON files and build an inverted index."""
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

        # Intent detection for data types
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
                if token in meta.repo_name.lower():
                    score += 1.5
                if token in meta.description.lower():
                    score += 0.5

            if intent_types & set(meta.data_types):
                score += 2.0
            if "__api__" in intent_types and meta.api_docs_found:
                score += 2.0

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
            "licensed_count": sum(1 for m in self._index if m.license),
        }
