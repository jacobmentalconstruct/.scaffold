"""
FILE: main_window.py
ROLE: UI orchestrator.
WHAT IT DOES: Composes panes and widgets, routes events between them.
    This file should contain ZERO rendering logic — only layout and dispatch.
CONTRACT:
    - Receives the Engine (or core facade) via __init__
    - Creates and arranges panes
    - Routes user events to the engine, engine results to the panes
    - Never contains business logic
"""

from __future__ import annotations

import tkinter as tk


class MainWindow:
    """UI orchestrator — composes panes, routes events."""

    def __init__(self, root: tk.Tk, *, engine) -> None:
        self._root = root
        self._engine = engine
        self._root.title("Application")
        # Compose panes here:
        #   self._chat = ChatPane(root, ...)
        #   self._controls = ControlPane(root, ...)

    def mainloop(self) -> None:
        self._root.mainloop()
