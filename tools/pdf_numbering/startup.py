"""Windows 'start at login' integration via a Startup-folder shortcut.

Creates/removes ``…\\Startup\\PDF Page Numberer.lnk`` pointing at the running
executable with ``--background`` so the agent launches hidden (to tray) at every
login. No admin rights and no extra Python dependency (the .lnk is created with
a small PowerShell snippet). All functions are no-ops off Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "PDF Page Numberer.lnk"


def _is_windows() -> bool:
    return sys.platform == "win32"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def is_startup_installed() -> bool:
    return _is_windows() and shortcut_path().exists()


def install_startup() -> bool:
    """Create the Startup shortcut. Returns True on success / no-op off Windows."""
    if not _is_windows():
        return False

    target = sys.executable
    link = shortcut_path()
    startup_dir().mkdir(parents=True, exist_ok=True)

    # When frozen by PyInstaller, sys.executable is the app .exe; launch it with
    # --background. When running from source it is python.exe, so pass the script.
    if getattr(sys, "frozen", False):
        arguments = "--background"
        workdir = str(Path(target).parent)
    else:
        arguments = f'"{os.path.abspath("app.py")}" --background'
        workdir = os.getcwd()

    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{link}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Arguments = '{arguments}'; "
        f"$s.WorkingDirectory = '{workdir}'; "
        "$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def remove_startup() -> bool:
    """Delete the Startup shortcut if present."""
    if not _is_windows():
        return False
    try:
        shortcut_path().unlink(missing_ok=True)
        return True
    except OSError:
        return False
