"""PDF page-numbering tool (first tool in office.helpers).

Stamps page numbers of the form ``<chapter>.<page>`` onto every page of each
PDF in a folder whose name ends with ``_<number>.pdf`` (e.g. ``report_1.pdf``
becomes ``1.1``, ``1.2`` ...).

Only :mod:`core` is imported here so the package can be used without a GUI
(and without tkinter installed).
"""

from .core import (
    POSITIONS,
    Settings,
    find_target_pdfs,
    parse_chapter,
    process_folder,
    stamp_pdf,
)

__all__ = [
    "POSITIONS",
    "Settings",
    "find_target_pdfs",
    "parse_chapter",
    "process_folder",
    "stamp_pdf",
]
__version__ = "0.1.0"
