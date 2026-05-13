# Branch 02 Transition Note — 2026-05-12

## Purpose

This note records an additive branch-local transition event for
`.scaffold_BRANCH-02`. It exists to preserve continuity for this branch
without mutating or rewriting earlier project history.

## Branch Context

- Active branch root during this repair session:
  - `C:\Users\jacob\Documents\_AppDesign\_LivePROJECTS\.scaffold_BRANCH-02`
- Intent of this branch note:
  - acknowledge that this branch diverged from prior workspace history
  - preserve a readable record of branch-specific cleanup and hardening
  - do so additively, in line with the append-only journal doctrine

## Work Completed In This Session

### 1. Contract-first onboarding

- Read `contracts/builder_constraint_contract.md` first as directed.
- Used the contract as the governing constraint field for subsequent edits.

### 2. Terminology repair

- Corrected live-project instances of the misspelling to `constraint`
  in writable project files.
- Verified the live SQLite state no longer contained the typo.

### 3. Smoke-test guard added

- Added a non-fatal typo guard to `smoke_test.py`.
- The guard warns on any future lingering misspelling and explains the
  intended spelling correction so a repair pass can address it deliberately.

### 4. Path privacy / portability hardening

- Reviewed the live branch for absolute root-path leakage.
- Preserved internal runtime path resolution where needed for filesystem work.
- Reworked outward-facing state and tool surfaces so they prefer public-safe
  relative labels such as `.` instead of exposing local HDD paths.
- Scrubbed live DB/log surfaces that still contained machine-specific branch
  root strings.

### 5. Verification

- Re-ran `python smoke_test.py` successfully after the path/privacy hardening.
- Verified live CLI and tool surfaces now report relative/public-safe roots.

## Files Most Directly Involved

- `smoke_test.py`
- `src/lib/common.py`
- `src/core/state.py`
- `src/core/projections.py`
- `src/app.py`
- `src/interfaces/cli_interface.py`
- `src/orchestrators/install_orchestrator.py`
- `src/orchestrators/scan_orchestrator.py`
- `src/orchestrators/closeout_orchestrator.py`
- `src/tools/workspace_boundary_audit.py`
- `src/tools/file_tree_snapshot.py`
- `src/tools/host_capability_probe.py`
- `src/components/manifest_generator.py`
- `src/managers/tool_registry_manager.py`
- `SOURCE_PROVENANCE.md`

## Contract Alignment

This branch note is intended to comply with the current builder contract by:

- preserving additive history instead of rewriting earlier records
- keeping the work legible in project-local documentation
- reflecting branch-specific changes in append-only form
- avoiding any claim that prior historical artifacts were retroactively edited

## Historical Interpretation Rule

This note should be read as:

- a branch-local continuity marker
- a record of work performed after branch divergence
- not a replacement for earlier tranche history, earlier park notes, or prior
  provenance entries

## Status

Branch-local cleanup and portability/privacy hardening for this session are
recorded here and should be cited by future work in this branch when relevant.
