#!/usr/bin/env python3
"""
DeepSeek_DataV4 — Personal Offline Data Warehouse Builder
=========================================================

Entry point. Imports the modular pipeline from the ``datawarehouse`` package.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the project root is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from datawarehouse.config import load_config, resolve_warehouse_root
from datawarehouse.pipeline import Pipeline
from datawarehouse.cli import interactive_loop
from datawarehouse.storage import StorageEngine

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _C = Fore
    _S = Style
except ImportError:
    class _F:  # type: ignore[no-redef]
        def __getattr__(self, _: str) -> str: return ""
    _C = _F()
    _S = _F()


def _setup_logging(warehouse_root: Path) -> Path:
    """Create directories and configure logging."""
    log_dir = warehouse_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"

    # Ensure warehouse subdirectories exist
    for d in [warehouse_root / "metadata", warehouse_root / "code",
              warehouse_root / "data" / "structured" / "csv",
              warehouse_root / "data" / "structured" / "json",
              warehouse_root / "data" / "structured" / "xml",
              warehouse_root / "data" / "structured" / "db",
              warehouse_root / "data" / "unstructured" / "raw",
              warehouse_root / "raw", warehouse_root / "processed",
              warehouse_root / "tmp", log_dir]:
        d.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(str(log_file), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_file


async def async_main() -> None:
    """Async entry point: run pipeline then drop into interactive console."""
    drive_root = resolve_warehouse_root().parent
    warehouse_root = drive_root / "DataWarehouse"
    config_path = drive_root / "config.json"
    log_file = _setup_logging(warehouse_root)

    logger = logging.getLogger("DeepSeek_DataV4")
    config = load_config(config_path)
    config["warehouse_root"] = str(warehouse_root)

    pipeline = Pipeline(config)
    logger.info("Starting DeepSeek_DataV4 pipeline...")
    try:
        stored = await asyncio.wait_for(pipeline.run(), timeout=600)
        logger.info("Pipeline finished. %d repos stored.", len(stored))
    except asyncio.TimeoutError:
        logger.warning("Pipeline timed out after 10 min — proceeding with partial results.")
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)

    interactive_loop(warehouse_root / "metadata", warehouse_root)


def main() -> None:
    """Synchronous entry point for the script."""
    drive_root = resolve_warehouse_root().parent
    warehouse_root = drive_root / "DataWarehouse"
    config_path = drive_root / "config.json"

    print(f"{_C.CYAN}")
    print(r"  ____                _     ____       _         ")
    print(r" |  _ \  ___  ___ ___| | __/ ___|  ___| | _____  ")
    print(r" | | | |/ _ \/ _ \/ _ \ |/ /\___ \ / _ \ |/ / _ \ ")
    print(r" | |_| |  __/  __/  __/   <  ___) |  __/   <  __/ ")
    print(r" |____/ \___|\___|\___|_|\_\|____/ \___|_|\_\___| ")
    print(r"     ____  __      ____   _  _   _____            ")
    print(r"    |  _ \|  \/  ||___ \ | || | |___ / _   _      ")
    print(r"    | | | | |\/| |  __) || || |_  |_ \| | | |     ")
    print(r"    | |_| | |  | | / __/ |__   _|___) | |_| |     ")
    print(r"    |____/|_|  |_||_____|   |_| |____/ \__, |     ")
    print(r"                                        |___/     ")
    print(f"{_S.RESET_ALL}")
    print(f"  DataWarehouse Explorer v2.0")
    print(f"  Drive   root: {drive_root}")
    print(f"  Warehouse   : {warehouse_root}")
    print(f"  Config file : {config_path}")
    print()

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
