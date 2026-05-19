"""
FILE: src/ui/local_agent_panel.py
ROLE: Tk operator panel for the local sidecar agent runtime.
WHAT IT DOES: Exposes model refresh, preflight, and run controls for the
              local Ollama-backed runtime inside the existing operator shell.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class LocalAgentPanel(ttk.Frame):
    def __init__(self, master, state):
        super().__init__(master, padding=8)
        self._state = state
        self._busy = False
        self._model_names: list[str] = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(5, weight=1)

        self._actor_var = tk.StringVar(value="agent:local:ollama")
        self._base_url_var = tk.StringVar(value="http://localhost:11434")
        self._model_var = tk.StringVar(value="qwen3.5:9b")
        self._rounds_var = tk.StringVar(value="4")
        self._status_var = tk.StringVar(value="Local agent idle.")

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

        ttk.Label(controls, text="Actor").pack(anchor="w")
        ttk.Entry(controls, textvariable=self._actor_var, width=28).pack(anchor="w", fill="x", pady=(0, 8))

        ttk.Label(controls, text="Ollama Base URL").pack(anchor="w")
        ttk.Entry(controls, textvariable=self._base_url_var, width=28).pack(anchor="w", fill="x", pady=(0, 8))

        ttk.Label(controls, text="Model").pack(anchor="w")
        self._model_combo = ttk.Combobox(controls, textvariable=self._model_var, width=26)
        self._model_combo.pack(anchor="w", fill="x", pady=(0, 8))

        ttk.Label(controls, text="Max Rounds").pack(anchor="w")
        ttk.Entry(controls, textvariable=self._rounds_var, width=10).pack(anchor="w", pady=(0, 8))

        button_row = ttk.Frame(controls)
        button_row.pack(anchor="w", fill="x", pady=(4, 8))
        self._models_btn = ttk.Button(button_row, text="Refresh Models", command=self._refresh_models)
        self._models_btn.pack(fill="x")
        self._preflight_btn = ttk.Button(button_row, text="Preflight", command=self._preflight)
        self._preflight_btn.pack(fill="x", pady=(6, 0))
        self._run_btn = ttk.Button(button_row, text="Run Local Agent", command=self._run_agent)
        self._run_btn.pack(fill="x", pady=(6, 0))
        self._stop_btn = ttk.Button(button_row, text="Request Stop", command=self._request_stop)
        self._stop_btn.pack(fill="x", pady=(6, 0))
        self._retry_btn = ttk.Button(button_row, text="Retry Selected Run", command=self._retry_selected_run)
        self._retry_btn.pack(fill="x", pady=(6, 0))

        ttk.Label(controls, textvariable=self._status_var, wraplength=240).pack(anchor="w", pady=(8, 0))

        ttk.Label(self, text="Task Prompt").grid(row=0, column=1, sticky="w")
        self._prompt_text = ScrolledText(self, wrap=tk.WORD, height=10)
        self._prompt_text.grid(row=1, column=1, sticky="nsew")
        self._prompt_text.insert(
            "1.0",
            "Inspect this project and take the safest bounded next step through the sidecar spine.",
        )

        ttk.Label(self, text="Runtime Status").grid(row=2, column=0, sticky="w", pady=(10, 6))
        ttk.Label(self, text="Last Result").grid(row=2, column=1, sticky="w", pady=(10, 6))

        self._status_text = ScrolledText(self, wrap=tk.WORD, height=12)
        self._status_text.grid(row=3, column=0, sticky="nsew", padx=(0, 10))
        self._result_text = ScrolledText(self, wrap=tk.WORD, height=12)
        self._result_text.grid(row=3, column=1, sticky="nsew")
        ttk.Label(self, text="Run History").grid(row=4, column=0, sticky="w", pady=(10, 6))
        ttk.Label(self, text="Run Detail").grid(row=4, column=1, sticky="w", pady=(10, 6))
        self._runs_tree = ttk.Treeview(
            self,
            columns=("status", "run_id", "recovery"),
            show="headings",
            height=10,
        )
        for col, label, width in (("status", "Status", 100), ("run_id", "Run", 240), ("recovery", "Recovery", 160)):
            self._runs_tree.heading(col, text=label)
            self._runs_tree.column(col, width=width, anchor=tk.W)
        self._runs_tree.grid(row=5, column=0, sticky="nsew", padx=(0, 10))
        self._runs_tree.bind("<<TreeviewSelect>>", self._on_run_select)
        self._run_detail_text = ScrolledText(self, wrap=tk.WORD, height=10)
        self._run_detail_text.grid(row=5, column=1, sticky="nsew")
        for widget in (self._status_text, self._result_text):
            widget.configure(state=tk.DISABLED)
        self._run_detail_text.configure(state=tk.DISABLED)
        self._selected_run_id = ""

    def refresh(self, data: dict) -> None:
        present = (data.get("viewport") or {}).get("present", {})
        current_state = present.get("current_state", {})
        runtime_status = current_state.get("agent_status", {}) or {}
        sessions = [
            row for row in present.get("agent_sessions", [])
            if row.get("channel") == "local"
        ]
        status_payload = {
            "runtime_status": runtime_status,
            "local_sessions": sessions,
            "pending_approvals": present.get("pending_approvals", 0),
            "current_agent": present.get("current_agent", {}),
            "memory": present.get("memory", {}),
            "runtime": data.get("runtime_cockpit", {}),
        }
        self._set_text(self._status_text, json.dumps(status_payload, indent=2))
        if runtime_status:
            self._status_var.set(
                f"{runtime_status.get('status', 'idle')} | "
                f"{runtime_status.get('model', '')} | "
                f"{runtime_status.get('last_seen_at', '')}"
            )
        recent_runs = (data.get("runtime_cockpit") or {}).get("recent_runs", [])
        self._runs_tree.delete(*self._runs_tree.get_children())
        for run in recent_runs:
            run_id = str(run.get("run_id", ""))
            self._runs_tree.insert("", tk.END, iid=run_id, values=(run.get("status", ""), run_id, run.get("recovery_class", "")))
        if self._selected_run_id and self._runs_tree.exists(self._selected_run_id):
            self._runs_tree.selection_set(self._selected_run_id)
        elif recent_runs:
            self._selected_run_id = str(recent_runs[0].get("run_id", ""))
            if self._selected_run_id and self._runs_tree.exists(self._selected_run_id):
                self._runs_tree.selection_set(self._selected_run_id)
        self._refresh_run_detail(recent_runs)

    def _refresh_models(self) -> None:
        self._run_background(
            "Refreshing local models...",
            lambda: self._state.local_agent_runtime.list_models(base_url=self._base_url_var.get().strip()),
            self._after_models,
        )

    def _preflight(self) -> None:
        self._run_background(
            "Running local preflight...",
            lambda: self._state.local_agent_runtime.preflight(
                model=self._model_var.get().strip(),
                base_url=self._base_url_var.get().strip(),
                actor_id=self._actor_var.get().strip(),
            ),
            self._after_result,
        )

    def _run_agent(self) -> None:
        prompt = self._prompt_text.get("1.0", tk.END).strip()
        self._run_background(
            "Running local sidecar agent...",
            lambda: self._state.local_agent_runtime.run(
                prompt=prompt,
                actor_id=self._actor_var.get().strip(),
                model=self._model_var.get().strip(),
                base_url=self._base_url_var.get().strip(),
                max_rounds=self._safe_rounds(),
            ),
            self._after_result,
        )

    def _request_stop(self) -> None:
        payload = self._state.local_agent_runtime.request_stop(
            actor_id=self._actor_var.get().strip(),
        )
        self._status_var.set("Stop requested.")
        self._set_text(self._result_text, json.dumps(payload, indent=2))
        try:
            self._state.projections.refresh("viewport_state")
        except Exception:
            pass

    def _retry_selected_run(self) -> None:
        if not self._selected_run_id:
            self._status_var.set("Select a run to retry.")
            return
        self._run_background(
            "Retrying selected run...",
            lambda: self._state.local_agent_runtime.retry_run(self._selected_run_id),
            self._after_result,
        )

    def _safe_rounds(self) -> int:
        try:
            return max(1, min(int(self._rounds_var.get().strip()), 8))
        except ValueError:
            return 4

    def _run_background(self, busy_text: str, fn, callback) -> None:
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
            self.after(0, lambda: callback(payload))

        threading.Thread(target=worker, daemon=True).start()

    def _after_models(self, payload: dict) -> None:
        models = payload.get("models", []) if payload.get("status") == "ok" else []
        self._model_names = list(models)
        self._model_combo.configure(values=self._model_names)
        if self._model_names and self._model_var.get().strip() not in self._model_names:
            self._model_var.set(self._model_names[0])
        self._after_result(payload)

    def _after_result(self, payload: dict) -> None:
        self._busy = False
        self._set_buttons("normal")
        if payload.get("status") == "error":
            self._status_var.set(payload.get("error", "Local runtime error"))
        else:
            self._status_var.set(payload.get("status", "ok"))
        self._set_text(self._result_text, json.dumps(payload, indent=2))
        try:
            self._state.projections.refresh("runtime_cockpit")
            self._state.projections.refresh("viewport_state")
        except Exception:
            pass

    def _set_buttons(self, state: str) -> None:
        for button in (self._models_btn, self._preflight_btn, self._run_btn, self._retry_btn):
            button.configure(state=state)
        self._stop_btn.configure(state="normal")

    def _on_run_select(self, _event=None) -> None:
        selection = self._runs_tree.selection()
        self._selected_run_id = selection[0] if selection else ""
        self._refresh_run_detail()

    def _refresh_run_detail(self, recent_runs: list[dict] | None = None) -> None:
        if not self._selected_run_id:
            self._set_text(self._run_detail_text, json.dumps({}, indent=2))
            return
        run_detail = {}
        summary_row = {}
        if recent_runs:
            for run in recent_runs:
                if str(run.get("run_id", "")) == self._selected_run_id:
                    summary_row = run
                    break
        try:
            run_row = self._state.run_trace_manager.get_run(self._selected_run_id)
            if run_row is not None:
                run_detail = {
                    "run": {
                        "run_id": run_row.run_id,
                        "session_id": run_row.session_id,
                        "actor_id": run_row.actor_id,
                        "model": run_row.model,
                        "status": run_row.status,
                        "authority_level": run_row.authority_level,
                        "task_summary": run_row.task_summary,
                        "started_at": run_row.started_at,
                        "ended_at": run_row.ended_at,
                        "final_summary": run_row.final_summary,
                        "final_message": run_row.final_message,
                        "recovery_class": run_row.recovery_class,
                        "retryable": run_row.retryable,
                        "operator_hint": run_row.operator_hint,
                        "retried_from_run_id": run_row.retried_from_run_id,
                        "last_round_index": run_row.last_round_index,
                        "last_runtime_event_type": run_row.last_runtime_event_type,
                        "journal_entry_uid": run_row.journal_entry_uid,
                        "approval_request_id": run_row.approval_request_id,
                        "approval_grant_id": run_row.approval_grant_id,
                        "config_snapshot": run_row.config_snapshot,
                        "metadata": run_row.metadata,
                    },
                    "summary_row": summary_row,
                    "rounds": self._state.run_trace_manager.get_run_rounds(self._selected_run_id),
                    "events": self._state.run_trace_manager.get_run_events(self._selected_run_id, limit=50),
                    "touched_paths": self._state.run_trace_manager.get_run_touched_paths(self._selected_run_id),
                    "links": self._state.run_trace_manager.get_run_links(self._selected_run_id),
                    "grounding": self._state.run_trace_manager.get_run_grounding(self._selected_run_id),
                }
        except Exception:
            run_detail = {}
        self._set_text(self._run_detail_text, json.dumps(run_detail, indent=2))

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
