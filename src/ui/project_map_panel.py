"""
FILE: src/ui/project_map_panel.py
ROLE: Read-only Tk panel for project map inspection.
WHAT IT DOES: Shows indexed files/directories with journal/evidence counts
              and a selection-linked detail pane.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class ProjectMapPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self._rows: list[dict] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._tree = ttk.Treeview(
            self,
            columns=("kind", "size_bytes", "journal_cite_count", "evidence_count", "path"),
            show="headings",
        )
        for column, label, width, anchor in (
            ("kind", "Kind", 90, tk.W),
            ("size_bytes", "Bytes", 100, tk.E),
            ("journal_cite_count", "Journal", 80, tk.E),
            ("evidence_count", "Evidence", 80, tk.E),
            ("path", "Path", 560, tk.W),
        ):
            self._tree.heading(column, text=label)
            self._tree.column(column, width=width, anchor=anchor)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        self._detail = ScrolledText(self, wrap=tk.WORD, height=16)
        self._detail.configure(state=tk.DISABLED)

        self._tree.grid(row=0, column=0, sticky="nsew")
        self._detail.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def refresh(self, data: dict) -> None:
        self._rows = list(data.get("project_map", []))
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in self._rows:
            iid = row.get("path", "")
            self._tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    row.get("kind", ""),
                    row.get("size_bytes", 0),
                    row.get("journal_cite_count", 0),
                    row.get("evidence_count", 0),
                    row.get("path", ""),
                ),
            )
        if self._rows:
            first = self._rows[0].get("path", "")
            if first:
                self._tree.selection_set(first)
                self._show_row(self._rows[0])
        else:
            self._set_text("Project map is empty.")

    def _on_select(self, _event=None) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        target = selected[0]
        for row in self._rows:
            if row.get("path") == target:
                self._show_row(row)
                return

    def _show_row(self, row: dict) -> None:
        self._set_text(json.dumps(row, indent=2))

    def _set_text(self, text: str) -> None:
        self._detail.configure(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.insert("1.0", text)
        self._detail.configure(state=tk.DISABLED)
