"""Folder-watching background agent for the PDF Page Numberer.

GUI-free so the watch *logic* can be unit-tested without tkinter/pystray. Uses
watchdog for instant change detection, a debounce so partially-copied PDFs are
only processed once they settle, and a persisted per-file signature map so the
agent never re-stamps its own output -- even across process restarts (the
auto-start-at-login case).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from tools.pdf_numbering.config import config_dir
from tools.pdf_numbering.core import (
    FileResult,
    FolderResult,
    Settings,
    find_target_pdfs,
    parse_chapter,
    stamp_pdf,
)

Sig = Tuple[float, int]
Progress = Optional[Callable[[str], None]]

BACKUP_DIRNAME = "backup"


def file_sig(path: Path) -> Sig:
    """Cheap change fingerprint: (mtime, size)."""
    stat = path.stat()
    return (stat.st_mtime, stat.st_size)


def should_process(path, state: Dict[Path, Sig]) -> bool:
    """True when ``path`` is a target PDF whose content differs from what we
    last stamped (so our own writes, recorded in ``state``, are skipped)."""
    path = Path(path)
    if path.parent.name == BACKUP_DIRNAME:
        return False
    if parse_chapter(path.name) is None:
        return False
    try:
        sig = file_sig(path)
    except OSError:
        return False
    return state.get(path) != sig


def process_path(
    path,
    settings: Settings,
    state: Dict[Path, Sig],
    progress: Progress = None,
) -> Optional[FileResult]:
    """Stamp a single PDF and record its post-stamp signature. Never raises."""
    path = Path(path)
    chapter = parse_chapter(path.name)
    if chapter is None:
        return None

    def log(message: str) -> None:
        if progress is not None:
            progress(message)

    try:
        pages = stamp_pdf(path, chapter, settings)
        state[path] = file_sig(path)
        log(f"OK    {path.name}  ->  {chapter}.1 ... {chapter}.{pages}")
        return FileResult(path, chapter, "ok", pages)
    except Exception as exc:  # noqa: BLE001 - keep the agent alive on one bad file
        log(f"FAIL  {path.name}: {exc}")
        return FileResult(path, chapter, "error", 0, str(exc))


def reconcile(
    folder,
    settings: Settings,
    state: Dict[Path, Sig],
    progress: Progress = None,
) -> FolderResult:
    """Process only the target PDFs that are new or changed since last stamped,
    and prune state entries for files that no longer exist."""
    folder = Path(folder)
    result = FolderResult()

    def log(message: str) -> None:
        if progress is not None:
            progress(message)

    all_pdfs = [
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"
    ]
    targets = find_target_pdfs(folder)
    matched = {p for p, _ in targets}
    skipped = [p for p in all_pdfs if p not in matched]

    result.total_matched = len(targets)
    result.skipped = len(skipped)

    if skipped:
        log(
            "Skipped (no _<number> right before .pdf -- check for hidden "
            "double extensions like name_1.pdf.pdf):"
        )
        for path in sorted(skipped):
            log(f"  - {path.name}")

    for path, _chapter in targets:
        if not should_process(path, state):
            continue
        file_result = process_path(path, settings, state, progress)
        if file_result is None:
            continue
        result.files.append(file_result)
        if file_result.status == "ok":
            result.processed += 1
        else:
            result.errors += 1

    # Drop tracking for files that have been removed.
    for tracked in list(state):
        if not tracked.exists():
            del state[tracked]

    return result


# --- cross-restart state persistence ---------------------------------------

def _state_file() -> Path:
    return config_dir() / "state.json"


def load_state() -> Dict[Path, Sig]:
    try:
        with open(_state_file(), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return {Path(k): (float(v[0]), int(v[1])) for k, v in raw.items()}
    except (FileNotFoundError, ValueError, OSError, TypeError, KeyError):
        return {}


def save_state(state: Dict[Path, Sig]) -> None:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        with open(_state_file(), "w", encoding="utf-8") as handle:
            json.dump({str(k): [v[0], v[1]] for k, v in state.items()}, handle)
    except OSError:
        pass


# --- watchdog-driven agent --------------------------------------------------

class _Handler(FileSystemEventHandler):
    """Forwards content-changing events to the watcher's debounce.

    Only created/modified/moved/deleted are handled -- read-only access events
    (``opened``/``closed``, emitted by the Linux inotify backend) are ignored so
    that merely viewing a PDF never triggers reprocessing.
    """

    def __init__(self, watcher: "FolderWatcher") -> None:
        self._watcher = watcher

    def _react(self, event) -> None:
        if event.is_directory:
            return
        path = Path(getattr(event, "dest_path", "") or event.src_path)
        if path.parent.name == BACKUP_DIRNAME:
            return
        if path.suffix.lower() != ".pdf":
            return
        self._watcher._schedule()

    def on_created(self, event) -> None:
        self._react(event)

    def on_modified(self, event) -> None:
        self._react(event)

    def on_moved(self, event) -> None:
        self._react(event)

    def on_deleted(self, event) -> None:
        self._react(event)


class FolderWatcher:
    """Watches one folder and auto-numbers PDFs as they appear or change."""

    def __init__(
        self,
        folder,
        settings: Settings,
        progress: Progress = None,
        on_result: Optional[Callable[[FolderResult], None]] = None,
        settle: float = 0.8,
    ) -> None:
        self.folder = Path(folder)
        self.settings = settings
        self.progress = progress
        self.on_result = on_result
        self.settle = settle
        self.state: Dict[Path, Sig] = load_state()
        self.paused = False
        self._observer: Optional[Observer] = None
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._stopped = False

    def _log(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def process_now(self) -> FolderResult:
        with self._lock:
            result = reconcile(self.folder, self.settings, self.state, self.progress)
            save_state(self.state)
        if self.on_result is not None:
            self.on_result(result)
        return result

    def _schedule(self) -> None:
        if self.paused or self._stopped:
            return
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.settle, self.process_now)
        self._timer.daemon = True
        self._timer.start()

    def start(self) -> None:
        self.process_now()  # initial reconcile of whatever is already there
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self.folder), recursive=False)
        self._observer.start()
        self._log(f"Watching {self.folder}")

    def pause(self) -> None:
        self.paused = True
        self._log("Auto-processing paused.")

    def resume(self) -> None:
        self.paused = False
        self._log("Auto-processing resumed.")
        self.process_now()

    def stop(self) -> None:
        self._stopped = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
