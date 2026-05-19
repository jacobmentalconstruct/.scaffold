# Park Notes — T8 Teaching Sandbox + Training Runway

> Generated: 2026-05-14T00:43:24.460Z | Status: sealed | tranche_id: tranche_18af46e292ab7fd8_1c183f14
> Started: 2026-05-14T00:25:16.771Z

## Declared Scope
Minimal core evaluation substrate with sidecar-owned disposable teaching sandboxes, deterministic scenarios, structured scorecards, trace linkage, compact projection/CLI/Tk visibility, and one live Ollama proof as tranche evidence.

### Non-goals
Old-harness parity, broad UI redesign, full live benchmarking suite, autonomous teaching loops, or T9 vendability proof.

### Completion Criteria
Seed scenarios load, sandbox create/reset is idempotent, mocked pass/fail scenario runs produce trace-linked structured scorecards and reviewer exports, training projection/CLI/Tk surfaces hydrate, one live Ollama proof is documented, docs are updated, and tranche parks cleanly.

## Decisions Recorded
_3 decision(s) captured during this tranche._

### Split T8 acceptance into deterministic mocked runs plus one live proof
**Impact area:** process

**Context:** The training runway needs always-green verification but also must prove the live Ollama path exists and produces reviewable evidence.

**Rationale:** Mocked deterministic runs keep smoke stable, while a single live proof captures real-model behavior without turning tranche acceptance into a brittle benchmark.

**Outcome:** Use mocked pass/fail scenarios for the core acceptance suite and require one documented live Ollama scenario run as tranche evidence only.

_decision_id: decision_18af47dad1764858_01689aea | importance: 8_

### Keep scenario runs distinct from local-agent runs
**Impact area:** architecture

**Context:** T8 needed durable evaluation history without collapsing scenario execution into raw T7 runtime traces.

**Rationale:** A scenario may wrap multiple agent attempts over time, so scenario execution identity must stay separate from operational run identity.

**Outcome:** Persist scenario_run_id as the evaluation wrapper and link it to one or more T7 run_id values through explicit trace linkage rows and scorecards.

_decision_id: decision_18af47dad1c70c84_b9bc725f | importance: 9_

### Allow evaluation-mode project writes only inside disposable teaching sandboxes
**Impact area:** tools

**Context:** Training scenarios need the local agent to mutate host-like project trees, but T8 must not broaden the real host-project mutation floor.

**Rationale:** Disposable sidecar-owned sandbox roots give the agent a realistic project target while preserving the host-project invisibility and safety invariants.

**Outcome:** Add evaluation-mode write routing that permits project-targeted writes only for explicitly flagged teaching sandbox runs with sandbox-specific protected paths.

_decision_id: decision_18af47dad6ce0ebc_77148cb0 | importance: 9_

## Files Changed
- `ARCHITECTURE.md` (modified)
- `DEV_LOG.md` (modified)
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `NORTHSTARS.md` (modified)
- `ONBOARDING.md` (modified)
- `README.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)
- `TOOLS.md` (modified)
- `WE_ARE_HERE_NOW.md` (modified)
- `config/tool_manifest.json` (modified)
- `config/toolbox_manifest.json` (modified)
- `smoke_test.py` (modified)
- `src/app.py` (modified)
- `src/components/sqlite_store.py` (modified)
- `src/core/projections.py` (modified)
- `src/core/state.py` (modified)
- `src/interfaces/cli_interface.py` (modified)
- `src/schemas/projection_schema.py` (modified)
- `src/ui/main_window.py` (modified)
- `TRAINING_RUNWAY.md` (added)
- `src/managers/training_runway_manager.py` (added)
- `src/ui/training_runway_panel.py` (added)
- `training_scenarios/definitions/notes_cli_remediation.json` (added)
- `training_scenarios/definitions/python_notes_cli.json` (added)
- `training_scenarios/definitions/static_status_board.json` (added)

## Tests Run
- `python smoke_test.py` → PASS (at 2026-05-14T00:43:07.980Z)

## Next Tranche
T9 Installed-Project Proof + Vendability Seal

## Additional Notes
T8 live proof used scenario_run_18af479b5372cfec_9413c8e0 linked to local_run_20260514T003830366Z and scorecard_18af479efb34d72c_bf9535e8. Reviewer exports were written to exports/training_runway/training_review_python_notes_cli_20260514T003845980Z.{md,json}. The live model path produced a reviewable failure with malformed_tool_call classification, which is acceptable tranche evidence because T8 measures and exports behavior rather than requiring live-model success.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-14T00:43:24.460Z._
_Source: tranche_id=tranche_18af46e292ab7fd8_1c183f14_
