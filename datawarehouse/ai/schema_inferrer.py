"""
Auto-generate field descriptions and business context for CSV columns via LLM.

Usage::

    from datawarehouse.ai import SchemaInferrer, load_llm_config

    config = load_llm_config()
    inferrer = SchemaInferrer(config)
    result = inferrer.infer("path/to/file.csv")
    # → {"name": {"description": "拳击手姓名", "type_guess": "string", ...}, ...}
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient, load_llm_config

logger = logging.getLogger("DataWarehouse.AI")


class SchemaInferrer:
    """Generate field-level metadata for CSV files using LLM.

    Reads the first N rows of a CSV, sends them to the configured LLM,
    and returns per-column descriptions, type guesses, and categories.

    Args:
        config: LLM config dict from :func:`load_llm_config`.
        sample_rows: Number of rows to send to the LLM (default: 10).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 sample_rows: int = 10) -> None:
        if config is None:
            config = load_llm_config()
        self._client = LLMClient(config)
        self._sample_rows = sample_rows
        self._enabled = config.get("features", {}).get("schema_inference", True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer(self, csv_path: Path) -> Dict[str, Dict[str, Any]]:
        """Infer schema for a CSV file.

        Args:
            csv_path: Path to the CSV file.

        Returns:
            Dict mapping column name → metadata dict::

                {
                    "name": {
                        "description": "拳击手姓名",
                        "type_guess": "string",
                        "nullable": false,
                        "category": "dimension"
                    },
                    ...
                }
        """
        if not csv_path.suffix.lower() == ".csv":
            raise ValueError(f"Expected a .csv file, got {csv_path.suffix}")

        headers, sample_rows = self._read_sample(csv_path)
        if not headers:
            logger.warning("Empty CSV: %s", csv_path)
            return {}

        if not self._enabled:
            logger.info("Schema inference disabled, returning basic types only")
            return self._basic_inference(headers, sample_rows)

        try:
            result = self._client.infer_schema(headers, sample_rows)
            logger.info("Schema inferred for %s: %d columns via %s",
                        csv_path.name, len(result), self._client.provider)
            return result
        except Exception as exc:
            logger.warning("LLM schema inference failed: %s. Falling back to basic inference.", exc)
            return self._basic_inference(headers, sample_rows)

    def infer_batch(self, csv_paths: List[Path]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Infer schema for multiple CSV files.

        Returns:
            Dict mapping filename → column metadata dict.
        """
        results: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for path in csv_paths:
            try:
                results[path.name] = self.infer(path)
            except Exception as exc:
                logger.error("Schema inference failed for %s: %s", path.name, exc)
                results[path.name] = {"__error__": str(exc)}
        return results

    def to_datahub_json(self, csv_path: Path, dataset_uuid: str) -> Dict[str, Any]:
        """Export inferred schema in DataHub-compatible JSON format.

        Args:
            csv_path: Path to the CSV file.
            dataset_uuid: UUID of the dataset in the warehouse.

        Returns:
            DataHub dataset schema JSON.
        """
        schema = self.infer(csv_path)
        fields = []
        for col_name, meta in schema.items():
            fields.append({
                "fieldPath": col_name,
                "description": meta.get("description", ""),
                "nativeDataType": meta.get("type_guess", "string"),
                "nullable": meta.get("nullable", True),
                "tags": [meta.get("category", "unknown")],
            })
        return {
            "dataset": dataset_uuid,
            "schema": {"fields": fields},
            "source": f"LLM ({self._client.provider}/{self._client.model})",
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_sample(self, path: Path) -> tuple:
        """Read headers and the first sample_rows from a CSV."""
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            rows = [row for _, row in zip(range(self._sample_rows), reader)]
        return headers, rows

    @staticmethod
    def _basic_inference(headers: List[str],
                         sample_rows: List[List[str]]) -> Dict[str, Dict[str, Any]]:
        """Fallback: basic type inference without LLM."""
        result: Dict[str, Dict[str, Any]] = {}
        for i, h in enumerate(headers):
            values = [row[i] for row in sample_rows if i < len(row) and row[i].strip()]
            # Guess type from values
            type_guess = "string"
            if values:
                if all(v.replace(".", "").replace("-", "").isdigit() or v == ""
                       for v in values):
                    if any("." in v for v in values):
                        type_guess = "float"
                    elif any("-" in v for v in values):
                        type_guess = "date" if len(values[0]) == 10 else "string"
                    else:
                        type_guess = "int"
            result[h] = {
                "description": h,
                "type_guess": type_guess,
                "nullable": any(i >= len(row) or row[i].strip() == ""
                               for row in sample_rows),
                "category": "unknown",
            }
        return result
