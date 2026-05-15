"""HTTP Basic Auth for the DataWarehouse web UI (opt-in)."""

from __future__ import annotations

import hashlib
import os
from functools import wraps

from flask import request, Response, current_app


def check_auth(username: str, password: str) -> bool:
    """Compare against configured credentials. If none are set, auth is skipped."""
    cfg_user = os.environ.get("DW_USER") or current_app.config.get("AUTH_USER")
    cfg_pass_hash = os.environ.get("DW_PASS_HASH") or current_app.config.get("AUTH_PASS_HASH")
    if not cfg_user or not cfg_pass_hash:
        return True
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    return username == cfg_user and pw_hash == cfg_pass_hash


def _auth_configured() -> bool:
    """Return True if auth credentials are configured."""
    cfg_user = os.environ.get("DW_USER") or current_app.config.get("AUTH_USER")
    cfg_pass = os.environ.get("DW_PASS_HASH") or current_app.config.get("AUTH_PASS_HASH")
    return bool(cfg_user and cfg_pass)


def requires_auth(f):
    """Decorator: enforce Basic Auth only when credentials are configured.

    If no auth credentials are set or DW_PUBLIC_MODE=1, all requests pass.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Public mode explicitly enabled → skip auth
        if os.environ.get("DW_PUBLIC_MODE") == "1":
            return f(*args, **kwargs)

        # No credentials configured → skip auth
        if not _auth_configured():
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Authentication required", 401,
                {"WWW-Authenticate": "Basic realm='DataWarehouse'"},
            )
        return f(*args, **kwargs)
    return decorated
