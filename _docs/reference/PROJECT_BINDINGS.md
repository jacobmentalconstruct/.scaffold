# PROJECT_BINDINGS.md — Local Binding Artifact

> **Status:** repository-local binding artifact declared under `contracts/BCC.md` Appendix B. This file may declare concrete local bindings only. It does not create new doctrine.

## Authority and interpretation

- `contracts/BCC.md` remains the sole binding doctrine source.
- This file binds local paths, named surfaces, runtime entrypoints, and package facts for this repository.
- This file is the single active Project Binding Artifact for the current development package context.
- If this file conflicts with `contracts/BCC.md`, the contract wins.
- If a required binding is missing or stale, the builder must stop at Observe or Propose and repair the binding artifact before relying on the missing binding.

## Binding status semantics

- All bindings listed below are `active` unless explicitly marked otherwise.
- `generated` means the surface is expected to resolve after boot/refresh and is derived rather than authored.
- `development-context` means the binding is true for this development repository specifically.
- `installed-context` means the binding is true for a vendored package inside a host project.
- If a listed binding does not resolve and is not status-marked, treat that as drift and repair it before relying on the binding.

## Packaging and root bindings

- Project Documentation Root: `_docs/` (`active`)
- Binding Contract Path: `contracts/BCC.md` (`active`)
- Vendored Tooling Sidecar Root: `.scaffold/` (`installed-context`)
- Current Repository Note: this development repository is the sidecar package itself, so the current Project Root is the package being edited in place rather than a host project containing a nested vendored sidecar folder (`development-context`).

## Doctrine and continuity bindings

- Architecture Surface: `_docs/reference/ARCHITECTURE.md` (`active`)
- Target-State Surface: `_docs/planning/TARGET_STATE.md` (`active`)
- Implementation Roadmap Surface: `_docs/planning/IMPLEMENTATION_ROADMAP.md` (`active`)
- Current-State Continuity Entry: `_docs/continuity/WE_ARE_HERE_NOW.md` (`active`)
- Convenience Orientation Entry: `_docs/continuity/ONBOARDING.md` (`active`)
- Historical Continuity Log: `_docs/history/DEV_LOG.md` (`active`)
- Provenance Surface: `_docs/reference/SOURCE_PROVENANCE.md` (`active`)
- Tool Index Surface: `_docs/reference/TOOLS.md` (`active`)

## Builder-memory bindings

- Durable Builder Memory Store: `data/sidecar.db` (`active`)
- Builder Memory Journal Binding: journal records stored in the SQLite spine and surfaced through the sidecar CLI, projections, and closeout artifacts (`active`)
- Generated Latest-Park Continuity Mirrors: `_docs/continuity/LATEST_PARKED_TRANCHE.md` and `_docs/continuity/LATEST_PARKED_TRANCHE.json` (`generated`)

## Tooling and verification bindings

- Tool Manifest Surfaces: `config/toolbox_manifest.json` and `config/tool_manifest.json` (`generated`)
- Canonical Cold-Start Projection Surface: `agent_bootstrap` (`active`)
- Canonical Handoff Projection Surface: `handoff` (`active`)
- Smoke / Verification Entrypoint: `python smoke_test.py` (`active`)
- Additional Live Verification Entrypoints:
  - `python -m src.app cli version`
  - `python -m src.app cli projection agent_bootstrap`
  - `python -m src.app cli projection handoff`
  - `python -m src.app cli list-projections`
