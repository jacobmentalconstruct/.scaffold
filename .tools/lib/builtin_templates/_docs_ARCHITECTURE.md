# Root Architecture

_Last updated: fill in current date. This is the root architecture truth for
the active project line._

---

## What This App Is

Replace this section with a plain-language description of the application:

- what it is
- what it is not
- what durable responsibilities it owns

Keep this section stable and high level.

---

## Core Doctrine

Describe the few layers or boundaries that define the system. Typical examples:

1. durable data or content units
2. coordination / scoring / runtime graph
3. retrieval, UI, or evidence surfaces

If the project has an intentional build order, record it here.

---

## Current component boundaries

Document the major owned surfaces, for example:

- `src/app.py`
  - composition root
- `src/ui/`
  - user-facing ownership
- `src/core/`
  - core runtime ownership
- `src/managers/` or `src/components/`
  - bounded implementation owners, if used
- `_docs/`
  - doctrine, continuity, and builder memory

Keep ownership statements concrete and short.

---

## Current runtime truth

Record the active runtime path or control model:

- what is live
- what is experimental
- what is intentionally deferred

Do not turn this section into a changelog.

---

## Active tranche

Record:

- the current bounded work slice
- the main goal of that slice
- explicit non-goals

This section should help stop scope drift.

---

## Prototype-done definition

Write down the conditions that will make the current prototype phase feel
meaningfully complete.

Typical examples:

- real inputs ingest or load cleanly
- durable units are inspectable
- runtime behavior is stable enough to test
- evidence or outputs are traceable
- builder memory and recovery are trustworthy
