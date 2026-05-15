#!/usr/bin/env python3
"""
DataWarehouse Web Viewer — Flask-based interactive browser.

Usage:  python DataWarehouse_Web.py [--public] [--port 5000]

    --public    Disable HTTP Basic Auth for public access.
                WARNING: Exposes your data warehouse to the network.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from datawarehouse.web import create_app


def _get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataWarehouse Web Viewer")
    parser.add_argument("--public", action="store_true",
                        help="Disable auth for public access")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to listen on (default: 5000)")
    args = parser.parse_args()

    if args.public:
        os.environ["DW_PUBLIC_MODE"] = "1"
        print("WARNING: Public mode enabled. Authentication is DISABLED.")
    else:
        os.environ["DW_PUBLIC_MODE"] = "0"

    # Detect warehouse
    warehouse_root = None
    for c in (Path("E:/DataWarehouse"), Path("D:/DataWarehouse")):
        if (c / "metadata").is_dir():
            warehouse_root = c
            break
    if warehouse_root is None:
        warehouse_root = _SCRIPT_DIR / "My Passport" / "DataWarehouse"

    app = create_app(warehouse_root=warehouse_root)

    local_ip = _get_local_ip()
    print(f"\n  DataWarehouse Explorer v2.0")
    print(f"  Warehouse : {warehouse_root}")
    print(f"  Local:     http://127.0.0.1:{args.port}")
    print(f"  Network:   http://{local_ip}:{args.port}")
    if args.public:
        print(f"  Mode:      PUBLIC (no auth)")
    else:
        auth_status = "enabled" if app.config.get("AUTH_USER") else "disabled (not configured)"
        print(f"  Mode:      Private (auth {auth_status})")
    print(f"  Quit:      Ctrl+C\n")

    app.run(host="0.0.0.0", port=args.port, debug=False)
