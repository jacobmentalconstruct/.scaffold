# `exports/` — Human / Machine Exports

> **Status:** Tranche 0 plan. Empty until an export is requested.

## Purpose

Holds artifacts produced under **`Export` authority** — markdown reports, JSON snapshots of state, packed bootstrap bundles. These are intended to leave the sidecar (shared with humans, ingested by other tools, attached to issues).

## Authority requirement

Per contract §"Authority Levels," writing here requires `Export` authority granted by explicit human approval, recorded in the event log. The act of exporting is itself an event.

## Planned shapes

| Subfolder / pattern | Purpose |
|---|---|
| `journal/<date>/*.md` | Markdown exports of journal entries. |
| `journal/<date>/*.json` | JSON exports for mechanical consumption. |
| `bootstrap/<date>-<sidecar_id>.json` | Agent bootstrap packets, exported for sharing. |
| `dashboards/<date>.html` | Human-readable dashboard snapshots (if/when we add HTML rendering). |
| `provenance/<date>.md` | Provenance reports linking files → events → contracts. |

## Rules

- Every export records an event in the `tool` stream with `operation_intent="export"`.
- Exports are immutable once written. Re-exporting writes a new file, never overwrites.
- Exports are gitignored. If you want one in version control, copy it elsewhere intentionally.
- Markdown exports are human-readable AND mechanically parseable per contract Pledge 5.
