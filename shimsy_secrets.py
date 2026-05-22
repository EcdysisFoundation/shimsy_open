"""
Load machine-local secrets and network settings from shimsy_local.json (gitignored).

Environment variables override JSON values where noted. See shimsy_local.example.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent
_LOCAL_FILE = _BASE_DIR / "shimsy_local.json"
_CONFIG: dict[str, Any] | None = None

_ENV_MAP = {
    "DJANGO_SECRET_KEY": "django_secret_key",
    "SHIMSY_SCANS_BASE": "shimsy_scans_base",
    "SHIMSY_STAGING": "shimsy_staging",
    "SHIMSY_TEMP_BASE": "shimsy_temp_base",
    "SHIMSY_REPO_HOME": "repo_home",
    "STITCHER_URL": "stitcher_url",
    "STITCHER_JS_URL": "stitcher_js_url",
    "STITCHER_FORM_URL_BASE": "stitcher_form_url_base",
    "NAS_IP": "nas_ip",
    "NAS_EXPORT": "nas_export",
    "DJANGO_DEBUG": "debug",
}


def _defaults() -> dict[str, Any]:
    return {
        "django_secret_key": "django-insecure-set-shimsy_local-json-or-DJANGO_SECRET_KEY",
        "allowed_hosts": ["localhost", "127.0.0.1"],
        "debug": True,
        "stitcher_url": "",
        "stitcher_js_url": "",
        "stitcher_form_url_base": "",
        "shimsy_scans_base": "",
        "shimsy_staging": "",
        "shimsy_temp_base": "",
        "nas_ip": "",
        "nas_export": "/pool1/srv/shimsy/shimsy_scans",
        "repo_home": str(_BASE_DIR),
    }


def _apply_env(cfg: dict[str, Any]) -> None:
    for env_name, key in _ENV_MAP.items():
        val = os.environ.get(env_name)
        if val is None or val == "":
            continue
        if key == "debug":
            cfg[key] = val.lower() in ("1", "true", "yes", "on")
        else:
            cfg[key] = val

    hosts = os.environ.get("DJANGO_ALLOWED_HOSTS")
    if hosts:
        cfg["allowed_hosts"] = [h.strip() for h in hosts.split(",") if h.strip()]


def get_config(reload: bool = False) -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None and not reload:
        return _CONFIG

    cfg = _defaults()
    if _LOCAL_FILE.is_file():
        with open(_LOCAL_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key, val in data.items():
                if val is not None and val != "":
                    cfg[key] = val

    _apply_env(cfg)
    _CONFIG = cfg
    return _CONFIG


def local_config_path() -> Path:
    return _LOCAL_FILE


def require_local_config() -> None:
    """Raise if shimsy_local.json is missing (optional strict check)."""
    if not _LOCAL_FILE.is_file():
        raise FileNotFoundError(
            f"Missing { _LOCAL_FILE }. Copy shimsy_local.example.json to shimsy_local.json "
            "and set your machine's hosts, paths, and API URLs."
        )
