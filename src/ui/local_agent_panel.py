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
        for widget in (self._status_text, self._result_text):
            widget.configure(state=tk.DISABLED)

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
        }
        self._set_text(self._status_text, json.dumps(status_payload, indent=2))
        if runtime_status:
            self._status_var.set(
                f"{runtime_status.get('status', 'idle')} | "
                f"{runtime_status.get('model', '')} | "
                f"{runtime_status.get('last_seen_at', '')}"
            )

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
            self._state.projections.refresh("viewport_state")
        except Exception:
            pass

    def _set_buttons(self, state: str) -> None:
        for button in (self._models_btn, self._preflight_btn, self._run_btn):
            button.configure(state=state)
        self._stop_btn.configure(state="normal")

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
