# NORTHSTARS.md — Satisfied Capabilities and Active Horizons

## Satisfied substrate capabilities

- One authoritative SQLite spine for events, graph relations, projections, journal, approvals, and session bookkeeping.
- Binding builder contract with acknowledgment, authority levels, and Park Phase doctrine.
- Native Tk operator surface backed by the same projections agents read.
- MCP surface that can now both read and submit envelope-routed proposals.
- Workspace-first bounded mutation path with explicit human approval and grant issuance.
- Cold-start continuity set at repo root: onboarding, fast pickup, development log, roadmap, provenance, tools, architecture, and contract.
- Local Ollama sidecar agent runtime inside the same spine, with session visibility, approval-aware bounded writes, and Tk operator controls.

## Active horizon

T7 is the active horizon: the next step is to make the local sidecar agent more observable and recoverable with run traces, recovery classes, retry guidance, and a fuller operator cockpit.

The deferred backlog is now explicitly tranche-mapped in `IMPLEMENTATION_ROADMAP.md` and mirrored into open journal todos so carry-forward work is visible in the UI, projections, and handoff flow.

## What still separates this branch from superseding the old experiment

- run trace and recovery classification
- teaching sandbox and training runway
- fresh installed-project proof that this branch can replace the older system end to end

## End-state north star

`.scaffold/` is the default agentic operating substrate that can be dropped into any project, onboard a cold team from docs and live surfaces alone, host its own local agent safely, and carry one full observe → propose → approve → mutate → journal → park loop without relying on conversation memory.
