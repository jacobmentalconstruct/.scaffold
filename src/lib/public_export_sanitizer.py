"""
FILE: src/lib/public_export_sanitizer.py
ROLE: T10.7 derived public-share bundle + sanitizer.
WHAT IT DOES: Builds a deterministic non-authoritative public-safe export
              bundle from selected sidecar surfaces, rewrites machine-local
              path leaks into stable placeholders, and audits selected tracked
              shareable surfaces for unsafe absolute-path leakage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.lib.common import now_iso, public_path, safe_json_dumps
from src.lib.doc_registry import doc_path


SANITIZER_VERSION = "1.0.0"
EXPORT_KIND = "public_share_bundle"
EXPORT_STATUS = "derived_non_authoritative_sanitized"

WINDOWS_ABS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"'`<>|]+")
POSIX_HOME_PATH_RE = re.compile(r"/(?:Users|home)/[^\s\"'`<>|]+")


@dataclass
class SanitizationContext:
    sidecar_root: Path
    project_root: Path
    user_home: Path | None
    placeholder_map: dict[str, str] = field(default_factory=dict)
    placeholder_counts: dict[str, int] = field(default_factory=dict)
    replacements: list[dict[str, str]] = field(default_factory=list)

    def register(self, category: str, raw: str, *, preferred: str = "") -> str:
        existing = self.placeholder_map.get(raw)
        if existing:
            return existing
        if preferred:
            placeholder = preferred
        else:
            index = self.placeholder_counts.get(category, 0) + 1
            self.placeholder_counts[category] = index
            placeholder = f"<{category}_{index:02d}>"
        self.placeholder_map[raw] = placeholder
        self.replacements.append({"category": category, "from": raw, "to": placeholder})
        return placeholder


def build_public_share_bundle(state) -> dict[str, Any]:
    ctx = SanitizationContext(
        sidecar_root=Path(state.sidecar_root).resolve(),
        project_root=Path(state.project_root).resolve(),
        user_home=_safe_home_dir(),
    )
    payload = {
        "handoff": _handoff_payload(state),
        "agent_bootstrap_summary": _agent_bootstrap_summary(state),
        "latest_parked_tranche": _latest_parked_tranche_payload(state),
        "installed_project_proof_summary": _installed_project_proof_summary(state),
        "continuity": _continuity_summary(state),
        "bundle_notice": {
            "private_truth_remains_authoritative": True,
            "public_bundle_is_non_authoritative": True,
            "sanitized_for_external_sharing": True,
            "note": (
                "This bundle is derived for external sharing and research use. "
                "Authoritative sidecar truth remains private and unchanged."
            ),
        },
    }
    sanitized_payload = sanitize_value(payload, ctx)
    remaining = find_unsafe_strings(sanitized_payload)
    report = {
        "status": "safe_to_share" if not remaining else "unsafe_remaining",
        "sanitizer_version": SANITIZER_VERSION,
        "generated_at": now_iso(),
        "replacement_count": len(ctx.replacements),
        "placeholder_counts": dict(ctx.placeholder_counts),
        "replacements": list(ctx.replacements),
        "unsafe_remaining_count": len(remaining),
        "unsafe_remaining_samples": remaining[:10],
        "private_truth_preserved": True,
        "requires_authoritative_replay": False,
    }
    return {
        "bundle_type": EXPORT_KIND,
        "status": EXPORT_STATUS,
        "sanitized_for_external_sharing": True,
        "generated_at": now_iso(),
        "sanitizer_version": SANITIZER_VERSION,
        "source_surfaces": [
            "projection://handoff",
            "projection://agent_bootstrap",
            "_docs/continuity/LATEST_PARKED_TRANCHE.json",
            "installed_project_proof.summary()",
            "_docs/continuity/WE_ARE_HERE_NOW.md",
            "README.md",
        ],
        "payload": sanitized_payload,
        "sanitization_report": report,
    }


def write_public_share_bundle(state) -> dict[str, Any]:
    bundle = build_public_share_bundle(state)
    stamp = now_iso().replace(":", "").replace("-", "").replace(".", "")
    export_dir = Path(state.sidecar_root) / "exports" / "public_share"
    export_dir.mkdir(parents=True, exist_ok=True)
    json_path = export_dir / f"public_share_bundle_{stamp}.json"
    md_path = export_dir / f"public_share_bundle_{stamp}.md"
    report_path = export_dir / f"public_share_bundle_{stamp}_report.json"
    json_path.write_text(safe_json_dumps(bundle, indent=2), encoding="utf-8")
    md_path.write_text(_bundle_to_markdown(bundle), encoding="utf-8")
    report_path.write_text(
        safe_json_dumps(bundle.get("sanitization_report", {}), indent=2),
        encoding="utf-8",
    )
    return {
        "status": "ok",
        "bundle_kind": EXPORT_KIND,
        "bundle_status": bundle.get("status"),
        "safe_to_share": bundle.get("sanitization_report", {}).get("unsafe_remaining_count", 1) == 0,
        "json_path": public_path(json_path, state.sidecar_root, "."),
        "markdown_path": public_path(md_path, state.sidecar_root, "."),
        "report_path": public_path(report_path, state.sidecar_root, "."),
        "replacement_count": bundle.get("sanitization_report", {}).get("replacement_count", 0),
        "unsafe_remaining_count": bundle.get("sanitization_report", {}).get("unsafe_remaining_count", 0),
    }


def audit_public_share_surfaces(state) -> dict[str, Any]:
    tracked_files = _tracked_shareable_surfaces(state)
    tracked_hits: list[dict[str, Any]] = []
    for path in tracked_files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        matches = _unsafe_matches_in_text(text)
        if matches:
            tracked_hits.append(
                {
                    "path": public_path(path, state.sidecar_root, "."),
                    "match_count": len(matches),
                    "samples": matches[:5],
                }
            )
    bundle = build_public_share_bundle(state)
    bundle_hits = find_unsafe_strings(bundle)
    return {
        "status": "ok" if not tracked_hits and not bundle_hits else "error",
        "tracked_surface_hits": tracked_hits,
        "bundle_unsafe_hits": bundle_hits[:20],
        "bundle_report": bundle.get("sanitization_report", {}),
        "tracked_surface_count": len(tracked_files),
        "checked_surfaces": [public_path(path, state.sidecar_root, ".") for path in tracked_files],
        "safe_to_share": not tracked_hits and not bundle_hits,
        "note": (
            "This audit covers selected shareable tracked surfaces and the derived public-share bundle. "
            "Authoritative private runtime state may still contain private machine-local truth."
        ),
    }


def sanitize_value(value: Any, ctx: SanitizationContext) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_value(item, ctx) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item, ctx) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, ctx)
    return value


def sanitize_text(text: str, ctx: SanitizationContext) -> str:
    sanitized = text
    sanitized = WINDOWS_ABS_PATH_RE.sub(lambda m: _sanitize_abs_path(m.group(0), ctx), sanitized)
    sanitized = POSIX_HOME_PATH_RE.sub(lambda m: _sanitize_abs_path(m.group(0), ctx), sanitized)
    return sanitized


def find_unsafe_strings(value: Any) -> list[str]:
    hits: list[str] = []

    def _walk(item: Any) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                _walk(nested)
            return
        if isinstance(item, list):
            for nested in item:
                _walk(nested)
            return
        if isinstance(item, str):
            hits.extend(_unsafe_matches_in_text(item))

    _walk(value)
    return hits


def _sanitize_abs_path(raw: str, ctx: SanitizationContext) -> str:
    normalized = raw.replace("\\", "/")
    sidecar_root = ctx.sidecar_root.as_posix().rstrip("/")
    project_root = ctx.project_root.as_posix().rstrip("/")
    user_home = ctx.user_home.as_posix().rstrip("/") if ctx.user_home else ""

    if normalized.startswith(sidecar_root):
        suffix = normalized[len(sidecar_root):].lstrip("/")
        return f"<sidecar_root>/{suffix}" if suffix else "<sidecar_root>"
    if normalized.startswith(project_root):
        suffix = normalized[len(project_root):].lstrip("/")
        return f"<project_root>/{suffix}" if suffix else "<project_root>"
    if user_home and normalized.startswith(user_home):
        suffix = normalized[len(user_home):].lstrip("/")
        placeholder = ctx.register("user_home", raw, preferred="<user_home>")
        return f"{placeholder}/{suffix}" if suffix else placeholder
    placeholder = ctx.register("absolute_path", raw)
    return placeholder


def _handoff_payload(state) -> dict[str, Any]:
    projection = state.projections.read("handoff")
    row = projection.rows[0] if projection.rows else {}
    return {
        "latest_closed_tranche": _loads_json(row.get("latest_closed_tranche_json"), {}),
        "active_horizon": _loads_json(row.get("active_horizon_json"), {}),
        "open_questions": _loads_json(row.get("open_questions_json"), []),
        "reading_order": _loads_json(row.get("reading_order_json"), []),
        "verification_commands": _loads_json(row.get("verification_commands_json"), []),
    }


def _agent_bootstrap_summary(state) -> dict[str, Any]:
    projection = state.projections.read("agent_bootstrap")
    row = projection.rows[0] if projection.rows else {}
    tool_index = _loads_json(row.get("tool_index_json"), [])
    return {
        "current_tranche_scope": _loads_json(row.get("current_tranche_scope_json"), {}),
        "next_planned_steps": _loads_json(row.get("next_planned_steps_json"), []),
        "constraint_map_summary": _loads_json(row.get("constraint_map_summary_json"), {}),
        "tool_names": [str(item.get("tool_name") or item.get("name") or "") for item in tool_index][:20],
        "tool_count": len(tool_index),
        "source_plan_hash": str(row.get("source_plan_hash") or ""),
    }


def _latest_parked_tranche_payload(state) -> dict[str, Any]:
    path = doc_path(Path(state.sidecar_root), "latest_parked_tranche_json")
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _installed_project_proof_summary(state) -> dict[str, Any]:
    summary = state.installed_project_proof_manager.summary(limit=3)
    latest = summary.get("latest_proof") or {}
    return {
        "fixture_summary": summary.get("fixture_summary", {}),
        "latest_proof": {
            "proof_run_id": latest.get("proof_run_id", ""),
            "fixture_id": latest.get("fixture_id", ""),
            "fixture_version": latest.get("fixture_version", ""),
            "host_root": latest.get("host_root", ""),
            "installed_sidecar_root": latest.get("installed_sidecar_root", ""),
            "status": latest.get("status", ""),
            "approval_request_id": latest.get("approval_request_id", ""),
            "approval_grant_id": latest.get("approval_grant_id", ""),
            "handoff_packet_ref": latest.get("handoff_packet_ref", ""),
            "supersession_status": latest.get("supersession_status", ""),
            "started_at": latest.get("started_at", ""),
            "ended_at": latest.get("ended_at", ""),
            "verification_summary": latest.get("verification_summary", {}),
            "proposal_summary": latest.get("proposal_summary", {}),
        },
        "handoff_status": summary.get("handoff_status", {}),
        "supersession_status": summary.get("supersession_status", {}),
    }


def _continuity_summary(state) -> dict[str, Any]:
    sidecar_root = Path(state.sidecar_root)
    where_now = doc_path(sidecar_root, "where_we_are_now")
    readme = sidecar_root / "README.md"
    return {
        "where_we_are_now_excerpt": _first_nonempty_lines(where_now, count=18),
        "readme_status_excerpt": _first_nonempty_lines(readme, count=10),
    }


def _first_nonempty_lines(path: Path, *, count: int) -> list[str]:
    if not path.is_file():
        return []
    lines = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[:count]


def _tracked_shareable_surfaces(state) -> list[Path]:
    sidecar_root = Path(state.sidecar_root)
    return [
        sidecar_root / "README.md",
        doc_path(sidecar_root, "onboarding"),
        doc_path(sidecar_root, "where_we_are_now"),
        doc_path(sidecar_root, "implementation_roadmap"),
        doc_path(sidecar_root, "target_state"),
        doc_path(sidecar_root, "architecture"),
        doc_path(sidecar_root, "latest_parked_tranche_json"),
        doc_path(sidecar_root, "latest_parked_tranche_md"),
        sidecar_root / "_docs" / "history" / "transitions" / "BRANCH_02_TRANSITION_NOTE_2026-05-12.md",
    ]


def _unsafe_matches_in_text(text: str) -> list[str]:
    hits = WINDOWS_ABS_PATH_RE.findall(text)
    hits.extend(POSIX_HOME_PATH_RE.findall(text))
    return hits


def _bundle_to_markdown(bundle: dict[str, Any]) -> str:
    report = bundle.get("sanitization_report", {})
    payload = bundle.get("payload", {})
    lines = [
        "# Public Share Bundle",
        "",
        "> Derived, non-authoritative, sanitized for external sharing.",
        "",
        f"- generated_at: `{bundle.get('generated_at', '')}`",
        f"- sanitizer_version: `{bundle.get('sanitizer_version', '')}`",
        f"- replacement_count: `{report.get('replacement_count', 0)}`",
        f"- unsafe_remaining_count: `{report.get('unsafe_remaining_count', 0)}`",
        "",
        "## Included Surfaces",
        "",
    ]
    for item in bundle.get("source_surfaces", []):
        lines.append(f"- `{item}`")
    lines.extend(
        [
            "",
            "## Latest Parked Tranche",
            "",
            "```json",
            safe_json_dumps(payload.get("latest_parked_tranche", {}), indent=2),
            "```",
            "",
            "## Handoff Summary",
            "",
            "```json",
            safe_json_dumps(payload.get("handoff", {}), indent=2),
            "```",
            "",
            "## Sanitization Report",
            "",
            "```json",
            safe_json_dumps(report, indent=2),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _loads_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _safe_home_dir() -> Path | None:
    try:
        return Path.home().resolve()
    except Exception:
        return None
