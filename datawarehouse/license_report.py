"""LICENSES.md report generator for the DataWarehouse."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def generate_licenses_report(metadata_dir: Path, output_path: Path) -> str:
    """Generate a LICENSES.md Markdown file listing all dataset licenses.

    Args:
        metadata_dir: Directory containing repo metadata JSON files.
        output_path: Where to write LICENSES.md.

    Returns:
        The generated Markdown content.
    """
    repos: List[Dict[str, Any]] = []
    if metadata_dir.is_dir():
        for mf in sorted(metadata_dir.glob("*.json")):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                repos.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Data Warehouse — Dataset Licenses",
        "",
        f"> Generated: {now_str}",
        "",
        "This file lists the license for each dataset stored in the DataWarehouse.",
        "Licenses are auto-detected from each repository's LICENSE file.",
        "",
        "| # | Dataset | License | Source |",
        "|---|---------|---------|--------|",
    ]

    licensed = 0
    for i, r in enumerate(repos, 1):
        lic = r.get("license") or "Unknown"
        if lic != "Unknown":
            licensed += 1
        lines.append(
            f"| {i} | [{r['repo_name']}]({r.get('repo_url', '')}) "
            f"| {lic} | {r.get('repo_url', '')} |"
        )

    lines += [
        "",
        f"**{licensed}/{len(repos)}** datasets have a detected license.",
        "",
        "> Note: License detection is based on pattern matching.",
        ">  Verify against the original source for legal certainty.",
    ]

    content = "\n".join(lines) + "\n"
    output_path.write_text(content, encoding="utf-8")
    return content
