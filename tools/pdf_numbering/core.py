"""Core PDF page-numbering logic.

Deliberately free of any GUI imports so it can be unit-tested and reused.
A PDF named ``<anything>_<number>.pdf`` is stamped with page numbers
``<number>.1``, ``<number>.2`` ... on each of its pages.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

# Matches a trailing "_<digits>" followed by one or more ".pdf" extensions
# (case-insensitive). The repeated extension tolerates the common Windows case
# where "Hide extensions for known file types" turns name_1.pdf into the
# on-disk name name_1.pdf.pdf.
CHAPTER_RE = re.compile(r"_(\d+)(?:\.pdf)+$", re.IGNORECASE)

POSITIONS: Tuple[str, ...] = (
    "bottom-center",
    "bottom-right",
    "bottom-left",
    "top-right",
)


@dataclass
class Settings:
    """User-configurable stamping options (exposed in the GUI settings panel)."""

    position: str = "bottom-center"
    font_size: float = 10.0
    margin_pt: float = 28.0  # ~0.4 inch
    make_backup: bool = True
    font_name: str = "Helvetica"


@dataclass
class FileResult:
    path: Path
    chapter: int
    status: str  # "ok" | "error"
    pages: int = 0
    error: str = ""


@dataclass
class FolderResult:
    total_matched: int = 0
    processed: int = 0
    skipped: int = 0  # PDFs in the folder that did not match the pattern
    errors: int = 0
    files: List[FileResult] = field(default_factory=list)


def parse_chapter(filename: str) -> Optional[int]:
    """Return the trailing number in ``*_<number>.pdf``, or ``None`` if absent."""
    match = CHAPTER_RE.search(filename)
    return int(match.group(1)) if match else None


def find_target_pdfs(folder) -> List[Tuple[Path, int]]:
    """Non-recursively list ``(path, chapter)`` for matching PDFs in ``folder``."""
    folder = Path(folder)
    targets: List[Tuple[Path, int]] = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file():
            continue
        chapter = parse_chapter(entry.name)
        if chapter is not None:
            targets.append((entry, chapter))
    return targets


def _make_overlay_bytes(text: str, width: float, height: float, settings: Settings) -> bytes:
    """Render a single-page PDF (matching the target page size) holding ``text``."""
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(width, height))
    pdf.setFont(settings.font_name, settings.font_size)
    margin = settings.margin_pt
    position = settings.position

    if position == "bottom-right":
        pdf.drawRightString(width - margin, margin, text)
    elif position == "bottom-left":
        pdf.drawString(margin, margin, text)
    elif position == "top-right":
        pdf.drawRightString(width - margin, height - margin - settings.font_size, text)
    else:  # "bottom-center" and any unknown value
        pdf.drawCentredString(width / 2.0, margin, text)

    pdf.save()
    return buf.getvalue()


def stamp_pdf(path, chapter: int, settings: Settings) -> int:
    """Stamp ``chapter.<page>`` onto each page of ``path`` and overwrite it.

    Returns the number of pages stamped. Raises ``ValueError`` for encrypted
    PDFs. Writing is done to a temp file in the same directory followed by an
    atomic ``os.replace`` so a failure can never leave a half-written file in
    place of the original.
    """
    path = Path(path)

    # Read fully into memory and close the handle, so the atomic replace below
    # works on Windows (which forbids replacing a file that is still open).
    reader = PdfReader(BytesIO(path.read_bytes()))

    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - normalize to a clean message
            raise ValueError("encrypted / password-protected PDF") from exc
        if int(decrypted) == 0:
            raise ValueError("encrypted / password-protected PDF")

    # Clone into the writer first, then stamp the writer-owned pages. Merging
    # onto reader-owned pages is deprecated (and unreliable) in modern pypdf.
    writer = PdfWriter(clone_from=reader)
    for index, page in enumerate(writer.pages, start=1):
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)
        overlay_bytes = _make_overlay_bytes(f"{chapter}.{index}", width, height, settings)
        overlay_page = PdfReader(BytesIO(overlay_bytes)).pages[0]
        page.merge_page(overlay_page)

    if settings.make_backup:
        shutil.copy2(path, path.with_name(path.name + ".bak"))

    fd, tmp_name = tempfile.mkstemp(suffix=".pdf", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            writer.write(handle)
        os.replace(tmp_name, str(path))
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise

    return len(writer.pages)


def process_folder(
    folder,
    settings: Settings,
    progress: Optional[Callable[[str], None]] = None,
) -> FolderResult:
    """Stamp every matching PDF in ``folder``; never raises on a single bad file."""

    def log(message: str) -> None:
        if progress is not None:
            progress(message)

    folder = Path(folder)
    result = FolderResult()

    all_pdfs = [
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"
    ]
    targets = find_target_pdfs(folder)
    matched_paths = {p for p, _ in targets}
    skipped_pdfs = [p for p in all_pdfs if p not in matched_paths]

    result.total_matched = len(targets)
    result.skipped = len(skipped_pdfs)

    if skipped_pdfs:
        log(
            "Skipped (no _<number> right before .pdf -- check for hidden "
            "double extensions like name_1.pdf.pdf):"
        )
        for path in sorted(skipped_pdfs):
            log(f"  - {path.name}")

    if not targets:
        log("No PDFs matching *_<number>.pdf found in this folder.")
        return result

    for path, chapter in targets:
        try:
            pages = stamp_pdf(path, chapter, settings)
            result.processed += 1
            result.files.append(FileResult(path, chapter, "ok", pages))
            log(f"OK    {path.name}  ->  {chapter}.1 ... {chapter}.{pages}")
        except Exception as exc:  # noqa: BLE001 - keep going on a single failure
            result.errors += 1
            result.files.append(FileResult(path, chapter, "error", 0, str(exc)))
            log(f"FAIL  {path.name}: {exc}")

    return result
