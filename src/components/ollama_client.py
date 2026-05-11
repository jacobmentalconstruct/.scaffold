"""
FILE: src/components/ollama_client.py
ROLE: Thin stdlib-only wrapper around Ollama's local HTTP API.
WHAT IT DOES (T2.6): Sends a generate request to a locally running Ollama
      server and returns the response text.  Uses only urllib.request from
      the standard library — no third-party packages (contract Pledge 1).

Usage pattern (from CloseoutOrchestrator):
    client = OllamaClient(base_url="http://localhost:11434", timeout=30)
    text = client.generate(model="qwen3.5:9b", prompt="...", system="...")
    # Returns None on any error so callers can fall back gracefully.

Ollama API used: POST /api/generate (non-streaming)
  https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-completion
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from src.lib.logging_setup import get_logger


log = get_logger("components.ollama_client")

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT  = 60   # seconds — park-notes generation is not latency-sensitive


class OllamaClient:
    """Minimal Ollama HTTP client (stdlib only)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        num_predict: int = 8192,
        think: bool = False,
    ) -> str | None:
        """Call POST /api/generate and return the completed text.

        Returns None on any error (network, timeout, bad response).
        Callers should fall back to the template-compiled output.

        Args:
            model:       Ollama model name, e.g. "qwen3.5:9b"
            prompt:      The user prompt.
            system:      Optional system message.
            temperature: Sampling temperature (default 0.3 — focused but not robotic).
            num_predict: Max tokens to generate (default 8192 — prevents GPU OOM on
                         large context; park notes rarely need more than ~2-3k tokens).
            think:       Enable extended thinking / chain-of-thought for models that
                         support it (e.g. qwen3.5).  Default False — thinking tokens
                         consume GPU memory and the response field stays empty when
                         the model uses them exclusively.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": think,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }
        if system:
            payload["system"] = system

        body = json.dumps(payload).encode("utf-8")
        url = f"{self._base_url}/api/generate"

        log.info("ollama generate: model=%s url=%s prompt_len=%d",
                 model, url, len(prompt))
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            log.warning("ollama generate: network error — %s (is Ollama running?)", e)
            return None
        except TimeoutError:
            log.warning("ollama generate: timed out after %ds", self._timeout)
            return None
        except Exception as e:
            log.warning("ollama generate: unexpected error — %s", e)
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("ollama generate: bad JSON response — %s", e)
            return None

        text = data.get("response", "").strip()
        if not text:
            log.warning("ollama generate: empty response from model %s", model)
            return None

        done = data.get("done", False)
        if not done:
            log.warning("ollama generate: stream not marked done — response may be truncated")

        log.info("ollama generate: ok model=%s response_len=%d", model, len(text))
        return text

    def is_available(self, model: str | None = None) -> bool:
        """Return True if Ollama is reachable (and optionally has the model).

        Uses GET /api/tags (lists available models) to confirm liveness.
        """
        try:
            url = f"{self._base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    return False
                if model is None:
                    return True
                data = json.loads(resp.read().decode("utf-8"))
                names = [m.get("name", "") for m in data.get("models", [])]
                # Match loosely: "qwen3.5:9b" matches "qwen3.5:9b" exactly,
                # or the base name without tag.
                return any(
                    n == model or n.split(":")[0] == model.split(":")[0]
                    for n in names
                )
        except Exception:
            return False
