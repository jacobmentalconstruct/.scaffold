"""
FILE: src/ui/handoff_panel.py
ROLE: Cold-start handoff panel for humans.
WHAT IT DOES: Shows the latest parked tranche, active horizon, reading
              order, and verification commands derived from the handoff
              projection.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class HandoffPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._text = ScrolledText(self, wrap=tk.WORD)
        self._text.configure(state=tk.DISABLED)
        self._text.grid(row=0, column=0, sticky="nsew")

    def refresh(self, data: dict) -> None:
        handoff = data.get("handoff", {})
        latest_closed = handoff.get("latest_closed_tranche", {})
        active_tranche = handoff.get("active_tranche", {})
        active_horizon = handoff.get("active_horizon", {})
        horizon_label = active_horizon.get("label", "Next Horizon")
        lines = [
            "Latest Parked Tranche",
            json.dumps(latest_closed, indent=2),
            "",
            "Active Tranche",
            json.dumps(active_tranche, indent=2),
            "",
            horizon_label,
            json.dumps(active_horizon, indent=2),
            "",
            "Open Questions",
            *[f"- {item}" for item in handoff.get("open_questions", [])],
            "",
            "Reading Order",
            *[f"{idx}. {item}" for idx, item in enumerate(handoff.get("reading_order", []), start=1)],
            "",
            "Verification Commands",
            *[f"- {item}" for item in handoff.get("verification_commands", [])],
        ]
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", "\n".join(lines))
        self._text.configure(state=tk.DISABLED)
