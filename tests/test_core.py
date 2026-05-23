from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from tools.pdf_numbering.core import (
    Settings,
    find_target_pdfs,
    parse_chapter,
    process_folder,
    stamp_pdf,
)


def _make_pdf(path: Path, pages: int) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    for n in range(pages):
        pdf.drawString(72, 720, f"content page {n + 1}")
        pdf.showPage()
    pdf.save()


def _page_texts(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    return [(page.extract_text() or "").replace(" ", "") for page in reader.pages]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("report_1.pdf", 1),
        ("invoice_2.pdf", 2),
        ("chapter_12.pdf", 12),
        ("a_b_7.pdf", 7),
        ("file_1.PDF", 1),  # case-insensitive extension
        ("doc_007.pdf", 7),
        ("test_1.pdf.pdf", 1),  # Windows hidden-extension double .pdf
        ("test_12.PDF.pdf", 12),
        ("notes.pdf", None),
        ("weird_1x.pdf", None),
        ("nounderscore.pdf", None),
        ("trailing_.pdf", None),
    ],
)
def test_parse_chapter(name, expected):
    assert parse_chapter(name) == expected


def test_find_target_pdfs(tmp_path):
    _make_pdf(tmp_path / "report_1.pdf", 1)
    _make_pdf(tmp_path / "report_2.pdf", 1)
    _make_pdf(tmp_path / "skip.pdf", 1)
    (tmp_path / "notes.txt").write_text("x")
    found = {p.name: c for p, c in find_target_pdfs(tmp_path)}
    assert found == {"report_1.pdf": 1, "report_2.pdf": 2}


def test_process_folder_stamps_numbers(tmp_path):
    _make_pdf(tmp_path / "doc_3.pdf", 4)
    result = process_folder(tmp_path, Settings(make_backup=False))

    assert result.processed == 1
    assert result.errors == 0
    assert result.total_matched == 1

    texts = _page_texts(tmp_path / "doc_3.pdf")
    assert len(texts) == 4
    assert "3.1" in texts[0]
    assert "3.2" in texts[1]
    assert "3.3" in texts[2]
    assert "3.4" in texts[3]


def test_process_folder_multiple_files(tmp_path):
    _make_pdf(tmp_path / "a_1.pdf", 2)
    _make_pdf(tmp_path / "b_2.pdf", 3)
    result = process_folder(tmp_path, Settings(make_backup=False))

    assert result.processed == 2
    assert "1.2" in _page_texts(tmp_path / "a_1.pdf")[1]
    assert "2.3" in _page_texts(tmp_path / "b_2.pdf")[2]


def test_success_removes_backup(tmp_path):
    _make_pdf(tmp_path / "doc_1.pdf", 1)
    result = process_folder(tmp_path, Settings(make_backup=True))

    assert result.processed == 1
    # No .bak files anywhere, and the backup/ folder is cleaned up on success.
    assert list(tmp_path.glob("*.bak")) == []
    assert not (tmp_path / "backup").exists()
    assert "1.1" in _page_texts(tmp_path / "doc_1.pdf")[0]


def test_failure_keeps_backup_in_backup_dir(tmp_path, monkeypatch):
    import tools.pdf_numbering.core as core

    _make_pdf(tmp_path / "doc_1.pdf", 1)
    original = (tmp_path / "doc_1.pdf").read_bytes()

    def boom(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(core.os, "replace", boom)

    with pytest.raises(OSError):
        stamp_pdf(tmp_path / "doc_1.pdf", 1, Settings(make_backup=True))

    backup = tmp_path / "backup" / "doc_1.pdf"
    assert backup.exists()
    assert backup.read_bytes() == original  # a real, recoverable .pdf copy
    assert (tmp_path / "doc_1.pdf").read_bytes() == original  # original untouched
    assert list(tmp_path.glob("tmp*")) == []  # temp file cleaned up


def test_no_backup_dir_when_disabled(tmp_path):
    _make_pdf(tmp_path / "doc_1.pdf", 1)
    process_folder(tmp_path, Settings(make_backup=False))
    assert not (tmp_path / "backup").exists()
    assert list(tmp_path.glob("*.bak")) == []


def test_non_matching_pdf_untouched(tmp_path):
    _make_pdf(tmp_path / "keep.pdf", 1)
    before = (tmp_path / "keep.pdf").read_bytes()
    result = process_folder(tmp_path, Settings(make_backup=False))
    after = (tmp_path / "keep.pdf").read_bytes()

    assert before == after
    assert result.processed == 0
    assert result.skipped == 1


@pytest.mark.parametrize("position", ["bottom-center", "bottom-right", "bottom-left", "top-right"])
def test_all_positions_stamp(tmp_path, position):
    _make_pdf(tmp_path / "p_5.pdf", 1)
    pages = stamp_pdf(tmp_path / "p_5.pdf", 5, Settings(position=position, make_backup=False))
    assert pages == 1
    assert "5.1" in _page_texts(tmp_path / "p_5.pdf")[0]


def test_double_extension_is_stamped(tmp_path):
    # Simulates a file created on Windows with "Hide extensions" on, which
    # turns "doc_4.pdf" into the on-disk name "doc_4.pdf.pdf".
    _make_pdf(tmp_path / "doc_4.pdf.pdf", 2)
    result = process_folder(tmp_path, Settings(make_backup=False))

    assert result.processed == 1
    assert result.skipped == 0
    texts = _page_texts(tmp_path / "doc_4.pdf.pdf")
    assert "4.1" in texts[0]
    assert "4.2" in texts[1]


def test_empty_folder(tmp_path):
    result = process_folder(tmp_path, Settings(make_backup=False))
    assert result.processed == 0
    assert result.total_matched == 0
    assert result.skipped == 0
