"""DataWarehouse Web Viewer — Flask application factory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask

from .routes import api, pages, init_dirs


def create_app(warehouse_root: Path | None = None,
               metadata_dir: Path | None = None,
               code_dir: Path | None = None) -> Flask:
    """Build and configure the Flask application.

    Args:
        warehouse_root: Root of the DataWarehouse directory.
        metadata_dir: Directory containing repo metadata JSON files.
        code_dir: Directory containing cloned repo code.
    """
    app = Flask(__name__)

    if warehouse_root is None:
        warehouse_root = _detect_warehouse()
    if metadata_dir is None:
        metadata_dir = warehouse_root / "metadata"
    if code_dir is None:
        code_dir = warehouse_root / "code"

    init_dirs(metadata_dir, code_dir)

    # Configuration
    app.config["AUTH_USER"] = os.environ.get("DW_USER")
    app.config["AUTH_PASS_HASH"] = os.environ.get("DW_PASS_HASH")
    app.config["WAREHOUSE_ROOT"] = str(warehouse_root)

    app.register_blueprint(pages)
    app.register_blueprint(api)

    return app


def _detect_warehouse() -> Path:
    """Detect the warehouse root from common locations."""
    candidates = [
        Path("E:/DataWarehouse"),
        Path("D:/DataWarehouse"),
        Path(__file__).resolve().parent.parent.parent / "My Passport" / "DataWarehouse",
    ]
    for c in candidates:
        if (c / "metadata").is_dir():
            return c
    return candidates[-1]
