# TOOLS.md — Tool Index

> **Status:** Tranche 0 plan. No tools registered yet. This index will be populated as tools land in `src/tools/` per the Standard Tool Contract (`contracts/builder_constrant_contract.md` §"Standard Tool Contract").

---

## How to read this index

Each tool entry is a one-line summary plus a link to the file. The tool's full metadata is authoritative in its own `FILE_METADATA` block; this file is a navigational shortcut, not a duplicate source of truth.

```
| tool_name | category | summary | mcp_name | file |
```

---

## Categories (for orientation)

- **bootstrap** — initialize the sidecar, the database, the contract acknowledgment.
- **scan** — observe the host project (file walk, git read, ast parse).
- **write** — create journal entries, evidence items, contract records.
- **query** — read projections, events, graph relations.
- **export** — emit markdown / JSON artifacts (requires `Export` authority).
- **scaffold** — produce file/folder skeletons inside `workspaces/` or, with `Apply` authority, inside the host project.
- **contract** — acknowledge contract, propose contract revisions.
- **projection** — refresh / rebuild / query projections.
- **snapshot** — write or restore Merkle snapshots of the spine.
- **ledger** — read / append the action ledger.

---

## Registered tools

*(none yet)*

| tool_name | category | summary | mcp_name | file |
|---|---|---|---|---|
| — | — | — | — | — |

---

## Tool authoring notes (planning-stage)

When writing a tool:

1. Begin with the docstring header (`FILE: ... ROLE: ... WHAT IT DOES: ...`).
2. Export `FILE_METADATA` with `tool_name`, `version`, `entrypoint`, `category`, `summary`, `mcp_name`, `input_schema`.
3. Implement `run(arguments) -> dict` returning `{ "status", "tool", "input", "result" }`.
4. Implement the three CLI modes: `metadata`, `run --input-json`, `run --input-file`.
5. Route any DB access through `src/managers/journal_manager.py` (or its peer manager) — never directly through `sqlite3`.
6. Construct envelopes for any state-changing action; do not mutate state outside the envelope path.
7. Add a row to this file when registered.
