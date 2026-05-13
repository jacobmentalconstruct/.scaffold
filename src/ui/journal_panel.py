"""
FILE: src/ui/journal_panel.py
ROLE: Read-only Tk panel for journal timeline inspection.
WHAT IT DOES: Shows journal entries in a table with a selection-linked
              detail pane for body excerpts, tags, evidence refs, and
              related paths.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class JournalPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._rows: list[dict] = []
        self._tree = ttk.Treeview(
            self,
            columns=("created_at", "kind", "status", "importance", "title"),
            show="headings",
        )
        for column, label, width in (
            ("created_at", "Created", 150),
            ("kind", "Kind", 90),
            ("status", "Status", 90),
            ("importance", "Imp", 60),
            ("title", "Title", 420),
        ):
            self._tree.heading(column, text=label)
            self._tree.column(column, width=width, anchor=tk.W)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        self._detail = ScrolledText(self, wrap=tk.WORD, height=16)
        self._detail.configure(state=tk.DISABLED)

        self._tree.grid(row=0, column=0, sticky="nsew")
        self._detail.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def refresh(self, data: dict) -> None:
        self._rows = list(data.get("journal", []))
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in self._rows:
            self._tree.insert(
                "",
                tk.END,
                iid=row.get("entry_uid", ""),
                values=(
                    row.get("created_at", ""),
                    row.get("kind", ""),
                    row.get("status", ""),
                    row.get("importance", ""),
                    row.get("title", ""),
                ),
            )
        if self._rows:
            first = self._rows[0].get("entry_uid", "")
            if first:
                self._tree.selection_set(first)
                self._show_row(self._rows[0])
        else:
            self._set_text("No journal entries available.")

    def _on_select(self, _event=None) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        target = selected[0]
        for row in self._rows:
            if row.get("entry_uid") == target:
                self._show_row(row)
                return

    def _show_row(self, row: dict) -> None:
        evidence_refs = row.get("evidence_refs_json")
        if isinstance(evidence_refs, str):
            try:
                evidence_refs = json.loads(evidence_refs)
            except json.JSONDecodeError:
                evidence_refs = []
        payload = {
            "entry_uid": row.get("entry_uid"),
            "kind": row.get("kind"),
            "source": row.get("source"),
            "title": row.get("title"),
            "status": row.get("status"),
            "importance": row.get("importance"),
            "created_at": row.get("created_at"),
            "tags": json.loads(row.get("tags_json") or "[]") if row.get("tags_json") else [],
            "related_path": row.get("related_path"),
            "body_excerpt": row.get("body_excerpt", ""),
            "evidence_refs": evidence_refs or [],
        }
        self._set_text(json.dumps(payload, indent=2))

    def _set_text(self, text: str) -> None:
        self._detail.configure(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.insert("1.0", text)
        self._detail.configure(state=tk.DISABLED)
