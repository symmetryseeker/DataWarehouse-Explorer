"""
Natural Language → SQL engine using LLM + RAG.

Users ask questions like "去年销售额最高的三个品类是什么？",
the system generates SQL, executes it against DuckDB, and returns results.

Architecture::

    User Question → Schema Context (RAG) → LLM → SQL → DuckDB → Result + Chart

Usage::

    from datawarehouse.ai import TextToSQLEngine, load_llm_config

    config = load_llm_config()
    engine = TextToSQLEngine(config, duckdb_path="E:/DataWarehouse/metadata.db")
    result = engine.query("Show me top 5 undefeated boxers by wins")
"""

from __future__ import annotations

import json
import logging
import re
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import duckdb
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "duckdb", "--quiet"])
    import duckdb  # type: ignore

from .llm_client import LLMClient, load_llm_config

logger = logging.getLogger("DataWarehouse.AI")


class TextToSQLEngine:
    """Natural language query engine with RAG-powered SQL generation.

    Uses LLM to translate user questions → SQL, executes against DuckDB,
    and returns structured results with optional chart configuration.

    Args:
        config: LLM config dict from :func:`load_llm_config`.
        duckdb_path: Path to DuckDB database file (or ``:memory:``).
        schema_context: Optional pre-built schema description string.
    """

    # SQL keywords that indicate a dangerous operation — blocked for safety
    DANGEROUS_SQL = re.compile(
        r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        duckdb_path: str = ":memory:",
        schema_context: Optional[str] = None,
    ) -> None:
        if config is None:
            config = load_llm_config()
        self._client = LLMClient(config)
        self._enabled = config.get("features", {}).get("text_to_sql", True)

        self._db = duckdb.connect(duckdb_path)
        self._schema_context = schema_context or ""
        self._query_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_csv(self, name: str, csv_path: Path) -> None:
        """Register a CSV file as a DuckDB table for querying.

        Args:
            name: Table name (e.g., ``"undefeated_boxers"``).
            csv_path: Path to the CSV file.
        """
        self._db.execute(
            f"CREATE OR REPLACE TABLE \"{name}\" AS "
            f"SELECT * FROM read_csv_auto('{csv_path}')"
        )
        logger.info("Registered CSV as table '%s': %s", name, csv_path.name)

    def register_csv_directory(self, dir_path: Path, pattern: str = "*.csv") -> int:
        """Register all CSV files in a directory as DuckDB tables.

        Returns:
            Number of tables registered.
        """
        count = 0
        for csv_file in sorted(dir_path.glob(pattern)):
            table_name = re.sub(r"[^\w]", "_", csv_file.stem)
            try:
                self.register_csv(table_name, csv_file)
                count += 1
            except Exception as exc:
                logger.warning("Failed to register %s: %s", csv_file, exc)
        return count

    def build_schema_context(self) -> str:
        """Auto-generate schema context from registered DuckDB tables.

        Returns:
            A string describing all tables, columns, and sample values.
        """
        tables = self._db.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main'"
        ).fetchall()

        if not tables:
            return "No tables registered."

        parts: List[str] = []
        for (tname,) in tables:
            cols = self._db.execute(
                f"DESCRIBE \"{tname}\""
            ).fetchall()
            col_desc = ", ".join(f"{c[0]} ({c[1]})" for c in cols)
            # Get row count
            row_count = self._db.execute(
                f"SELECT COUNT(*) FROM \"{tname}\""
            ).fetchone()[0]
            parts.append(f"Table '{tname}' ({row_count} rows): {col_desc}")

        self._schema_context = "\n".join(parts)
        return self._schema_context

    def query(self, question: str) -> Dict[str, Any]:
        """Translate a natural language question to SQL and execute it.

        Args:
            question: Natural language query in English or Chinese.

        Returns:
            Dict with keys: ``question``, ``sql``, ``columns``, ``rows``,
            ``row_count``, ``chart_type``, ``chart_config``.
        """
        if not self._enabled:
            return {
                "question": question,
                "error": "Text-to-SQL is disabled in config",
            }

        # Build or refresh schema context for RAG
        if not self._schema_context:
            self.build_schema_context()

        # Generate SQL via LLM
        sql = self._generate_sql(question)

        # Safety check
        if self.DANGEROUS_SQL.search(sql):
            return {
                "question": question,
                "sql": sql,
                "error": "Generated SQL contains write operations — blocked for safety",
            }

        # Execute
        try:
            result = self._db.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            rows_list = [list(r) for r in rows]

            # Auto-suggest chart type
            chart_type, chart_config = self._suggest_chart(question, columns, rows_list)

            entry = {
                "question": question,
                "sql": sql,
                "columns": columns,
                "rows": rows_list,
                "row_count": len(rows_list),
                "chart_type": chart_type,
                "chart_config": chart_config,
            }
            self._query_history.append(entry)
            return entry

        except Exception as exc:
            logger.error("SQL execution failed: %s\nSQL: %s", exc, sql)
            return {
                "question": question,
                "sql": sql,
                "error": str(exc),
            }

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._db.close()

    @property
    def history(self) -> List[Dict[str, Any]]:
        """Return query history."""
        return list(self._query_history)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_sql(self, question: str) -> str:
        """Use LLM to generate DuckDB-compatible SQL from a question."""
        system = (
            "You are a DuckDB SQL expert. Given table schemas and a user question, "
            "generate a single SELECT query that answers the question. "
            "Rules:\n"
            "- Use ONLY the tables and columns provided in the schema context.\n"
            "- Return ONLY the raw SQL, no markdown, no explanation.\n"
            "- DuckDB SQL syntax (supports read_csv_auto, columns()).\n"
            "- For Chinese questions, use Chinese-friendly column aliases with AS.\n"
            "- Limit results to 100 rows unless the user asks for more.\n"
            "- For 'top N' questions, use ORDER BY ... DESC LIMIT N."
        )
        prompt = (
            f"Schema context:\n{self._schema_context}\n\n"
            f"User question: {question}\n\n"
            f"Generate the SQL query:"
        )

        sql = self._client.chat(prompt, system, temperature=0.0)

        # Strip markdown wrapping if present
        if "```sql" in sql:
            sql = sql.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0].strip()

        return sql.strip().rstrip(";")

    @staticmethod
    def _suggest_chart(
        question: str, columns: List[str], rows: List[List[str]]
    ) -> Tuple[str, Dict[str, Any]]:
        """Auto-suggest a chart type and config based on query results."""
        # Heuristic rules
        num_cols = len(columns)
        num_rows = len(rows)
        numeric_cols = 0
        for c in range(num_cols):
            if rows and all(
                isinstance(r[c], (int, float)) or
                (isinstance(r[c], str) and r[c].replace(".", "").replace("-", "").isdigit())
                for r in rows
            ):
                numeric_cols += 1

        # If 1 text col + 1 numeric col → bar chart
        if num_cols == 2 and numeric_cols == 1:
            return "bar", {
                "x_axis": columns[0],
                "y_axis": columns[1],
                "title": question,
            }

        # If 1 text col + multiple numeric → multi-bar or line
        if num_cols >= 3 and numeric_cols >= 2:
            if "趋势" in question or "时间" in question or "trend" in question.lower():
                return "line", {
                    "x_axis": columns[0],
                    "y_axes": columns[1:],
                    "title": question,
                }
            return "bar", {
                "x_axis": columns[0],
                "y_axes": columns[1:],
                "title": question,
            }

        # Default: table only
        return "table", {
            "columns": columns,
            "title": question,
        }
