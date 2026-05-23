"""Persistent configuration for the PDF Page Numberer.

Stores the chosen folder and settings in a small JSON file under the user's
config directory so the background agent can resume across launches and reboots.
GUI-free and import-light so it can be unit-tested.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from tools.pdf_numbering.core import Settings

APP_DIR_NAME = "PDFPageNumberer"

DEFAULTS: Dict[str, Any] = {
    "folder": "",
    "position": "bottom-center",
    "font_size": 10.0,
    "margin_pt": 28.0,
    "make_backup": True,
    "watch_enabled": False,
}


def config_dir() -> Path:
    """Per-user config directory (``%APPDATA%`` on Windows, ``~/.config`` elsewhere)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def log_file_path() -> Path:
    return config_dir() / "agent.log"


def load_config() -> Dict[str, Any]:
    """Return the saved config merged over defaults; defaults if missing/corrupt."""
    merged = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            merged.update({k: saved[k] for k in DEFAULTS if k in saved})
    except (FileNotFoundError, ValueError, OSError):
        pass
    return merged


def save_config(config: Dict[str, Any]) -> None:
    """Persist the given config (only known keys) to the config file."""
    config_dir().mkdir(parents=True, exist_ok=True)
    to_write = {k: config.get(k, DEFAULTS[k]) for k in DEFAULTS}
    with open(config_path(), "w", encoding="utf-8") as handle:
        json.dump(to_write, handle, indent=2)


def settings_from_config(config: Dict[str, Any]) -> Settings:
    """Build a core ``Settings`` from a config dict."""
    return Settings(
        position=str(config.get("position", DEFAULTS["position"])),
        font_size=float(config.get("font_size", DEFAULTS["font_size"])),
        margin_pt=float(config.get("margin_pt", DEFAULTS["margin_pt"])),
        make_backup=bool(config.get("make_backup", DEFAULTS["make_backup"])),
    )
