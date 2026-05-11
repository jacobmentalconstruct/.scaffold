# `.scaffold/` — Vended Sidecar Package

> **Status:** Tranche 0 — scaffolding & plan files. No executable code yet.
> Every file in this tree is a prose plan describing what it will become.

## What this is

`.scaffold/` is a self-contained **sidecar package** designed to be pasted into any project root as `<project>/.scaffold/`. It carries:

- a binding contract (`contracts/builder_constrant_contract.md`)
- a single SQLite spine (`data/sidecar.db`) holding events, graph relations, projections, and the journal
- an MCP interface for agents
- a Tkinter UI for humans
- a tool library (`src/tools/`) following a strict tool contract
- reference materials (in `.parts/` during development; not vended)

## The invariant

**The host project does not know the sidecar exists.** The host's application code never imports from `.scaffold/`. The sidecar observes and acts on the host project through tools, with authority climbing from `Observe` → `Propose` → `Sandbox Execute` → `Apply` → `Export` only by contract and human approval.

## How it works in one sentence

Every state mutation flows: **Interface → Envelope → Router → ContractCheck → Orchestrator → Manager → Event → derived views.** No sideways calls. No back-channels. The envelope is the only currency.

## Folder map

| Path | Purpose |
|---|---|
| `contracts/` | Binding contracts. `builder_constrant_contract.md` is the entry point. |
| `config/` | Sidecar-local configuration. |
| `data/` | The SQLite spine (`sidecar.db`) at runtime. |
| `logs/` | Runtime logs. `print()` is prohibited; everything routes here. |
| `cache/` | Derived/regenerable caches. Safe to delete. |
| `exports/` | Markdown / JSON exports. Written under `Export` authority. |
| `workspaces/` | Sandbox workspaces for tool execution. Isolated from host project tree. |
| `snapshots/` | Point-in-time Merkle snapshots of the spine. |
| `src/` | The runtime: core spine, orchestrators, managers, components, interfaces, UI, schemas, lib, tools. |
| `ARCHITECTURE.md` | Design truth. |
| `SOURCE_PROVENANCE.md` | Provenance of any re-homed materials. |
| `TOOLS.md` | Quick-reference tool index. |
| `.parts/` | Read-only precursor reference materials (development only; not vended). |

## Reading order for a new agent

1. `contracts/builder_constrant_contract.md` — acknowledge before any work.
2. `ARCHITECTURE.md` — the spine, MVP-5 order, layer model.
3. `TOOLS.md` — what tools exist and how to call them.
4. The DB itself (`data/sidecar.db`) once initialized — it is self-orienting via `journal_meta` and the manifest tables.

## Reading order for a new human

1. This README.
2. `ARCHITECTURE.md` for the design.
3. The Tkinter UI (`python -m src.app`) once running, for live state and approvals.

## Status

This package is currently being scaffolded in **development scope** — i.e., `.scaffold/` *is* the active project being built, not yet vended into a host. See `contracts/builder_constrant_contract.md` §0.10 for the dual-scope definition.
