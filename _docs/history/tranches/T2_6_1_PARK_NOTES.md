# Park Notes — T2.6.1 Ollama GPU fix

## Declared Scope
Fix two issues blocking successful Ollama park-notes generation:
1.  **60s timeout**: Caused by `qwen3.5:9b` cold-start GPU load. Resolved by adding a `num_predict` cap (default 8192) to `OllamaClient.generate()` and exposing a `--ollama-num-predict` CLI flag.
2.  **Empty response**: Caused by `qwen3.5` extended-thinking mode emitting output to a separate `thinking` field. Resolved by adding `think:false` to the Ollama payload to ensure normal response routing.

## Decisions Recorded

### num_predict cap prevents GPU OOM during generation
*   **Context**: `qwen3.5:9b` timed out at 60s on a cold GPU start; uncapped generation can allocate unbounded VRAM, leading to OOM or indefinite execution.
*   **Rationale**: Ollama's `/api/generate` accepts `num_predict` to hard-cap output tokens. Park notes are at most ~3k tokens of Markdown; 8192 is a generous ceiling that fits comfortably in VRAM without risk.
*   **Outcome**: `OllamaClient.generate()` now accepts `num_predict` (default 8192) in options. This is exposed as the `--ollama-num-predict` CLI flag for easy tuning.

### think:false disables qwen3.5 extended thinking in Ollama payload
*   **Context**: `qwen3.5` models default to extended thinking mode in Ollama, writing reasoning to a `thinking` field and leaving the `response` field empty, causing `OllamaClient` to return `None`.
*   **Rationale**: Ollama exposes a top-level `think` boolean in `/api/generate`. Setting `think:false` suppresses extended thinking and routes output to `response` as expected. This is a no-op on models that do not support thinking.
*   **Outcome**: `OllamaClient.generate()` sends `think:False` by default. A `think=True` kwarg exists for callers explicitly wanting chain-of-thought output.

## Files Changed
*   `src/components/ollama_client.py` (modified)
*   `src/orchestrators/closeout_orchestrator.py` (modified)
*   `src/interfaces/cli_interface.py` (modified)

## Tests Run
*   `smoke_test.py` (passed at 2026-05-11T20:35:23.874Z)

## Deviations
None.

## Open Questions
None.

## Next Tranche
None known.

*Tranche closed by closeout_orchestrator*