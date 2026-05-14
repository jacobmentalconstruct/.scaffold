"""
FILE: src/ui/main_window.py
ROLE: Tkinter operator console for the sidecar.
WHAT IT DOES: Launches a Tk UI that surfaces monitoring state plus the
              approval/operator surfaces added in T4 through a unified
              dashboard and detailed tabs for state, journal, evidence,
              project map, contracts, and handoff.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from src.lib.common import now_iso
from src.ui.contracts_panel import ContractsPanel
from src.ui.evidence_panel import EvidencePanel
from src.ui.handoff_panel import HandoffPanel
from src.ui.journal_panel import JournalPanel
from src.ui.local_agent_panel import LocalAgentPanel
from src.ui.project_map_panel import ProjectMapPanel
from src.ui.state_panel import StatePanel
from src.ui.training_runway_panel import TrainingRunwayPanel


POLL_MS = 3000


class DashboardView(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._columns = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._columns.grid(row=0, column=0, sticky="nsew")

        self._past = ttk.Frame(self._columns, padding=6)
        self._present = ttk.Frame(self._columns, padding=6)
        self._future = ttk.Frame(self._columns, padding=6)
        for frame in (self._past, self._present, self._future):
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(1, weight=1)
        self._columns.add(self._past, weight=1)
        self._columns.add(self._present, weight=1)
        self._columns.add(self._future, weight=1)

        self._build_past()
        self._build_present()
        self._build_future()

        self._log = ScrolledText(self, wrap=tk.NONE, height=10)
        _style_text_widget(self._log)
        self._log.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.rowconfigure(1, weight=0)

    def _build_past(self) -> None:
        ttk.Label(self._past, text="PAST", style="Heading.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        body = ttk.Frame(self._past)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)
        body.rowconfigure(5, weight=1)

        ttk.Label(body, text="Recent Journal").grid(row=0, column=0, sticky="w")
        self._journal_tree = ttk.Treeview(
            body,
            columns=("kind", "status", "title"),
            show="headings",
            height=6,
        )
        for col, label, width in (("kind", "Kind", 90), ("status", "Status", 90), ("title", "Title", 280)):
            self._journal_tree.heading(col, text=label)
            self._journal_tree.column(col, width=width, anchor=tk.W)
        self._journal_tree.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        ttk.Label(body, text="Recent Events").grid(row=2, column=0, sticky="w")
        self._events_tree = ttk.Treeview(
            body,
            columns=("created_at", "operation_intent", "actor_id"),
            show="headings",
            height=6,
        )
        for col, label, width in (
            ("created_at", "Created", 150),
            ("operation_intent", "Intent", 150),
            ("actor_id", "Actor", 220),
        ):
            self._events_tree.heading(col, text=label)
            self._events_tree.column(col, width=width, anchor=tk.W)
        self._events_tree.grid(row=3, column=0, sticky="nsew", pady=(0, 8))

        ttk.Label(body, text="Recent Tool Invocations").grid(row=4, column=0, sticky="w")
        self._tools_tree = ttk.Treeview(
            body,
            columns=("started_at", "tool_name", "status"),
            show="headings",
            height=6,
        )
        for col, label, width in (
            ("started_at", "Started", 150),
            ("tool_name", "Tool", 180),
            ("status", "Status", 90),
        ):
            self._tools_tree.heading(col, text=label)
            self._tools_tree.column(col, width=width, anchor=tk.W)
        self._tools_tree.grid(row=5, column=0, sticky="nsew")

    def _build_present(self) -> None:
        ttk.Label(self._present, text="PRESENT", style="Heading.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._present_text = ScrolledText(self._present, wrap=tk.WORD)
        _style_text_widget(self._present_text)
        self._present_text.grid(row=1, column=0, sticky="nsew")

    def _build_future(self) -> None:
        ttk.Label(self._future, text="FUTURE", style="Heading.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        body = ttk.Frame(self._future)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(body, text="Drift Checks").grid(row=0, column=0, sticky="w")
        self._drift_tree = ttk.Treeview(
            body,
            columns=("ok", "label"),
            show="headings",
            height=5,
        )
        self._drift_tree.heading("ok", text="OK")
        self._drift_tree.heading("label", text="Check")
        self._drift_tree.column("ok", width=60, anchor=tk.CENTER)
        self._drift_tree.column("label", width=320, anchor=tk.W)
        self._drift_tree.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        ttk.Label(body, text="Scope / Plan / Open Items").grid(row=2, column=0, sticky="w")
        self._future_text = ScrolledText(body, wrap=tk.WORD)
        _style_text_widget(self._future_text)
        self._future_text.grid(row=3, column=0, sticky="nsew")

    def refresh(self, data: dict) -> None:
        viewport = data.get("viewport", {})
        past = viewport.get("past", {})
        present = viewport.get("present", {})
        future = viewport.get("future", {})

        _replace_tree(
            self._journal_tree,
            [
                (row.get("kind", ""), row.get("status", ""), row.get("title", ""))
                for row in past.get("recent_journal", [])
            ],
        )
        _replace_tree(
            self._events_tree,
            [
                (
                    row.get("created_at", ""),
                    row.get("operation_intent", ""),
                    row.get("actor_id", ""),
                )
                for row in past.get("recent_events", [])
            ],
        )
        _replace_tree(
            self._tools_tree,
            [
                (
                    row.get("started_at", ""),
                    row.get("tool_name", ""),
                    row.get("status", ""),
                )
                for row in past.get("recent_tools", [])
            ],
        )

        present_lines = [
            "Current Snapshot",
            "",
            f"sidecar_id: {present.get('current_state', {}).get('sidecar_id', '')}",
            f"project_root: {present.get('current_state', {}).get('project_root', '')}",
            f"sidecar_root: {present.get('current_state', {}).get('sidecar_root', '')}",
            f"event_log_position: {present.get('current_state', {}).get('event_log_position', 0)}",
            f"registered_tools: {present.get('current_state', {}).get('registered_tool_count', 0)}",
            f"pending_approvals: {present.get('pending_approvals', 0)}",
            f"local_agent_status: {(present.get('current_state', {}).get('agent_status') or {}).get('status', 'idle')}",
            f"stm_count: {(present.get('memory', {}) or {}).get('stm_count', 0)}",
            f"bag_count: {(present.get('memory', {}) or {}).get('bag_count', 0)}",
            f"shelf_count: {(present.get('memory', {}) or {}).get('shelf_count', 0)}",
            "",
            "Current Agent",
            f"actor_id: {present.get('current_agent', {}).get('actor_id', 'none')}",
            f"last_operation: {present.get('current_agent', {}).get('last_operation_intent', 'n/a')}",
            f"last_seen_at: {present.get('current_agent', {}).get('last_seen_at', 'n/a')}",
            f"active_sessions: {len(present.get('agent_sessions', []))}",
            "",
            "Latest Scan",
            f"scan_id: {present.get('latest_scan', {}).get('scan_id', 'n/a')}",
            f"status: {present.get('latest_scan', {}).get('status', 'n/a')}",
            f"files: {present.get('latest_scan', {}).get('file_count', 0)}",
            "",
            "Latest Git",
            f"branch: {present.get('latest_git', {}).get('branch', 'n/a')}",
            f"dirty_count: {present.get('latest_git', {}).get('dirty_count', 0)}",
            "",
            "Active Tranche",
            f"title: {present.get('active_tranche', {}).get('title', 'none')}",
            f"decisions_count: {present.get('active_tranche', {}).get('decisions_count', 0)}",
        ]
        _set_text(self._present_text, "\n".join(present_lines))

        _replace_tree(
            self._drift_tree,
            [("yes" if row.get("ok") else "no", row.get("label", "")) for row in future.get("drift_checks", [])],
        )

        future_lines = [
            "Current Tranche Scope",
            json.dumps(future.get("current_tranche_scope", {}), indent=2),
            "",
            "Next Planned Steps",
            *[f"- {line}" for line in future.get("next_planned_steps", [])],
            "",
            "Active Goals",
            *[f"- {line}" for line in future.get("active_goals", [])],
            "",
            "Open TODOs",
            *[
                f"- {row.get('title', row.get('body', row.get('body_excerpt', '')))}"
                for row in future.get("open_todos", [])
            ],
            "",
            "Evidence Shelf",
            *[
                f"- {row.get('summary', '')}"
                for row in present.get("memory", {}).get("evidence_shelf", [])
            ],
            "",
            "Open Questions",
            *[f"- {line}" for line in future.get("open_questions", [])],
        ]
        _set_text(self._future_text, "\n".join(future_lines))

        _set_text(self._log, "\n".join(data.get("viewport", {}).get("log", {}).get("lines", [])))


class MonitoringConsole(ttk.Frame):
    def __init__(self, master: tk.Tk, state):
        super().__init__(master)
        self.master = master
        self.state = state
        self._tab_ids: dict[str, str] = {}
        self._refresh_after_id: str | None = None
        self._closed = False

        self.master.title(".scaffold — Tk Operator Console")
        self.master.geometry("1680x1020")
        self.master.minsize(1240, 820)
        self.master.bind("<Destroy>", self._on_destroy, add="+")

        _configure_style(master)

        self.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._title_var = tk.StringVar(value=".SCAFFOLD — Sidecar Operator Console")
        self._status_var = tk.StringVar(value="Booting UI...")
        self._drift_var = tk.StringVar(value="")
        self._path_var = tk.StringVar(value=".")

        self._build_header()
        self._build_body()
        self._build_status_bar()

        self._refresh_loop()

    def _build_header(self) -> None:
        titlebar = ttk.Frame(self, padding=(10, 8))
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.columnconfigure(1, weight=1)
        ttk.Label(titlebar, text="●", style="Accent.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(titlebar, textvariable=self._title_var, style="Title.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 0))

        topbar = ttk.Frame(self, padding=(10, 0, 10, 8))
        topbar.grid(row=1, column=0, sticky="ew")
        topbar.columnconfigure(1, weight=1)
        ttk.Label(topbar, text="PROJECT").grid(row=0, column=0, sticky="w")
        ttk.Label(topbar, textvariable=self._path_var, style="Mono.TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._pill_frame = ttk.Frame(topbar)
        self._pill_frame.grid(row=0, column=2, sticky="e")

        self._drift_banner = ttk.Label(self, textvariable=self._drift_var, style="Banner.TLabel", anchor="w")
        self._drift_banner.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

    def _build_body(self) -> None:
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 8))

        left = ttk.Frame(body, padding=8)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Focus", style="Heading.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._focus_tree = ttk.Treeview(left, columns=("label", "count"), show="headings", height=18)
        self._focus_tree.heading("label", text="Surface")
        self._focus_tree.heading("count", text="Count")
        self._focus_tree.column("label", width=180, anchor=tk.W)
        self._focus_tree.column("count", width=70, anchor=tk.E)
        self._focus_tree.grid(row=1, column=0, sticky="nsew")
        self._focus_tree.bind("<<TreeviewSelect>>", self._on_focus_select)
        body.add(left, weight=1)

        right = ttk.Frame(body, padding=4)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self._notebook = ttk.Notebook(right)
        self._notebook.grid(row=0, column=0, sticky="nsew")
        body.add(right, weight=5)

        self._dashboard = DashboardView(self._notebook)
        self._state_panel = StatePanel(self._notebook)
        self._journal_panel = JournalPanel(self._notebook)
        self._evidence_panel = EvidencePanel(self._notebook, self.state)
        self._project_map_panel = ProjectMapPanel(self._notebook)
        self._contracts_panel = ContractsPanel(self._notebook, self.state)
        self._local_agent_panel = LocalAgentPanel(self._notebook, self.state)
        self._training_panel = TrainingRunwayPanel(self._notebook, self.state)
        self._handoff_panel = HandoffPanel(self._notebook)

        self._add_tab("dashboard", "Dashboard", self._dashboard)
        self._add_tab("state", "State", self._state_panel)
        self._add_tab("journal", "Journal", self._journal_panel)
        self._add_tab("evidence", "Evidence", self._evidence_panel)
        self._add_tab("projmap", "Project Map", self._project_map_panel)
        self._add_tab("contracts", "Contracts", self._contracts_panel)
        self._add_tab("localagent", "Local Agent", self._local_agent_panel)
        self._add_tab("training", "Training Runway", self._training_panel)
        self._add_tab("handoff", "Handoff", self._handoff_panel)

    def _build_status_bar(self) -> None:
        status = ttk.Frame(self, padding=(10, 4))
        status.grid(row=4, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self._status_var, style="Mono.TLabel").grid(row=0, column=0, sticky="w")

    def _add_tab(self, key: str, title: str, widget: ttk.Frame) -> None:
        self._notebook.add(widget, text=title)
        self._tab_ids[key] = str(widget)

    def _on_focus_select(self, _event=None) -> None:
        selection = self._focus_tree.selection()
        if not selection:
            return
        focus_id = selection[0]
        tab_widget = self._tab_ids.get(focus_id)
        if tab_widget:
            self._notebook.select(tab_widget)

    def _refresh_loop(self) -> None:
        if self._closed:
            return
        try:
            bundle = self._load_bundle()
            self._apply_bundle(bundle)
        except tk.TclError:
            self._closed = True
            return
        except Exception as exc:
            self._status_var.set(f"UI refresh error: {type(exc).__name__}: {exc}")
        finally:
            if not self._closed and self.master.winfo_exists():
                self._refresh_after_id = self.master.after(POLL_MS, self._refresh_loop)

    def _on_destroy(self, _event=None) -> None:
        self._closed = True
        if self._refresh_after_id and self.master.winfo_exists():
            try:
                self.master.after_cancel(self._refresh_after_id)
            except tk.TclError:
                pass
            self._refresh_after_id = None

    def _load_bundle(self) -> dict:
        self.state.human_ui_status.update(
            {
                "mode": "operator",
                "active_tab": self._notebook.tab(self._notebook.select(), "text"),
                "last_poll_at": now_iso(),
            }
        )
        self.state.projections.refresh("viewport_state")
        self.state.projections.refresh("handoff")
        self.state.projections.refresh("training_runway")

        viewport_row = _first_row(self.state.projections.read("viewport_state").rows)
        current_state_row = _first_row(self.state.projections.read("current_sidecar_state").rows)
        contract_status_row = _first_row(self.state.projections.read("contract_status").rows)
        human_dashboard_row = _first_row(self.state.projections.read("human_dashboard").rows)
        tranche_rows = self.state.projections.read("tranche_checklist").rows
        journal_rows = self.state.projections.read("journal_timeline").rows
        evidence_rows = self.state.projections.read("evidence_bag").rows
        project_rows = self.state.projections.read("project_map").rows
        handoff_row = _first_row(self.state.projections.read("handoff").rows)
        runtime_cockpit_row = _first_row(self.state.projections.read("runtime_cockpit").rows)
        training_runway_row = _first_row(self.state.projections.read("training_runway").rows)

        contract_text = ""
        blob_ref = (self.state.current_contract or {}).get("text_blob_ref")
        if blob_ref:
            try:
                contract_text = self.state.blob_store.get_text(blob_ref)
            except Exception:
                contract_text = ""

        contract_status = {
            "contract_id": contract_status_row.get("contract_id"),
            "version": contract_status_row.get("version"),
            "text_hash": contract_status_row.get("text_hash"),
            "acks": _loads(contract_status_row.get("acks_json"), []),
            "outstanding_grants": _loads(contract_status_row.get("outstanding_grants_json"), []),
            "recent_events": _loads(contract_status_row.get("recent_contract_events_json"), []),
        }
        human_dashboard = {
            "pending_approvals": _loads(human_dashboard_row.get("pending_approvals_json"), []),
            "recent_journal": _loads(human_dashboard_row.get("recent_journal_json"), []),
            "unresolved_issues": _loads(human_dashboard_row.get("unresolved_issues_json"), []),
            "current_tranche_scope": _loads(human_dashboard_row.get("current_tranche_scope_json"), {}),
            "last_scan_summary": _loads(human_dashboard_row.get("last_scan_summary_json"), {}),
        }
        handoff = {
            "latest_closed_tranche": _loads(handoff_row.get("latest_closed_tranche_json"), {}),
            "active_tranche": _loads(handoff_row.get("active_tranche_json"), {}),
            "active_horizon": _loads(handoff_row.get("active_horizon_json"), {}),
            "open_questions": _loads(handoff_row.get("open_questions_json"), []),
            "reading_order": _loads(handoff_row.get("reading_order_json"), []),
            "verification_commands": _loads(handoff_row.get("verification_commands_json"), []),
        }
        runtime_cockpit = {
            "active_run": _loads(runtime_cockpit_row.get("active_run_json"), {}),
            "recent_runs": _loads(runtime_cockpit_row.get("recent_runs_json"), []),
            "recent_failures": _loads(runtime_cockpit_row.get("recent_failures_json"), []),
            "latest_recovery_summary": _loads(runtime_cockpit_row.get("latest_recovery_summary_json"), {}),
            "run_heartbeat": _loads(runtime_cockpit_row.get("run_heartbeat_json"), {}),
            "last_runtime_event": _loads(runtime_cockpit_row.get("last_runtime_event_json"), {}),
            "touched_path_counts": _loads(runtime_cockpit_row.get("touched_path_counts_json"), {}),
            "grounding_counts": _loads(runtime_cockpit_row.get("grounding_counts_json"), {}),
            "selected_run_ids": _loads(runtime_cockpit_row.get("selected_run_ids_json"), []),
        }
        training_runway = {
            "scenario_inventory": _loads(training_runway_row.get("scenario_inventory_json"), []),
            "recent_runs": _loads(training_runway_row.get("recent_runs_json"), []),
            "recent_scorecards": _loads(training_runway_row.get("recent_scorecards_json"), []),
            "pass_fail_counts": _loads(training_runway_row.get("pass_fail_counts_json"), {}),
            "latest_live_proof": _loads(training_runway_row.get("latest_live_proof_json"), {}),
            "reviewer_export_handles": _loads(training_runway_row.get("reviewer_export_handles_json"), []),
        }
        operator_row = self.state.store.query_one(
            """
            SELECT actor_id FROM acknowledgments
            WHERE actor_id LIKE 'human:%'
            ORDER BY acknowledged_at DESC LIMIT 1;
            """
        )

        viewport = {
            "topbar": _loads(viewport_row.get("topbar_json"), {}),
            "focus": _loads(viewport_row.get("focus_json"), {}),
            "past": _loads(viewport_row.get("past_json"), {}),
            "present": _loads(viewport_row.get("present_json"), {}),
            "future": _loads(viewport_row.get("future_json"), {}),
            "log": _loads(viewport_row.get("log_json"), {}),
            "status_bar": _loads(viewport_row.get("status_bar_json"), {}),
            "last_refreshed_at": viewport_row.get("last_refreshed_at"),
        }

        return {
            "viewport": viewport,
            "current_state": current_state_row,
            "journal": journal_rows,
            "evidence": evidence_rows,
            "project_map": project_rows,
            "contract_status": contract_status,
            "contract_text": contract_text,
            "approval_queue": human_dashboard.get("pending_approvals", []),
            "human_dashboard": human_dashboard,
            "tranche_checklist": tranche_rows,
            "handoff": handoff,
            "runtime_cockpit": runtime_cockpit,
            "training_runway": training_runway,
            "default_operator_actor": operator_row["actor_id"] if operator_row else "human:ui",
        }

    def _apply_bundle(self, bundle: dict) -> None:
        viewport = bundle["viewport"]
        topbar = viewport.get("topbar", {})
        status_bar = viewport.get("status_bar", {})
        selected_focus = self._focus_tree.selection()
        selected_focus_id = selected_focus[0] if selected_focus else ""
        current_tab_widget = self._notebook.select()

        project_root = topbar.get("project_root", ".")
        sidecar_root = topbar.get("sidecar_root", ".")
        self._path_var.set(f"project={project_root}  sidecar={sidecar_root}")

        drift = topbar.get("drift_banner", {})
        self._drift_var.set(drift.get("message", ""))
        self._drift_banner.configure(style="BannerOk.TLabel" if drift.get("state") == "ok" else "BannerWarn.TLabel")

        for child in self._pill_frame.winfo_children():
            child.destroy()
        for pill in topbar.get("pills", []):
            style = {
                "ok": "PillOk.TLabel",
                "warn": "PillWarn.TLabel",
                "live": "PillLive.TLabel",
                "err": "PillErr.TLabel",
            }.get(pill.get("state"), "PillOk.TLabel")
            ttk.Label(self._pill_frame, text=pill.get("label", ""), style=style).pack(side=tk.LEFT, padx=(6, 0))

        for item in self._focus_tree.get_children():
            self._focus_tree.delete(item)
        for focus in viewport.get("focus", {}).get("options", []):
            self._focus_tree.insert(
                "",
                tk.END,
                iid=focus.get("id", ""),
                values=(focus.get("label", ""), focus.get("count", 0)),
            )
        if selected_focus_id and self._focus_tree.exists(selected_focus_id):
            self._focus_tree.selection_set(selected_focus_id)
        else:
            current_focus_id = self._focus_id_for_tab(current_tab_widget)
            if current_focus_id and self._focus_tree.exists(current_focus_id):
                self._focus_tree.selection_set(current_focus_id)
            elif self._focus_tree.exists("dashboard"):
                self._focus_tree.selection_set("dashboard")

        self._dashboard.refresh(bundle)
        self._state_panel.refresh(bundle)
        self._journal_panel.refresh(bundle)
        self._evidence_panel.refresh(bundle)
        self._project_map_panel.refresh(bundle)
        self._contracts_panel.refresh(bundle)
        self._local_agent_panel.refresh(bundle)
        self._training_panel.refresh(bundle)
        self._handoff_panel.refresh(bundle)

        if current_tab_widget:
            try:
                self._notebook.select(current_tab_widget)
            except tk.TclError:
                pass

        self._status_var.set(
            " | ".join(
                [
                    "READY" if status_bar.get("ready") else "NOT READY",
                    f"schema v{status_bar.get('schema_version', '?')}",
                    f"events {status_bar.get('events', 0)}",
                    f"journal {status_bar.get('journal', 0)}",
                    f"tools {status_bar.get('tools', 0)}",
                    f"agents {status_bar.get('agents', 0)}",
                    f"refreshed {viewport.get('last_refreshed_at', '')}",
                ]
            )
        )

    def _focus_id_for_tab(self, tab_widget: str) -> str:
        for focus_id, widget_id in self._tab_ids.items():
            if widget_id == tab_widget:
                return focus_id
        return ""


def run(state) -> int:
    root = tk.Tk()
    MonitoringConsole(root, state)
    root.mainloop()
    return 0


def _configure_style(root: tk.Tk) -> None:
    palette = {
        "bg": "#161A1F",
        "panel": "#1E252D",
        "field": "#263140",
        "border": "#2A3441",
        "text": "#E7EDF4",
        "muted": "#97A4B3",
        "accent": "#C56F3D",
        "teal": "#2E7081",
        "ok": "#2F8E6A",
        "warn": "#C99A3D",
        "err": "#B75A4D",
    }
    root.configure(background=palette["bg"])

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=palette["bg"], foreground=palette["text"])
    style.configure("TFrame", background=palette["bg"])
    style.configure("TLabel", background=palette["bg"], foreground=palette["text"])
    style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"), foreground=palette["text"])
    style.configure("Heading.TLabel", font=("Segoe UI", 10, "bold"), foreground=palette["text"])
    style.configure("Accent.TLabel", foreground=palette["accent"], background=palette["bg"])
    style.configure("Mono.TLabel", font=("Consolas", 10), foreground=palette["muted"], background=palette["bg"])

    style.configure("TNotebook", background=palette["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(12, 6), background=palette["panel"], foreground=palette["text"])
    style.map("TNotebook.Tab", background=[("selected", palette["field"])], foreground=[("selected", palette["accent"])])

    style.configure("Treeview", background=palette["panel"], fieldbackground=palette["panel"], foreground=palette["text"], rowheight=24)
    style.configure("Treeview.Heading", background=palette["field"], foreground=palette["text"], relief="flat")
    style.map("Treeview", background=[("selected", palette["teal"])], foreground=[("selected", palette["text"])])

    style.configure("PillOk.TLabel", background=palette["ok"], foreground=palette["text"], padding=(8, 4))
    style.configure("PillWarn.TLabel", background=palette["warn"], foreground="#111111", padding=(8, 4))
    style.configure("PillLive.TLabel", background=palette["accent"], foreground=palette["text"], padding=(8, 4))
    style.configure("PillErr.TLabel", background=palette["err"], foreground=palette["text"], padding=(8, 4))
    style.configure("Banner.TLabel", padding=(10, 6))
    style.configure("BannerOk.TLabel", background="#20352B", foreground="#89D6A0", padding=(10, 6))
    style.configure("BannerWarn.TLabel", background="#3A2E16", foreground="#F4C76A", padding=(10, 6))


def _style_text_widget(widget: ScrolledText) -> None:
    widget.configure(
        background="#10161E",
        foreground="#E7EDF4",
        insertbackground="#E7EDF4",
        selectbackground="#2E7081",
        font=("Consolas", 10),
        relief=tk.FLAT,
        borderwidth=1,
    )


def _replace_tree(tree: ttk.Treeview, rows: list[tuple]) -> None:
    for item in tree.get_children():
        tree.delete(item)
    for row in rows:
        tree.insert("", tk.END, values=row)


def _set_text(widget: ScrolledText, text: str) -> None:
    widget.configure(state=tk.NORMAL)
    widget.delete("1.0", tk.END)
    widget.insert("1.0", text)
    widget.configure(state=tk.DISABLED)


def _loads(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _first_row(rows: list[dict]) -> dict:
    return rows[0] if rows else {}
