"""
FILE: src/ui/contracts_panel.py
ROLE: Read-only Tk panel for contract and drift visibility.
WHAT IT DOES: Shows the in-force contract, acknowledgments, recent
              contract events, and the contract text from CAS.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class ContractsPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

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

        self._contract_text = ScrolledText(self, wrap=tk.WORD, height=20)
        self._contract_text.configure(state=tk.DISABLED)

        ttk.Label(self, text="Acknowledgments").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(self, text="Recent Contract Events").grid(row=0, column=1, sticky="w", pady=(0, 6))
        self._acks_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._events_tree.grid(row=1, column=1, sticky="nsew")

        ttk.Label(self, text="Contract Summary").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 6))
        self._summary.grid(row=3, column=0, columnspan=2, sticky="nsew")

        ttk.Label(self, text="Contract Text").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 6))
        self._contract_text.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(5, weight=1)

    def refresh(self, data: dict) -> None:
        contract_status = data.get("contract_status", {})
        acks = contract_status.get("acks", [])
        events = contract_status.get("recent_events", [])
        summary = {
            "contract_id": contract_status.get("contract_id"),
            "version": contract_status.get("version"),
            "text_hash": contract_status.get("text_hash"),
            "outstanding_grants": contract_status.get("outstanding_grants", []),
        }

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

    @staticmethod
    def _replace_tree_rows(tree: ttk.Treeview, rows: list[tuple]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for row in rows:
            tree.insert("", tk.END, values=row)

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
