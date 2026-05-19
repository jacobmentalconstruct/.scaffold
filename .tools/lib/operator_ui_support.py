"""Support helpers for the local agent operator UI."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


WINDOWS_ABSOLUTE_RE = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/](?![\\/nrtbfav0])(?:[^\\/\s\"'<>|]+[\\/])*[^\\/\s\"'<>|]*"
)
GENERIC_PRIVATE_PATH_MARKERS = ("\\" + "Users" + "\\", "/" + "Users" + "/")
MUTATING_CATEGORIES = {"write", "editing", "scaffold", "operations", "cleanup", "agent-runtime"}
MUTATING_TOOLS = {
    "text_file_writer",
    "directory_scaffold",
    "file_move_guarded",
    "file_delete_guarded",
    "git_private_workspace",
    "journal_write",
    "journal_actions",
    "journal_scaffold",
    "journal_pack",
    "journal_snapshot",
    "sidecar_install",
    "project_setup",
    "dev_server_manager",
    "docker_ops",
    "k8s_ops",
    "runtime_artifact_cleaner",
    "local_sidecar_agent",
    "session_evidence_store",
    "agent_run_trace",
    "teaching_sandbox_harness",
}


def toolbox_root_from(start: str | Path | None = None) -> Path:
    if start is None:
        return Path(__file__).resolve().parents[2]
    path = Path(start).resolve()
    if path.is_file():
        path = path.parent
    for candidate in [path, *path.parents]:
        if (candidate / "tool_manifest.json").is_file() and (candidate / "src").is_dir():
            return candidate
    raise ValueError(f"could not resolve toolbox root from {start}")


def load_tool_manifest(toolbox_root: str | Path) -> dict[str, Any]:
    root = Path(toolbox_root).resolve()
    manifest_path = root / "tool_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
        raise ValueError("tool_manifest.json is missing a tools list")
    return data


def tool_index(toolbox_root: str | Path) -> dict[str, dict[str, Any]]:
    manifest = load_tool_manifest(toolbox_root)
    index: dict[str, dict[str, Any]] = {}
    for item in manifest["tools"]:
        if isinstance(item, dict) and item.get("tool_name") and item.get("script"):
            index[str(item["tool_name"])] = dict(item)
    return index


def is_mutating_tool(tool: dict[str, Any]) -> bool:
    name = str(tool.get("tool_name", ""))
    category = str(tool.get("category", ""))
    return name in MUTATING_TOOLS or category in MUTATING_CATEGORIES


def load_tool_metadata(toolbox_root: str | Path, tool: dict[str, Any]) -> dict[str, Any]:
    module = _load_tool_module(toolbox_root, tool)
    metadata = getattr(module, "FILE_METADATA", None)
    if not isinstance(metadata, dict):
        raise ValueError(f"{tool.get('tool_name')} does not expose FILE_METADATA")
    return metadata


def default_input_from_schema(schema: dict[str, Any] | None, project_root: str | Path | None = None) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return {}
    payload: dict[str, Any] = {}
    for key, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        if key == "project_root" and project_root is not None:
            payload[key] = str(project_root)
        elif "default" in spec:
            payload[key] = spec["default"]
        elif "enum" in spec and isinstance(spec["enum"], list) and spec["enum"]:
            payload[key] = spec["enum"][0]
    return payload


def choose_model(models: list[str], preferred_prefixes: list[str], fallback: str) -> str:
    normalized = [str(model) for model in models if str(model).strip()]
    for prefix in preferred_prefixes:
        for model in normalized:
            if model.lower().startswith(prefix.lower()):
                return model
    return normalized[0] if normalized else fallback


def agent_payload(
    *,
    project_root: str,
    prompt: str,
    ollama_base_url: str,
    planner_model: str,
    response_model: str,
    allowed_tools: list[str],
    timeout_seconds: int,
    max_tool_rounds: int,
    confirm_mutations: bool,
    confirm_checkpoint: bool,
    checkpoint: bool,
    confirm_evidence: bool = False,
    heartbeat: bool = False,
    use_recovery_model: bool = False,
    recovery_model: str = "",
    claim_enforcement: str = "warn",
    planning_workspace: bool = False,
    use_evidence_shelf: bool = True,
    window_turns: int = 8,
    session_id: str = "",
) -> dict[str, Any]:
    payload = {
        "action": "run",
        "project_root": project_root,
        "prompt": prompt,
        "ollama_base_url": ollama_base_url,
        "planner_model": planner_model,
        "response_model": response_model,
        "allowed_tools": allowed_tools,
        "timeout_seconds": timeout_seconds,
        "max_tool_rounds": max_tool_rounds,
        "confirm_mutations": confirm_mutations,
        "confirm_checkpoint": confirm_checkpoint,
        "checkpoint": checkpoint,
        "confirm_evidence": confirm_evidence,
        "heartbeat": heartbeat,
        "use_recovery_model": use_recovery_model,
        "claim_enforcement": claim_enforcement,
        "planning_workspace": planning_workspace,
        "use_evidence_shelf": use_evidence_shelf,
        "window_turns": window_turns,
        "write_session": True,
    }
    if recovery_model:
        payload["recovery_model"] = recovery_model
    if session_id:
        payload["session_id"] = session_id
    return payload


def recovery_decisions(result: dict[str, Any]) -> list[dict[str, Any]]:
    payload = result.get("result", {}) if isinstance(result, dict) else {}
    recovery = payload.get("recovery", {}) if isinstance(payload, dict) else {}
    decisions = recovery.get("decisions", []) if isinstance(recovery, dict) else []
    if isinstance(decisions, list):
        return [dict(item) for item in decisions if isinstance(item, dict) and item.get("id")]
    return []


def apply_recovery_decision(payload: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    updated = dict(payload)
    decision_id = str(decision.get("id", ""))
    patch = decision.get("patch", {})
    if isinstance(patch, dict):
        updated.update(patch)
    if decision_id == "confirm_mutations":
        updated["confirm_mutations"] = True
    elif decision_id == "confirm_evidence":
        updated["confirm_evidence"] = True
    elif decision_id == "confirm_checkpoint":
        updated["confirm_checkpoint"] = True
    elif decision_id == "retry_with_citations":
        updated["claim_enforcement"] = "require_citation"
        prompt = str(updated.get("prompt", "")).strip()
        updated["prompt"] = (
            prompt
            + "\n\nWhen summarizing completed work, cite touched paths or evidence IDs exactly."
        ).strip()
    return updated


def dispatch_tool(toolbox_root: str | Path, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    root = Path(toolbox_root).resolve()
    tools = tool_index(root)
    if tool_name not in tools:
        raise ValueError(f"unknown tool: {tool_name}")
    module = _load_tool_module(root, tools[tool_name])
    run = getattr(module, "run", None)
    if not callable(run):
        raise ValueError(f"{tool_name} does not expose run(arguments)")
    result = run(arguments)
    if not isinstance(result, dict):
        raise ValueError(f"{tool_name} returned a non-dict result")
    return result


def sanitize_path_text(text: str, *, project_root: str | Path | None = None, toolbox_root: str | Path | None = None) -> str:
    output = str(text)
    replacements: list[tuple[Path, str]] = []
    if project_root is not None:
        replacements.append((Path(project_root).resolve(), "<project_root>"))
    if toolbox_root is not None:
        replacements.append((Path(toolbox_root).resolve(), "<toolbox_root>"))
    try:
        replacements.append((Path.home().resolve(), "<home>"))
    except Exception:
        pass
    replacements.sort(key=lambda item: len(str(item[0])), reverse=True)
    for path, label in replacements:
        raw = str(path)
        output = output.replace(raw, label)
        output = output.replace(raw.replace("\\", "/"), label)
    return WINDOWS_ABSOLUTE_RE.sub("<absolute_path>", output)


def sanitize_for_display(value: Any, *, project_root: str | Path | None = None, toolbox_root: str | Path | None = None) -> Any:
    if isinstance(value, str):
        return sanitize_path_text(value, project_root=project_root, toolbox_root=toolbox_root)
    if isinstance(value, list):
        return [sanitize_for_display(item, project_root=project_root, toolbox_root=toolbox_root) for item in value]
    if isinstance(value, dict):
        return {
            key: sanitize_for_display(item, project_root=project_root, toolbox_root=toolbox_root)
            for key, item in value.items()
        }
    return value


def format_json(value: Any, *, project_root: str | Path | None = None, toolbox_root: str | Path | None = None) -> str:
    sanitized = sanitize_for_display(value, project_root=project_root, toolbox_root=toolbox_root)
    return json.dumps(sanitized, indent=2, sort_keys=False)


def agent_recovery_status(result: dict[str, Any]) -> str:
    status = str(result.get("status", "unknown"))
    payload = result.get("result", {}) if isinstance(result, dict) else {}
    if not isinstance(payload, dict):
        return f"Agent finished: {status}"
    recovery = payload.get("recovery", {})
    if not isinstance(recovery, dict) or not recovery.get("class"):
        if status == "approval_required":
            return "Approval required. Review output, then rerun with the needed confirmation toggle."
        return f"Agent finished: {status}"
    recovery_class = str(recovery.get("class", "unknown"))
    actions = recovery.get("next_actions", [])
    action_text = ", ".join(str(item).replace("_", " ") for item in actions[:3]) if isinstance(actions, list) else ""
    if recovery_class == "request_timeout":
        prefix = "Timed out."
    elif recovery_class == "ollama_unreachable":
        prefix = "Ollama unreachable."
    elif recovery_class == "model_missing":
        prefix = "Model missing."
    elif recovery_class == "approval_required":
        prefix = "Approval required."
    elif recovery_class == "max_rounds_exhausted":
        prefix = "Max rounds reached."
    elif recovery_class == "malformed_tool_call":
        prefix = "Malformed tool call."
    elif recovery_class == "tool_schema_error":
        prefix = "Tool schema error."
    elif recovery_class == "tool_runtime_error":
        prefix = "Tool failed."
    elif recovery_class == "claim_guardrail_warning":
        prefix = "Claim guardrail warning."
    else:
        prefix = f"Recovery: {recovery_class}."
    return f"{prefix} Next: {action_text}." if action_text else prefix


def scan_privacy_leaks(paths: list[Path], *, allow_names: set[str] | None = None) -> list[dict[str, Any]]:
    allow = allow_names or {"LICENSE.md"}
    private_fragments = _private_fragments()
    findings: list[dict[str, Any]] = []
    for path in paths:
        if path.name in allow or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if WINDOWS_ABSOLUTE_RE.search(line) or any(fragment and fragment in line for fragment in private_fragments):
                findings.append({
                    "path": str(path),
                    "line": line_number,
                    "text": sanitize_path_text(line),
                })
    return findings


def _private_fragments() -> tuple[str, ...]:
    fragments = set(GENERIC_PRIVATE_PATH_MARKERS)
    try:
        home = Path.home().resolve()
        if home.name:
            fragments.add(home.name)
    except Exception:
        pass
    try:
        cwd = Path.cwd().resolve()
        for part in cwd.parts:
            if part.startswith("_") and len(part) > 3:
                fragments.add(part)
    except Exception:
        pass
    return tuple(sorted(fragments))


def _load_tool_module(toolbox_root: str | Path, tool: dict[str, Any]):
    root = Path(toolbox_root).resolve()
    script = (root / str(tool["script"])).resolve()
    if root not in [script, *script.parents]:
        raise ValueError(f"tool script escapes toolbox root: {script}")
    if str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    module_name = f"_operator_ui_{tool['tool_name']}_{abs(hash(str(script)))}"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load tool module: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    old_cwd = Path.cwd()
    try:
        os.chdir(root)
        spec.loader.exec_module(module)
    finally:
        os.chdir(old_cwd)
    return module
