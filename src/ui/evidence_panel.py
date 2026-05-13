"""
FILE: src/ui/evidence_panel.py
ROLE: Read-only Tk panel for evidence inspection.
WHAT IT DOES: Shows recent evidence items with a detail pane and, when
              possible, a text preview of the underlying blob.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class EvidencePanel(ttk.Frame):
    def __init__(self, master, state):
        super().__init__(master, padding=8)
        self._state = state
        self._rows: list[dict] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._tree = ttk.Treeview(
            self,
            columns=("kind", "status", "created_at", "summary"),
            show="headings",
        )
        for column, label, width in (
            ("kind", "Kind", 120),
            ("status", "Status", 90),
            ("created_at", "Created", 150),
            ("summary", "Summary", 460),
        ):
            self._tree.heading(column, text=label)
            self._tree.column(column, width=width, anchor=tk.W)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        self._detail = ScrolledText(self, wrap=tk.WORD, height=16)
        self._detail.configure(state=tk.DISABLED)

        self._tree.grid(row=0, column=0, sticky="nsew")
        self._detail.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def refresh(self, data: dict) -> None:
        self._rows = list(data.get("evidence", []))
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in self._rows:
            self._tree.insert(
                "",
                tk.END,
                iid=row.get("evidence_id", ""),
                values=(
                    row.get("kind", ""),
                    row.get("status", ""),
                    row.get("created_at", ""),
                    row.get("summary", ""),
                ),
            )
        if self._rows:
            first = self._rows[0].get("evidence_id", "")
            if first:
                self._tree.selection_set(first)
                self._show_row(self._rows[0])
        else:
            self._set_text("No evidence items available.")

    def _on_select(self, _event=None) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        target = selected[0]
        for row in self._rows:
            if row.get("evidence_id") == target:
                self._show_row(row)
                return

    def _show_row(self, row: dict) -> None:
        preview = None
        hash_hex = row.get("hash", "")
        if hash_hex and self._state.blob_store.exists(hash_hex):
            meta = self._state.blob_store.metadata(hash_hex)
            content_type = meta.get("content_type", "")
            if content_type.startswith("text/") or content_type == "application/json":
                try:
                    preview = self._state.blob_store.get_text(hash_hex)[:1200]
                except Exception:
                    preview = None

        payload = {
            "evidence_id": row.get("evidence_id"),
            "kind": row.get("kind"),
            "status": row.get("status"),
            "summary": row.get("summary"),
            "created_at": row.get("created_at"),
            "attached_to_object": row.get("attached_to_object"),
            "hash": hash_hex,
            "preview": preview,
        }
        self._set_text(json.dumps(payload, indent=2))

    def _set_text(self, text: str) -> None:
        self._detail.configure(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.insert("1.0", text)
        self._detail.configure(state=tk.DISABLED)
