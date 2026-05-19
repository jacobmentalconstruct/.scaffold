"""Local Ollama-backed sidecar agent runtime floor."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import ensure_dir, standard_main, tool_error, tool_result, write_json
from lib.text_workspace import resolve_project_root, runtime_root, safe_relative
from tools.directory_scaffold import FILE_METADATA as DIRECTORY_SCAFFOLD_METADATA, run as run_directory_scaffold
from tools.git_private_workspace import FILE_METADATA as GIT_PRIVATE_METADATA, run as run_git_private_workspace
from tools.journal_write import FILE_METADATA as JOURNAL_WRITE_METADATA, run as run_journal_write
from tools.agent_run_trace import FILE_METADATA as AGENT_RUN_TRACE_METADATA, run as run_agent_run_trace
from tools.local_agent_bootstrap import run as run_local_agent_bootstrap
from tools.project_setup import run as run_project_setup
from tools.session_evidence_store import FILE_METADATA as SESSION_EVIDENCE_METADATA, run as run_session_evidence_store
from tools.text_file_reader import FILE_METADATA as TEXT_FILE_READER_METADATA, run as run_text_file_reader
from tools.text_file_validator import FILE_METADATA as TEXT_FILE_VALIDATOR_METADATA, run as run_text_file_validator
from tools.text_file_writer import FILE_METADATA as TEXT_FILE_WRITER_METADATA, run as run_text_file_writer
from tools.workspace_boundary_audit import run as run_workspace_boundary_audit


FILE_METADATA = {
    "tool_name": "local_sidecar_agent",
    "version": "1.0.0",
    "entrypoint": "src/tools/local_sidecar_agent.py",
    "category": "agent-runtime",
    "summary": "Run the safe floor of an Ollama-backed local sidecar agent through guarded toolbox tools.",
    "mcp_name": "local_sidecar_agent",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "models", "preflight", "run"], "default": "run"},
            "project_root": {"type": "string", "default": "."},
            "prompt": {"type": "string", "description": "User task for the local sidecar agent."},
            "ollama_base_url": {"type": "string", "default": "http://localhost:11434"},
            "planner_model": {"type": "string", "default": "qwen2.5-coder:7b"},
            "response_model": {"type": "string", "default": "qwen3.5:4b"},
            "timeout_seconds": {"type": "number", "default": 60},
            "max_tool_rounds": {"type": "integer", "default": 4},
            "allowed_tools": {"type": "array", "items": {"type": "string"}},
            "confirm_mutations": {"type": "boolean", "default": False},
            "confirm_checkpoint": {"type": "boolean", "default": False},
            "checkpoint": {"type": "boolean", "default": True},
            "confirm_evidence": {"type": "boolean", "default": False},
            "heartbeat": {"type": "boolean", "default": False},
            "use_recovery_model": {"type": "boolean", "default": False},
            "recovery_model": {"type": "string", "description": "Optional model used only to draft operator recovery advice."},
            "mock_recovery_model_response": {
                "type": "string",
                "description": "Deterministic recovery-model advice for smoke tests.",
            },
            "claim_enforcement": {"type": "string", "enum": ["warn", "require_citation"], "default": "warn"},
            "planning_workspace": {
                "type": "boolean",
                "default": False,
                "description": "Expose a disposable ignored planning workspace path for future verification loops.",
            },
            "session_id": {"type": "string"},
            "window_turns": {"type": "integer", "default": 8},
            "evidence_mode": {
                "type": "string",
                "enum": ["overflow", "evaluation"],
                "default": "overflow",
                "description": "overflow archives sliding-window overflow; evaluation archives one durable run-level evidence item.",
            },
            "evidence_metadata": {
                "type": "object",
                "description": "Optional run-level metadata to include when evidence_mode=evaluation.",
            },
            "use_evidence_shelf": {"type": "boolean", "default": True},
            "write_trace": {"type": "boolean", "default": True},
            "preflight": {"type": "boolean", "default": True},
            "mock_ollama_failure": {
                "type": "string",
                "enum": ["request_timeout", "ollama_unreachable", "model_missing"],
                "description": "Deterministic model transport failure for smoke tests.",
            },
            "mock_ollama_responses": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Deterministic model responses for smoke tests.",
            },
            "protected_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Project-relative paths that mutating text tools must not write.",
            },
            "write_session": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    },
}


TOOL_CALL_RE = re.compile(r"```tool_call\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
DEFAULT_ALLOWED_TOOLS = [
    "text_file_reader",
    "text_file_writer",
    "directory_scaffold",
    "text_file_validator",
    "git_private_workspace",
    "journal_write",
    "session_evidence_store",
]
MUTATING_TOOLS = {"text_file_writer", "directory_scaffold", "journal_write"}
MUTATING_EVIDENCE_ACTIONS = {"init", "append", "archive_window", "export"}
MUTATING_TRACE_ACTIONS = {"init", "append", "export"}
RISKY_GIT_ACTIONS = {"init", "add", "commit", "checkout", "pull", "push"}


@dataclass
class AgentConfig:
    project_root: str
    ollama_base_url: str = "http://localhost:11434"
    planner_model: str = "qwen2.5-coder:7b"
    response_model: str = "qwen3.5:4b"
    timeout_seconds: int = 60
    max_tool_rounds: int = 4
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    confirm_mutations: bool = False
    confirm_checkpoint: bool = False
    checkpoint: bool = True
    confirm_evidence: bool = False
    heartbeat: bool = False
    use_recovery_model: bool = False
    recovery_model: str = ""
    claim_enforcement: str = "warn"
    planning_workspace: bool = False
    session_id: str = ""
    window_turns: int = 8
    evidence_mode: str = "overflow"
    evidence_metadata: dict[str, Any] = field(default_factory=dict)
    use_evidence_shelf: bool = True
    write_trace: bool = True
    preflight: bool = True
    protected_paths: list[str] = field(default_factory=list)


TOOL_REGISTRY: dict[str, tuple[dict[str, Any], Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "text_file_reader": (TEXT_FILE_READER_METADATA, run_text_file_reader),
    "text_file_writer": (TEXT_FILE_WRITER_METADATA, run_text_file_writer),
    "directory_scaffold": (DIRECTORY_SCAFFOLD_METADATA, run_directory_scaffold),
    "text_file_validator": (TEXT_FILE_VALIDATOR_METADATA, run_text_file_validator),
    "git_private_workspace": (GIT_PRIVATE_METADATA, run_git_private_workspace),
    "journal_write": (JOURNAL_WRITE_METADATA, run_journal_write),
    "session_evidence_store": (SESSION_EVIDENCE_METADATA, run_session_evidence_store),
    "agent_run_trace": (AGENT_RUN_TRACE_METADATA, run_agent_run_trace),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _runtime_paths(project_root: Path) -> dict[str, Path]:
    base = runtime_root(project_root) / "local_agent"
    return {
        "base": base,
        "sessions": base / "sessions",
        "logs": base / "logs",
        "state": base / "state",
        "runs": base / "runs",
        "outputs": base / "outputs",
        "parts": base / "parts",
        "ref": base / "ref",
        "tools": base / "tools",
        "audit_log": base / "logs" / "audit.jsonl",
        "action_journal": base / "logs" / "action_journal.jsonl",
    }


def _ensure_runtime(project_root: Path) -> dict[str, Path]:
    paths = _runtime_paths(project_root)
    for key in ["base", "sessions", "logs", "state", "runs", "outputs", "parts", "ref", "tools"]:
        ensure_dir(paths[key])
    return paths


def _public_runtime(paths: dict[str, Path], project_root: Path) -> dict[str, str]:
    return {
        key: safe_relative(value, project_root)
        for key, value in paths.items()
        if key not in {"audit_log", "action_journal"}
    }


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _timeout(arguments: dict[str, Any]) -> int:
    try:
        value = int(arguments.get("timeout_seconds", 60))
    except (TypeError, ValueError):
        return 60
    return max(1, min(value, 300))


def _config(arguments: dict[str, Any], project_root: Path) -> AgentConfig:
    allowed_tools = arguments.get("allowed_tools")
    if not isinstance(allowed_tools, list) or not allowed_tools:
        allowed = list(DEFAULT_ALLOWED_TOOLS)
    else:
        allowed = [str(item) for item in allowed_tools]
    protected_paths = arguments.get("protected_paths", [])
    if not isinstance(protected_paths, list):
        protected = []
    else:
        protected = [str(item) for item in protected_paths if str(item).strip()]
    try:
        max_rounds = int(arguments.get("max_tool_rounds", 4))
    except (TypeError, ValueError):
        max_rounds = 4
    try:
        window_turns = int(arguments.get("window_turns", 8))
    except (TypeError, ValueError):
        window_turns = 8
    return AgentConfig(
        project_root=str(project_root),
        ollama_base_url=str(arguments.get("ollama_base_url", "http://localhost:11434")).rstrip("/"),
        planner_model=str(arguments.get("planner_model", "qwen2.5-coder:7b")),
        response_model=str(arguments.get("response_model", "qwen3.5:4b")),
        timeout_seconds=_timeout(arguments),
        max_tool_rounds=max(1, min(max_rounds, 12)),
        allowed_tools=allowed,
        confirm_mutations=arguments.get("confirm_mutations") is True,
        confirm_checkpoint=arguments.get("confirm_checkpoint") is True,
        checkpoint=arguments.get("checkpoint", True) is not False,
        confirm_evidence=arguments.get("confirm_evidence") is True,
        heartbeat=arguments.get("heartbeat") is True,
        use_recovery_model=arguments.get("use_recovery_model") is True,
        recovery_model=str(arguments.get("recovery_model", "")).strip(),
        claim_enforcement=str(arguments.get("claim_enforcement", "warn")).strip()
        if str(arguments.get("claim_enforcement", "warn")).strip() in {"warn", "require_citation"}
        else "warn",
        planning_workspace=arguments.get("planning_workspace") is True,
        session_id=str(arguments.get("session_id", "")).strip(),
        window_turns=max(0, min(window_turns, 50)),
        evidence_mode=(
            str(arguments.get("evidence_mode", "overflow")).strip()
            if str(arguments.get("evidence_mode", "overflow")).strip() in {"overflow", "evaluation"}
            else "overflow"
        ),
        evidence_metadata=arguments.get("evidence_metadata") if isinstance(arguments.get("evidence_metadata"), dict) else {},
        use_evidence_shelf=arguments.get("use_evidence_shelf", True) is not False,
        write_trace=arguments.get("write_trace", True) is not False,
        preflight=arguments.get("preflight", True) is not False,
        protected_paths=protected,
    )


def _scan_models(base_url: str, timeout: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"available": False, "base_url": base_url, "models": [], "error": str(exc)}
    models = data.get("models", []) if isinstance(data, dict) else []
    names = [item.get("name", "") for item in models if isinstance(item, dict)]
    return {"available": True, "base_url": base_url, "models": names, "model_count": len(names)}


def _heartbeat(
    runtime_paths: dict[str, Path],
    config: AgentConfig,
    session_id: str,
    phase: str,
    message: str,
) -> dict[str, Any]:
    path = runtime_paths["logs"] / "heartbeat.jsonl"
    if not config.heartbeat:
        return {"enabled": False, "path": "logs/heartbeat.jsonl"}
    event = {"ts": _now(), "session_id": session_id, "phase": phase, "message": message}
    _append_jsonl(path, event)
    return {"enabled": True, "path": "logs/heartbeat.jsonl", "last": event}


def _planning_workspace(project_root: Path, runtime_paths: dict[str, Path], config: AgentConfig, session_id: str) -> dict[str, Any]:
    rel_path = f".dev-tools/runtime/local_agent/planning_workspaces/{session_id}"
    workspace = runtime_paths["base"] / "planning_workspaces" / session_id
    result: dict[str, Any] = {
        "enabled": config.planning_workspace,
        "path": rel_path,
        "created": False,
        "reason": "planning_workspace=false",
    }
    if not config.planning_workspace:
        return result
    result["reason"] = "confirm_mutations=false"
    if not config.confirm_mutations:
        return result
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text(
        "Disposable local-agent planning workspace.\n\n"
        "This ignored runtime folder is for future verification planning notes only.\n",
        encoding="utf-8",
    )
    result.update({"created": True, "reason": "created under ignored runtime state"})
    return result


def _model_readiness(config: AgentConfig) -> dict[str, Any]:
    scan = _scan_models(config.ollama_base_url, min(config.timeout_seconds, 10))
    warnings: list[str] = []
    if config.timeout_seconds < 15:
        warnings.append("timeout_seconds is low for local model inference")
    if not scan.get("available"):
        return {
            "ready": False,
            "recovery_class": "ollama_unreachable",
            "message": str(scan.get("error", "Ollama is not reachable")),
            "next_actions": ["check_ollama_service", "refresh_models", "retry_run"],
            "scan": scan,
            "warnings": warnings,
        }
    models = [str(item) for item in scan.get("models", [])]
    missing = [model for model in [config.planner_model, config.response_model] if model not in models]
    if missing:
        return {
            "ready": False,
            "recovery_class": "model_missing",
            "message": "selected model is not available: " + ", ".join(missing),
            "next_actions": ["refresh_models", "choose_available_model", "retry_run"],
            "scan": scan,
            "warnings": warnings,
        }
    return {
        "ready": True,
        "recovery_class": "",
        "message": "",
        "next_actions": [],
        "scan": scan,
        "warnings": warnings,
    }


def _ollama_chat(config: AgentConfig, messages: list[dict[str, str]], model: str) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    request = urllib.request.Request(
        f"{config.ollama_base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    message = data.get("message", {}) if isinstance(data, dict) else {}
    content = message.get("content", "") if isinstance(message, dict) else ""
    return str(content)


def _sanitize_model_text(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def _tool_catalog_text(allowed_tools: list[str]) -> str:
    lines = []
    for name in allowed_tools:
        item = TOOL_REGISTRY.get(name)
        if not item:
            continue
        metadata, _ = item
        lines.append(f"- {name}: {metadata.get('summary', '')}")
        props = metadata.get("input_schema", {}).get("properties", {})
        if props:
            lines.append(f"  args: {', '.join(sorted(props.keys()))}")
    return "\n".join(lines)


def _system_prompt(config: AgentConfig, bootstrap_summary: str, evidence_summary: str) -> str:
    return (
        "You are a local sidecar agent. Use only the listed toolbox tools.\n"
        "Never claim a file was created, modified, or validated unless a tool result proves it.\n"
        "Return tool calls as fenced JSON blocks exactly like:\n"
        "```tool_call\n{\"tool\":\"text_file_reader\",\"arguments\":{\"path\":\"README.md\"}}\n```\n"
        "Do not use raw shell, PowerShell, cmd, bash, cat, echo, or arbitrary commands.\n"
        "All paths are relative to the project root; the runtime injects project_root.\n\n"
        f"Project root: {config.project_root}\n"
        f"Allowed tools:\n{_tool_catalog_text(config.allowed_tools)}\n\n"
        f"Bootstrap summary:\n{bootstrap_summary[:3000]}\n\n"
        f"Evidence Shelf:\n{evidence_summary[:2000]}"
    )


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    position = 0
    opener = re.compile(r"```tool_call\s*", re.IGNORECASE)
    while True:
        match = opener.search(text, position)
        if not match:
            break
        content_start = match.end()
        search_at = content_start
        raw = ""
        payload: Any = None
        error = ""
        repair_signals: list[str] = []
        close_at = -1
        while True:
            close_at = text.find("```", search_at)
            if close_at == -1:
                raw = text[content_start:].strip()
                try:
                    payload, repair_signals = _load_tool_call_payload_with_repair(raw)
                except json.JSONDecodeError as exc:
                    error = str(exc)
                position = len(text)
                break
            raw = text[content_start:close_at].strip()
            try:
                payload, repair_signals = _load_tool_call_payload_with_repair(raw)
                position = close_at + 3
                break
            except json.JSONDecodeError as exc:
                error = str(exc)
                search_at = close_at + 3
                continue
        if payload is None:
            calls.append({"tool": "__malformed__", "arguments": {}, "raw": raw, "error": error})
            continue
        if not isinstance(payload, dict):
            calls.append({"tool": "__malformed__", "arguments": {}, "raw": raw, "error": "tool_call must be a JSON object"})
            continue
        tool_name = str(payload.get("tool", payload.get("name", ""))).strip()
        arguments = payload.get("arguments", payload.get("args", {}))
        if not isinstance(arguments, dict):
            calls.append({"tool": "__malformed__", "arguments": {}, "raw": raw, "error": "arguments must be an object"})
            continue
        call = {"tool": tool_name, "arguments": arguments, "raw": raw}
        if repair_signals:
            call["repair_signals"] = repair_signals
        calls.append(call)
    return calls


def _load_tool_call_payload(raw: str) -> Any:
    payload, _repair_signals = _load_tool_call_payload_with_repair(raw)
    return payload


def _load_tool_call_payload_with_repair(raw: str) -> tuple[Any, list[str]]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[str, list[str]]] = [(raw, [])]
    seen = {raw}
    for signal, repair in (
        ("raw_control_chars_in_json_string", _escape_string_control_chars),
        ("model_escaped_structural_quotes", _unescape_model_escaped_quotes),
        ("invalid_json_escape_repair", _repair_invalid_json_escapes),
        ("content_string_quote_repair", _escape_content_string_quotes),
    ):
        for candidate, signals in list(candidates):
            repaired = repair(candidate)
            if repaired != candidate and repaired not in seen:
                seen.add(repaired)
                candidates.append((repaired, signals + [signal]))
    for candidate, signals in list(candidates):
        repaired = _escape_content_string_quotes(_repair_invalid_json_escapes(_escape_string_control_chars(candidate)))
        if repaired != candidate and repaired not in seen:
            seen.add(repaired)
            combined = list(dict.fromkeys(signals + [
                "raw_control_chars_in_json_string",
                "invalid_json_escape_repair",
                "content_string_quote_repair",
            ]))
            candidates.append((repaired, combined))
    last_error: json.JSONDecodeError | None = None
    for candidate, signals in candidates:
        try:
            payload, end = decoder.raw_decode(candidate)
            trailing = candidate[end:].strip()
            if trailing in {"", "[/tool_call]"}:
                return payload, signals
        except json.JSONDecodeError as exc:
            last_error = exc
    try:
        return json.loads(raw), []
    except json.JSONDecodeError as original:
        raise last_error or original


def _escape_string_control_chars(raw: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue
        out.append(ch)
        if ch == '"':
            in_string = True
    return "".join(out)


def _unescape_model_escaped_quotes(raw: str) -> str:
    if '\\"' not in raw:
        return raw
    return raw.replace('\\"', '"')


def _repair_invalid_json_escapes(raw: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    changed = False
    valid_json_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}
    while i < len(raw):
        ch = raw[i]
        next_ch = raw[i + 1] if i + 1 < len(raw) else ""
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                i += 1
                continue
            if ch == "\\":
                if next_ch == "'":
                    out.append("'")
                    changed = True
                    i += 2
                    continue
                if next_ch and next_ch not in valid_json_escapes:
                    out.append(next_ch)
                    changed = True
                    i += 2
                    continue
                out.append(ch)
                escaped = True
                i += 1
                continue
            out.append(ch)
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == "\\" and next_ch == '"':
            out.append('"')
            in_string = True
            changed = True
            i += 2
            continue
        out.append(ch)
        if ch == '"':
            in_string = True
        i += 1
    return "".join(out) if changed else raw


def _escape_content_string_quotes(raw: str) -> str:
    out: list[str] = []
    i = 0
    changed = False
    content_key = '"content"'
    while i < len(raw):
        if raw.startswith(content_key, i):
            start = i
            j = i + len(content_key)
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j >= len(raw) or raw[j] != ":":
                out.append(raw[i])
                i += 1
                continue
            j += 1
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j >= len(raw) or raw[j] != '"':
                out.append(raw[i])
                i += 1
                continue
            out.append(raw[start : j + 1])
            i = j + 1
            escaped = False
            while i < len(raw):
                ch = raw[i]
                if escaped:
                    out.append(ch)
                    escaped = False
                    i += 1
                    continue
                if ch == "\\":
                    out.append(ch)
                    escaped = True
                    i += 1
                    continue
                if ch == '"':
                    if _looks_like_content_terminator(raw, i):
                        out.append(ch)
                        i += 1
                        break
                    out.append('\\"')
                    changed = True
                    i += 1
                    continue
                out.append(ch)
                i += 1
            continue
        out.append(raw[i])
        i += 1
    return "".join(out) if changed else raw


def _looks_like_content_terminator(raw: str, quote_index: int) -> bool:
    j = quote_index + 1
    while j < len(raw) and raw[j].isspace():
        j += 1
    if j >= len(raw):
        return True
    if raw[j] == "}":
        return True
    if raw[j] != ",":
        return False
    j += 1
    while j < len(raw) and raw[j].isspace():
        j += 1
    if j >= len(raw):
        return True
    if raw[j] in "}]":
        return True
    for key in ('"overwrite"', '"type"', '"path"', '"file_type"', '"kind"'):
        if raw.startswith(key, j):
            return True
    return False


def _validate_schema(metadata: dict[str, Any], args: dict[str, Any]) -> list[str]:
    schema = metadata.get("input_schema", {})
    props = schema.get("properties", {})
    errors: list[str] = []
    if schema.get("additionalProperties") is False:
        for key in args:
            if key not in props:
                errors.append(f"unexpected argument: {key}")
    for key, spec in props.items():
        if key not in args:
            continue
        value = args[key]
        expected = spec.get("type") if isinstance(spec, dict) else None
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{key} must be a string")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{key} must be a boolean")
        elif expected == "array":
            if not isinstance(value, list):
                errors.append(f"{key} must be an array")
            else:
                item_spec = spec.get("items", {}) if isinstance(spec, dict) else {}
                item_type = item_spec.get("type") if isinstance(item_spec, dict) else None
                for index, item in enumerate(value):
                    if item_type == "object" and not isinstance(item, dict):
                        errors.append(f"{key}[{index}] must be an object")
                    elif item_type == "string" and not isinstance(item, str):
                        errors.append(f"{key}[{index}] must be a string")
        elif expected == "object" and not isinstance(value, dict):
            errors.append(f"{key} must be an object")
        elif expected == "integer" and not isinstance(value, int):
            errors.append(f"{key} must be an integer")
        enum = spec.get("enum") if isinstance(spec, dict) else None
        if enum and value not in enum:
            errors.append(f"{key} must be one of: {', '.join(map(str, enum))}")
    return errors


def _is_mutating(tool_name: str, args: dict[str, Any]) -> bool:
    if tool_name == "git_private_workspace":
        return str(args.get("action", "status")) in RISKY_GIT_ACTIONS
    if tool_name == "session_evidence_store":
        return str(args.get("action", "status")) in MUTATING_EVIDENCE_ACTIONS
    if tool_name == "agent_run_trace":
        return str(args.get("action", "status")) in MUTATING_TRACE_ACTIONS
    return tool_name in MUTATING_TOOLS


def _inject_confirm(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    updated = dict(args)
    if tool_name in {"text_file_writer", "directory_scaffold", "git_private_workspace", "session_evidence_store", "agent_run_trace"}:
        updated["confirm"] = True
    return updated


def _drop_read_only_null_defaults(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in {"text_file_reader", "text_file_validator"}:
        return args
    return {key: value for key, value in args.items() if value is not None}


def _execute_tool_call(
    call: dict[str, Any],
    *,
    config: AgentConfig,
    project_root: Path,
    runtime_paths: dict[str, Path],
    touched_paths: list[str],
) -> dict[str, Any]:
    tool_name = call["tool"]
    if tool_name == "__malformed__":
        return {
            "status": "error",
            "tool": "__malformed__",
            "input": call,
            "result": {
                "message": call.get("error", "malformed tool call"),
                "raw": call.get("raw", "")[:800],
                "recovery_class": "malformed_tool_call",
            },
        }
    if tool_name not in config.allowed_tools:
        return tool_error("local_sidecar_agent", call, f"tool is not allowlisted: {tool_name}")
    entry = TOOL_REGISTRY.get(tool_name)
    if not entry:
        return tool_error("local_sidecar_agent", call, f"unknown tool: {tool_name}")
    metadata, runner = entry
    args = dict(call.get("arguments", {}))
    args["project_root"] = str(project_root)
    if config.protected_paths and tool_name in {"text_file_writer", "directory_scaffold"}:
        args["protected_paths"] = list(config.protected_paths)
    args = _drop_read_only_null_defaults(tool_name, args)
    schema_errors = _validate_schema(metadata, args)
    if schema_errors:
        return tool_result(
            "local_sidecar_agent",
            call,
            {"message": "; ".join(schema_errors), "recovery_class": "tool_schema_error", "tool": tool_name},
            status="error",
        )
    mutating = _is_mutating(tool_name, args)
    if mutating and not config.confirm_mutations:
        return tool_result(
            "local_sidecar_agent",
            call,
            {
                "approval_required": True,
                "tool": tool_name,
                "reason": "mutating tool call requires confirm_mutations=true",
                "arguments": args,
            },
            status="approval_required",
        )
    if mutating:
        args = _inject_confirm(tool_name, args)
    started = time.time()
    try:
        result = runner(args)
    except Exception as exc:
        result = tool_result(
            "local_sidecar_agent",
            call,
            {"message": str(exc), "recovery_class": "tool_runtime_error", "tool": tool_name},
            status="error",
        )
    duration_ms = round((time.time() - started) * 1000)
    _append_jsonl(
        runtime_paths["audit_log"],
        {
            "ts": _now(),
            "tool": tool_name,
            "status": result.get("status"),
            "duration_ms": duration_ms,
            "mutating": mutating,
        },
    )
    if result.get("status") == "ok":
        payload = result.get("result", {})
        if isinstance(payload, dict) and payload.get("path"):
            touched_paths.append(str(payload["path"]))
        if tool_name == "directory_scaffold":
            for item in payload.get("entries", []) if isinstance(payload, dict) else []:
                if isinstance(item, dict) and item.get("path"):
                    touched_paths.append(str(item["path"]))
    return result


def _format_tool_results(results: list[dict[str, Any]]) -> str:
    slim = []
    for result in results:
        text = json.dumps(result, sort_keys=True)
        slim.append(text[:4000])
    return "\n".join(f"[tool_result]\n{item}\n[/tool_result]" for item in slim)


def _validate_touched(project_root: Path, touched_paths: list[str]) -> dict[str, Any]:
    unique = sorted(set(touched_paths))
    checks = []
    for rel in unique:
        path = project_root / rel
        checks.append({"path": rel, "exists": path.exists(), "is_file": path.is_file()})
    return {
        "touched_paths": unique,
        "checks": checks,
        "valid": all(item["exists"] for item in checks),
    }


def _claim_guardrails(
    final_text: str,
    touched_paths: list[str],
    evidence_ids: list[str],
    *,
    enforcement: str = "warn",
) -> dict[str, Any]:
    text = final_text.lower()
    claim_patterns = [
        "i created", "i modified", "i updated", "i wrote", "i validated",
        "created ", "modified ", "updated ", "wrote ", "validated ",
    ]
    claims_work = any(pattern in text for pattern in claim_patterns)
    path_citations = [path for path in sorted(set(touched_paths)) if path and path.lower() in text]
    evidence_citations = [item for item in evidence_ids if item and item.lower() in text]
    has_sources = bool(touched_paths or evidence_ids)
    has_explicit_citation = bool(path_citations or evidence_citations)
    warnings: list[str] = []
    if claims_work and not has_sources:
        warnings.append("final_text appears to claim completed work without touched paths or evidence IDs")
    if enforcement == "require_citation" and claims_work and has_sources and not has_explicit_citation:
        warnings.append("final_text claims completed work but does not cite a touched path or evidence ID")
    return {
        "passed": not warnings,
        "enforcement": enforcement,
        "claims_work": claims_work,
        "has_touched_paths": bool(touched_paths),
        "has_evidence_ids": bool(evidence_ids),
        "has_explicit_citation": has_explicit_citation,
        "path_citations": path_citations,
        "evidence_citations": evidence_citations,
        "warnings": warnings,
    }


def _checkpoint(project_root: Path, touched_paths: list[str], config: AgentConfig, summary: str) -> dict[str, Any]:
    if not config.checkpoint or not touched_paths:
        return {"skipped": True, "reason": "checkpoint disabled or no touched paths"}
    if not config.confirm_checkpoint:
        return {"skipped": True, "approval_required": True, "reason": "checkpoint requires confirm_checkpoint=true"}
    init = run_git_private_workspace({"project_root": str(project_root), "action": "init", "confirm": True})
    if init.get("status") != "ok":
        return {"skipped": False, "status": "error", "step": "init", "result": init}
    add = run_git_private_workspace({
        "project_root": str(project_root),
        "action": "add",
        "paths": sorted(set(touched_paths)),
        "confirm": True,
    })
    if add.get("status") != "ok":
        return {"skipped": False, "status": "error", "step": "add", "result": add}
    message = f"local_sidecar_agent checkpoint | files={len(set(touched_paths))} | {summary[:80]}"
    commit = run_git_private_workspace({
        "project_root": str(project_root),
        "action": "commit",
        "message": message,
        "confirm": True,
    })
    return {"skipped": False, "status": commit.get("status"), "message": message, "result": commit}


def _model_response(
    *,
    config: AgentConfig,
    messages: list[dict[str, str]],
    model: str,
    mock_responses: list[str],
    mock_failure: str,
    round_index: int,
) -> str:
    if round_index == 0 and mock_failure:
        if mock_failure == "request_timeout":
            raise TimeoutError("timed out")
        if mock_failure == "ollama_unreachable":
            raise urllib.error.URLError("connection refused")
        if mock_failure == "model_missing":
            raise RuntimeError(f"model not found: {model}")
    if mock_responses:
        if round_index < len(mock_responses):
            return mock_responses[round_index]
        return "No further tool calls."
    return _ollama_chat(config, messages, model)


def _evidence_shelf_text(evidence_shelf: dict[str, Any]) -> str:
    payload = evidence_shelf.get("result", {}) if isinstance(evidence_shelf, dict) else {}
    if not isinstance(payload, dict) or not payload:
        return "No Evidence Shelf available."
    lines = [
        f"Session: {payload.get('session_id', '')}",
        f"Items: {payload.get('item_count', 0)}",
    ]
    if payload.get("rolling_summary"):
        lines.append(f"Summary: {payload.get('rolling_summary')}")
    for label in ["open_loops", "decisions"]:
        values = payload.get(label, [])
        if isinstance(values, list) and values:
            lines.append(f"{label.replace('_', ' ').title()}:")
            lines.extend(f"- {item}" for item in values[:8])
    index = payload.get("item_index", [])
    if isinstance(index, list) and index:
        lines.append("Evidence Index:")
        for item in index[:12]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('item_id')}: {item.get('summary')}")
    return "\n".join(lines)


def _evidence_turns(prompt: str, rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = [{
        "sequence": 1,
        "role": "user",
        "kind": "user_turn",
        "content": prompt,
        "summary": f"User prompt: {prompt[:160]}",
        "tags": ["local-agent", "user-turn"],
    }]
    sequence = 2
    for round_item in rounds:
        response = str(round_item.get("response", ""))
        if response:
            turns.append({
                "sequence": sequence,
                "role": "assistant",
                "kind": "agent_round",
                "content": response,
                "summary": f"Agent round {round_item.get('round')}: {response[:160]}",
                "tags": ["local-agent", "agent-round"],
            })
            sequence += 1
        results = round_item.get("results", [])
        if isinstance(results, list) and results:
            tools = [str(result.get("tool", "")) for result in results if isinstance(result, dict) and result.get("tool")]
            turns.append({
                "sequence": sequence,
                "role": "tool",
                "kind": "tool_result",
                "content": json.dumps(results, indent=2, sort_keys=False),
                "summary": f"Tool results for round {round_item.get('round')}: {', '.join(tools) or 'none'}",
                "tags": ["local-agent", "tool-result"],
                "tools": tools,
            })
            sequence += 1
    return turns


def _archive_evidence(
    project_root: Path,
    *,
    session_id: str,
    prompt: str,
    rounds: list[dict[str, Any]],
    config: AgentConfig,
    approval_required: bool,
    touched_paths: list[str] | None = None,
    validation: dict[str, Any] | None = None,
    final_text: str = "",
    halted_reason: str = "",
    recovery: dict[str, Any] | None = None,
    parse_repair_signals: list[str] | None = None,
) -> dict[str, Any]:
    if not config.use_evidence_shelf:
        return {"skipped": True, "reason": "use_evidence_shelf=false"}
    if not config.confirm_evidence:
        return {"skipped": True, "approval_required": True, "reason": "evidence archive requires confirm_evidence=true"}
    turns = _evidence_turns(prompt, rounds)
    if config.evidence_mode == "evaluation":
        metadata = dict(config.evidence_metadata)
        scenario_id = str(metadata.get("scenario_id", "")).strip()
        run_id = str(metadata.get("run_id", "")).strip()
        verification = validation or {}
        recovery_class = str((recovery or {}).get("class", "")).strip()
        signal_summary = {
            "parse_repair_signals": parse_repair_signals or [],
            "recovery_class": recovery_class,
        }
        evaluation_item = {
            "sequence": len(turns) + 1,
            "role": "system",
            "kind": "evaluation_run_summary",
            "source": "local_sidecar_agent",
            "summary": (
                "Evaluation evidence"
                + (f" for {run_id}" if run_id else "")
                + (f" / {scenario_id}" if scenario_id else "")
            ),
            "content": json.dumps({
                "evidence_mode": "evaluation",
                "metadata": metadata,
                "session_id": session_id,
                "prompt_summary": prompt[:500],
                "round_count": len(rounds),
                "touched_paths": sorted(set(touched_paths or [])),
                "validation": verification,
                "halted_reason": halted_reason,
                "recovery": recovery or {},
                "signals": signal_summary,
                "final_text_summary": final_text[:1000],
            }, indent=2, sort_keys=False),
            "tags": ["local-agent", "evaluation-evidence", "bag-of-evidence"],
            "paths": sorted(set(touched_paths or [])),
            "importance": 1,
        }
        return run_session_evidence_store({
            "project_root": str(project_root),
            "action": "archive_window",
            "confirm": True,
            "session_id": session_id,
            "turns": [evaluation_item],
            "window_turns": 0,
            "archive_all": True,
            "rolling_summary": f"Evaluation evidence for latest prompt: {prompt[:160]}",
            "open_loops": ["Approval required before continuing."] if approval_required else [],
            "tags": ["local-agent", "evaluation-evidence", "bag-of-evidence"],
        })
    return run_session_evidence_store({
        "project_root": str(project_root),
        "action": "archive_window",
        "confirm": True,
        "session_id": session_id,
        "turns": turns,
        "window_turns": config.window_turns,
        "rolling_summary": f"Local agent session evidence for latest prompt: {prompt[:160]}",
        "open_loops": ["Approval required before continuing."] if approval_required else [],
        "tags": ["local-agent", "bag-of-evidence"],
    })


def _recovery_from_exception(exc: Exception, config: AgentConfig) -> dict[str, Any]:
    message = str(exc)
    lowered = message.lower()
    if isinstance(exc, TimeoutError) or "timed out" in lowered or "timeout" in lowered:
        recovery_class = "request_timeout"
        next_actions = ["increase_timeout", "retry_run", "refresh_models"]
    elif isinstance(exc, urllib.error.URLError) or "connection refused" in lowered or "failed to establish" in lowered:
        recovery_class = "ollama_unreachable"
        next_actions = ["check_ollama_service", "refresh_models", "retry_run"]
    elif "model" in lowered and ("not found" in lowered or "missing" in lowered):
        recovery_class = "model_missing"
        next_actions = ["refresh_models", "choose_available_model", "retry_run"]
    else:
        recovery_class = "model_request_failed"
        next_actions = ["inspect_details", "refresh_models", "retry_run"]
    recovery = {
        "class": recovery_class,
        "message": message,
        "next_actions": next_actions,
        "selected_models": {
            "planner_model": config.planner_model,
            "response_model": config.response_model,
        },
        "timeout_seconds": config.timeout_seconds,
    }
    recovery["decisions"] = _recovery_decisions(recovery, config)
    return recovery


def _recovery_from_class(
    recovery_class: str,
    message: str,
    config: AgentConfig,
    *,
    next_actions: list[str] | None = None,
) -> dict[str, Any]:
    defaults = {
        "malformed_tool_call": ["inspect_tool_call_json", "retry_with_valid_json", "stop_for_operator_review"],
        "tool_schema_error": ["inspect_tool_schema", "retry_with_valid_arguments", "stop_for_operator_review"],
        "tool_runtime_error": ["inspect_tool_result", "retry_or_choose_safer_tool", "stop_for_operator_review"],
        "control_file_tamper": ["inspect_tool_call", "preserve_control_files", "stop_for_operator_review"],
        "approval_required": ["review_output", "enable_named_confirmation", "rerun_if_safe"],
        "max_rounds_exhausted": ["increase_max_tool_rounds", "narrow_task_prompt", "inspect_trace"],
        "claim_guardrail_warning": ["inspect_final_text", "cite_touched_paths_or_evidence", "retry_summary"],
    }
    recovery = {
        "class": recovery_class,
        "message": message,
        "next_actions": next_actions if next_actions is not None else defaults.get(recovery_class, ["inspect_details"]),
        "selected_models": {
            "planner_model": config.planner_model,
            "response_model": config.response_model,
        },
        "timeout_seconds": config.timeout_seconds,
    }
    recovery["decisions"] = _recovery_decisions(recovery, config)
    return recovery


def _recovery_decisions(recovery: dict[str, Any], config: AgentConfig) -> list[dict[str, Any]]:
    recovery_class = str(recovery.get("class", ""))
    decisions: list[dict[str, Any]] = [{"id": "stop_for_review", "label": "Stop for operator review", "kind": "stop"}]
    if recovery_class in {"request_timeout", "model_request_failed", "max_rounds_exhausted"}:
        decisions.insert(0, {
            "id": "retry_longer_timeout",
            "label": "Retry with longer timeout",
            "kind": "retry",
            "patch": {"timeout_seconds": min(max(config.timeout_seconds * 2, 30), 300)},
        })
    if recovery_class in {"ollama_unreachable", "model_missing", "request_timeout", "model_request_failed"}:
        decisions.insert(0, {"id": "refresh_models", "label": "Refresh model list", "kind": "refresh_models"})
    if recovery_class == "model_missing":
        decisions.insert(0, {"id": "choose_available_model", "label": "Choose available models", "kind": "operator"})
    if recovery_class == "approval_required":
        decisions.insert(0, {"id": "confirm_mutations", "label": "Enable mutation confirmation", "kind": "set_confirm_mutations"})
    if recovery_class == "claim_guardrail_warning":
        decisions.insert(0, {"id": "retry_with_citations", "label": "Retry with evidence citations", "kind": "retry"})
    if recovery_class in {"malformed_tool_call", "tool_schema_error", "tool_runtime_error"}:
        decisions.insert(0, {"id": "retry_same_settings", "label": "Retry same settings", "kind": "retry"})
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for decision in decisions:
        decision_id = str(decision.get("id", ""))
        if decision_id and decision_id not in seen:
            seen.add(decision_id)
            unique.append(decision)
    return unique


def _recovery_model_advice(
    recovery: dict[str, Any],
    config: AgentConfig,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if not config.use_recovery_model:
        return {"enabled": False}
    mock = str(arguments.get("mock_recovery_model_response", "")).strip()
    model = config.recovery_model or config.response_model
    if mock:
        return {"enabled": True, "model": model, "message": mock, "mocked": True}
    prompt = (
        "Convert this local-agent recovery event into concise operator next steps. "
        "Do not add authority or recommend raw terminal use.\n\n"
        + json.dumps({
            "class": recovery.get("class"),
            "message": recovery.get("message"),
            "next_actions": recovery.get("next_actions", []),
            "decisions": recovery.get("decisions", []),
        }, sort_keys=True)
    )
    try:
        message = _ollama_chat(config, [{"role": "user", "content": prompt}], model)
    except Exception as exc:
        return {"enabled": True, "model": model, "status": "error", "message": str(exc)}
    return {"enabled": True, "model": model, "status": "ok", "message": _sanitize_model_text(message)[:1200]}


def _prepare_recovery(
    recovery: dict[str, Any],
    config: AgentConfig,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if not recovery:
        return recovery
    if "decisions" not in recovery:
        recovery["decisions"] = _recovery_decisions(recovery, config)
    recovery["recovery_model_advice"] = _recovery_model_advice(recovery, config, arguments)
    return recovery


def _recovery_from_result(result: dict[str, Any], config: AgentConfig) -> dict[str, Any]:
    payload = result.get("result", {}) if isinstance(result, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    recovery_class = str(payload.get("recovery_class", "")).strip()
    message = str(payload.get("message", result.get("status", "tool failed")))
    if recovery_class:
        return _recovery_from_class(recovery_class, message, config)
    if result.get("status") == "approval_required":
        return _recovery_from_class("approval_required", message or "approval required", config)
    return _recovery_from_class("tool_runtime_error", message or "tool runtime error", config)


def _evidence_ids(evidence_archive: dict[str, Any]) -> list[str]:
    payload = evidence_archive.get("result", evidence_archive)
    evidence_items = payload.get("archived_items", []) if isinstance(payload, dict) else []
    return [
        str(item.get("item_id"))
        for item in evidence_items
        if isinstance(item, dict) and item.get("item_id")
    ]


def _trace_payload(
    *,
    session_id: str,
    prompt: str,
    config: AgentConfig,
    status: str,
    recovery: dict[str, Any] | None,
    rounds: list[dict[str, Any]],
    touched_paths: list[str],
    validation: dict[str, Any],
    evidence_ids: list[str],
    journal_entry_uid: str,
    duration_ms: int,
    summary: str,
) -> dict[str, Any]:
    tool_results: list[dict[str, Any]] = []
    for round_item in rounds:
        for result in round_item.get("results", []):
            if isinstance(result, dict):
                tool_results.append({
                    "round": round_item.get("round"),
                    "tool": result.get("tool"),
                    "status": result.get("status"),
                })
    return {
        "action": "append",
        "confirm": True,
        "session_id": session_id,
        "status": status,
        "recovery_class": (recovery or {}).get("class", ""),
        "recovery_message": (recovery or {}).get("message", ""),
        "prompt": prompt,
        "summary": summary,
        "selected_models": {
            "planner_model": config.planner_model,
            "response_model": config.response_model,
            "ollama_base_url": config.ollama_base_url,
            "timeout_seconds": config.timeout_seconds,
        },
        "allowed_tools": config.allowed_tools,
        "tool_calls": [
            {
                "round": item.get("round"),
                "tool_call_count": item.get("tool_call_count", 0),
                "parse_repair_signals": item.get("parse_repair_signals", []),
            }
            for item in rounds
        ],
        "tool_results": tool_results,
        "approvals": {
            "confirm_mutations": config.confirm_mutations,
            "confirm_checkpoint": config.confirm_checkpoint,
            "confirm_evidence": config.confirm_evidence,
        },
        "touched_paths": sorted(set(touched_paths)),
        "evidence_ids": evidence_ids,
        "verification": validation,
        "journal_entry_uid": journal_entry_uid,
        "duration_ms": duration_ms,
        "trace": {
            "rounds": rounds,
            "recovery": recovery or {},
            "builder_loop_step": "local_sidecar_agent_run",
        },
    }


def _record_run_trace(project_root: Path, config: AgentConfig, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.write_trace:
        return {"status": "skipped", "result": {"reason": "write_trace=false"}}
    try:
        trace_input = dict(payload)
        trace_input["project_root"] = str(project_root)
        return run_agent_run_trace(trace_input)
    except Exception as exc:  # pragma: no cover - trace failure must not break agent runs
        return {"status": "error", "tool": "agent_run_trace", "input": {}, "result": {"message": str(exc)}}


def _finish_recovery_event(
    *,
    arguments: dict[str, Any],
    project_root: Path,
    runtime_paths: dict[str, Path],
    config: AgentConfig,
    session_id: str,
    prompt: str,
    run_started: float,
    evidence_shelf: dict[str, Any],
    rounds: list[dict[str, Any]],
    touched_paths: list[str],
    recovery: dict[str, Any],
) -> dict[str, Any]:
    recovery = _prepare_recovery(recovery, config, arguments)
    _heartbeat(runtime_paths, config, session_id, "recovery", f"Recovery event: {recovery['class']}")
    halted_reason = recovery["class"]
    validation = _validate_touched(project_root, touched_paths)
    evidence_archive = _archive_evidence(
        project_root,
        session_id=session_id,
        prompt=prompt,
        rounds=rounds,
        config=config,
        approval_required=False,
    )
    evidence_ids = _evidence_ids(evidence_archive)
    journal = run_journal_write({
        "project_root": str(project_root),
        "action": "create",
        "title": "Local sidecar agent recovery event",
        "body": (
            f"Prompt: {prompt}\n\n"
            f"Recovery: {recovery['class']} - {recovery['message']}\n\n"
            f"Evidence IDs: {', '.join(evidence_ids) or 'none'}"
        ),
        "kind": "agent-recovery",
        "source": "local_sidecar_agent",
        "author": "local_sidecar_agent",
        "tags": ["local-agent", "sidecar", "recovery", "tranche-12"],
        "status": "blocked",
        "related_path": ".dev-tools/runtime/local_agent",
        "metadata": {
            "session_id": session_id,
            "recovery": recovery,
            "evidence_item_ids": evidence_ids,
            "evidence_archive_status": evidence_archive.get("status"),
        },
    })
    journal_uid = journal.get("result", {}).get("entry", {}).get("entry_uid", "")
    trace = _record_run_trace(project_root, config, _trace_payload(
        session_id=session_id,
        prompt=prompt,
        config=config,
        status="error",
        recovery=recovery,
        rounds=rounds,
        touched_paths=touched_paths,
        validation=validation,
        evidence_ids=evidence_ids,
        journal_entry_uid=journal_uid,
        duration_ms=round((time.time() - run_started) * 1000),
        summary=f"Recovery event: {recovery['class']}",
    ))
    session = {
        "session_id": session_id,
        "created_at": _now(),
        "config": asdict(config),
        "prompt": prompt,
        "recovery": recovery,
        "evidence_shelf": evidence_shelf,
        "evidence_archive": evidence_archive,
        "rounds": rounds,
        "validation": validation,
        "checkpoint": {"skipped": True, "reason": "agent recovery event"},
        "journal": journal,
        "trace": trace,
        "halted_reason": halted_reason,
        "approval_required": recovery["class"] == "approval_required",
    }
    if arguments.get("write_session", True) is not False:
        write_json(runtime_paths["sessions"] / f"{session_id}.json", session)
    _append_jsonl(runtime_paths["action_journal"], {
        "ts": _now(),
        "action": "agent_recovery",
        "session_id": session_id,
        "summary": prompt[:160],
        "halted_reason": halted_reason,
        "recovery_class": recovery["class"],
    })
    return tool_result(
        FILE_METADATA["tool_name"],
        arguments,
        {
            "session_id": session_id,
            "project_root": str(project_root),
            "runtime": _public_runtime(runtime_paths, project_root),
            "round_count": len(rounds),
            "touched_paths": sorted(set(touched_paths)),
            "validation": validation,
            "recovery": recovery,
            "evidence_shelf": evidence_shelf.get("result", {}),
            "evidence_archive": evidence_archive.get("result", evidence_archive),
            "trace": trace.get("result", trace),
            "journal_entry_uid": journal_uid,
            "halted_reason": halted_reason,
            "approval_required": recovery["class"] == "approval_required",
            "final_text": "",
        },
        status="approval_required" if recovery["class"] == "approval_required" else "error",
    )


def _run_agent(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    config = _config(arguments, project_root)
    prompt = str(arguments.get("prompt", "")).strip()
    if not prompt:
        return tool_error(FILE_METADATA["tool_name"], arguments, "prompt is required for action=run")

    runtime_paths = _ensure_runtime(project_root)
    run_started = time.time()
    session_id = config.session_id or f"{_stamp()}_{uuid.uuid4().hex[:8]}"
    heartbeat = _heartbeat(runtime_paths, config, session_id, "start", "Agent run started")
    planning = _planning_workspace(project_root, runtime_paths, config, session_id)
    mock_responses = arguments.get("mock_ollama_responses")
    if not isinstance(mock_responses, list):
        mock_responses = []
    mock_responses = [str(item) for item in mock_responses]
    mock_failure = str(arguments.get("mock_ollama_failure", "")).strip()
    if config.preflight and not mock_responses and not mock_failure:
        _heartbeat(runtime_paths, config, session_id, "preflight", "Checking model readiness")
        readiness = _model_readiness(config)
        if not readiness.get("ready"):
            recovery = _recovery_from_class(
                str(readiness.get("recovery_class", "model_request_failed")),
                str(readiness.get("message", "model readiness failed")),
                config,
                next_actions=[str(item) for item in readiness.get("next_actions", [])],
            )
            rounds = [{
                "round": 0,
                "tool_call_count": 0,
                "results": [],
                "response": "",
                "recovery": recovery,
                "preflight": readiness,
            }]
            return _finish_recovery_event(
                arguments=arguments,
                project_root=project_root,
                runtime_paths=runtime_paths,
                config=config,
                session_id=session_id,
                prompt=prompt,
                run_started=run_started,
                evidence_shelf={"status": "skipped", "result": {"reason": "preflight stopped before shelf load"}},
                rounds=rounds,
                touched_paths=[],
                recovery=recovery,
            )

    bootstrap = run_local_agent_bootstrap({
        "project_root": str(project_root),
        "format": "markdown",
        "include_markdown": True,
        "journal_limit": 5,
        "timeout_seconds": min(config.timeout_seconds, 10),
        "include_evidence_shelf": config.use_evidence_shelf,
        "evidence_session_id": session_id,
        "evidence_limit": 12,
    })
    _heartbeat(runtime_paths, config, session_id, "bootstrap", "Loaded bootstrap, boundary, setup, and evidence context")
    boundary = run_workspace_boundary_audit({"project_root": str(project_root), "max_depth": 2})
    setup = run_project_setup({"project_root": str(project_root), "action": "audit"})

    evidence_shelf = run_session_evidence_store({
        "project_root": str(project_root),
        "action": "shelf",
        "session_id": session_id,
        "limit": 12,
    }) if config.use_evidence_shelf else {"status": "skipped", "result": {"reason": "use_evidence_shelf=false"}}
    evidence_summary = _evidence_shelf_text(evidence_shelf)
    bootstrap_summary = str(bootstrap.get("result", {}).get("rendered", ""))[:3000]
    messages = [
        {"role": "system", "content": _system_prompt(config, bootstrap_summary, evidence_summary)},
        {"role": "user", "content": prompt},
    ]

    touched_paths: list[str] = []
    rounds: list[dict[str, Any]] = []
    parse_repair_events: list[dict[str, Any]] = []
    final_text = ""
    approval_required = False
    halted_reason = ""
    recovery: dict[str, Any] = {}

    for round_index in range(config.max_tool_rounds):
        try:
            _heartbeat(runtime_paths, config, session_id, "model_round", f"Requesting model round {round_index + 1}")
            response = _sanitize_model_text(_model_response(
                config=config,
                messages=messages,
                model=config.planner_model if round_index == 0 else config.response_model,
                mock_responses=mock_responses,
                mock_failure=mock_failure,
                round_index=round_index,
            ))
        except Exception as exc:
            recovery = _recovery_from_exception(exc, config)
            rounds.append({
                "round": round_index + 1,
                "tool_call_count": 0,
                "results": [],
                "response": "",
                "recovery": recovery,
            })
            return _finish_recovery_event(
                arguments=arguments,
                project_root=project_root,
                runtime_paths=runtime_paths,
                config=config,
                session_id=session_id,
                prompt=prompt,
                run_started=run_started,
                evidence_shelf=evidence_shelf,
                rounds=rounds,
                touched_paths=touched_paths,
                recovery=recovery,
            )
        final_text = response
        calls = _parse_tool_calls(response)
        round_repair_signals = sorted({
            signal
            for call in calls
            for signal in call.get("repair_signals", [])
            if isinstance(signal, str) and signal
        })
        for call in calls:
            signals = [str(signal) for signal in call.get("repair_signals", []) if str(signal).strip()]
            if signals:
                parse_repair_events.append({
                    "round": round_index + 1,
                    "tool": call.get("tool", ""),
                    "signals": signals,
                })
        _heartbeat(runtime_paths, config, session_id, "tool_round", f"Parsed {len(calls)} tool call(s)")
        round_results: list[dict[str, Any]] = []
        for call in calls:
            result = _execute_tool_call(
                call,
                config=config,
                project_root=project_root,
                runtime_paths=runtime_paths,
                touched_paths=touched_paths,
            )
            round_results.append(result)
            if result.get("status") == "approval_required":
                approval_required = True
                halted_reason = "approval_required"
                recovery = _recovery_from_result(result, config)
                break
            if result.get("status") == "error":
                recovery = _recovery_from_result(result, config)
                halted_reason = recovery["class"]
                break
        rounds.append({
            "round": round_index + 1,
            "tool_call_count": len(calls),
            "parse_repair_signals": round_repair_signals,
            "results": round_results,
            "response": response,
        })
        if approval_required or halted_reason or not calls:
            break
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": _format_tool_results(round_results)})
    else:
        halted_reason = "max_tool_rounds_exhausted"
        recovery = _recovery_from_class("max_rounds_exhausted", "maximum tool rounds exhausted", config)

    validation = _validate_touched(project_root, touched_paths)
    parse_repair_signals = sorted({
        signal
        for event in parse_repair_events
        for signal in event.get("signals", [])
        if isinstance(signal, str) and signal
    })
    validation["parse_repair_signals"] = parse_repair_signals
    evidence_archive = _archive_evidence(
        project_root,
        session_id=session_id,
        prompt=prompt,
        rounds=rounds,
        config=config,
        approval_required=approval_required,
        touched_paths=touched_paths,
        validation=validation,
        final_text=final_text,
        halted_reason=halted_reason,
        recovery=recovery,
        parse_repair_signals=parse_repair_signals,
    )
    _heartbeat(runtime_paths, config, session_id, "evidence", f"Evidence archive status: {evidence_archive.get('status', 'skipped')}")
    checkpoint = _checkpoint(project_root, touched_paths, config, prompt) if not approval_required else {
        "skipped": True,
        "approval_required": True,
        "reason": "turn stopped before checkpoint",
    }
    evidence_payload = evidence_archive.get("result", evidence_archive)
    evidence_ids = _evidence_ids(evidence_archive)
    evidence_status = evidence_archive.get("status", "skipped")
    claim_guardrails = _claim_guardrails(
        final_text,
        touched_paths,
        evidence_ids,
        enforcement=config.claim_enforcement,
    )
    validation["claim_guardrails"] = claim_guardrails
    if not recovery and halted_reason:
        recovery = _recovery_from_class(halted_reason, halted_reason, config)
    if not recovery and not claim_guardrails["passed"]:
        recovery = _recovery_from_class(
            "claim_guardrail_warning",
            "; ".join(claim_guardrails["warnings"]),
            config,
        )
    recovery = _prepare_recovery(recovery, config, arguments)

    journal = run_journal_write({
        "project_root": str(project_root),
        "action": "create",
        "title": "Local sidecar agent turn",
        "body": (
            f"Prompt: {prompt}\n\n"
            f"Touched paths: {', '.join(sorted(set(touched_paths))) or 'none'}\n\n"
            f"Evidence archive: {evidence_status}"
            f"{' (' + ', '.join(evidence_ids) + ')' if evidence_ids else ''}\n\n"
            f"Halted: {halted_reason or 'no'}"
        ),
        "kind": "agent-turn",
        "source": "local_sidecar_agent",
        "author": "local_sidecar_agent",
        "tags": ["local-agent", "sidecar", "evidence", "tranche-9", "tranche-11", "tranche-12"],
        "status": "active" if not approval_required else "blocked",
        "related_path": ".dev-tools/runtime/local_agent",
        "metadata": {
            "session_id": session_id,
            "halted_reason": halted_reason,
            "evidence_archive_status": evidence_status,
            "evidence_item_ids": evidence_ids,
            "evidence_archive": evidence_payload,
            "recovery": recovery,
            "claim_guardrails": claim_guardrails,
            "parse_repair_signals": parse_repair_signals,
            "parse_repair_events": parse_repair_events,
            "heartbeat": heartbeat,
            "planning_workspace": planning,
        },
    })
    journal_uid = journal.get("result", {}).get("entry", {}).get("entry_uid", "")
    result_status = "approval_required" if approval_required else ("error" if halted_reason else "ok")
    trace = _record_run_trace(project_root, config, _trace_payload(
        session_id=session_id,
        prompt=prompt,
        config=config,
        status=result_status,
        recovery=recovery,
        rounds=rounds,
        touched_paths=touched_paths,
        validation=validation,
        evidence_ids=evidence_ids,
        journal_entry_uid=journal_uid,
        duration_ms=round((time.time() - run_started) * 1000),
        summary=f"Local sidecar agent run: {result_status}",
    ))

    session = {
        "session_id": session_id,
        "created_at": _now(),
        "config": asdict(config),
        "prompt": prompt,
        "bootstrap_status": bootstrap.get("status"),
        "boundary_status": boundary.get("status"),
        "setup_status": setup.get("status"),
        "evidence_shelf": evidence_shelf,
        "evidence_archive": evidence_archive,
        "rounds": rounds,
        "validation": validation,
        "checkpoint": checkpoint,
        "journal": journal,
        "trace": trace,
        "halted_reason": halted_reason,
        "approval_required": approval_required,
        "heartbeat": heartbeat,
        "planning_workspace": planning,
    }
    if arguments.get("write_session", True) is not False:
        write_json(runtime_paths["sessions"] / f"{session_id}.json", session)
    _append_jsonl(runtime_paths["action_journal"], {
        "ts": _now(),
        "action": "agent_turn",
        "session_id": session_id,
        "summary": prompt[:160],
        "touched_paths": sorted(set(touched_paths)),
        "halted_reason": halted_reason,
        "parse_repair_signals": parse_repair_signals,
    })

    return tool_result(
        FILE_METADATA["tool_name"],
        arguments,
        {
            "session_id": session_id,
            "project_root": str(project_root),
            "runtime": _public_runtime(runtime_paths, project_root),
            "heartbeat": heartbeat,
            "planning_workspace": planning,
            "round_count": len(rounds),
            "touched_paths": sorted(set(touched_paths)),
            "validation": validation,
            "parse_repair_signals": parse_repair_signals,
            "parse_repair_events": parse_repair_events,
            "recovery": recovery,
            "evidence_shelf": evidence_shelf.get("result", {}),
            "evidence_archive": evidence_archive.get("result", evidence_archive),
            "trace": trace.get("result", trace),
            "checkpoint": checkpoint,
            "journal_entry_uid": journal_uid,
            "halted_reason": halted_reason,
            "approval_required": approval_required,
            "final_text": final_text,
        },
        status=result_status,
    )


def run(arguments: dict[str, Any]) -> dict[str, Any]:
    action = str(arguments.get("action", "run")).strip().lower()
    if action not in {"status", "models", "preflight", "run"}:
        return tool_error(FILE_METADATA["tool_name"], arguments, f"unsupported action: {action}")
    try:
        project_root = resolve_project_root(arguments.get("project_root"))
    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    config = _config(arguments, project_root)
    if action == "status":
        paths = _runtime_paths(project_root)
        return tool_result(FILE_METADATA["tool_name"], arguments, {
            "project_root": str(project_root),
            "runtime": _public_runtime(paths, project_root),
            "runtime_exists": paths["base"].exists(),
            "allowed_tools": config.allowed_tools,
            "config": asdict(config),
        })
    if action == "models":
        return tool_result(FILE_METADATA["tool_name"], arguments, _scan_models(config.ollama_base_url, min(config.timeout_seconds, 30)))
    if action == "preflight":
        return tool_result(FILE_METADATA["tool_name"], arguments, _model_readiness(config))
    return _run_agent(arguments, project_root)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
