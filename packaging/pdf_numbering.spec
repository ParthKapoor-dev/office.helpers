# PyInstaller spec for the PDF Page Numberer.
# Build from the repository root:  pyinstaller packaging/pdf_numbering.spec
# Produces a single self-contained Windows executable in dist/.

import os

# SPECPATH is injected by PyInstaller and points to this spec file's directory
# (packaging/). Anchor the entry script and module search path to the repo root
# so the build works regardless of the current working directory.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=["pystray._win32", "PIL"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PDF-Page-Numberer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app: no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
