# Setup Doctrine

_Use this when the project is first being armed and scaffolded._

## First Rule

Before building features:

1. set up the project correctly,
2. read `_docs/BCC.md`,
3. treat `_docs/BCC.md` as the sole binding contract surface,
3. proceed in loyalty to the project and the app being built, not to shortcut
   convenience.

## Required Startup Sequence

### 1. Establish the project root

- Confirm active project folder.
- Keep writes inside project root unless explicitly authorized.
- Keep the project vendorable and self-contained.
- Do not create runtime dependency on sibling folders, `.parts`,
  `.dev-tools`, or external repos.

### 2. Establish the scaffold

Required baseline:

- `src/app.py`
- `src/core/`
- `src/ui/`
- `README.md`
- `LICENSE.md`
- `requirements.txt`
- `setup_env.bat`
- `run.bat`
- `_docs/`
- `tests/`

### 3. Establish the continuity packet

Create and keep current:

- `_docs/BCC.md`
- `_docs/BCC.md` (binding contract)
- `_docs/continuity/WE_ARE_HERE_NOW.md` or local current-state equivalent
- `_docs/TODO.md`
- `_docs/history/DEV_LOG.md`
- journal surfaces under `_docs/_journalDB/` and `_docs/_AppJOURNAL/`

### 4. Establish the composition root

`src/app.py` should own:

- settings load
- logging setup
- engine creation
- status reporting
- clear exit behavior

### 5. Establish logging and config owners

- use Python logging, not operational `print()`
- keep CLI JSON output separate from logs
- keep config paths project-local

### 6. Verify setup

Typical checks:

- `python -m compileall src tests`
- `python -m unittest discover -s tests`
- `python -m src.app status`
- `python -m src.app status --dump-json`

### 7. Park the setup tranche

Before feature work:

- update current-state docs
- update TODO/backlog
- write append-only journal entry
- regenerate mirrors if used
- re-run final verification
- name the next tranche clearly

## Loyalty Rule

The builder's operative loyalty is to:

- the application being created
- the contract
- the project's long-term health

It is not loyalty to prompt haste, drift, or convenience that weakens the app.
