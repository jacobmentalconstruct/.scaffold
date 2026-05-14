"""
FILE: src/ui/training_runway_panel.py
ROLE: Tk operator panel for T8 Teaching Sandbox + Training Runway.
WHAT IT DOES: Lists tracked scenarios, shows recent scenario runs and
              scorecards, and exposes modest controls for sandbox create,
              mocked/live scenario execution, verification, and reviewer export.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class TrainingRunwayPanel(ttk.Frame):
    def __init__(self, master, state):
        super().__init__(master, padding=8)
        self._state = state
        self._busy = False
        self._selected_scenario_id = ""
        self._selected_run_id = ""

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(5, weight=1)

        self._mode_var = tk.StringVar(value="mocked")
        self._variant_var = tk.StringVar(value="good")
        self._model_var = tk.StringVar(value="qwen3.5:9b")
        self._status_var = tk.StringVar(value="Training runway idle.")

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

        ttk.Label(controls, text="Mode").pack(anchor="w")
        ttk.Combobox(controls, textvariable=self._mode_var, values=["mocked", "live"], width=16, state="readonly").pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Label(controls, text="Mock Variant").pack(anchor="w")
        ttk.Entry(controls, textvariable=self._variant_var, width=18).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Label(controls, text="Live Model").pack(anchor="w")
        ttk.Entry(controls, textvariable=self._model_var, width=18).pack(anchor="w", fill="x", pady=(0, 8))

        self._create_btn = ttk.Button(controls, text="Create Sandbox", command=self._create_sandbox)
        self._create_btn.pack(fill="x", pady=(2, 0))
        self._reset_btn = ttk.Button(controls, text="Reset Sandbox", command=self._reset_sandbox)
        self._reset_btn.pack(fill="x", pady=(6, 0))
        self._run_btn = ttk.Button(controls, text="Run Scenario", command=self._run_scenario)
        self._run_btn.pack(fill="x", pady=(6, 0))
        self._verify_btn = ttk.Button(controls, text="Verify Selected Run", command=self._verify_selected_run)
        self._verify_btn.pack(fill="x", pady=(6, 0))
        self._export_btn = ttk.Button(controls, text="Export Review", command=self._export_selected_run)
        self._export_btn.pack(fill="x", pady=(6, 0))

        ttk.Label(controls, textvariable=self._status_var, wraplength=240).pack(anchor="w", pady=(8, 0))

        ttk.Label(self, text="Scenario Inventory").grid(row=0, column=1, sticky="w")
        self._scenario_tree = ttk.Treeview(
            self,
            columns=("scenario_id", "category", "checks"),
            show="headings",
            height=8,
        )
        for col, label, width in (("scenario_id", "Scenario", 200), ("category", "Category", 120), ("checks", "Checks", 70)):
            self._scenario_tree.heading(col, text=label)
            self._scenario_tree.column(col, width=width, anchor=tk.W)
        self._scenario_tree.grid(row=1, column=1, sticky="nsew")
        self._scenario_tree.bind("<<TreeviewSelect>>", self._on_scenario_select)

        ttk.Label(self, text="Scenario Detail").grid(row=2, column=0, sticky="w", pady=(10, 6))
        ttk.Label(self, text="Recent Scenario Runs").grid(row=2, column=1, sticky="w", pady=(10, 6))
        self._detail_text = ScrolledText(self, wrap=tk.WORD, height=10)
        self._detail_text.grid(row=3, column=0, sticky="nsew", padx=(0, 10))
        self._runs_tree = ttk.Treeview(
            self,
            columns=("scenario_run_id", "scenario_id", "result", "score"),
            show="headings",
            height=10,
        )
        for col, label, width in (
            ("scenario_run_id", "Scenario Run", 220),
            ("scenario_id", "Scenario", 160),
            ("result", "Result", 90),
            ("score", "Score", 70),
        ):
            self._runs_tree.heading(col, text=label)
            self._runs_tree.column(col, width=width, anchor=tk.W)
        self._runs_tree.grid(row=3, column=1, sticky="nsew")
        self._runs_tree.bind("<<TreeviewSelect>>", self._on_run_select)

        ttk.Label(self, text="Selected Scorecard").grid(row=4, column=0, sticky="w", pady=(10, 6))
        ttk.Label(self, text="Runway Summary").grid(row=4, column=1, sticky="w", pady=(10, 6))
        self._scorecard_text = ScrolledText(self, wrap=tk.WORD, height=12)
        self._scorecard_text.grid(row=5, column=0, sticky="nsew", padx=(0, 10))
        self._summary_text = ScrolledText(self, wrap=tk.WORD, height=12)
        self._summary_text.grid(row=5, column=1, sticky="nsew")
        for widget in (self._detail_text, self._scorecard_text, self._summary_text):
            widget.configure(state=tk.DISABLED)

    def refresh(self, data: dict) -> None:
        runway = data.get("training_runway", {}) or {}
        inventory = runway.get("scenario_inventory", [])
        self._scenario_tree.delete(*self._scenario_tree.get_children())
        for scenario in inventory:
            iid = str(scenario.get("scenario_id", ""))
            self._scenario_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(iid, scenario.get("category", ""), scenario.get("check_count", 0)),
            )
        if self._selected_scenario_id and self._scenario_tree.exists(self._selected_scenario_id):
            self._scenario_tree.selection_set(self._selected_scenario_id)
        elif inventory:
            self._selected_scenario_id = str(inventory[0].get("scenario_id", ""))
            if self._scenario_tree.exists(self._selected_scenario_id):
                self._scenario_tree.selection_set(self._selected_scenario_id)

        recent_runs = runway.get("recent_runs", [])
        self._runs_tree.delete(*self._runs_tree.get_children())
        for run in recent_runs:
            iid = str(run.get("scenario_run_id", ""))
            self._runs_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(iid, run.get("scenario_id", ""), run.get("aggregate_result", ""), run.get("total_score", 0)),
            )
        if self._selected_run_id and self._runs_tree.exists(self._selected_run_id):
            self._runs_tree.selection_set(self._selected_run_id)
        elif recent_runs:
            self._selected_run_id = str(recent_runs[0].get("scenario_run_id", ""))
            if self._runs_tree.exists(self._selected_run_id):
                self._runs_tree.selection_set(self._selected_run_id)

        self._refresh_selected_scenario()
        self._refresh_selected_run()
        self._set_text(self._summary_text, json.dumps(runway, indent=2))

    def _on_scenario_select(self, _event=None) -> None:
        selection = self._scenario_tree.selection()
        self._selected_scenario_id = selection[0] if selection else ""
        self._refresh_selected_scenario()

    def _on_run_select(self, _event=None) -> None:
        selection = self._runs_tree.selection()
        self._selected_run_id = selection[0] if selection else ""
        self._refresh_selected_run()

    def _refresh_selected_scenario(self) -> None:
        if not self._selected_scenario_id:
            self._set_text(self._detail_text, "{}")
            return
        try:
            payload = self._state.training_runway_manager.get_scenario(self._selected_scenario_id)
        except Exception as exc:
            payload = {"status": "error", "error": str(exc)}
        self._set_text(self._detail_text, json.dumps(payload, indent=2))

    def _refresh_selected_run(self) -> None:
        if not self._selected_run_id:
            self._set_text(self._scorecard_text, "{}")
            return
        try:
            payload = self._state.training_runway_manager.get_scorecard(scenario_run_id=self._selected_run_id)
        except Exception as exc:
            payload = {"status": "error", "error": str(exc)}
        self._set_text(self._scorecard_text, json.dumps(payload, indent=2))

    def _create_sandbox(self) -> None:
        if not self._selected_scenario_id:
            self._status_var.set("Select a scenario first.")
            return
        self._run_background(
            "Creating sandbox...",
            lambda: self._state.training_runway_manager.create_sandbox(self._selected_scenario_id, reset=False),
        )

    def _reset_sandbox(self) -> None:
        if not self._selected_scenario_id:
            self._status_var.set("Select a scenario first.")
            return
        self._run_background(
            "Resetting sandbox...",
            lambda: self._state.training_runway_manager.create_sandbox(self._selected_scenario_id, reset=True),
        )

    def _run_scenario(self) -> None:
        if not self._selected_scenario_id:
            self._status_var.set("Select a scenario first.")
            return
        self._run_background(
            "Running teaching scenario...",
            lambda: self._state.training_runway_manager.run_scenario(
                self._selected_scenario_id,
                run_mode=self._mode_var.get().strip(),
                mock_variant=self._variant_var.get().strip() or "good",
                model=self._model_var.get().strip() or "qwen3.5:9b",
            ),
        )

    def _verify_selected_run(self) -> None:
        if not self._selected_run_id:
            self._status_var.set("Select a scenario run first.")
            return
        self._run_background(
            "Verifying selected scenario run...",
            lambda: self._state.training_runway_manager.verify_scenario_run(self._selected_run_id),
        )

    def _export_selected_run(self) -> None:
        if not self._selected_run_id:
            self._status_var.set("Select a scenario run first.")
            return
        self._run_background(
            "Exporting reviewer packet...",
            lambda: self._state.training_runway_manager.export_review(scenario_run_id=self._selected_run_id),
        )

    def _run_background(self, busy_text: str, fn) -> None:
        if self._busy:
            return
        self._busy = True
        self._status_var.set(busy_text)
        self._set_buttons("disabled")

        def worker() -> None:
            try:
                payload = fn()
            except Exception as exc:  # pragma: no cover - defensive UI wrapper
                payload = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            self.after(0, lambda: self._after_result(payload))

        threading.Thread(target=worker, daemon=True).start()

    def _after_result(self, payload: dict) -> None:
        self._busy = False
        self._set_buttons("normal")
        self._status_var.set(payload.get("status", "ok"))
        self._set_text(self._summary_text, json.dumps(payload, indent=2))
        try:
            self._state.projections.refresh("training_runway")
            self._state.projections.refresh("viewport_state")
        except Exception:
            pass

    def _set_buttons(self, state: str) -> None:
        for button in (self._create_btn, self._reset_btn, self._run_btn, self._verify_btn, self._export_btn):
            button.configure(state=state)

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
