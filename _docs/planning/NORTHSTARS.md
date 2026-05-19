# NORTHSTARS.md — Satisfied Capabilities and Next Horizons

## Satisfied substrate capabilities

- One authoritative SQLite spine for events, graph relations, projections, journal, approvals, and session bookkeeping.
- Binding builder contract with acknowledgment, authority levels, and Park Phase doctrine.
- Native Tk operator surface backed by the same projections agents read.
- MCP surface that can now both read and submit envelope-routed proposals.
- Workspace-first bounded mutation path with explicit human approval and grant issuance.
- Cold-start continuity set at repo root: onboarding, fast pickup, development log, roadmap, provenance, tools, architecture, and contract.
- Local Ollama sidecar agent runtime inside the same spine, with session visibility, approval-aware bounded writes, and Tk operator controls.
- Durable runtime trace for local-agent runs, rounds, runtime events, touched paths, grounded claims, recovery classes, and explicit retry lineage.
- Operator cockpit visibility through `runtime_cockpit`, CLI run-inspection commands, and the Tk local-agent panel.
- Teaching Sandbox + Training Runway substrate with tracked scenarios, deterministic mocked pass/fail runs, scorecards, reviewer exports, and Tk/CLI/projection visibility.
- Fresh installed-project vendability proof with a governed host mutation, trace/evidence/journal/projection chain, and cold-team handoff packet.
- Generated closeout metadata surfaces so latest parked tranche identifiers and CAS refs are derived mechanically instead of mirrored by hand.
- A codified target-state doctrine that recenters the next phase around a chat cockpit over the existing spine instead of expanding the Tk monitor into a second project brain.

## Next horizon

No tranche is currently open.

The next implementation candidate is **T10.2 Chat Review Gate Surface**.

The broader horizon remains **T10 post-baseline hardening + chat-centered sidecar alignment** only after the vendable substrate baseline has already been proven.

The deferred backlog is now explicitly tranche-mapped in `_docs/planning/IMPLEMENTATION_ROADMAP.md` and mirrored into open journal todos so carry-forward work is visible in the UI, projections, and handoff flow.

## Prototype target now locked

The binding prototype target is now documented in `_docs/planning/TARGET_STATE.md`:

- **Chat:** primary cockpit for planning, scoped work, review packet inspection, approve/return/park, continuity inspection, and export requests.
- **Tk:** secondary operator surface for monitoring, traces, queues, deeper inspection, training/eval visibility, and emergency/manual control.
- **DB:** authoritative memory.
- **Spine:** only authority path.

## What still separates this branch from broader deployment confidence

- longer concurrent Tk + MCP + local-agent stress proof
- migration-harness and snapshot-policy hardening
- optional transport and tooling expansion only if later work justifies it
- the first narrow chat-over-spine implementation slice (`T10.2`) still needs to be built

## End-state north star

`.scaffold/` is the default agentic operating substrate that can be dropped into any project, onboard a cold team from docs and live surfaces alone, host its own local agent safely, carry one full observe → propose → approve → mutate → journal → park loop without relying on conversation memory, and increasingly let the human operate the project through chat without creating a second memory or authority layer.
