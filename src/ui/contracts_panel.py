"""
FILE: src/ui/contracts_panel.py
ROLE: Contract + approval operator panel.
WHAT IT DOES: Shows the approval queue, acknowledgments, recent
              contract events, and lets a human approve or reject
              authority-elevation requests through the spine.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class ContractsPanel(ttk.Frame):
    def __init__(self, master, state):
        super().__init__(master, padding=8)
        self._state = state
        self._pending_index: dict[str, dict] = {}
        self._last_data: dict = {}

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(5, weight=1)
        self.rowconfigure(7, weight=1)

        self._pending_tree = ttk.Treeview(
            self,
            columns=("actor_id", "requested_level", "summary", "requested_at"),
            show="headings",
            height=8,
        )
        for column, label, width in (
            ("actor_id", "Actor", 180),
            ("requested_level", "Level", 110),
            ("summary", "Summary", 260),
            ("requested_at", "Requested", 180),
        ):
            self._pending_tree.heading(column, text=label)
            self._pending_tree.column(column, width=width, anchor=tk.W)
        self._pending_tree.bind("<<TreeviewSelect>>", self._on_pending_select)

        self._acks_tree = ttk.Treeview(
            self,
            columns=("actor_id", "actor_type", "acknowledged_at"),
            show="headings",
            height=8,
        )
        for column, label, width in (
            ("actor_id", "Actor", 220),
            ("actor_type", "Type", 90),
            ("acknowledged_at", "Acknowledged", 180),
        ):
            self._acks_tree.heading(column, text=label)
            self._acks_tree.column(column, width=width, anchor=tk.W)

        self._events_tree = ttk.Treeview(
            self,
            columns=("intent", "actor_id", "created_at"),
            show="headings",
            height=8,
        )
        for column, label, width in (
            ("intent", "Intent", 160),
            ("actor_id", "Actor", 200),
            ("created_at", "Created", 180),
        ):
            self._events_tree.heading(column, text=label)
            self._events_tree.column(column, width=width, anchor=tk.W)

        self._summary = ScrolledText(self, wrap=tk.WORD, height=10)
        self._summary.configure(state=tk.DISABLED)

        self._approval_detail = ScrolledText(self, wrap=tk.WORD, height=10)
        self._approval_detail.configure(state=tk.DISABLED)

        self._contract_text = ScrolledText(self, wrap=tk.WORD, height=20)
        self._contract_text.configure(state=tk.DISABLED)

        self._operator_var = tk.StringVar(value="human:ui")
        self._decision_reason_var = tk.StringVar(value="")
        self._action_status_var = tk.StringVar(value="Queue idle.")

        ttk.Label(self, text="Pending Approvals").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(self, text="Acknowledgments").grid(row=0, column=1, sticky="w", pady=(0, 6))
        self._pending_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._acks_tree.grid(row=1, column=1, sticky="nsew")

        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        controls.columnconfigure(5, weight=1)
        ttk.Label(controls, text="Operator").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self._operator_var, width=20).grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(controls, text="Decision Note").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self._decision_reason_var, width=44).grid(row=0, column=3, sticky="ew", padx=(6, 12))
        ttk.Button(controls, text="Approve", command=self._approve_selected).grid(row=0, column=4, sticky="w", padx=(0, 6))
        ttk.Button(controls, text="Reject", command=self._reject_selected).grid(row=0, column=5, sticky="w")

        ttk.Label(self, text="Approval Detail").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 6))
        self._approval_detail.grid(row=4, column=0, columnspan=2, sticky="nsew")

        ttk.Label(self, text="Recent Contract Events").grid(row=5, column=0, sticky="w", pady=(10, 6))
        ttk.Label(self, text="Contract Summary").grid(row=5, column=1, sticky="w", pady=(10, 6))
        self._events_tree.grid(row=6, column=0, sticky="nsew", padx=(0, 8))
        self._summary.grid(row=6, column=1, sticky="nsew")

        ttk.Label(self, textvariable=self._action_status_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 4))
        ttk.Label(self, text="Contract Text").grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 6))
        self._contract_text.grid(row=9, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(9, weight=1)

    def refresh(self, data: dict) -> None:
        self._last_data = data
        contract_status = data.get("contract_status", {})
        acks = contract_status.get("acks", [])
        events = contract_status.get("recent_events", [])
        pending = data.get("approval_queue", [])
        summary = {
            "contract_id": contract_status.get("contract_id"),
            "version": contract_status.get("version"),
            "text_hash": contract_status.get("text_hash"),
            "outstanding_grants": contract_status.get("outstanding_grants", []),
        }
        default_actor = data.get("default_operator_actor") or self._operator_var.get()
        if not self._operator_var.get().strip() or self._operator_var.get().strip() == "human:ui":
            self._operator_var.set(default_actor)

        self._pending_index = {item.get("request_id", ""): item for item in pending if item.get("request_id")}
        self._replace_tree_rows(
            self._pending_tree,
            [
                (
                    item.get("actor_id", ""),
                    item.get("requested_level", ""),
                    item.get("summary", ""),
                    item.get("requested_at", ""),
                )
                for item in pending
            ],
            iids=[item.get("request_id", "") for item in pending],
        )
        self._replace_tree_rows(
            self._acks_tree,
            [(ack.get("actor_id", ""), ack.get("actor_type", ""), ack.get("acknowledged_at", "")) for ack in acks],
        )
        self._replace_tree_rows(
            self._events_tree,
            [(event.get("intent", ""), event.get("actor_id", ""), event.get("created_at", "")) for event in events],
        )
        self._set_text(self._summary, json.dumps(summary, indent=2))
        self._set_text(self._contract_text, data.get("contract_text", ""))
        self._refresh_detail_from_selection()

    def _on_pending_select(self, _event=None) -> None:
        self._refresh_detail_from_selection()

    def _refresh_detail_from_selection(self) -> None:
        selection = self._pending_tree.selection()
        if not selection:
            self._set_text(self._approval_detail, "No pending approval selected.")
            return
        request_id = selection[0]
        payload = self._pending_index.get(request_id, {})
        self._set_text(self._approval_detail, json.dumps(payload, indent=2))

    def _approve_selected(self) -> None:
        self._dispatch_decision("approve_authority_request")

    def _reject_selected(self) -> None:
        self._dispatch_decision("reject_authority_request")

    def _dispatch_decision(self, operation_intent: str) -> None:
        selection = self._pending_tree.selection()
        if not selection:
            self._action_status_var.set("Select a pending approval first.")
            return
        actor_id = self._operator_var.get().strip() or "human:ui"
        request_id = selection[0]
        payload = {
            "request_id": request_id,
            "decision_reason": self._decision_reason_var.get().strip(),
        }
        if operation_intent == "approve_authority_request":
            payload["expires_minutes"] = 60
            payload["single_use"] = True
        payload_ref = self._state.blob_store.put_json(payload)
        from src.core.envelope import SidecarEnvelope

        envelope = SidecarEnvelope.new(
            object_type="authority_grant",
            actor_id=actor_id,
            operation_intent=operation_intent,
            payload_ref=payload_ref,
        )
        result = self._state.router.dispatch(envelope)
        self._action_status_var.set(
            f"{operation_intent} → {result.status} (request_id={request_id}, event_id={result.event_id or 'n/a'})"
        )

    @staticmethod
    def _replace_tree_rows(tree: ttk.Treeview, rows: list[tuple], iids: list[str] | None = None) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for index, row in enumerate(rows):
            kwargs = {"values": row}
            if iids and iids[index]:
                kwargs["iid"] = iids[index]
            tree.insert("", tk.END, **kwargs)

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
