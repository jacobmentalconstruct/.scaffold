"""
FILE: src/ui/installed_project_proof_panel.py
ROLE: Tk operator panel for T9 installed-project proof visibility.
WHAT IT DOES: Shows the latest vendability proof, recent proof runs,
              verification state, and exports the cold-team handoff packet.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class InstalledProjectProofPanel(ttk.Frame):
    def __init__(self, master, state):
        super().__init__(master, padding=8)
        self._state = state
        self._busy = False
        self._selected_proof_id = ""

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        self._status_var = tk.StringVar(value="Installed-project proof idle.")

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self._create_btn = ttk.Button(controls, text="Create Fixture", command=self._create_fixture)
        self._create_btn.pack(fill="x")
        self._run_btn = ttk.Button(controls, text="Run Proof", command=self._run_proof)
        self._run_btn.pack(fill="x", pady=(6, 0))
        self._verify_btn = ttk.Button(controls, text="Verify Latest Proof", command=self._verify_latest)
        self._verify_btn.pack(fill="x", pady=(6, 0))
        self._export_btn = ttk.Button(controls, text="Export Handoff Packet", command=self._export_latest)
        self._export_btn.pack(fill="x", pady=(6, 0))
        ttk.Label(controls, textvariable=self._status_var, wraplength=240).pack(anchor="w", pady=(10, 0))

        ttk.Label(self, text="Recent Proof Runs").grid(row=0, column=1, sticky="w")
        self._proof_tree = ttk.Treeview(
            self,
            columns=("proof_run_id", "status", "supersession"),
            show="headings",
            height=8,
        )
        for col, label, width in (
            ("proof_run_id", "Proof Run", 260),
            ("status", "Status", 90),
            ("supersession", "Supersession", 180),
        ):
            self._proof_tree.heading(col, text=label)
            self._proof_tree.column(col, width=width, anchor=tk.W)
        self._proof_tree.grid(row=1, column=1, sticky="nsew")
        self._proof_tree.bind("<<TreeviewSelect>>", self._on_select)

        ttk.Label(self, text="Selected Proof Detail").grid(row=2, column=0, sticky="w", pady=(10, 6))
        ttk.Label(self, text="Proof Summary").grid(row=2, column=1, sticky="w", pady=(10, 6))
        self._detail_text = ScrolledText(self, wrap=tk.WORD, height=16)
        self._summary_text = ScrolledText(self, wrap=tk.WORD, height=16)
        self._detail_text.grid(row=3, column=0, sticky="nsew", padx=(0, 10))
        self._summary_text.grid(row=3, column=1, sticky="nsew")
        for widget in (self._detail_text, self._summary_text):
            widget.configure(state=tk.DISABLED)

    def refresh(self, data: dict) -> None:
        summary = data.get("installed_project_proof", {}) or {}
        proofs = summary.get("recent_proofs", [])
        self._proof_tree.delete(*self._proof_tree.get_children())
        for proof in proofs:
            iid = str(proof.get("proof_run_id", ""))
            self._proof_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(iid, proof.get("status", ""), proof.get("supersession_status", "")),
            )
        if self._selected_proof_id and self._proof_tree.exists(self._selected_proof_id):
            self._proof_tree.selection_set(self._selected_proof_id)
        elif proofs:
            self._selected_proof_id = str(proofs[0].get("proof_run_id", ""))
            if self._proof_tree.exists(self._selected_proof_id):
                self._proof_tree.selection_set(self._selected_proof_id)

        detail = {}
        if self._selected_proof_id:
            for proof in proofs:
                if str(proof.get("proof_run_id", "")) == self._selected_proof_id:
                    detail = proof
                    break
        self._set_text(self._detail_text, json.dumps(detail, indent=2))
        self._set_text(self._summary_text, json.dumps(summary, indent=2))

    def _on_select(self, _event=None) -> None:
        selection = self._proof_tree.selection()
        self._selected_proof_id = selection[0] if selection else ""

    def _create_fixture(self) -> None:
        self._run_background(
            "Creating installed proof fixture...",
            lambda: self._state.installed_project_proof_manager.create_fixture(reset=True),
        )

    def _run_proof(self) -> None:
        self._run_background(
            "Running installed-project vendability proof...",
            self._state.installed_project_proof_manager.run_proof,
        )

    def _verify_latest(self) -> None:
        self._run_background(
            "Verifying latest installed-project proof...",
            lambda: self._state.installed_project_proof_manager.verify_proof(proof_run_id=self._selected_proof_id or ""),
        )

    def _export_latest(self) -> None:
        self._run_background(
            "Exporting installed-project handoff packet...",
            lambda: self._state.installed_project_proof_manager.export_handoff_packet(proof_run_id=self._selected_proof_id or ""),
        )

    def _run_background(self, busy_text: str, fn) -> None:
        if self._busy:
            return
        self._busy = True
        self._status_var.set(busy_text)
        self._set_buttons("disabled")

        def worker() -> None:
            try:
                payload = fn()
            except Exception as exc:  # pragma: no cover - UI defensive wrapper
                payload = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            self.after(0, lambda: self._after_result(payload))

        threading.Thread(target=worker, daemon=True).start()

    def _after_result(self, payload: dict) -> None:
        self._busy = False
        self._set_buttons("normal")
        self._status_var.set(payload.get("status", "ok"))
        self._set_text(self._summary_text, json.dumps(payload, indent=2))
        try:
            self._state.projections.refresh("installed_project_proof")
            self._state.projections.refresh("viewport_state")
            self._state.projections.refresh("handoff")
        except Exception:
            pass

    def _set_buttons(self, state: str) -> None:
        for button in (self._create_btn, self._run_btn, self._verify_btn, self._export_btn):
            button.configure(state=state)

    @staticmethod
    def _set_text(widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
