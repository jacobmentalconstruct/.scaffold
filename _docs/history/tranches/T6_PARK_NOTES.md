# Park Notes — T6 STM + Bag of Evidence + Evidence Shelf

## Declared Scope
Promote the memory model from LTM-only plus reserved fields into a real three-layer stack by implementing explicit STM for the local sidecar agent session, Bag of Evidence archival and retrieval, Evidence Shelf summary surfaces for UI and bootstrap consumption, and per-hunk diff provenance for exact code-change memory.

## Decisions Recorded

### Persist T6 memory as session-backed SQLite layers with projection-first visibility
*   **Context:** T6 required explicit STM, Bag of Evidence, Evidence Shelf, and per-hunk provenance without introducing hidden memory channels or bypassing the existing spine.
*   **Rationale:** A single SQLite-backed memory manager keeps STM overflow, shelf summaries, and change hunks queryable by bootstrap, Tk, CLI, and later training/recovery surfaces. Projection selection should prefer in-flight agent status only while a run is active; otherwise the richest persisted memory session should drive the read models.
*   **Outcome:** Added schema v8 with `session_memory_items` and `change_hunks`, wired local-agent overflow into Bag/Shelf, captured bounded-write hunks, and surfaced the memory layers through `agent_bootstrap` and `viewport_state`.

## Files Changed
*   `src/components/sqlite_store.py` (modified)
*   `src/components/diff_builder.py` (added)
*   `src/managers/memory_manager.py` (added)
*   `src/runtime/local_agent_runtime.py` (modified)
*   `src/tools/text_file_writer.py` (modified)
*   `src/core/projections.py` (modified)
*   `src/schemas/projection_schema.py` (modified)
*   `src/app.py` (modified)
*   `src/core/state.py` (modified)
*   `src/managers/tool_registry_manager.py` (modified)
*   `src/ui/main_window.py` (modified)
*   `src/ui/state_panel.py` (modified)
*   `src/ui/local_agent_panel.py` (modified)
*   `smoke_test.py` (modified)
*   `README.md` (modified)
*   `ONBOARDING.md` (modified)
*   `ARCHITECTURE.md` (modified)
*   `WE_ARE_HERE_NOW.md` (modified)
*   `DEV_LOG.md` (modified)
*   `NORTHSTARS.md` (modified)
*   `IMPLEMENTATION_ROADMAP.md` (modified)
*   `SOURCE_PROVENANCE.md` (modified)

## Tests Run
*   `smoke_test.py` (passed at 2026-05-13T11:43:40.213Z)
*   `smoke_test.py` (passed at 2026-05-13T11:45:29.947Z)

## Deviations
None.

## Open Questions
None.

## Next Tranche
None known.

*Tranche closed by closeout_orchestrator*