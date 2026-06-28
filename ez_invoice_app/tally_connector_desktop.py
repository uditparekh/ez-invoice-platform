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
        test_tally_connection,
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
        test_tally_connection,
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

    def __init__(self, root: tk.Tk, config_path: Optional[Path] = None, start_minimized: bool = False) -> None:
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
        self.running_badge: Optional[tk.Label] = None

        self._build_window()
        self.root.after(250, self._drain_events)
        if start_minimized:
            self.root.iconify()

    def _build_window(self) -> None:
        self.root.title("SiftEntry Tally Connector")
        self.root.geometry("980x720")
        self.root.minsize(900, 660)
        self.root.configure(bg=self.BG)

        outer = tk.Frame(self.root, bg=self.BG, padx=26, pady=26)
        outer.pack(fill="both", expand=True)

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
        self._status_card(status_grid, 1, 0, "Last posted invoice", self.last_invoice)
        self._status_card(status_grid, 1, 1, "Retry failed jobs", self.failed_jobs)

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

        controls = tk.Frame(outer, bg=self.BG)
        controls.pack(fill="x", pady=(0, 16))
        self._button(controls, "Save settings", lambda: self.save_settings(notify=True)).pack(
            side="left",
            padx=(0, 10),
        )
        self._button(controls, "Test Tally", self.test_tally).pack(side="left", padx=(0, 10))
        self._button(controls, "Poll once", self.poll_once_now).pack(side="left", padx=(0, 10))
        self._button(controls, "Start connector", self.start, primary=True).pack(side="left", padx=(0, 10))
        self._button(controls, "Stop", self.stop).pack(side="left")
        self.running_badge = tk.Label(
            controls,
            textvariable=self.running,
            bg="#EEF2F7",
            fg=self.MUTED,
            font=(self.FONT, 11, "bold"),
            padx=18,
            pady=8,
        )
        self.running_badge.pack(side="right")

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
        if title.lower() in {"connected to siftentry", "tally detected"}:
            tk.Label(row_frame, text="●", bg=self.CARD, fg=self.SUCCESS, font=(self.FONT, 13, "bold")).pack(
                side="left",
                padx=(0, 8),
            )
        tk.Label(
            row_frame,
            textvariable=value,
            bg=self.CARD,
            fg=self.INK,
            font=(self.FONT, 16, "bold"),
            wraplength=390,
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

    def _button(self, parent: tk.Widget, text: str, command: Any, primary: bool = False) -> tk.Frame:
        bg = self.PRIMARY if primary else self.CARD
        fg = "#FFFFFF" if primary else self.INK
        border_color = self.PRIMARY if primary else "#CBD5E1"
        outer = tk.Frame(parent, bg=border_color)
        label = tk.Label(
            outer,
            text=text,
            bg=bg,
            fg=fg,
            font=(self.FONT, 11, "bold"),
            padx=22,
            pady=11,
            cursor="hand2",
        )
        label.pack(fill="both", expand=True, padx=1, pady=1)

        def click(_event: Any = None) -> None:
            command()

        def hover(_event: Any = None) -> None:
            label.configure(bg=self.PRIMARY_DARK if primary else self.FIELD)

        def leave(_event: Any = None) -> None:
            label.configure(bg=bg)

        for widget in (outer, label):
            widget.bind("<Button-1>", click)
            widget.bind("<Enter>", hover)
            widget.bind("<Leave>", leave)
        return outer

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
        )

    def save_settings(self, notify: bool = False) -> None:
        config = self.current_config()
        saved_path = save_config(config, self.config_path)
        self.config = config
        self._append_log("Saved settings to " + str(saved_path))
        if notify:
            messagebox.showinfo("SiftEntry Tally Connector", "Settings saved.")

    def test_tally(self) -> None:
        self._append_log("Testing TallyPrime at " + self.tally_url.get().strip())
        threading.Thread(target=self._test_tally_worker, daemon=True).start()

    def _test_tally_worker(self) -> None:
        result = test_tally_connection(self.current_config().tally_url)
        self.events.put({"type": "tally_test", "result": result})

    def poll_once_now(self) -> None:
        self.save_settings()
        self._append_log("Polling SiftEntry once.")
        threading.Thread(target=self._poll_once_worker, daemon=True).start()

    def _poll_once_worker(self) -> None:
        status = poll_once(self.current_config())
        write_status(status, self.status_path)
        self.events.put({"type": "poll", "status": status})

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.save_settings()
        self.stop_event.clear()
        self._set_running_state(True)
        self.worker = threading.Thread(target=self._poll_loop, daemon=True)
        self.worker.start()
        self._append_log("Connector started.")

    def stop(self) -> None:
        self.stop_event.set()
        self._set_running_state(False)
        self._append_log("Connector stopped.")

    def _poll_loop(self) -> None:
        while not self.stop_event.is_set():
            status = poll_once(self.current_config())
            write_status(status, self.status_path)
            self.events.put({"type": "poll", "status": status})
            for _ in range(max(1, self.current_config().poll_interval)):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def _drain_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event.get("type") == "tally_test":
                self._apply_tally_result(event["result"])
            elif event.get("type") == "poll":
                self._apply_poll_status(event["status"])
        self.root.after(250, self._drain_events)

    def _apply_tally_result(self, result: Dict[str, Any]) -> None:
        ok = bool(result.get("success"))
        self.tally_status.set("Online" if ok else "Offline")
        self._append_log(("Tally test passed: " if ok else "Tally test failed: ") + str(result.get("message", result)))

    def _apply_poll_status(self, status: Dict[str, Any]) -> None:
        connected = status.get("connected_to_siftentry")
        if connected is True:
            self.siftentry_status.set("Connected")
        elif connected is False:
            self.siftentry_status.set("Disconnected")
        else:
            self.siftentry_status.set("Not checked")
        self.tally_status.set("Online" if status.get("tally_detected") else "Offline")
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
        timestamp = time.strftime("%H:%M:%S")
        self.activity.insert("end", f"[{timestamp}] {message}\n")
        self.activity.see("end")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open the SiftEntry Tally Connector status window.")
    parser.add_argument("--config", default="", help="Optional connector config JSON path.")
    parser.add_argument("--minimized", action="store_true", help="Start minimized.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    root = tk.Tk()
    config_path = Path(args.config) if args.config else None
    TallyConnectorWindow(root, config_path=config_path, start_minimized=args.minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
