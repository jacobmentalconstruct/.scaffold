# T2 Park Notes — Install + Scan + Journal + MCP

> **Status:** Code-time artifact written alongside the T2 closeout journal entry. The journal entry (kind='tranche') is the authoritative LTM record; this file is its human-readable mirror, cited by the entry's `related_path` and `evidence_refs`.
>
> **No SUPERSEDED banner here.** Unlike T1's degraded Park Phase, T2 was closed with a proper journal entry from the start. Going forward, every tranche closes this way.

---

## Tranche scope (declared at open)

Per `IMPLEMENTATION_ROADMAP.md` T2 spec:

> **Install + Scan + Journal + read-only MCP.** First proving-loop walk: install, scan a project, journal it, expose projections via MCP. The sidecar becomes self-aware (its own LTM accumulates).

Files declared: ~20 additional. Tools 1–11 from the slate. Three projection builders (Project Map, Journal Timeline, Current Sidecar State — the last already done in T1).

## Sub-tranche breakdown

T2 was executed in three sub-tranches:

| Sub | Title | Headline outcome |
|---|---|---|
| T2.1 | Journal layer + handoff | journal_manager up; **T1 handoff HONORED** with proper journal entry at `journal_18ae7c440531739c_104fb685` citing the T1 closeout blob hash. |
| T2.2 | Install + Scan + Project Index | file_scanner walks ~65 files; project_index populated; install_orchestrator records first-boot event; scan_orchestrator commits one summary event with per-file rows in project_index. |
| T2.3 | Git + Evidence + Tools + MCP | git_reader read-only; evidence_manager attach+verify; tool_registry_manager discovers tools; 5 tools landed; **read-only MCP stdio server functional**. |

## What was built (T2 totals)

**Migrations applied:** v2 (T2.1), v3 (T2.2), v4 (T2.3). Schema went from 19 tables → 27 tables.

**New code files (~25):**

- `src/managers/`: journal_manager, project_index_manager, evidence_manager, git_state_manager, tool_registry_manager
- `src/orchestrators/`: journal_orchestrator (basic), install_orchestrator, scan_orchestrator, agent_task_orchestrator (skeleton)
- `src/components/`: file_scanner, git_reader
- `src/interfaces/`: mcp_interface (read-only MCP stdio server)
- `src/tools/`: file_tree_snapshot, workspace_boundary_audit, host_capability_probe, text_file_reader, read_projection
- Updates to: sqlite_store (migrations v2/v3/v4), state, app, router (scan finalize hook), projections (3 real builders added — journal_timeline, project_map, human_dashboard), cli_interface (~12 new subcommands), schemas (event_schema + contract_schema + projection_schema additions)

**~5,000 additional lines of Python code** beyond T1's ~3,850.

**Handlers registered (12 new in T2, plus 1 from T1 = 13 total):**
- T2.1: create_journal_entry, update_journal_entry, close_journal_entry, archive_journal_entry
- T2.2: install, scan
- T2.3: attach_evidence, verify_evidence, observe_git, tool_invoked, accept_task, complete_task

**Tools registered:** 5 (all `Observe` authority).

**Projection builders real (T2 raised count from 2 → 5):**
- current_sidecar_state, contract_status (from T1)
- journal_timeline (T2.1), project_map (T2.2), human_dashboard (T2.2)
- Still stubs: agent_bootstrap, evidence_bag (defer to T3+)

**CLI surface (T2 totals — 17 subcommands):**
- T1: ack-contract, status, version, projection, list-projections
- T2.1: journal-write, journal-query, journal-show
- T2.2: install, scan, scan-status
- T2.3: git-observe, git-status, evidence-attach, evidence-list, tool-list, tool-invoke

**MCP modes:** stdio read-only — `python -m src.app mcp`. Methods: initialize, tools/list, tools/call, resources/list, resources/read, ping.

## Verification

**`python smoke_test.py` — 35/35 sections PASS.** Coverage:

- Spine integrity (sections 1–10): boot, constraints seeded, contract loaded, gate behavior pre/post-ack, ack envelope round-trip, PENDING marker resolution, projections refresh.
- Journal layer (11–16): schema v2, handlers, write end-to-end, PENDING resolution, timeline projection, **T1 handoff HONORED**.
- Install + Scan (17–25): schema v3, handlers, idempotent install event, scan walks 65+ files, scan-record bound to event, project_index populated, project_map populated, human_dashboard refreshed, sidecar self-indexed.
- Git + Evidence + Tools + MCP (26–35): schema v4, 6 handlers, tool discovery, tool invocation, tool_invocations table, git observation, evidence attach + verify, MCP initialize / tools/list / tools/call / resources/list / resources/read.

## Proving-loop status (per ARCHITECTURE.md §10)

| # | Step | Status |
|---|---|---|
| 1 | Install sidecar into project | ✓ (idempotent install_orchestrator) |
| 2 | Scan project files | ✓ (scan_orchestrator + file_scanner) |
| 3 | Create project map | ✓ (proj_project_map populated) |
| 4 | Emit events for scan | ✓ (1 scan event with summary; tool_invoked events too) |
| 5 | Create graph edges for file structure | ⏳ Deferred design choice — per-file edges would violate Envelope Lightness. Graph relations land for journal/evidence chains (T4+). |
| 6 | Generate human dashboard projection | ✓ (proj_human_dashboard real builder) |
| 7 | Generate agent bootstrap packet | ⚠️ Stub builder — real builder lands T3 (alongside Tk UI which consumes it). |
| 8 | Agent proposes a journal entry | ✓ (create_journal_entry envelope works via CLI and MCP) |
| 9 | Human inspects the evidence | ⚠️ CLI-only for now — Tk UI lands T3. |

**~70% of the proving loop is end-to-end working.** The remaining 30% (Tk UI + agent_bootstrap projection) is the T3 focus.

## Decisions made at code time (T2)

1. **Per-file scan events deferred** — scan emits ONE event with summary blob; per-file rows live in project_index. Per-file events would balloon the event log and violate Envelope Lightness (Pledge 7).
2. **Graph edges during scan deferred** — same reasoning. Graph relations get applied during evidence/journal flows (which already need them).
3. **Tool registry: in-memory + DB dual** — registered tools live both in tool_registry SQL table (persistent, queryable, hash-tracked) AND in an in-memory dict on the manager (for fast `run_fn` callable access). Discovery on every boot is idempotent via INSERT...ON CONFLICT.
4. **MCP actor resolution** — `agent:mcp:<client_name>` derived from `params._meta.client_name`. Real per-session identity is deferred to T3 when MCP sessions become first-class.
5. **HARD_BLOCK gate still advisory** — tools enforce their own `required_authority` via `tool_registry_manager.handle_invoke`. The gate enforces the overarching `tool_invoked` authority (Observe). This two-tier check works without bloating the gate.
6. **Tool finalize hook NOT registered** — tool_invocations table records invocations directly inside handle_invoke (which has access to the started/finished timestamps). The Router post-commit hook for tool_invoked could update event_id; deferred until needed.
7. **agent_task is skeleton-only** — accept_task / complete_task track state.active_task in memory. Persistent task records via journal entries of kind='task' lands T4 when the proposal/approval cycle needs full task lifecycle.
8. **Evidence kinds open** — `attach_evidence` accepts kinds outside the documented `VALID_KINDS` tuple with a warning. Strict enforcement would require updating the contract; defer.
9. **Removal counting deferred** — `mark_removed_for_scan` is a placeholder; we don't currently delete or tombstone removed paths from project_index. Future scans re-observe; absent paths just stop incrementing `observe_count`.
10. **File scanner ignore list is hard-coded** — `.gitignore` parsing deferred. Hard-coded skip list covers `.git`, `__pycache__`, runtime folders, common file patterns. Good enough for our scaffold; refine if/when scanning host projects with unusual ignore rules.

## Open questions discovered (beyond ARCHITECTURE.md §15)

- **Removed-file lifecycle** — when a file disappears between scans, do we tombstone, delete, or just stop updating? Currently option 3.
- **Tool hot-reload** — if a tool's source changes, the in-memory `run_fn` is stale until next boot. Reload-on-source-hash-change is straightforward; defer until it matters.
- **MCP transport** — stdio only. HTTP transport for remote agents is a Phase 2 question.
- **Per-file relations** — design tension between "track everything in the graph" and "envelopes stay light." Current resolution: graph stays sparse, project_index is dense. Revisit if a downstream tool needs per-file graph traversal.

## Next tranche

**T3 — Tk UI surfaces.** Per IMPLEMENTATION_ROADMAP.md:
- `src/ui/main_window.py` + 4 panels (state, journal, evidence, project_map).
- Real `proj_agent_bootstrap` builder (PAST/PRESENT/FUTURE layers — closes the §3.6 commitment in ARCHITECTURE).
- Polling discipline + envelope submission from UI buttons.
- T3 Park Phase with proper journal entry — same discipline going forward.

Standing by for T3 greenlight.
