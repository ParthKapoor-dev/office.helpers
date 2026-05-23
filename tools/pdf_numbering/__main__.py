"""Entry point: ``python -m tools.pdf_numbering`` launches the GUI.

Pass ``--background`` to start hidden in the system tray and resume watching.
"""

import sys

from tools.pdf_numbering.gui import main

if __name__ == "__main__":
    main(background="--background" in sys.argv)
