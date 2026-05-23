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

> Every push to `main` is compiled **and tested on a Windows runner** by GitHub
> Actions, which then publishes a Release for the version in the `VERSION` file.

### Use it

1. Double-click `PDF-Page-Numberer.exe`.
2. **Browse…** to the folder containing your PDFs.
3. Adjust **Settings** if you like:
   - **Number position** — bottom center / bottom right / bottom left / top right.
   - **Font size** and **Margin (pt)**.
   - **Back up each file to `backup/` during processing** (on by default).
4. Click **Process now** for a one-off run, or enable background mode (below).

> ⚠️ **The matching PDFs are overwritten in place.**

### Background auto-processing (the agent)

Tick **"Enable background auto-processing (watch this folder)"** and the tool
keeps watching the chosen folder and numbers PDFs automatically the moment they
are added or changed — no clicking required.

- It keeps running after you **close the window**, living in the **system tray**
  (right-click the tray icon for *Open settings / Pause / Process now / Open log
  / Quit*).
- It **starts at Windows login** (a shortcut in your Startup folder, no admin),
  so it's always on. Turn the toggle off to stop it and remove the startup entry.
- Your folder + settings are **saved** and resume automatically.
- It never re-numbers a file it already stamped (a per-file fingerprint is kept,
  even across restarts), so there's no runaway double-numbering.

### Backups

When the backup option is on, each file being processed is first copied into a
`backup/` subfolder of your folder (a real `.pdf` with the original name). The
backup is **deleted once that file is processed successfully**, and kept only if
the write fails so you can recover the original.

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

## Cutting a release

Releases are driven by the `VERSION` file (e.g. `v0.1.0`). To publish a new
one, bump the version and push it to `main`:

```bash
echo v0.2.0 > VERSION
git commit -am "Release v0.2.0" && git push origin main
```

The Windows CI builds + tests the `.exe`, then creates the matching git tag and
GitHub Release with the binary attached. Versions that already have a Release
are skipped, so ordinary pushes to `main` don't re-release.

## Develop / test

```bash
pip install -r requirements-dev.txt
pytest
```

Layout (all GUI-free modules are unit-tested):
- `tools/pdf_numbering/core.py` — stamping logic.
- `tools/pdf_numbering/watcher.py` — folder watching + idempotent reconcile.
- `tools/pdf_numbering/config.py` — persisted folder/settings.
- `tools/pdf_numbering/startup.py` — Windows start-at-login shortcut.
- `tools/pdf_numbering/gui.py` — tkinter window + system tray.

### Known limitations

- Scans the selected folder only (not subfolders); the `backup/` subfolder is ignored.
- Pages with a `/Rotate` flag may place the number using unrotated coordinates;
  standard (unrotated) PDFs — the common case — work correctly.
- Encrypted / password-protected PDFs are reported and skipped, not unlocked.
