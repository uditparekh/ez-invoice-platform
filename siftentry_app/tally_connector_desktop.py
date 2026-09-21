"""Small desktop status window for the SiftEntry Tally connector."""

from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any, Dict, Optional

try:
    from .tally_connector_runtime import (
        ConnectorConfig,
        default_config_path,
        default_status_path,
        load_config,
        poll_once,
        save_config,
        test_connection,
        connection_config_error,
        APP_VERSION,
        OutboxUnreadable,
        write_status,
    )
except ImportError:
    from tally_connector_runtime import (
        ConnectorConfig,
        default_config_path,
        default_status_path,
        load_config,
        poll_once,
        save_config,
        test_connection,
        connection_config_error,
        APP_VERSION,
        OutboxUnreadable,
        write_status,
    )


class TallyConnectorWindow:
    BG = "#F8FAFC"
    CARD = "#FFFFFF"
    FIELD = "#F8FAFC"
    BORDER = "#DCE4F0"
    INK = "#08111F"
    MUTED = "#667085"
    LABEL = "#98A2B3"
    PRIMARY = "#4F46E5"
    PRIMARY_DARK = "#4338CA"
    SUCCESS = "#16A34A"
    SUCCESS_BG = "#DCFCE7"
    DANGER = "#EF4444"
    FONT = "Segoe UI"

    def __init__(
        self,
        root: tk.Tk,
        config_path: Optional[Path] = None,
        start_minimized: bool = False,
        autostart: bool = False,
    ) -> None:
        self.root = root
        self.config_path = config_path or default_config_path()
        self.status_path = default_status_path()
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None

        self.config = load_config(self.config_path)
        self.cloud_url = tk.StringVar(value=self.config.cloud_url)
        self.workspace_id = tk.StringVar(value=self.config.workspace_id)
        self.token = tk.StringVar(value=self.config.token)
        self.tally_url = tk.StringVar(value=self.config.tally_url)
        self.poll_interval = tk.IntVar(value=self.config.poll_interval)
        self.claim_limit = tk.IntVar(value=self.config.claim_limit)
        self.dry_run = tk.BooleanVar(value=self.config.dry_run)

        self.running = tk.StringVar(value="Stopped")
        self.siftentry_status = tk.StringVar(value="Not connected")
        self.tally_status = tk.StringVar(value="Not tested")
        self.last_invoice = tk.StringVar(value="None")
        self.failed_jobs = tk.StringVar(value="0")
        self.last_message = tk.StringVar(value="Ready.")
        self.company_status = tk.StringVar(value="Not checked")
        self.master_status = tk.StringVar(value="Not verified — master sync pending")
        self.running_badge: Optional[tk.Label] = None

        self.poll_lock = threading.Lock()
        self._build_window()
        self.root.after(250, self._drain_events)
        if start_minimized:
            self.root.iconify()
        if autostart:
            # Launched at Windows sign-in: begin polling by itself when the
            # saved settings are complete, so a rebooted PC resumes posting
            # without anyone clicking Start.
            config = self.current_config()
            if config.cloud_url.strip() and config.token.strip():
                self.root.after(1500, self.start)
                self._append_log("Auto-starting connector (launched at sign-in).")
            else:
                self._append_log("Not auto-starting: settings are incomplete.")

    def _build_window(self) -> None:
        self.root.title("SiftEntry Tally Connector " + APP_VERSION)
        self.root.geometry("980x720")
        self.root.minsize(640, 480)
        self.root.configure(bg=self.BG)

        # Reserve feedback and actions before allocating the scrollable body.
        # At Windows 125/150% scaling no fixed-height form can hide an error.
        self.message_label = tk.Label(self.root, textvariable=self.last_message,
            bg="#EEF2FF", fg=self.INK, font=(self.FONT, 11), justify="left",
            anchor="w", padx=16, pady=10, wraplength=900)
        self.message_label.pack(side="top", fill="x")
        self.controls = tk.Frame(self.root, bg=self.BG, padx=10, pady=10)
        self.controls.pack(side="bottom", fill="x")
        viewport = tk.Frame(self.root, bg=self.BG)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, bg=self.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        outer = tk.Frame(canvas, bg=self.BG, padx=16, pady=16)
        window_id = canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        def resize(event):
            canvas.itemconfigure(window_id, width=event.width)
            self.message_label.configure(wraplength=max(300, event.width - 32))
        canvas.bind("<Configure>", resize)
        self.root.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-1 if event.delta > 0 else 1, "units"))

        header = tk.Frame(outer, bg=self.BG)
        header.pack(fill="x", pady=(0, 18))
        self._logo(header).pack(side="left", padx=(0, 16))

        title_block = tk.Frame(header, bg=self.BG)
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_block,
            text="SiftEntry Tally Connector",
            bg=self.BG,
            fg=self.INK,
            font=(self.FONT, 24, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Securely posts approved SiftEntry invoices into the local TallyPrime company.",
            bg=self.BG,
            fg=self.MUTED,
            font=(self.FONT, 12),
        ).pack(anchor="w", pady=(2, 0))

        status_grid = tk.Frame(outer, bg=self.BG)
        status_grid.pack(fill="x", pady=(0, 18))
        for index in range(2):
            status_grid.columnconfigure(index, weight=1, uniform="status")
        self._status_card(status_grid, 0, 0, "Connected to SiftEntry", self.siftentry_status)
        self._status_card(status_grid, 0, 1, "Tally detected", self.tally_status)
        self._status_card(status_grid, 1, 0, "Configured company", self.company_status)
        self._status_card(status_grid, 1, 1, "Master readiness", self.master_status)

        form_outer, form = self._panel(outer)
        form_outer.pack(fill="x", pady=(0, 16))
        tk.Label(
            form,
            text="Connector settings",
            bg=self.CARD,
            fg=self.INK,
            font=(self.FONT, 15, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        field_grid = tk.Frame(form, bg=self.CARD)
        field_grid.pack(fill="x")
        field_grid.columnconfigure(0, weight=1, minsize=260)
        field_grid.columnconfigure(1, weight=1, minsize=260)
        self._field(field_grid, 0, 0, "SiftEntry URL", self.cloud_url)
        self._field(field_grid, 0, 1, "Workspace ID", self.workspace_id)
        self._field(field_grid, 1, 0, "Connector token", self.token, show="*")
        self._field(field_grid, 1, 1, "Tally URL", self.tally_url)

        compact = tk.Frame(form, bg=self.CARD)
        compact.pack(fill="x", pady=(12, 0))
        self._compact_number(compact, "Poll seconds", self.poll_interval, 0, 5, 300)
        self._compact_number(compact, "Claim limit", self.claim_limit, 1, 1, 25)
        tk.Checkbutton(
            compact,
            text="Dry run only",
            variable=self.dry_run,
            bg=self.CARD,
            fg=self.MUTED,
            activebackground=self.CARD,
            activeforeground=self.INK,
            selectcolor=self.CARD,
            font=(self.FONT, 11),
            bd=0,
            highlightthickness=0,
        ).grid(row=0, column=2, sticky="w", padx=(30, 0))

        controls = self.controls
        for column in range(3):
            controls.columnconfigure(column, weight=1)
        actions = [("Save settings", lambda: self.save_settings(notify=True)),
                   ("Test connection", self.test_tally), ("Poll once", self.poll_once_now),
                   ("Start connector", self.start), ("Stop", self.stop)]
        for index, (label, action) in enumerate(actions):
            self._button(controls, label, action, primary=label == "Start connector").grid(
                row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
        self.running_badge = tk.Label(
            controls,
            textvariable=self.running,
            bg="#EEF2F7",
            fg=self.MUTED,
            font=(self.FONT, 11, "bold"),
            padx=18,
            pady=8,
        )
        self.running_badge.grid(row=1, column=2, sticky="ew", padx=4)

        log_outer, log_frame = self._panel(outer)
        log_outer.pack(fill="both", expand=True)
        tk.Label(
            log_frame,
            text="Activity",
            bg=self.CARD,
            fg=self.INK,
            font=(self.FONT, 15, "bold"),
        ).pack(anchor="w", pady=(0, 12))
        activity_border = tk.Frame(log_frame, bg=self.BORDER)
        activity_border.pack(fill="both", expand=True)
        self.activity = tk.Text(
            activity_border,
            height=8,
            wrap="word",
            bg=self.CARD,
            fg=self.INK,
            bd=0,
            relief="flat",
            font=("Consolas", 10),
            padx=12,
            pady=10,
            insertbackground=self.INK,
        )
        self.activity.pack(fill="both", expand=True, padx=1, pady=1)
        self._append_log("Status window ready.")

    def _logo(self, parent: tk.Widget) -> tk.Canvas:
        logo = tk.Canvas(parent, width=56, height=56, bg=self.BG, highlightthickness=0)
        logo.create_rectangle(4, 4, 52, 52, fill=self.PRIMARY, outline=self.PRIMARY)
        logo.create_line(21, 17, 34, 29, 21, 41, fill="#FFFFFF", width=5, capstyle="round", joinstyle="round")
        logo.create_line(20, 42, 42, 42, fill="#67E8F9", width=5, capstyle="round")
        return logo

    def _panel(self, parent: tk.Widget) -> tuple[tk.Frame, tk.Frame]:
        border = tk.Frame(parent, bg=self.BORDER)
        inner = tk.Frame(border, bg=self.CARD, padx=16, pady=16)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return border, inner

    def _status_card(self, parent: tk.Frame, row: int, column: int, title: str, value: tk.StringVar) -> None:
        border = tk.Frame(parent, bg=self.BORDER)
        border.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 10, 0),
            pady=(0 if row == 0 else 10, 0),
        )
        card = tk.Frame(border, bg=self.CARD, padx=18, pady=16)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(
            card,
            text=title.upper(),
            bg=self.CARD,
            fg=self.LABEL,
            font=(self.FONT, 10, "bold"),
        ).pack(anchor="w")
        row_frame = tk.Frame(card, bg=self.CARD)
        row_frame.pack(fill="x", pady=(8, 0))
        # Do not show a permanent green dot beside a disconnected/untested state.
        tk.Label(
            row_frame,
            textvariable=value,
            bg=self.CARD,
            fg=self.INK,
            font=(self.FONT, 16, "bold"),
            wraplength=240,
            justify="left",
        ).pack(side="left", fill="x", expand=True, anchor="w")

    def _field(
        self,
        parent: tk.Frame,
        row: int,
        column: int,
        label: str,
        value: tk.StringVar,
        show: str = "",
    ) -> None:
        cell = tk.Frame(parent, bg=self.CARD)
        cell.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 16, 0), pady=(0, 12))
        cell.columnconfigure(0, weight=1)
        tk.Label(cell, text=label, bg=self.CARD, fg=self.MUTED, font=(self.FONT, 10, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 6),
        )
        entry = tk.Entry(
            cell,
            textvariable=value,
            show=show,
            bg=self.FIELD,
            fg=self.INK,
            insertbackground=self.INK,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#CBD5E1",
            highlightcolor=self.PRIMARY,
            font=(self.FONT, 12),
        )
        entry.grid(row=1, column=0, sticky="ew", ipady=9)

    def _compact_number(
        self,
        parent: tk.Frame,
        label: str,
        value: tk.IntVar,
        column: int,
        from_value: int,
        to_value: int,
    ) -> None:
        group = tk.Frame(parent, bg=self.CARD)
        group.grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else 28, 0))
        tk.Label(group, text=label, bg=self.CARD, fg=self.MUTED, font=(self.FONT, 10, "bold")).pack(
            side="left",
            padx=(0, 10),
        )
        spinbox = tk.Spinbox(
            group,
            from_=from_value,
            to=to_value,
            textvariable=value,
            width=7,
            bg=self.FIELD,
            fg=self.INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#CBD5E1",
            highlightcolor=self.PRIMARY,
            font=(self.FONT, 11),
        )
        spinbox.pack(side="left", ipady=5)

    def _button(self, parent: tk.Widget, text: str, command: Any, primary: bool = False) -> tk.Button:
        bg = self.PRIMARY if primary else self.CARD
        fg = "#FFFFFF" if primary else self.INK
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=self.PRIMARY_DARK if primary else self.FIELD,
            activeforeground=fg, font=(self.FONT, 11, "bold"), padx=10, pady=8,
            relief="solid", bd=1, takefocus=True)

    def _set_running_state(self, is_running: bool) -> None:
        self.running.set("Running" if is_running else "Stopped")
        if not self.running_badge:
            return
        self.running_badge.configure(
            bg=self.SUCCESS_BG if is_running else "#EEF2F7",
            fg="#166534" if is_running else self.MUTED,
        )

    def current_config(self) -> ConnectorConfig:
        return ConnectorConfig(
            cloud_url=self.cloud_url.get().strip(),
            workspace_id=self.workspace_id.get().strip(),
            token=self.token.get().strip(),
            tally_url=self.tally_url.get().strip() or "http://localhost:9000",
            poll_interval=max(5, int(self.poll_interval.get())),
            claim_limit=max(1, min(25, int(self.claim_limit.get()))),
            dry_run=bool(self.dry_run.get()),
            config_path=str(self.config_path),
        )

    def _is_busy(self) -> bool:
        return bool(self.worker and self.worker.is_alive()) or self.poll_lock.locked()

    def save_settings(self, notify: bool = False) -> bool:
        if self._is_busy():
            self._append_log("Stop the connector and wait for the current check before saving settings.")
            return False
        try:
            config = self.current_config()
        except (ValueError, tk.TclError):
            self._append_log("Poll seconds and claim limit must be whole numbers.")
            return False
        problem = connection_config_error(config)
        if problem:
            self._append_log(problem)
            return False
        try:
            saved_path = save_config(config, self.config_path)
        except OutboxUnreadable:
            self._append_log("Pending or unreadable recovery data prevents changing settings. Preserve the files and contact support.")
            return False
        except OSError:
            self._append_log("Settings could not be saved. Check folder permissions or contact support.")
            return False
        self.config = config
        self._append_log("Saved settings to " + str(saved_path))
        if notify:
            messagebox.showinfo("SiftEntry Tally Connector", "Settings saved.")
        return True

    def test_tally(self) -> None:
        if self._is_busy():
            self._append_log("Stop the connector and wait for the current poll before running a read-only test.")
            return
        try:
            config = self.current_config()
        except (ValueError, tk.TclError):
            self._append_log("Poll seconds and claim limit must be whole numbers.")
            return
        self._append_log("Checking cloud authentication and Tally. This test never claims or posts invoices.")
        self.worker = threading.Thread(target=self._test_tally_worker, args=(config,), daemon=True)
        self.worker.start()

    def _test_tally_worker(self, config: ConnectorConfig) -> None:
        self._run_check(config, diagnostic=True)

    def _run_check(self, config: ConnectorConfig, diagnostic: bool = False) -> None:
        try:
            with self.poll_lock:
                status = test_connection(config) if diagnostic else poll_once(config)
            write_status(status, self.status_path)
            self.events.put({"type": "poll", "status": status})
        except Exception:
            self.stop_event.set()
            self.events.put({"type": "error", "message":
                "Connector paused after an unexpected error. Preserve recovery files and contact support; do not re-enter vouchers."})

    def poll_once_now(self) -> None:
        if self.worker and self.worker.is_alive():
            self._append_log("Connector is already running; background polling covers this.")
            return
        if not self.poll_lock.acquire(blocking=False):
            self._append_log("A poll is already in progress.")
            return
        self.poll_lock.release()
        if not self.save_settings():
            return
        self._append_log("Polling SiftEntry once.")
        self.worker = threading.Thread(target=self._poll_once_worker, args=(self.config,), daemon=True)
        self.worker.start()

    def _poll_once_worker(self, config: ConnectorConfig) -> None:
        # Mutual exclusion with the background loop: a manual poll can never
        # overlap a scheduled one, so one machine cannot race itself.
        self._run_check(config)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.save_settings():
            return
        self.stop_event.clear()
        self._set_running_state(True)
        self.worker = threading.Thread(target=self._poll_loop, args=(self.config,), daemon=True)
        self.worker.start()
        self._append_log("Connector started.")

    def stop(self) -> None:
        self.stop_event.set()
        self._set_running_state(False)
        self._append_log("Connector stopped.")

    def _poll_loop(self, config: ConnectorConfig) -> None:
        while not self.stop_event.is_set():
            self._run_check(config)
            self.stop_event.wait(config.poll_interval)

    def _drain_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event.get("type") == "error":
                self._set_running_state(False)
                self._append_log(event["message"])
            elif event.get("type") == "poll":
                self._apply_poll_status(event["status"])
        self.root.after(250, self._drain_events)

    def _apply_poll_status(self, status: Dict[str, Any]) -> None:
        connected = status.get("connected_to_siftentry")
        if connected is True:
            self.siftentry_status.set("Connected")
        elif connected is False:
            self.siftentry_status.set("Disconnected")
        else:
            self.siftentry_status.set("Not checked")
        self.tally_status.set("Online" if status.get("tally_detected") else "Offline")
        for key, variable in (("company", self.company_status), ("masters", self.master_status)):
            check = status.get("checks", {}).get(key)
            if check:
                variable.set(check["message"])
        if status.get("last_posted_invoice"):
            self.last_invoice.set(self._short_text(str(status.get("last_posted_invoice")), 34))
        self.failed_jobs.set(str(status.get("failed_jobs", 0)))
        self.last_message.set(str(status.get("message", "")))
        self._append_log(str(status.get("message", "Polling completed.")))

    @staticmethod
    def _short_text(value: str, limit: int) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(0, limit - 1)].rstrip() + "..."

    def _append_log(self, message: str) -> None:
        self.last_message.set(message)
        timestamp = time.strftime("%H:%M:%S")
        self.activity.insert("end", f"[{timestamp}] {message}\n")
        self.activity.see("end")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open the SiftEntry Tally Connector status window.")
    parser.add_argument("--config", default="", help="Optional connector config JSON path.")
    parser.add_argument("--minimized", action="store_true", help="Start minimized.")
    parser.add_argument("--autostart", action="store_true", help="Begin polling automatically if settings are complete.")
    parser.add_argument("--self-test", action="store_true", help="Run isolated packaging/UI checks without connecting to a workspace.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.self_test:
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix="siftentry-self-test-") as directory:
            config_path = Path(directory) / "connector_config.json"
            save_config(ConnectorConfig(cloud_url="https://example.invalid", workspace_id="self-test", token="synthetic"), config_path)
            root = tk.Tk()
            root.withdraw()
            scheduled = []
            original_after = root.after
            def record_after(delay, callback=None, *arguments):
                scheduled.append(delay)
                return original_after(delay, callback, *arguments)
            root.after = record_after
            window = TallyConnectorWindow(root, config_path=config_path, autostart=True)
            assert 1500 in scheduled, "Autostart callback was not scheduled"
            assert window.current_config().config_path == str(config_path)
            messages = []
            window._append_log = messages.append
            window.worker = SimpleNamespace(is_alive=lambda: True)
            window.poll_once_now()
            assert any("background polling" in message for message in messages)
            root.update_idletasks()
            # Check the layout at small work areas and high Windows DPI.
            # All essential actions and the feedback strip stay on-screen.
            for scaling in (1.0, 1.5, 2.0):
                root.tk.call("tk", "scaling", scaling)
                root.geometry("800x600")
                root.deiconify()
                root.update()
                assert window.controls.winfo_y() + window.controls.winfo_height() <= root.winfo_height()
                assert window.message_label.winfo_y() == 0
                assert window.controls.winfo_height() > 40
            root.destroy()
        return
    root = tk.Tk()
    config_path = Path(args.config) if args.config else None
    TallyConnectorWindow(
        root,
        config_path=config_path,
        start_minimized=args.minimized,
        autostart=args.autostart or args.minimized,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
