"""
FILE: src/ui/state_panel.py
ROLE: Read-only Tk panel for sidecar state and operational summaries.
WHAT IT DOES: Shows the current sidecar snapshot, focus counts, current
              agent/tranche, and latest scan/git summaries.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class StatePanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self._focus_tree = ttk.Treeview(
            self,
            columns=("label", "count"),
            show="headings",
            height=8,
        )
        self._focus_tree.heading("label", text="Surface")
        self._focus_tree.heading("count", text="Count")
        self._focus_tree.column("label", width=220, anchor=tk.W)
        self._focus_tree.column("count", width=70, anchor=tk.E)

        self._summary_text = ScrolledText(self, wrap=tk.WORD, height=16)
        self._summary_text.configure(state=tk.DISABLED)

        self._detail_text = ScrolledText(self, wrap=tk.WORD, height=14)
        self._detail_text.configure(state=tk.DISABLED)

        ttk.Label(self, text="Monitoring Surfaces").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(self, text="Current State").grid(row=0, column=1, sticky="w", pady=(0, 6))

        self._focus_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._summary_text.grid(row=1, column=1, sticky="nsew")

        ttk.Label(self, text="Details").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 6))
        self._detail_text.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(3, weight=1)

    def refresh(self, data: dict) -> None:
        viewport = data.get("viewport", {})
        present = viewport.get("present", {})
        focus = viewport.get("focus", {}).get("options", [])
        current_state = present.get("current_state") or data.get("current_state", {})

        self._replace_tree_rows(
            self._focus_tree,
            [(item.get("label", ""), item.get("count", 0)) for item in focus],
        )

        summary_lines = [
            "Current Sidecar State",
            "",
            f"sidecar_id: {current_state.get('sidecar_id', '')}",
            f"sidecar_root: {current_state.get('sidecar_root', '')}",
            f"project_root: {current_state.get('project_root', '')}",
            f"event_log_position: {current_state.get('event_log_position', 0)}",
            f"registered_tools: {current_state.get('registered_tool_count', 0)}",
            f"registered_objects: {current_state.get('registered_object_count', 0)}",
            f"stm_count: {(current_state.get('memory_state') or {}).get('stm_count', 0)}",
            f"bag_count: {(current_state.get('memory_state') or {}).get('bag_count', 0)}",
            f"shelf_count: {(current_state.get('memory_state') or {}).get('shelf_count', 0)}",
            "",
            "Contract",
            f"contract_id: {present.get('contract', {}).get('contract_id', '')}",
            f"version: {present.get('contract', {}).get('version', '')}",
            f"ack_count: {present.get('contract', {}).get('ack_count', 0)}",
            "",
            "Latest Agent",
            f"actor_id: {present.get('current_agent', {}).get('actor_id', 'none')}",
            f"authority: {present.get('current_agent', {}).get('authority', 'n/a')}",
            f"last_seen_at: {present.get('current_agent', {}).get('last_seen_at', 'n/a')}",
            "",
            "Active Tranche",
            f"title: {present.get('active_tranche', {}).get('title', 'none')}",
            f"decisions_count: {present.get('active_tranche', {}).get('decisions_count', 0)}",
        ]
        self._set_text(self._summary_text, "\n".join(summary_lines))

        detail = {
            "latest_scan": present.get("latest_scan", {}),
            "latest_git": present.get("latest_git", {}),
            "memory": present.get("memory", {}),
            "human_dashboard": data.get("human_dashboard", {}),
            "tranche_checklist": data.get("tranche_checklist", []),
        }
        self._set_text(self._detail_text, json.dumps(detail, indent=2))

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
