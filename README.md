# `.scaffold/` — Vended Sidecar Package

> **Status:** T8/T8.1 complete and parked (2026-05-14). Spine boot ✓, journal ✓, install + scan ✓, proposal-capable MCP ✓, 7 tools registered, Tk operator UI ✓, approval loop ✓, local sidecar agent floor ✓, schema v8 memory layer ✓, runtime trace/cockpit ✓, teaching sandbox/training runway ✓, continuity alignment ✓.
> See [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) for tranche progress. T8 parked the minimal evaluation substrate, and T8.1 aligned the post-park handoff/parser surfaces so T9 still appears as concrete next-step work to smoke, agents, and cold-team onboarding. T9 is next.
>
> **New here?** Read **[ONBOARDING.md](ONBOARDING.md)** first — explicit reading order + verification commands.

## What this is

`.scaffold/` is a self-contained **sidecar package** designed to be pasted into any project root as `<project>/.scaffold/`. It carries:

- a binding contract (`contracts/builder_constraint_contract.md`)
- a single SQLite spine (`data/sidecar.db`) holding events, graph relations, projections, and the journal
- an MCP interface for agents
- a Tkinter UI for humans
- a tool library (`src/tools/`) following a strict tool contract
- reference materials (in `.parts/` during development; not vended)

## The invariant

**The host project does not know the sidecar exists.** The host's application code never imports from `.scaffold/`. The sidecar observes and acts on the host project through tools, with authority climbing from `Observe` → `Propose` → `Sandbox Execute` → `Apply` → `Export` only by contract and human approval.

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
| `contracts/` | Binding contracts. `builder_constraint_contract.md` is the entry point. |
| `config/` | Sidecar-local configuration. |
| `data/` | The SQLite spine (`sidecar.db`) at runtime. |
| `logs/` | Runtime logs. `print()` is prohibited; everything routes here. |
| `cache/` | Derived/regenerable caches. Safe to delete. |
| `exports/` | Markdown / JSON exports. Written under `Export` authority. |
| `workspaces/` | Sandbox workspaces for tool execution. Isolated from host project tree. |
| `snapshots/` | Point-in-time Merkle snapshots of the spine. |
| `src/` | The runtime: core spine, orchestrators, managers, components, interfaces, UI, schemas, lib, tools. |
| `ARCHITECTURE.md` | Design truth. |
| `ONBOARDING.md` | Cold-start reading order + verification commands. |
| `WE_ARE_HERE_NOW.md` | Fast pickup note for a cold session. |
| `NORTHSTARS.md` | Satisfied capabilities vs active horizons. |
| `DEV_LOG.md` | Append-only milestone log. |
| `SOURCE_PROVENANCE.md` | Provenance of any re-homed materials. |
| `TOOLS.md` | Quick-reference tool index. |
| `.parts/` | Read-only precursor reference materials (development only; not vended). |

## Reading order for a new agent

1. `ONBOARDING.md`
2. `WE_ARE_HERE_NOW.md`
3. `README.md`
4. `IMPLEMENTATION_ROADMAP.md`
5. `contracts/builder_constraint_contract.md`
6. `ARCHITECTURE.md`
7. `NORTHSTARS.md`
8. `DEV_LOG.md`
9. `TOOLS.md`

## Reading order for a new human

1. This README.
2. `ONBOARDING.md`.
3. `WE_ARE_HERE_NOW.md`.
4. `ARCHITECTURE.md` for the design.
5. The Tkinter UI (`python -m src.app ui`) once running, for live state and monitoring.

## Status

This package is currently being hardened in **development scope** — i.e., `.scaffold/` *is* the active project being built, not yet vended into a host. T5 reintroduced the local Ollama sidecar agent with bootstrap parity, approval-aware bounded writes, explicit session-backed authority rows, and operator controls; T6 completed the three-layer memory model with STM overflow into a Bag of Evidence, an Evidence Shelf surfaced in bootstrap/UI, and per-hunk code-change provenance; T7 made local-agent execution a first-class temporal object with durable run traces, recovery classes, retry lineage, grounded final summaries, and a richer operator cockpit; T8 added the minimum teaching substrate with disposable sandboxes, deterministic scenarios, structured scorecards, reviewer exports, and a compact training runway surface. T9 now becomes the installed-project proof horizon. See `contracts/builder_constraint_contract.md` §0.10 for the dual-scope definition.
