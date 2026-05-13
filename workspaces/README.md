# `workspaces/` — Sandbox Execution

> **Status:** Tranche 0 plan. Empty until the first sandbox tool runs.

## Purpose

Holds **isolated workspaces for `Sandbox Execute` operations**. When a tool needs to run something that produces files, executes code, or applies a patch *as a trial*, it does so here — never in the host project tree.

This is the sidecar's "scratch space." Anything inside is disposable.

## Planned shape

```
workspaces/
├── <workspace_id>/                  ← one folder per execution
│   ├── inputs/                      ← copies of relevant host project files (read-only origin)
│   ├── outputs/                     ← whatever the tool produced
│   ├── logs/                        ← per-workspace logs
│   └── manifest.json                ← what spawned this, what authority, what envelope
└── _retired/                        ← workspaces moved here on cleanup; auto-pruned
```

## Authority requirement

Writing here requires at least `Sandbox Execute` authority. Promoting a workspace's outputs into the host project tree requires `Apply` authority on a separate, follow-up envelope — sandbox execution alone never mutates the host project.

## Rules

- One workspace per envelope. The workspace id matches the envelope's `event_id` for traceability.
- Workspaces are gitignored; they are runtime state.
- A workspace's `manifest.json` records: spawning envelope id, actor id, authority level, input hashes, output hashes, completion status.
- Cleanup: workspaces older than the configured retention window move to `_retired/` and are eventually deleted. Retention is set in `config/sidecar.json`.
- A workspace must never resolve paths that escape itself (no `../host_project/...`). Path containment is enforced by the executor.
