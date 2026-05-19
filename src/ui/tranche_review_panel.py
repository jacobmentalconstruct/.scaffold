"""
FILE: src/ui/tranche_review_panel.py
ROLE: Tk operator panel for the tranche review gate.
WHAT IT DOES: Exposes the mechanical pre-park review packet, plus
              request / return / approve controls over the same spine
              paths used by the CLI.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class TrancheReviewPanel(ttk.Frame):
    def __init__(self, master, state):
        super().__init__(master, padding=8)
        self._state = state
        self._busy = False

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(5, weight=1)

        self._operator_var = tk.StringVar(value="human:ui")
        self._return_reason_var = tk.StringVar(value="")
        self._approval_notes_var = tk.StringVar(value="")
        self._extra_notes_var = tk.StringVar(value="")
        self._skip_smoke_var = tk.BooleanVar(value=False)
        self._use_ollama_var = tk.BooleanVar(value=False)
        self._status_var = tk.StringVar(value="No tranche review pending.")

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        controls.columnconfigure(7, weight=1)

        ttk.Label(controls, text="Operator").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self._operator_var, width=20).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(controls, text="Return Reason").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self._return_reason_var, width=28).grid(row=0, column=3, sticky="ew", padx=(6, 12))
        ttk.Label(controls, text="Approval Notes").grid(row=0, column=4, sticky="w")
        ttk.Entry(controls, textvariable=self._approval_notes_var, width=28).grid(row=0, column=5, sticky="ew", padx=(6, 12))
        ttk.Button(controls, text="Request Review", command=self._request_review).grid(row=0, column=6, sticky="w", padx=(0, 6))
        ttk.Button(controls, text="Return To Agent", command=self._return_review).grid(row=0, column=7, sticky="w", padx=(0, 6))
        ttk.Button(controls, text="Approve Park", command=self._approve_and_close).grid(row=0, column=8, sticky="w")

        extras = ttk.Frame(self)
        extras.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        extras.columnconfigure(1, weight=1)
        ttk.Label(extras, text="Park Extra Notes").grid(row=0, column=0, sticky="w")
        ttk.Entry(extras, textvariable=self._extra_notes_var).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Checkbutton(extras, text="Skip Smoke Gate", variable=self._skip_smoke_var).grid(row=0, column=2, sticky="w", padx=(0, 12))
        ttk.Checkbutton(extras, text="Use Ollama For Park Notes", variable=self._use_ollama_var).grid(row=0, column=3, sticky="w")

        ttk.Label(self, textvariable=self._status_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(self, text="Current Tranche / Latest Review").grid(row=3, column=0, sticky="w", pady=(0, 6))
        ttk.Label(self, text="Review History").grid(row=3, column=1, sticky="w", pady=(0, 6))

        self._summary_text = ScrolledText(self, wrap=tk.WORD, height=14)
        self._summary_text.grid(row=4, column=0, sticky="nsew", padx=(0, 10))
        self._history_tree = ttk.Treeview(
            self,
            columns=("status", "review_id", "generated_at", "reviewed_by"),
            show="headings",
            height=12,
        )
        for col, label, width in (
            ("status", "Status", 100),
            ("review_id", "Review", 240),
            ("generated_at", "Generated", 170),
            ("reviewed_by", "Reviewed By", 170),
        ):
            self._history_tree.heading(col, text=label)
            self._history_tree.column(col, width=width, anchor=tk.W)
        self._history_tree.grid(row=4, column=1, sticky="nsew")
        self._history_tree.bind("<<TreeviewSelect>>", self._on_history_select)

        ttk.Label(self, text="Selected Review Detail").grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 6))
        self._detail_text = ScrolledText(self, wrap=tk.WORD, height=14)
        self._detail_text.grid(row=6, column=0, columnspan=2, sticky="nsew")
        for widget in (self._summary_text, self._detail_text):
            widget.configure(state=tk.DISABLED)

        self._last_payload: dict = {}
        self._selected_review_id = ""

    def refresh(self, data: dict) -> None:
        review_gate = data.get("tranche_review_gate", {})
        self._last_payload = review_gate
        default_actor = data.get("default_operator_actor") or self._operator_var.get()
        if not self._operator_var.get().strip() or self._operator_var.get().strip() == "human:ui":
            self._operator_var.set(default_actor)

        current_tranche = review_gate.get("current_tranche", {})
        latest_review = review_gate.get("latest_review", {})
        history = review_gate.get("history", [])
        allowed_actions = review_gate.get("allowed_actions", [])

        summary = {
            "current_tranche": current_tranche,
            "latest_review": latest_review,
            "allowed_actions": allowed_actions,
            "park_phase_allowed": bool(review_gate.get("park_phase_allowed")),
        }
        self._set_text(self._summary_text, json.dumps(summary, indent=2))
        self._status_var.set(
            f"status={current_tranche.get('status', 'none')} | "
            f"allowed={', '.join(allowed_actions) if allowed_actions else 'none'}"
        )

        self._history_tree.delete(*self._history_tree.get_children())
        for item in history:
            review_id = str(item.get("review_id", ""))
            self._history_tree.insert(
                "",
                tk.END,
                iid=review_id,
                values=(
                    item.get("status", ""),
                    review_id,
                    item.get("generated_at", ""),
                    item.get("reviewed_by_actor", ""),
                ),
            )
        if self._selected_review_id and self._history_tree.exists(self._selected_review_id):
            self._history_tree.selection_set(self._selected_review_id)
        elif latest_review.get("review_id") and self._history_tree.exists(str(latest_review.get("review_id"))):
            self._selected_review_id = str(latest_review.get("review_id"))
            self._history_tree.selection_set(self._selected_review_id)
        self._refresh_detail()

    def _on_history_select(self, _event=None) -> None:
        selection = self._history_tree.selection()
        self._selected_review_id = selection[0] if selection else ""
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        history = self._last_payload.get("history", [])
        selected = next((item for item in history if item.get("review_id") == self._selected_review_id), None)
        if selected is None:
            selected = self._last_payload.get("latest_review", {})
        self._set_text(self._detail_text, json.dumps(selected or {}, indent=2))

    def _request_review(self) -> None:
        self._run_background(
            "Generating mechanical review packet...",
            self._dispatch_request_review,
        )

    def _return_review(self) -> None:
        if not self._return_reason_var.get().strip():
            self._status_var.set("Return reason is required.")
            return
        self._run_background(
            "Returning tranche review to the agent...",
            self._dispatch_return_review,
        )

    def _approve_and_close(self) -> None:
        current_tranche = self._last_payload.get("current_tranche", {})
        if current_tranche.get("status") == "review_approved":
            self._run_background(
                "Closing review-approved tranche through Park Phase...",
                self._dispatch_close_only,
            )
            return
        self._run_background(
            "Approving tranche review and starting Park Phase...",
            self._dispatch_approve_and_close,
        )

    def _dispatch_request_review(self) -> dict:
        from src.core.envelope import SidecarEnvelope

        envelope = SidecarEnvelope.new(
            object_type="tranche_review",
            actor_id=self._operator_var.get().strip() or "human:ui",
            operation_intent="request_tranche_review",
        )
        result = self._state.router.dispatch(envelope)
        return self._result_payload(result)

    def _dispatch_return_review(self) -> dict:
        from src.core.envelope import SidecarEnvelope

        payload_ref = self._state.blob_store.put_json(
            {
                "review_id": self._selected_review_id or "",
                "return_reason": self._return_reason_var.get().strip(),
            }
        )
        envelope = SidecarEnvelope.new(
            object_type="tranche_review",
            actor_id=self._operator_var.get().strip() or "human:ui",
            operation_intent="return_tranche_review",
            payload_ref=payload_ref,
        )
        result = self._state.router.dispatch(envelope)
        return self._result_payload(result)

    def _dispatch_approve_and_close(self) -> dict:
        from src.core.envelope import SidecarEnvelope

        actor_id = self._operator_var.get().strip() or "human:ui"
        approve_payload_ref = self._state.blob_store.put_json(
            {
                "review_id": self._selected_review_id or "",
                "approval_notes": self._approval_notes_var.get().strip(),
            }
        )
        approve_envelope = SidecarEnvelope.new(
            object_type="tranche_review",
            actor_id=actor_id,
            operation_intent="approve_tranche_review",
            payload_ref=approve_payload_ref,
        )
        approve_result = self._state.router.dispatch(approve_envelope)
        payload = {
            "approval": self._result_payload(approve_result),
        }
        if approve_result.status not in ("accepted", "completed"):
            return payload

        close_payload_ref = self._state.blob_store.put_json(
            {
                "skip_smoke_check": bool(self._skip_smoke_var.get()),
                "extra_notes": self._extra_notes_var.get().strip(),
                "use_ollama": bool(self._use_ollama_var.get()),
                "ollama_model": "qwen3.5:9b",
                "ollama_num_predict": 8192,
            }
        )
        close_envelope = SidecarEnvelope.new(
            object_type="tranche",
            actor_id=actor_id,
            operation_intent="close_tranche",
            payload_ref=close_payload_ref,
        )
        close_result = self._state.router.dispatch(close_envelope)
        payload["closeout"] = self._result_payload(close_result)
        return payload

    def _dispatch_close_only(self) -> dict:
        from src.core.envelope import SidecarEnvelope

        actor_id = self._operator_var.get().strip() or "human:ui"
        close_payload_ref = self._state.blob_store.put_json(
            {
                "skip_smoke_check": bool(self._skip_smoke_var.get()),
                "extra_notes": self._extra_notes_var.get().strip(),
                "use_ollama": bool(self._use_ollama_var.get()),
                "ollama_model": "qwen3.5:9b",
                "ollama_num_predict": 8192,
            }
        )
        close_envelope = SidecarEnvelope.new(
            object_type="tranche",
            actor_id=actor_id,
            operation_intent="close_tranche",
            payload_ref=close_payload_ref,
        )
        close_result = self._state.router.dispatch(close_envelope)
        return {
            "status": close_result.status,
            "closeout": self._result_payload(close_result),
        }

    def _run_background(self, busy_text: str, fn) -> None:
        if self._busy:
            return
        self._busy = True
        self._status_var.set(busy_text)

        def worker() -> None:
            try:
                payload = fn()
            except Exception as exc:  # pragma: no cover - defensive UI wrapper
                payload = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            self.after(0, lambda: self._after_action(payload))

        threading.Thread(target=worker, daemon=True).start()

    def _after_action(self, payload: dict) -> None:
        self._busy = False
        self._status_var.set(payload.get("status", "ok"))
        self._set_text(self._detail_text, json.dumps(payload, indent=2))
        try:
            self._state.projections.refresh("tranche_checklist")
            self._state.projections.refresh("tranche_review_gate")
            self._state.projections.refresh("handoff")
            self._state.projections.refresh("viewport_state")
        except Exception:
            pass

    def _result_payload(self, result) -> dict:
        response = {}
        if getattr(result, "payload_ref", ""):
            try:
                response = self._state.blob_store.get_json(result.payload_ref)
            except Exception:
                response = {}
        return {
            "status": result.status,
            "event_id": result.event_id,
            "operation_intent": result.operation_intent,
            "response": response,
        }

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
