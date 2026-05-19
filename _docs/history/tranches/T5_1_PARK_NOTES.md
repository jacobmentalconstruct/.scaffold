# Park Notes — T5.1 Companion Monitor Default + UI Stability

## Declared Scope
Make the Tk monitor auto-launch for agent-facing runs by default, preserve the active UI tab during refresh, and align the viewport drift warning with real continuity state.

## Decisions Recorded
### Auto-launch the Tk monitor for agent-facing runs with explicit headless opt-out
*   **Context:** The sidecar is now interactive enough that agent activity benefits from an always-visible operator surface, but some runs still need to stay headless.
*   **Rationale:** Default-visible monitoring matches the product identity and makes local/MCP agent behavior observable without extra operator steps, while `--no-ui` preserves scripting and headless workflows.
*   **Outcome:** Start the Tk monitor automatically for `python -m src.app mcp` and `python -m src.app cli local-agent-run ...`, and require an explicit `--no-ui` flag to suppress it.

## Files Changed
*   `src/lib/ui_launcher.py` (added)
*   `src/app.py` (modified)
*   `src/interfaces/cli_interface.py` (modified)
*   `src/ui/main_window.py` (modified)
*   `src/core/projections.py` (modified)
*   `README.md` (modified)
*   `ONBOARDING.md` (modified)
*   `WE_ARE_HERE_NOW.md` (modified)
*   `DEV_LOG.md` (modified)
*   `ARCHITECTURE.md` (modified)
*   `IMPLEMENTATION_ROADMAP.md` (modified)
*   `SOURCE_PROVENANCE.md` (modified)

## Tests Run
*   `smoke_test.py` (passed at 2026-05-13T11:08:01.404Z)

## Deviations
None.

## Open Questions
None.

## Next Tranche
T6 STM + Bag of Evidence + Evidence Shelf

*Credit to closeout_orchestrator for finalizing this tranche.*