# TRAINING_RUNWAY.md

T8 rebuilt the minimum training/evaluation substrate inside `.scaffold/`.

## What exists now

- sidecar-owned disposable teaching sandboxes under `workspaces/teaching_sandbox/projects/`
- tracked scenario definitions under `training_scenarios/definitions/`
- deterministic mocked scenario runs
- structured scorecards linked to T7 run traces
- compact reviewer exports under `exports/training_runway/`
- Tk / CLI / projection visibility through `training_runway`

## Seed scenarios

- `python_notes_cli`
- `static_status_board`
- `notes_cli_remediation`

## Core commands

```bash
python -m src.app cli training-scenario-list
python -m src.app cli training-scenario-show --scenario-id python_notes_cli
python -m src.app cli training-sandbox-create --scenario-id python_notes_cli --reset
python -m src.app cli training-run-scenario --scenario-id python_notes_cli --mode mocked --variant good
python -m src.app cli training-run-scenario --scenario-id python_notes_cli --mode mocked --variant bad
python -m src.app cli training-run-scenario --scenario-id python_notes_cli --mode live --model qwen3.5:9b
python -m src.app cli training-scorecard-show --scenario-run-id <scenario_run_id>
python -m src.app cli training-review-export --scenario-run-id <scenario_run_id>
python -m src.app cli projection training_runway
```

## Current tranche evidence

Deterministic proof:
- mocked good run passes with trace-linked scorecard
- mocked bad run fails with structured verifier output

Live proof:
- a real Ollama run was executed for `python_notes_cli`
- it failed as `malformed_tool_call`
- the failure still produced a run trace, scorecard, reviewer export, evidence ref, and journal entry

That outcome is acceptable for T8. The point of T8 is to make local-agent behavior measurable and reviewable, not to force the live model to pass every seed scenario yet.
