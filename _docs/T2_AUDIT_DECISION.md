# Audit findings + decision to bake Park Phase into codified process

**Date:** 2026-05-11
**Context:** Triggered by user audit question after T2 close — "is everything robustly and correctly parked?"

## Audit findings

Verification check after T2 Park Phase revealed four documentation drift items that were not caught by the existing Park Phase ritual:

1. **TOOLS.md was stale** — said "No tools registered yet" while `tool_registry` contained 5 tools.
2. **README.md status header was stale** — still declared "Tranche 0 — scaffolding & plan files. No executable code yet." (Two tranches out of date.)
3. **ARCHITECTURE.md §15 was incomplete** — only listed "Resolved at T1" decisions; T2's resolved decisions (MCP transport, tool registry dual pattern, HARD_BLOCK enforcement strategy, etc.) were not promoted to §15.
4. **Tranche journal entries had status='open'** — both T1 and T2 closure entries remained `'open'` after Park Phase, even though the tranches they document are done.

## Root cause

The Park Phase as previously written in ARCHITECTURE.md §12.2 said only "update continuity docs" without listing them. That's a *ritual remembered conversationally*, not a codified discipline. The user's directive is precise:

> "We should ensure that we (append only) are aware of this going forward and that it is baked into our documentation. I want to ensure the documentation is not ritual we know only in this convo but is part of the codified process we iterate over."

## Decision

Make the Park Phase **mechanically enforceable** by encoding it in three load-bearing places:

1. **`contracts/builder_constraint_contract.md` §D (NEW)** — add Park Phase Discipline as a contract clause. The phase is binding, not optional. Re-seed the constraint registry to pick up the new clause.

2. **`ARCHITECTURE.md §12.2` (revised)** — replace "update continuity docs" with an explicit named checklist: `IMPLEMENTATION_ROADMAP.md`, `SOURCE_PROVENANCE.md`, `TOOLS.md`, `ARCHITECTURE.md §15`, `README.md`. Add explicit step "close the tranche entry."

3. **`smoke_test.py` (extended)** — add **drift-detection sections** that fail when:
   - `TOOLS.md` row count ≠ `tool_registry` count.
   - `README.md` status header references a prior tranche.
   - `ARCHITECTURE.md §15` lacks `Resolved at T_n` for each completed tranche.
   - The latest tranche journal entry has `status='open'` (i.e., not yet closed via `close_journal_entry`).

The smoke test becomes the mechanical gate. If drift exists, smoke test fails. If smoke test fails, the tranche is not parked.

## Companion fix

The four drift items are corrected in this same Park Phase completion:
- TOOLS.md populated.
- README.md header updated.
- ARCHITECTURE.md §15 "Resolved at T2" section added.
- T1 + T2 tranche journal entries closed via `close_journal_entry` envelopes.

## Going forward

Per `ARCHITECTURE.md §13.1` (Journal Doctrine — append-only): the T2 tranche entry's body remains as written. This decision entry documents the audit + correction as a separate decision-kind entry. Both T1 and T2 tranche entries get `status='closed'` (state change, not content edit).

No tranche is "parked" until `smoke_test.py` passes including the drift-detection sections.
