# DEV_LOG.md — Development Log

Append-only milestone log for humans and agents onboarding cold.

## 2026-05-19 — T10.5 Derived BCC Constraint-Map Slice (branch implementation)

- Added a dedicated BCC constraint-map compiler and durable compiled-map store.
- Exposed `projection://bcc_constraint_map` plus a compact `agent_bootstrap` summary for lower-token intent decomposition.
- Kept `contracts/BCC.md` as the sole authored doctrine source; the compiled map is hash-bound, explicitly non-authoritative, and requires explicit refresh on contract-hash drift.
- Surfaced runtime authority drift and compatibility aliases as truth in the map without correcting the underlying runtime enum in this slice.

## 2026-05-10 — T1 Spine Boot

- Bootstrapped the SQLite spine, contract gate, router, graph, and first projection refresh loop.
- Established the envelope as the only mutation currency through the sidecar.

## 2026-05-11 — T2 Install / Scan / Journal / MCP

- Landed install, scan, journal, evidence, git observation, and the first read-only MCP surface.
- Made the sidecar self-describing through projections and the journal.

## 2026-05-11 — T2.5 Active Tranche Ledger

- Replaced reconstruct-at-close habits with structured tranche capture (`active_tranche`, `decision_records`, `tranche_checklist`).
- Added the `close_tranche` compile-and-seal path for Park Phase.

## 2026-05-11 — T2.6 / T2.6.1 Ollama Closeout Hardening

- Added local Ollama park-note generation with template fallback.
- Fixed qwen3.5 empty-response behavior and capped output tokens to avoid GPU memory pressure.

## 2026-05-12 — Branch 02 Continuity / Privacy Hardening

- Repaired outward-facing `constraint` spelling drift and added the typo warning guard.
- Hardened path/public-label reporting so persisted state avoids machine-specific absolute paths when possible.

## 2026-05-12 — T3 Tk Monitoring UI

- Shipped the native Tk monitoring console and the `viewport_state` projection.
- Preserved the browser mock only as a design reference; runtime stayed Tk-native and stdlib-only.

## 2026-05-13 — T4 Approval Loop + Handoff Doctrine Uplift

- Added the first complete proposal → approval → bounded mutation path.
- Upgraded MCP from read-only to proposal-capable with `sidecar/submit`.
- Added `agent_sessions`, `approval_requests`, the `handoff` projection, and the first workspace-first write tools.
- Promoted cold-start continuity docs (`WE_ARE_HERE_NOW.md`, `NORTHSTARS.md`, this log) to first-class project doctrine.

## 2026-05-13 — T4.1 Deferred Backlog Normalization

- Mapped scattered deferred items into explicit owner tranches/horizons in `IMPLEMENTATION_ROADMAP.md`.
- Promoted the deferred backlog into open `todo` journal entries so it appears in projections, UI future surfaces, and cold-team handoff flow.
- Corrected stale roadmap claims that still described T4-delivered components as plan-only.

## 2026-05-13 — T5 Local Sidecar Agent Reintegration

- Reintroduced the local Ollama-backed sidecar agent inside the contract-bound spine instead of relying on an external stand-in.
- Added local-agent CLI and Tk operator controls, bootstrap parity, approval-aware bounded writes, and cooperative stop support.
- Normalized local-agent writes onto the same `text_file_writer` contract as the rest of the substrate and added explicit session-backed authority rows for local-agent actors.

## 2026-05-13 — T5.1 Companion Monitor Default + UI Stability

- Made the Tk monitor auto-launch by default for agent-facing MCP and local-agent runs, with explicit `--no-ui` headless opt-outs.
- Fixed the Tk refresh loop so the active tab stays selected instead of snapping back to `Dashboard`.
- Aligned the viewport drift banner with the same tranche-resolution rule used by smoke, removing a false warning state.

## 2026-05-13 — T6 STM + Bag of Evidence + Evidence Shelf

- Added schema v8 with `session_memory_items` and `change_hunks` so STM, Bag overflow, shelf summaries, and per-hunk provenance all live in the SQLite spine.
- Wired the local Ollama runtime to persist prompt/action/tool-result memory, overflow older working context into a Bag, and rebuild an Evidence Shelf for bootstrap and Tk visibility.
- Turned `diff_builder.py` into real code and captured bounded-write hunks with path, old/new line ranges, raw diff text refs, and session/tranche linkage.
- Surfaced the memory model through `agent_bootstrap`, `viewport_state`, and the Tk operator panels; smoke now proves the memory layers and hunk provenance end to end.
- Parked the tranche with `_docs/history/tranches/T6_PARK_NOTES.md`, tranche journal entry `journal_18af1d7325d57744_83774848`, and blob hash `598a76da026c778f19bdc1a4c1597cc4405a12d051d830001e190fdf002a1309`.

## 2026-05-13 — T6.1 Post-Park Continuity Alignment

- Reconciled the continuity docs after T6 close so README, onboarding, roadmap, architecture, provenance, and fast-pickup notes all agree on the parked state.
- Tightened smoke expectations to follow the real tranche horizon instead of stale hard-coded assumptions.
- Left the branch in a clean handoff state with T7 clearly named as the next active horizon.

## 2026-05-14 — T7 Run Trace, Recovery, and Operator Cockpit

- Added schema v9 for `local_agent_runs`, `local_agent_run_rounds`, `local_agent_runtime_events`, `local_agent_run_touched_paths`, `local_agent_run_links`, and `local_agent_claim_grounding`.
- Instrumented the local Ollama runtime so runs, rounds, approvals, tool activity, failures, retry lineage, and final claim grounding are durable instead of implicit.
- Added normalized recovery classification plus CLI/Tk inspection surfaces (`runtime_cockpit`, `local-agent-run-list`, `local-agent-run-show`, `local-agent-run-events`, `local-agent-recovery-summary`, `local-agent-run-retry`).
- Extended the Tk local-agent panel into a real operator cockpit with run history, selected-run detail, recovery hints, and retry actions.
- Upgraded smoke to prove successful, failed, stopped, retried, grounded, projected, and Tk-hydrated T7 paths end to end.

## 2026-05-14 — T8 Teaching Sandbox + Training Runway

- Added schema v10 for `teaching_scenario_runs`, `teaching_scenario_run_trace_links`, `teaching_scorecards`, and `teaching_reviewer_exports`.
- Added `TrainingRunwayManager`, tracked scenario definitions, disposable sandbox materialization, structured verifiers, reviewer exports, and evidence/journal linkage on top of T7 run traces.
- Taught the local runtime how to target disposable sandbox projects safely during evaluation runs without changing the normal host-project write floor.
- Added the `training_runway` projection, new training CLI commands, and a Tk Training Runway panel inside the existing operator shell.
- Upgraded smoke to prove deterministic mocked pass/fail scenarios, projection hydration, reviewer export output, and Tk training-panel hydration.
- Recorded one live Ollama proof for `python_notes_cli`; it failed as `malformed_tool_call`, but the sidecar still captured a complete review packet.

## 2026-05-14 — T8.1 Post-Park Training Handoff Alignment

- Fixed roadmap parsing so `agent_bootstrap.next_planned_steps_json` stays populated even when the next tranche is described by proof/outcome criteria instead of a file/surface list.
- Re-ran continuity validation so smoke, handoff, bootstrap, and fast-pickup docs all agree on T9 as the next horizon after the T8 park.

## 2026-05-14 — T9 Installed-Project Proof + Vendability Seal

- Added schema v11 plus the installed-project proof subsystem and `installed_project_proof` projection.
- Fixed clean-install migration overlap so a fresh installed `.scaffold` boots cleanly instead of only upgraded development DBs.
- Corrected installed-context project-root resolution so `<host>/.scaffold` treats the host project as `project_root` automatically.
- Tightened host-project write hard blocks so installed `.scaffold` cannot write into its own runtime subtree while still allowing disposable sandbox targets.
- Proved a fresh host loop end to end: install, contract ack, scan, projection/UI hydration, governed proposal, human approval, bounded host mutation, trace/evidence/journal/projection capture, reviewer packet export.
- Added CLI, projection, Tk, and smoke surfaces for the vendability proof and sealed the old experiment as superseded by this branch.

## 2026-05-14 — T10 Closeout Metadata Derivation Hardening

- Mechanized latest parked tranche closeout identifiers into generated continuity artifacts instead of hand-copying them into prose docs.
- Added tranche-specific and latest-alias closeout metadata files under `_docs/`, plus CLI surfaces to inspect and backfill them.
- Hardened smoke so generated closeout metadata must match the latest closed tranche exactly, preventing stale journal ids or CAS refs from lingering in mirror docs.

## 2026-05-15 — T10.1 Prototype Target Requirements Map + Chat-Centered Sidecar Alignment

- Added `TARGET_STATE.md` as the binding target map for the next phase.
- Explicitly separated the near-term Prototype Target State from the Long-Term Evolutionary Target.
- Recentered doctrine so chat is the planned primary cockpit and Tk is the secondary operator surface.
- Locked the key anti-drift rule into project truth: chat must stay a governed surface over the spine rather than becoming a second memory or authority layer.
- Reclassified the existing open backlog honestly without silently erasing stale historical todos.
- Fixed the next narrow implementation slice as `T10.2 Chat Review Gate Surface`.

## 2026-05-18 — T10.2 Chat Review Gate Surface

- Added MCP-readable `review://...` and `closeout://...` resources so chat can inspect full review packets and generated closeout metadata directly from existing truth surfaces.
- Kept chat mutation on `sidecar/submit` by adding the default tranche-review/tranche-close intent mappings and documenting the inspect -> approve -> inspect gate -> close flow.
- Expanded smoke to prove MCP discovery, review packet reads, closeout reads, blocked pre-approval close, and explicit return/approve/close sequencing.
- Parked the tranche through the mechanical review gate and generated `_docs/history/tranches/T10_2_PARK_NOTES.md` plus latest closeout metadata mirrors.

## 2026-05-18 — T10.3 Explicit Authority Registration Hardening

- Began reducing reliance on default-by-prefix authority inference by seeding explicit authorities rows for ordinary routed actors as they first traverse the contract gate.
- Added smoke coverage proving a non-session actor that routes through the spine now gets a durable authority row with recorded provenance.
- Parked the tranche and generated `_docs/history/tranches/T10_3_PARK_NOTES.md` plus the updated latest-closeout metadata mirrors.

## 2026-05-19 — T10.4 HARD_BLOCK and Mutation-Path Trust-Gate Completion

- Centralized project-targeted mutation policy at the contract gate so `text_file_writer` and `directory_scaffold` hard-block before tool execution when host-write intent, path bounds, or runtime-subtree rules are violated.
- Tightened scaffold approvals from broad tool-name matching to exact manifest-aware `entry_paths`, so changed scaffold manifests no longer inherit stale grants.
- Added an authoritative Park/continuity drift helper and made `declare_tranche` fail fast when latest-closeout state and `WE_ARE_HERE_NOW.md` disagree on the parked lifecycle story.
- Extended smoke to prove the new hard-block reasons, manifest-aware approval matching, and declare-tranche drift blocking without regressing MCP review/park or installed-proof verification.
