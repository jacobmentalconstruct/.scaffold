# `.scaffold/` — Vended Sidecar Package

> **Status:** Latest parked tranche is **T10.4 HARD_BLOCK and Mutation-Path Trust-Gate Completion**. Substrate baseline remains achieved, the first chat-over-spine review cockpit slice is parked, routed actors materialize explicit authority rows through the spine, mutation-path trust gates now fail early from one explicit policy path, and the next narrow implementation slice is **T10.5 Derived BCC Constraint-Map Slice for Intent Decomposition**. Spine boot ✓, journal ✓, install + scan ✓, proposal-capable MCP ✓, 8 tools registered, Tk operator UI ✓, approval loop ✓, local sidecar agent floor ✓, schema v8 memory layer ✓, runtime trace/cockpit ✓, teaching sandbox/training runway ✓, installed-project vendability proof ✓, target-state doctrine locked ✓.
> See [_docs/planning/IMPLEMENTATION_ROADMAP.md](_docs/planning/IMPLEMENTATION_ROADMAP.md) for tranche progress and [_docs/planning/TARGET_STATE.md](_docs/planning/TARGET_STATE.md) for the binding prototype target. T10.1 codifies the governing rule for the next phase: **chat becomes the cockpit, the DB remains the memory, and the spine remains the authority path.**
>
> **New here?** Read **[contracts/BCC.md](contracts/BCC.md)** first, then **[_docs/reference/PROJECT_BINDINGS.md](_docs/reference/PROJECT_BINDINGS.md)** for this repo's concrete local bindings, then **[_docs/continuity/ONBOARDING.md](_docs/continuity/ONBOARDING.md)** as the convenience orientation surface derived from them.

## What this is

`.scaffold/` is a self-contained **sidecar package** designed to be pasted into any project root as `<project>/.scaffold/`. It carries:

- a binding contract (`contracts/BCC.md`) that serves as the sole authored doctrine source
- a single SQLite spine (`data/sidecar.db`) holding events, graph relations, projections, and the journal
- an MCP interface for agents
- a Tkinter operator surface for monitoring and deep inspection
- a tool library (`src/tools/`) following a strict tool contract
- reference materials (in `.parts/` during development; not vended)

The current target is **not** “expand the dashboard.” The current target is a **chat-centered, project-bound sidecar** where chat becomes the primary cockpit over the existing governed spine and Tk remains the secondary operator surface.

For the first chat-cockpit slice, MCP-connected chat clients should drive the review/park loop by reading `projection://tranche_review_gate`, then `review://latest`, then submitting review intents through `sidecar/submit`, and finally reading `closeout://latest` after Park Phase. The spine remains the only authority path.

Current branch work for `T10.5` also exposes `projection://bcc_constraint_map`: a derived, non-authoritative surface hash-bound to `contracts/BCC.md` that exists to improve intent decomposition and token efficiency. If the compiled hash drifts from the live contract, guidance is stale until `python -m src.app cli contract-constraint-map-refresh` is run. Runtime authority drift is exposed there, not corrected.

## The invariant

**The host project does not know the sidecar exists.** The host's application code never imports from `.scaffold/`. The sidecar observes and acts on the host project through tools under the authority model governed by `contracts/BCC.md`; `projection://bcc_constraint_map` exists only to surface that doctrine compactly and to expose current runtime authority drift without hiding it.

## How it works in one sentence

Every state mutation flows: **Interface → Envelope → Router → ContractCheck → Orchestrator → Manager → Event → derived views.** No sideways calls. No back-channels. The envelope is the only currency.

## Operator default

Agent-facing sidecar runs now open the Tk monitor by default so a human can watch the substrate live while an agent is connected or running. This applies to:

- `python -m src.app mcp`
- `python -m src.app cli local-agent-run ...`

Use `--no-ui` when you intentionally want a headless run.

## Folder map

| Path | Purpose |
|---|---|
| `contracts/` | Binding contracts. `BCC.md` is the sole binding contract and seed source. |
| `config/` | Sidecar-local configuration. |
| `data/` | The SQLite spine (`sidecar.db`) at runtime. |
| `logs/` | Runtime logs. `print()` is prohibited; everything routes here. |
| `cache/` | Derived/regenerable caches. Safe to delete. |
| `exports/` | Markdown / JSON exports. Written under `Export` authority. |
| `workspaces/` | Sandbox workspaces for tool execution. Isolated from host project tree. |
| `snapshots/` | Point-in-time Merkle snapshots of the spine. |
| `src/` | The runtime: core spine, orchestrators, managers, components, interfaces, UI, schemas, lib, tools. |
| `_docs/reference/PROJECT_BINDINGS.md` | Concrete local bindings for this repository/package. |
| `_docs/reference/ARCHITECTURE.md` | Design truth. |
| `_docs/continuity/ONBOARDING.md` | Cold-start reading order + verification commands. |
| `_docs/continuity/WE_ARE_HERE_NOW.md` | Fast pickup note for a cold session. |
| `_docs/planning/TARGET_STATE.md` | Binding prototype target map for the chat-centered sidecar phase. |
| `_docs/planning/NORTHSTARS.md` | Satisfied capabilities vs active horizons. |
| `_docs/history/DEV_LOG.md` | Append-only milestone log. |
| `_docs/reference/SOURCE_PROVENANCE.md` | Provenance of any re-homed materials. |
| `_docs/reference/TOOLS.md` | Quick-reference tool index. |
| `.parts/` | Read-only precursor reference materials (development only; not vended). |

## Reading order for a new agent

1. `contracts/BCC.md`
2. `_docs/reference/PROJECT_BINDINGS.md`
3. `_docs/reference/ARCHITECTURE.md`
4. `_docs/planning/TARGET_STATE.md`
5. `_docs/continuity/WE_ARE_HERE_NOW.md`
6. `_docs/planning/IMPLEMENTATION_ROADMAP.md`
7. `_docs/reference/SOURCE_PROVENANCE.md`
8. `_docs/reference/TOOLS.md`
9. `_docs/continuity/ONBOARDING.md`
10. `README.md`
11. `_docs/planning/NORTHSTARS.md`
12. `_docs/history/DEV_LOG.md`

## Reading order for a new human

1. `contracts/BCC.md`.
2. `_docs/reference/PROJECT_BINDINGS.md`.
3. `_docs/reference/ARCHITECTURE.md` for the design.
4. `_docs/planning/TARGET_STATE.md` for the current target state.
5. `_docs/continuity/WE_ARE_HERE_NOW.md`.
6. `_docs/continuity/ONBOARDING.md`.
7. This README.
8. The Tkinter UI (`python -m src.app ui`) once running, for live state, traces, and monitoring.

## Status

This package now has a **proven installed-project baseline**. It was still built in development scope here, but T9 demonstrated the real vendable path by installing a clean `.scaffold` copy into a disposable tiny host project, booting it in installed context, running the governed proposal → approval → bounded mutation loop, and exporting a cold-team handoff packet. T10.1 then locked the next target in writing: the sidecar should evolve into a **chat-centered cockpit over the existing spine**, not into a second memory or authority layer. The live contract is `contracts/BCC.md`, and historical legacy references are interpreted through `BCC.md` Appendix A.
