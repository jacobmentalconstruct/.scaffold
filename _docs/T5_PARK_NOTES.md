# Park Notes — T5 Local Sidecar Agent Reintegration

## Declared Scope
Reintroduce the local Ollama-backed sidecar agent as a spine-governed subsystem with local runtime controls, session visibility, bootstrap parity, and approval-aware bounded writes.

**Declared Non-Goals:**
- Do not implement STM, Bag of Evidence, run traces, recovery taxonomy, or Teaching Sandbox in this tranche.

## Decisions Recorded

### Normalize local-agent writes to text_file_writer content field
- **Impact Area:** Runtime
- **Context:** The first deterministic T5 proof run reported a successful workspace write, but the file was zero bytes because `LocalAgentRuntime` sent `body` while `text_file_writer` expects `content`.
- **Rationale:** The local agent must produce truthful bounded-write results through the same spine the rest of the substrate uses. Runtime and tool schemas need one canonical text payload field.
- **Outcome:** Use `content` as the canonical write payload for local-agent calls and make `text_file_writer` tolerate `body` as a compatibility alias so existing callers do not silently produce empty files.
- **Importance:** 9

## Files Changed
- `src/runtime/local_agent_runtime.py` (added)
- `src/app.py` (modified)
- `src/core/state.py` (modified)
- `src/core/projections.py` (modified)
- `src/interfaces/cli_interface.py` (modified)
- `src/ui/main_window.py` (modified)
- `src/ui/local_agent_panel.py` (added)
- `src/managers/agent_session_manager.py` (added)
- `src/tools/text_file_writer.py` (added)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `ONBOARDING.md` (modified)
- `ARCHITECTURE.md` (modified)
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `WE_ARE_HERE_NOW.md` (modified)
- `DEV_LOG.md` (modified)
- `NORTHSTARS.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)
- `TOOLS.md` (modified)

## Tests Run
- **smoke_test.py**: Passed (2026-05-13T10:40:01.273Z)

## Deviations
None.

## Open Questions
- Concurrent Tk + MCP + local-agent load should get a longer soak beyond the T5 floor; keep the heavier concurrency hardening visible in later horizons.

## Next Tranche
T6 STM + Bag of Evidence + Evidence Shelf

*Credit to closeout_orchestrator for tranche closeout.*