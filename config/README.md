# `config/` — Sidecar Configuration

> **Status:** active generated/inspected config surfaces. Files here are derived from the running sidecar unless explicitly documented otherwise.

## Purpose

Holds sidecar-local configuration files. These are configuration *for the sidecar itself*, not for the host project.

## Planned files

| File | Purpose | Created by |
|---|---|---|
| `sidecar.json` | Top-level config: sidecar id, version, project root, default authority, log level, MCP transport choice, projection refresh policy. | `install_orchestrator` on first run. |
| `journal_config.json` | Journal-specific settings: schema version, hint paths, default tags, importance thresholds. | `install_orchestrator` on first run. |
| `db_manifest.json` | Authoritative manifest of tables, entrypoints, conventions. Mirrors the manifest stored inside `journal_meta` in the DB but is also written here for human inspection. | Generated from the DB on schema migrations. |
| `tool_manifest.json` | Generated machine-readable index of every tool registered in `src/tools/`: name, version, entrypoint, category, summary, mcp_name, required_authority, input_schema, source_hash. See [`tool_manifest.json.PLAN.md`](tool_manifest.json.PLAN.md). | `tool_registry_manager` on register/unregister. |
| `toolbox_manifest.json` | High-level descriptor of the entire `.scaffold/` toolbox for **zero-context agent entry**. It is read only after `contracts/BCC.md` and the repo-local binding artifact. See [`toolbox_manifest.json.PLAN.md`](toolbox_manifest.json.PLAN.md). | `install_orchestrator` on first run; refreshed on tool register/unregister and contract revision. |

## Rules

- No secrets here. If a secret is ever needed, it lives outside `.scaffold/` and is referenced by env var.
- Files are JSON (or TOML if a strong reason emerges) — no YAML, no INI.
- Schemas for these files live in `src/schemas/` and are versioned.
- The sidecar must boot from `data/sidecar.db` alone if these files are absent; this folder is for human inspection and override, not for source-of-truth state.
