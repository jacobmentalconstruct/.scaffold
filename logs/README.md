# `logs/` — Runtime Logs

> **Status:** Tranche 0 plan. Empty until the logger boots.

## Purpose

The print-prohibition (contract §2.1) routes all runtime output here. This is where you look when you want to see what the sidecar actually did during a run, in chronological detail.

## Planned files

| File | Purpose |
|---|---|
| `sidecar.log` | Main rotating log. INFO+ by default; configurable via `config/sidecar.json`. |
| `sidecar.log.1`, `sidecar.log.2`, ... | Rotated older logs. |
| `agent.log` | Agent-specific events (envelopes proposed, tools invoked, projections consumed). |
| `ui.log` | Tkinter UI events (panel opened, action submitted). |
| `mcp.log` | MCP-side requests and responses (compact form; payloads summarized, full payloads stay in DB). |
| `.gitkeep` | Placeholder. |

## Rules

- All log lines are structured: timestamp (ISO 8601 UTC) + level + logger name + message + optional structured fields. Format defined in `src/lib/logging_setup.py`.
- No secrets in logs. Sanitization is the writer's responsibility.
- Logs are gitignored. Long-term audit history lives in the event log inside the DB; logs are operational, not authoritative.
- Rotation is size-based with a retention cap. Defaults set in `src/lib/logging_setup.py`.
