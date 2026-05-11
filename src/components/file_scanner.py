"""
FILE: src/components/file_scanner.py
ROLE: Walks the host project tree, yielding observed files with metadata.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

PURPOSE
-------
The mechanical worker behind `scan_orchestrator`. Walks the host project
filesystem, applies ignore rules, computes hashes, and emits one observed
file record per visit.

WHAT IT EXPOSES
---------------
- `class FileScanner`
- `FileScanner.walk(project_root, ignore_rules) -> Iterable[ObservedFile]`
  Yields:
      ObservedFile(
          path,               # relative to project_root
          kind,               # "file" | "directory" | "symlink"
          size_bytes,
          content_hash,       # SHA-256 of file body, or "" for directories
          mtime,
          ext,
      )
- `FileScanner.read_ignore(project_root) -> IgnoreRules` — reads
  `.gitignore` and `.scaffoldignore`, merges them with sidecar defaults.

IGNORE BEHAVIOR
---------------
- Always skip: `.scaffold/` itself, `.git/`, `__pycache__/`, `.venv/`,
  `node_modules/`, `*.pyc`.
- Honor `.gitignore` semantics for everything else.
- `.scaffoldignore` overrides .gitignore (lets the user tell the sidecar
  to look at things git ignores).
- Symlinks: never follow outside `project_root`.

PERFORMANCE
-----------
- MVP: serial walk. Small to medium projects.
- Hashes computed in chunks (don't slurp huge files).
- Optional max-file-size cap for hashing; over the cap, record size and
  set `content_hash = "TOO_LARGE:<size>"`.

SPINE FIT
---------
- Called by `scan_orchestrator`. The scanner itself does not produce
  envelopes — it yields records, and the orchestrator wraps them.
- Read-only with respect to the host project.

NON-GOALS
---------
- Does not interpret content. No language detection beyond extension.
- Does not maintain index state — that's `project_index_manager`.

OPEN QUESTIONS
--------------
- Include hidden directories at the project root? Yes for `.github/`
  and similar; no for things like `.idea/` (handled by ignores).
- Use `os.scandir()` or `pathlib.walk()`? `scandir` is faster; decide at
  code time.
"""
