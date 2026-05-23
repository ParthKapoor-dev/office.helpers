"""Top-level launcher used as the PyInstaller entry point and for `python app.py`.

Pass --background to start hidden in the system tray and resume watching the
saved folder (used by the Windows 'start at login' shortcut).
"""

import sys

from tools.pdf_numbering.gui import main

if __name__ == "__main__":
    main(background="--background" in sys.argv)
