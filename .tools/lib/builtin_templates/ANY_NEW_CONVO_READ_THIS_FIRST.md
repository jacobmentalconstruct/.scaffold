# ANY_NEW_CONVO_READ_THIS_FIRST

If you are a fresh conversation or a new builder session, start here before
proposing changes.

## What This Installed Regiment Provides

This project includes a reusable authority and continuity regimen:

- a builder constraint contract
- an app journal for durable project memory
- current-state and backlog documents
- a standard project scaffold
- optional shared-registry workflow support for visible collaboration

This file is the fastest way to orient a new session to that regimen.

## Fresh-Session Pickup Loop

1. If project setup is incomplete, read `_docs/SETUP_DOCTRINE.md` first and finish setup before feature work.
2. Read `_docs/BCC.md`.
3. Use `_docs/BCC.md` as the sole binding contract surface.
4. Read `_docs/continuity/WE_ARE_HERE_NOW.md`.
5. Read `_docs/TODO.md`.
6. Read `_docs/history/DEV_LOG.md`.
7. Read `_docs/reference/ARCHITECTURE.md`.
8. If a shared registry or sidecar viewer exists, sync to it before acting.

## Core Working Doctrine

- Setup comes before substantial implementation.
- The builder contract is the governing discipline, not a suggestion list.
- The builder's loyalty is to the project and the application being built under
  the contract, not to short-term convenience or drift.
- The app journal is the durable builder-memory surface.
- The preferred collaboration loop is:
  - `sync -> think -> act -> resync`
- The standard scaffold uses:
  - `src/app.py` as the composition root
  - `src/ui/` for UI ownership
  - `src/core/` for core/runtime ownership
  - `_docs/` for doctrine, state, and continuity records
- `.dev-tools` is a builder/tool surface, not a runtime dependency by default.

## What To Fill In Immediately

Before substantial work continues, make sure these are real and current:

- project root and trust boundary
- required scaffold and setup surfaces
- project mission and scope
- current phase or tranche
- explicit non-goals
- current bottleneck
- next best move
- any important setup or runtime assumptions

## Trust Boundary

This starter pack exports doctrine and starter templates, not live project
truth. After installation:

- replace placeholders and starter notes with project-specific facts
- keep `_docs/continuity/WE_ARE_HERE_NOW.md` current
- append meaningful changes to `_docs/history/DEV_LOG.md`
- keep `_docs/TODO.md` aligned with the actual next work

If these documents drift from the real project state, fix them before taking on
larger changes.
