"""Small desktop status window for the SiftEntry Tally connector."""

from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
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

        self._build_window()
        self.root.after(250, self._drain_events)
        if start_minimized:
            self.root.iconify()

    def _build_window(self) -> None:
        self.root.title("SiftEntry Tally Connector")
        self.root.geometry("980x720")
        self.root.minsize(900, 660)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#08111F")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#667085")
        style.configure("Card.TFrame", background="#FFFFFF", borderwidth=1, relief="solid")
        style.configure("StatusTitle.TLabel", background="#FFFFFF", font=("Segoe UI", 9, "bold"), foreground="#667085")
        style.configure("StatusValue.TLabel", background="#FFFFFF", font=("Segoe UI", 14, "bold"), foreground="#08111F")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TFrame", background="#F8FAFC")
        style.configure("TLabel", background="#F8FAFC", foreground="#08111F")
        style.configure("TCheckbutton", background="#F8FAFC")

        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="SiftEntry Tally Connector", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Securely posts approved SiftEntry invoices into the local TallyPrime company.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        status_grid = ttk.Frame(outer)
        status_grid.pack(fill="x", pady=(0, 18))
        for index in range(2):
            status_grid.columnconfigure(index, weight=1, uniform="status")
        self._status_card(status_grid, 0, 0, "Connected to SiftEntry", self.siftentry_status)
        self._status_card(status_grid, 0, 1, "Tally detected", self.tally_status)
        self._status_card(status_grid, 1, 0, "Last posted invoice", self.last_invoice)
        self._status_card(status_grid, 1, 1, "Retry failed jobs", self.failed_jobs)

        form = ttk.LabelFrame(outer, text="Connector settings", padding=16)
        form.pack(fill="x", pady=(0, 16))
        form.columnconfigure(1, weight=1, minsize=260)
        form.columnconfigure(3, weight=1, minsize=260)

        self._field(form, 0, 0, "SiftEntry URL", self.cloud_url)
        self._field(form, 0, 2, "Workspace ID", self.workspace_id)
        self._field(form, 1, 0, "Connector token", self.token, show="*")
        self._field(form, 1, 2, "Tally URL", self.tally_url)

        ttk.Label(form, text="Poll seconds").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(12, 0))
        ttk.Spinbox(form, from_=5, to=300, textvariable=self.poll_interval, width=8).grid(
            row=2,
            column=1,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Label(form, text="Claim limit").grid(row=2, column=2, sticky="w", padx=(18, 12), pady=(12, 0))
        ttk.Spinbox(form, from_=1, to=25, textvariable=self.claim_limit, width=8).grid(
            row=2,
            column=3,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Checkbutton(form, text="Dry run only", variable=self.dry_run).grid(
            row=3,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 16))
        ttk.Button(controls, text="Save settings", command=lambda: self.save_settings(notify=True)).pack(
            side="left",
            padx=(0, 10),
        )
        ttk.Button(controls, text="Test Tally", command=self.test_tally).pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="Poll once", command=self.poll_once_now).pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="Start connector", style="Primary.TButton", command=self.start).pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="Stop", style="Danger.TButton", command=self.stop).pack(side="left")
        ttk.Label(controls, textvariable=self.running, style="Subtitle.TLabel").pack(side="right")

        log_frame = ttk.LabelFrame(outer, text="Activity", padding=12)
        log_frame.pack(fill="both", expand=True)
        self.activity = tk.Text(
            log_frame,
            height=8,
            wrap="word",
            bg="#FFFFFF",
            fg="#08111F",
            bd=0,
            relief="flat",
            font=("Consolas", 10),
        )
        self.activity.pack(fill="both", expand=True)
        self._append_log("Status window ready.")

    def _status_card(self, parent: ttk.Frame, row: int, column: int, title: str, value: tk.StringVar) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 10, 0),
            pady=(0 if row == 0 else 10, 0),
        )
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title.upper(), style="StatusTitle.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            textvariable=value,
            style="StatusValue.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(8, 0))

    def _field(
        self,
        parent: ttk.LabelFrame,
        row: int,
        column: int,
        label: str,
        value: tk.StringVar,
        show: str = "",
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 12), pady=(0, 10))
        entry = ttk.Entry(parent, textvariable=value, show=show)
        entry.grid(row=row, column=column + 1, sticky="ew", pady=(0, 10))

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
        self.running.set("Running")
        self.worker = threading.Thread(target=self._poll_loop, daemon=True)
        self.worker.start()
        self._append_log("Connector started.")

    def stop(self) -> None:
        self.stop_event.set()
        self.running.set("Stopped")
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
        return cleaned[: max(0, limit - 1)].rstrip() + "…"

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
