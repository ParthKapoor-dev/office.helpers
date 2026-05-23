# office.helpers

Small, Windows-first office utilities. The first tool is the **PDF Page Numberer**.

## PDF Page Numberer

Stamps page numbers onto PDFs in a folder. The number comes from the file name:
any PDF named `something_<N>.pdf` is treated as **chapter `N`**, and each of its
pages is stamped `N.1`, `N.2`, `N.3`, …

| File name        | Pages stamped          |
| ---------------- | ---------------------- |
| `report_1.pdf`   | `1.1`, `1.2`, … `1.11` |
| `invoice_2.pdf`  | `2.1`, `2.2`, …        |
| `chapter_12.pdf` | `12.1`, `12.2`, …      |
| `notes.pdf`      | *(skipped — no `_<N>`)* |

Files that don't match `*_<number>.pdf` are left untouched.

### Download (Windows)

Grab the latest `PDF-Page-Numberer.exe` from the
**[Releases](../../releases)** page. It's a single self-contained file — no
Python install required.

> Each tagged build (`vX.Y.Z`) is compiled **and tested on a Windows runner**
> by GitHub Actions before the `.exe` is attached to the release.

### Use it

1. Double-click `PDF-Page-Numberer.exe`.
2. **Browse…** to the folder containing your PDFs.
3. Adjust **Settings** if you like:
   - **Number position** — bottom center / bottom right / bottom left / top right.
   - **Font size** and **Margin (pt)**.
   - **Create .bak backup before overwriting** (on by default).
4. Click **Start** and confirm.

> ⚠️ **The matching PDFs are overwritten in place.** Leave the backup option on
> if you want a `.bak` copy of each original kept alongside it.

## Run from source

```bash
pip install -r requirements.txt
python -m tools.pdf_numbering        # launches the GUI
# or
python app.py
```

(The GUI needs `tkinter`, which ships with the standard Python installer on
Windows and macOS. On Linux install it via your package manager, e.g.
`sudo apt install python3-tk`.)

## Build the Windows .exe yourself

```bash
pip install -r requirements-dev.txt
pyinstaller packaging/pdf_numbering.spec
# -> dist/PDF-Page-Numberer.exe
```

## Develop / test

```bash
pip install -r requirements-dev.txt
pytest
```

All PDF logic lives in `tools/pdf_numbering/core.py` (no GUI imports, fully
unit-tested). The `tkinter` front-end is in `tools/pdf_numbering/gui.py`.

### Known limitations

- Scans the selected folder only (not subfolders).
- Pages with a `/Rotate` flag may place the number using unrotated coordinates;
  standard (unrotated) PDFs — the common case — work correctly.
- Encrypted / password-protected PDFs are reported and skipped, not unlocked.
