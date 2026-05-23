"""Tkinter GUI + system-tray background agent for the PDF Page Numberer."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import pystray
from PIL import Image, ImageDraw

from tools.pdf_numbering.config import (
    config_dir,
    load_config,
    log_file_path,
    save_config,
    settings_from_config,
)
from tools.pdf_numbering.core import Settings
from tools.pdf_numbering.startup import install_startup, remove_startup
from tools.pdf_numbering.watcher import FolderWatcher, load_state, reconcile, save_state

# GUI label -> internal position value used by core.Settings.
POSITION_LABELS = {
    "Bottom center": "bottom-center",
    "Bottom right": "bottom-right",
    "Bottom left": "bottom-left",
    "Top right": "top-right",
}
POSITION_VALUE_TO_LABEL = {v: k for k, v in POSITION_LABELS.items()}


def _log_to_file(message: str) -> None:
    try:
        path = log_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self, background: bool = False) -> None:
        super().__init__()
        self.title("PDF Page Numberer")
        self.geometry("660x600")
        self.minsize(580, 520)

        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self.watcher: FolderWatcher | None = None
        self.tray_icon: pystray.Icon | None = None
        self.state = load_state()

        self._build()
        self._apply_config(load_config())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_queue)

        if background:
            self.withdraw()
            self._start_watching(confirm=False, install=False)
        elif bool(load_config().get("watch_enabled")):
            self._start_watching(confirm=False, install=False)

    # ---- layout -----------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}

        ttk.Label(
            self,
            text=(
                "Pick a folder. Every PDF named like  name_1.pdf, name_2.pdf  is numbered\n"
                "as  1.1, 1.2 ...  /  2.1, 2.2 ...  Originals are overwritten in place."
            ),
            justify="left",
        ).pack(fill="x", **pad)

        folder_row = ttk.Frame(self)
        folder_row.pack(fill="x", **pad)
        ttk.Label(folder_row, text="Folder:").pack(side="left")
        self.folder_var = tk.StringVar()
        ttk.Entry(folder_row, textvariable=self.folder_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=6
        )
        self.browse_btn = ttk.Button(folder_row, text="Browse...", command=self._browse)
        self.browse_btn.pack(side="left")

        box = ttk.LabelFrame(self, text="Settings")
        box.pack(fill="x", **pad)

        ttk.Label(box, text="Number position:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.position_var = tk.StringVar(value="Bottom center")
        ttk.Combobox(
            box, textvariable=self.position_var, values=list(POSITION_LABELS),
            state="readonly", width=16,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(box, text="Font size:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.font_var = tk.IntVar(value=10)
        ttk.Spinbox(box, from_=6, to=48, textvariable=self.font_var, width=6).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        ttk.Label(box, text="Margin (pt):").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.margin_var = tk.IntVar(value=28)
        ttk.Spinbox(box, from_=0, to=200, textvariable=self.margin_var, width=6).grid(
            row=2, column=1, sticky="w", padx=6, pady=4
        )

        self.backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            box,
            text="Back up each file to backup/ during processing (deleted on success)",
            variable=self.backup_var,
            command=self._save_config,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        self.background_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            actions,
            text="Enable background auto-processing (watch this folder)",
            variable=self.background_var,
            command=self._toggle_background,
        ).pack(side="left")
        self.process_btn = ttk.Button(actions, text="Process now", command=self._process_now)
        self.process_btn.pack(side="right")

        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(self, textvariable=self.status_var, foreground="#444").pack(fill="x", **pad)

        self.log = ScrolledText(self, height=12, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **pad)

    # ---- config <-> widgets ----------------------------------------------
    def _apply_config(self, cfg: dict) -> None:
        self.folder_var.set(str(cfg.get("folder", "")))
        self.position_var.set(POSITION_VALUE_TO_LABEL.get(cfg.get("position"), "Bottom center"))
        self.font_var.set(int(float(cfg.get("font_size", 10))))
        self.margin_var.set(int(float(cfg.get("margin_pt", 28))))
        self.backup_var.set(bool(cfg.get("make_backup", True)))
        self.background_var.set(bool(cfg.get("watch_enabled", False)))

    def _current_config(self) -> dict:
        return {
            "folder": self.folder_var.get().strip(),
            "position": POSITION_LABELS.get(self.position_var.get(), "bottom-center"),
            "font_size": float(self.font_var.get()),
            "margin_pt": float(self.margin_var.get()),
            "make_backup": bool(self.backup_var.get()),
            "watch_enabled": bool(self.background_var.get()),
        }

    def _save_config(self) -> None:
        cfg = self._current_config()
        save_config(cfg)
        if self.watcher is not None:
            self.watcher.set_settings(settings_from_config(cfg))

    def _settings(self) -> Settings:
        return settings_from_config(self._current_config())

    # ---- helpers ----------------------------------------------------------
    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Select a folder containing PDFs")
        if folder:
            self.folder_var.set(folder)
            self._save_config()

    def _append(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _progress(self, message: str) -> None:
        self._queue.put(("log", message))
        _log_to_file(message)

    def _set_status(self, text: str) -> None:
        self._queue.put(("status", text))

    # ---- background watching ---------------------------------------------
    def _toggle_background(self) -> None:
        if self.background_var.get():
            self._start_watching(confirm=True, install=True)
        else:
            self._stop_watching()

    def _start_watching(self, confirm: bool, install: bool) -> None:
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Choose a valid folder first.")
            self.background_var.set(False)
            return
        if self.watcher is not None:
            return
        if confirm and not messagebox.askyesno(
            "Enable background auto-processing?",
            "Matching PDFs in:\n\n"
            f"{folder}\n\n"
            "will be numbered automatically and overwritten whenever they change, "
            "even after this window is closed (the agent lives in the system tray).\n\n"
            "Continue?",
        ):
            self.background_var.set(False)
            return

        self.background_var.set(True)
        self._save_config()
        self._show_tray()
        self.watcher = FolderWatcher(
            folder, self._settings(), progress=self._progress, on_result=self._on_result
        )

        def worker() -> None:
            if install:
                install_startup()
            self.watcher.start()  # type: ignore[union-attr]
            self._set_status(f"Watching {folder}")

        threading.Thread(target=worker, daemon=True).start()

    def _stop_watching(self) -> None:
        self.background_var.set(False)
        self._save_config()
        watcher, self.watcher = self.watcher, None
        if watcher is not None:
            threading.Thread(target=watcher.stop, daemon=True).start()
        remove_startup()
        self._hide_tray()
        self._set_status("Idle.")
        self._append("Background auto-processing disabled.")

    def _process_now(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Choose a valid folder first.")
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._save_config()
        self.process_btn.configure(state="disabled")
        self._append(f"Scanning: {folder}")

        watcher = self.watcher
        settings = self._settings()

        def run() -> None:
            try:
                if watcher is not None:
                    result = watcher.process_now()
                else:
                    result = reconcile(folder, settings, self.state, progress=self._progress)
                    save_state(self.state)
                self._queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("error", str(exc)))

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def _on_result(self, result) -> None:
        if result.processed or result.errors:
            self._queue.put(("done", result))

    # ---- system tray ------------------------------------------------------
    def _make_tray_image(self) -> Image.Image:
        image = Image.new("RGB", (64, 64), "#1f6feb")
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 12, 52, 52), outline="white", width=3)
        draw.text((20, 24), "PN", fill="white")
        return image

    def _show_tray(self) -> None:
        if self.tray_icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open settings", lambda i, item: self._queue.put(("cmd", "show"))),
            pystray.MenuItem(
                "Pause",
                lambda i, item: self._queue.put(("cmd", "toggle_pause")),
                checked=lambda item: bool(self.watcher and self.watcher.paused),
            ),
            pystray.MenuItem("Process now", lambda i, item: self._queue.put(("cmd", "process_now"))),
            pystray.MenuItem("Open log folder", lambda i, item: self._queue.put(("cmd", "open_log"))),
            pystray.MenuItem("Quit", lambda i, item: self._queue.put(("cmd", "quit"))),
        )
        self.tray_icon = pystray.Icon(
            "pdfnumberer", self._make_tray_image(), "PDF Page Numberer", menu
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _hide_tray(self) -> None:
        icon, self.tray_icon = self.tray_icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001
                pass

    # ---- window / lifecycle ----------------------------------------------
    def _on_close(self) -> None:
        if self.watcher is not None:
            self.withdraw()  # keep running in the tray
            self._set_status("Running in the background (system tray).")
        else:
            self._quit()

    def _quit(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        self._hide_tray()
        self.destroy()

    # ---- main loop pump ---------------------------------------------------
    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._append(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "done":
                    result = payload
                    self._append(
                        f"Done. Processed {result.processed}, skipped {result.skipped}, "
                        f"errors {result.errors} (matched {result.total_matched})."
                    )
                    self.process_btn.configure(state="normal")
                elif kind == "error":
                    self._append(f"Unexpected error: {payload}")
                    self.process_btn.configure(state="normal")
                elif kind == "cmd":
                    self._run_command(str(payload))
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _run_command(self, name: str) -> None:
        if name == "show":
            self.deiconify()
            self.lift()
            self.focus_force()
        elif name == "toggle_pause":
            if self.watcher is not None:
                if self.watcher.paused:
                    self.watcher.resume()
                    self._set_status("Watching (resumed).")
                else:
                    self.watcher.pause()
                    self._set_status("Paused.")
        elif name == "process_now":
            self._process_now()
        elif name == "open_log":
            self._open_log_folder()
        elif name == "quit":
            self._quit()

    def _open_log_folder(self) -> None:
        folder = config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except OSError:
            pass


def main(background: bool = False) -> None:
    App(background=background).mainloop()


if __name__ == "__main__":
    main("--background" in sys.argv)
