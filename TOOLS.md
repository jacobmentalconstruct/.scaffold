# TOOLS.md — Tool Index

> **Status:** T9 complete. 7 tools registered. Source of truth for each tool's metadata is the `FILE_METADATA` block in its source file; this index is a navigational mirror, regenerated as part of every tranche's Park Phase (see `ARCHITECTURE.md §12.2`). T9 did not widen the tool belt; it proved vendability using the existing governed tool floor.

---

## How to read this index

Each tool entry includes: `tool_name`, `category`, one-line summary, `mcp_name`, `required_authority`, and a link to the source file. The tool's full metadata is authoritative in its own `FILE_METADATA` block.

---

## Categories (for orientation)

- **bootstrap** — initialize the sidecar, the database, the contract acknowledgment.
- **scan** — observe the host project (file walk, git read, ast parse).
- **introspection** — read-only inspection of project / host / boundaries.
- **write** — create journal entries, evidence items, contract records.
- **query** — read projections, events, graph relations.
- **export** — emit markdown / JSON artifacts (requires `Export` authority).
- **scaffold** — produce file/folder skeletons inside `workspaces/` or, with `Apply` authority, inside the host project.
- **contract** — acknowledge contract, propose contract revisions.
- **memory** — evidence + Bag-of-Evidence operations.
- **projection** — refresh / rebuild / query projections.
- **snapshot** — write or restore Merkle snapshots of the spine.
- **ledger** — read / append the action ledger.

---

## Registered tools

7 tools registered. The sidecar still keeps the runtime tool floor intentionally narrow. T8 added a training/evaluation substrate around those same tools, and T9 proved installed vendability without expanding the belt prematurely.

| tool_name | category | summary | mcp_name | required_authority | file |
|---|---|---|---|---|---|
| `file_tree_snapshot` | introspection | Snapshot the host project's file tree from project_index. | `file_tree_snapshot` | Observe | [src/tools/file_tree_snapshot.py](src/tools/file_tree_snapshot.py) |
| `directory_scaffold` | scaffold | Dry-run-first declarative scaffolding under workspaces or approved project paths. | `directory_scaffold` | Apply | [src/tools/directory_scaffold.py](src/tools/directory_scaffold.py) |
| `host_capability_probe` | introspection | Probe Python version, platform, and common-tool availability. | `host_capability_probe` | Observe | [src/tools/host_capability_probe.py](src/tools/host_capability_probe.py) |
| `read_projection` | query | Read a named projection; returns its rows + last_refreshed_at. | `read_projection` | Observe | [src/tools/read_projection.py](src/tools/read_projection.py) |
| `text_file_reader` | introspection | Bounded text read of a host-project file. | `text_file_reader` | Observe | [src/tools/text_file_reader.py](src/tools/text_file_reader.py) |
| `text_file_writer` | write | Confirmed text writes to sidecar workspaces or approved host-project paths. | `text_file_writer` | Apply | [src/tools/text_file_writer.py](src/tools/text_file_writer.py) |
| `workspace_boundary_audit` | introspection | Audit project root, sidecar root, and runtime folder containment. | `workspace_boundary_audit` | Observe | [src/tools/workspace_boundary_audit.py](src/tools/workspace_boundary_audit.py) |

**Live verification:** `python -m src.app cli tool-list`

---

## Tool authoring notes

When writing a new tool:

1. Begin with the docstring header (`FILE: ... ROLE: ... WHAT IT DOES: ...`).
2. Export `FILE_METADATA` with `tool_name`, `version`, `entrypoint`, `category`, `summary`, `mcp_name`, `required_authority`, `input_schema`.
3. Implement `run(arguments, state) -> dict` returning `{ "status", "tool", "input", "result" }`.
4. Route any DB access through the appropriate manager — never directly through `sqlite3` (Pledge 2: Single Store).
5. Construct envelopes for any state-changing action; do not mutate state outside the envelope path (Pledge 6: Spine Discipline).
6. **Tools register automatically** at boot via `tool_registry_manager.discover_all()` (walks `src/tools/`, validates `FILE_METADATA`, upserts to `tool_registry` table).
7. **This file (`TOOLS.md`) gets updated as part of Park Phase step 5** — when a new tool lands in a tranche, the Park Phase includes a row addition here. Drift between `tool_registry` row count and `TOOLS.md` row count is caught by `smoke_test.py` Park Phase drift-detection.
