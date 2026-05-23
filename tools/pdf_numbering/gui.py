"""Tkinter GUI for the PDF page-numbering tool."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from tools.pdf_numbering.core import Settings, process_folder

# GUI label -> internal position value used by core.Settings.
POSITION_LABELS = {
    "Bottom center": "bottom-center",
    "Bottom right": "bottom-right",
    "Bottom left": "bottom-left",
    "Top right": "top-right",
}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF Page Numberer")
        self.geometry("640x540")
        self.minsize(560, 480)

        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build()
        self.after(100, self._drain_queue)

    # ---- layout -----------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}

        intro = ttk.Label(
            self,
            text=(
                "Select a folder. Every PDF named like  name_1.pdf, name_2.pdf  "
                "will be numbered\nas  1.1, 1.2 ...  /  2.1, 2.2 ...  Originals are "
                "overwritten in place."
            ),
            justify="left",
        )
        intro.pack(fill="x", **pad)

        folder_row = ttk.Frame(self)
        folder_row.pack(fill="x", **pad)
        ttk.Label(folder_row, text="Folder:").pack(side="left")
        self.folder_var = tk.StringVar()
        ttk.Entry(folder_row, textvariable=self.folder_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(folder_row, text="Browse...", command=self._browse).pack(side="left")

        settings_box = ttk.LabelFrame(self, text="Settings")
        settings_box.pack(fill="x", **pad)

        ttk.Label(settings_box, text="Number position:").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        self.position_var = tk.StringVar(value="Bottom center")
        ttk.Combobox(
            settings_box,
            textvariable=self.position_var,
            values=list(POSITION_LABELS),
            state="readonly",
            width=16,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(settings_box, text="Font size:").grid(
            row=1, column=0, sticky="w", padx=6, pady=4
        )
        self.font_var = tk.IntVar(value=10)
        ttk.Spinbox(settings_box, from_=6, to=48, textvariable=self.font_var, width=6).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        ttk.Label(settings_box, text="Margin (pt):").grid(
            row=2, column=0, sticky="w", padx=6, pady=4
        )
        self.margin_var = tk.IntVar(value=28)
        ttk.Spinbox(settings_box, from_=0, to=200, textvariable=self.margin_var, width=6).grid(
            row=2, column=1, sticky="w", padx=6, pady=4
        )

        self.backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            settings_box,
            text="Create .bak backup before overwriting",
            variable=self.backup_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        self.start_btn = ttk.Button(self, text="Start", command=self._start)
        self.start_btn.pack(**pad)

        self.log = ScrolledText(self, height=12, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **pad)

    # ---- helpers ----------------------------------------------------------
    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Select a folder containing PDFs")
        if folder:
            self.folder_var.set(folder)

    def _append(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _settings(self) -> Settings:
        return Settings(
            position=POSITION_LABELS.get(self.position_var.get(), "bottom-center"),
            font_size=float(self.font_var.get()),
            margin_pt=float(self.margin_var.get()),
            make_backup=bool(self.backup_var.get()),
        )

    # ---- actions ----------------------------------------------------------
    def _start(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("No folder", "Please choose a folder first.")
            return
        if self._worker is not None and self._worker.is_alive():
            return

        backup_note = (
            "A .bak backup of each file will be created first.\n\n"
            if self.backup_var.get()
            else "No backups will be created.\n\n"
        )
        if not messagebox.askyesno(
            "Overwrite originals?",
            f"This will overwrite the matching PDF files in:\n\n{folder}\n\n"
            + backup_note
            + "Continue?",
        ):
            return

        settings = self._settings()
        self.start_btn.configure(state="disabled")
        self._append(f"Scanning: {folder}")

        def run() -> None:
            try:
                result = process_folder(
                    folder,
                    settings,
                    progress=lambda m: self._queue.put(("log", m)),
                )
                self._queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("error", str(exc)))

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._append(str(payload))
                elif kind == "done":
                    result = payload  # type: ignore[assignment]
                    self._append(
                        f"\nDone. Processed {result.processed}, "
                        f"skipped {result.skipped}, errors {result.errors} "
                        f"(matched {result.total_matched})."
                    )
                    self.start_btn.configure(state="normal")
                elif kind == "error":
                    self._append(f"Unexpected error: {payload}")
                    self.start_btn.configure(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
