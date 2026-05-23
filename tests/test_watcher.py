from __future__ import annotations

import time
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import tools.pdf_numbering.watcher as watcher_mod
from tools.pdf_numbering.core import Settings
from tools.pdf_numbering.watcher import (
    FolderWatcher,
    file_sig,
    process_path,
    reconcile,
    should_process,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    # Redirect persisted state away from the real user config dir.
    monkeypatch.setattr(watcher_mod, "config_dir", lambda: tmp_path / "cfg")


def _make_pdf(path: Path, pages: int) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    for n in range(pages):
        pdf.drawString(72, 720, f"body {n}")
        pdf.showPage()
    pdf.save()


def _texts(path: Path) -> list[str]:
    return [(p.extract_text() or "").replace(" ", "") for p in PdfReader(str(path)).pages]


def test_should_process_new_then_unchanged(tmp_path):
    p = tmp_path / "doc_1.pdf"
    _make_pdf(p, 1)
    state: dict = {}
    assert should_process(p, state) is True
    state[p] = file_sig(p)
    assert should_process(p, state) is False


def test_should_process_detects_change(tmp_path):
    p = tmp_path / "doc_1.pdf"
    _make_pdf(p, 1)
    state = {p: file_sig(p)}
    _make_pdf(p, 3)  # size changes
    assert should_process(p, state) is True


def test_should_process_ignores_backup_and_nonmatching(tmp_path):
    (tmp_path / "backup").mkdir()
    backup_file = tmp_path / "backup" / "doc_1.pdf"
    _make_pdf(backup_file, 1)
    assert should_process(backup_file, {}) is False

    nonmatching = tmp_path / "notes.pdf"
    _make_pdf(nonmatching, 1)
    assert should_process(nonmatching, {}) is False


def test_process_path_stamps_and_records(tmp_path):
    p = tmp_path / "doc_3.pdf"
    _make_pdf(p, 1)
    state: dict = {}
    result = process_path(p, Settings(make_backup=False), state)
    assert result is not None and result.status == "ok"
    assert "3.1" in _texts(p)[0]
    assert should_process(p, state) is False  # won't be reprocessed


def test_reconcile_is_idempotent(tmp_path):
    _make_pdf(tmp_path / "doc_1.pdf", 2)
    state: dict = {}
    first = reconcile(tmp_path, Settings(make_backup=False), state)
    assert first.processed == 1
    second = reconcile(tmp_path, Settings(make_backup=False), state)
    assert second.processed == 0  # already stamped -> no re-stamp loop

    texts = _texts(tmp_path / "doc_1.pdf")
    assert texts[0].count("1.1") == 1
    assert "1.2" in texts[1]


def test_reconcile_prunes_deleted(tmp_path):
    p = tmp_path / "doc_1.pdf"
    _make_pdf(p, 1)
    state: dict = {}
    reconcile(tmp_path, Settings(make_backup=False), state)
    assert p in state
    p.unlink()
    reconcile(tmp_path, Settings(make_backup=False), state)
    assert p not in state


def test_state_persists_across_restart(tmp_path):
    p = tmp_path / "doc_5.pdf"
    _make_pdf(p, 1)
    state: dict = {}
    reconcile(tmp_path, Settings(make_backup=False), state)
    watcher_mod.save_state(state)

    reloaded = watcher_mod.load_state()
    assert reloaded.get(p) == file_sig(p)


def test_folder_watcher_auto_processes(tmp_path):
    watcher = FolderWatcher(tmp_path, Settings(make_backup=False), settle=0.3)
    watcher.start()  # initial reconcile of empty folder
    try:
        _make_pdf(tmp_path / "doc_9.pdf", 1)
        deadline = time.time() + 8.0
        stamped = False
        while time.time() < deadline:
            if "9.1" in _texts(tmp_path / "doc_9.pdf")[0]:
                stamped = True
                break
            time.sleep(0.2)
        assert stamped, "watcher did not stamp the new file in time"

        time.sleep(1.0)  # let any further events settle
        assert _texts(tmp_path / "doc_9.pdf")[0].count("9.1") == 1  # no double-stamp
    finally:
        watcher.stop()
