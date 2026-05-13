# Park Notes — T2.6 Ollama Park Notes

> Generated: 2026-05-11T20:28:06.015Z | Status: sealed | tranche_id: tranche_18ae9cb13441ac28_b3e216e6
> Started: 2026-05-11T20:26:27.757Z

## Declared Scope
Add optional Ollama-backed LLM generation for Tn_PARK_NOTES.md. If --with-ollama is passed to tranche-close, the closeout orchestrator calls a local Ollama model (default: qwen3.5:9b) to generate natural prose park notes from structured tranche data. Falls back to the deterministic template compiler if Ollama is unavailable.

### Completion Criteria
tranche-close --with-ollama produces LLM-prose park notes; falls back gracefully if Ollama unavailable; smoke_test.py 51/51 PASS

## Decisions Recorded
_3 decision(s) captured during this tranche._

### stdlib-only Ollama HTTP client (Contract Pledge 1)
**Impact area:** architecture

**Context:** Ollama has a Python SDK but Contract Pledge 1 forbids third-party packages in the sidecar.

**Rationale:** urllib.request from the stdlib is sufficient for a single POST to /api/generate. No third-party deps needed; the contract is honoured.

**Outcome:** OllamaClient in src/components/ollama_client.py uses only urllib.request and json. Returns None on any error so callers fall back gracefully.

_decision_id: decision_18ae9cb33e9f748c_7e752093 | importance: 8_

### Graceful fallback — Park Phase never blocks on Ollama
**Impact area:** reliability

**Context:** Park Phase is a contract obligation (§D). Ollama is a local service that may be unavailable (not running, model not loaded, GPU crash, timeout).

**Rationale:** OllamaClient.generate() returns None on any failure. CloseoutOrchestrator falls back to _compile_park_notes() (the deterministic template) if Ollama returns None. The close_tranche response includes ollama_used: true/false so the outcome is always transparent.

**Outcome:** Two-path design: Ollama path (prose) if available, template path (structured) otherwise. Park Phase always succeeds regardless of Ollama state.

_decision_id: decision_18ae9cb4da89716c_ddb537c0 | importance: 9_

### opt-in --with-ollama flag; default model qwen3.5:9b
**Impact area:** ux

**Context:** Multiple Qwen models are available locally. Ollama generation is slower (~10-20s) and not always wanted.

**Rationale:** Flag keeps the default behaviour deterministic. qwen3.5:9b was chosen as best prose quality from the available Qwen lineup at reasonable speed. --ollama-model allows override without a code change.

**Outcome:** tranche-close --with-ollama uses Ollama; without the flag the template compiler runs as before. Model defaults to qwen3.5:9b, overridable via --ollama-model.

_decision_id: decision_18ae9cb68ec26854_7b6a2518 | importance: 6_

## Files Changed
- `src/components/ollama_client.py` (added)
- `src/orchestrators/closeout_orchestrator.py` (modified)
- `src/interfaces/cli_interface.py` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-11T20:26:58.039Z)

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-11T20:28:06.015Z._
_Source: tranche_id=tranche_18ae9cb13441ac28_b3e216e6_
