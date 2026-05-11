"""
FILE: src/lib/common.py
ROLE: Small shared helpers used across the sidecar.
WHAT IT DOES: ID generation, time helpers, hash helpers, path resolvers,
              tool result envelope, JSON helpers. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ENVELOPE_VERSION_CURRENT = "1.0.0"

STANDARD_TOOL_RESULT_KEYS = ("status", "tool", "input", "result")

RELATION_TYPES_CLOSED_SET = (
    "belongs_to",
    "observes",
    "derives_from",
    "supersedes",
    "cites",
    "modifies",
    "validates",
    "requires",
    "emitted_by",
    "approved_by",
    "failed_due_to",
    "produces",
)

AUTHORITY_LEVELS = (
    "Observe",
    "Propose",
    "Sandbox Execute",
    "Apply",
    "Export",
)

# Authority level ordering for comparisons.
_AUTHORITY_RANK = {level: i for i, level in enumerate(AUTHORITY_LEVELS)}


def authority_at_least(actual: str, required: str) -> bool:
    """True if actual authority is >= required."""
    return _AUTHORITY_RANK.get(actual, -1) >= _AUTHORITY_RANK.get(required, 999)


def now_iso() -> str:
    """ISO 8601 UTC timestamp with millisecond precision and Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gen_id(prefix: str = "") -> str:
    """Sortable unique id: <prefix><time_ns_hex>_<8 random hex>."""
    ts = f"{time.time_ns():016x}"
    rand = secrets.token_hex(4)
    return f"{prefix}{ts}_{rand}"


def gen_event_id() -> str:
    return gen_id("evt_")


def gen_envelope_id() -> str:
    return gen_id("obj_")


def gen_correlation_id() -> str:
    return gen_id("cor_")


def gen_relation_id(subject_id: str, predicate: str, object_id: str, emitted_by: str) -> str:
    """Deterministic relation id: SHA-256 of the tuple."""
    payload = f"{subject_id}|{predicate}|{object_id}|{emitted_by}".encode("utf-8")
    return "rel_" + sha256_hex(payload)[:24]


def gen_constraint_uid(section: str, title: str) -> str:
    """Deterministic constraint uid from its section and title."""
    payload = f"{section}|{title}".encode("utf-8")
    return "con_" + sha256_hex(payload)[:16]


class _SidecarJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Path):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if is_dataclass(o):
            return asdict(o)
        if isinstance(o, set):
            return sorted(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", errors="replace")
        return super().default(o)


def safe_json_dumps(obj: Any, indent: int | None = None) -> str:
    return json.dumps(obj, cls=_SidecarJSONEncoder, indent=indent, sort_keys=False)


def safe_json_loads(text: str) -> Any:
    return json.loads(text)


def tool_result(status: str, tool: str, input_arg: dict, result: Any) -> dict:
    return {
        "status": status,
        "tool": tool,
        "input": input_arg,
        "result": result,
    }


def resolve_paths(sidecar_root: Path) -> SimpleNamespace:
    """Convenience namespace of well-known sidecar subfolder paths."""
    sidecar_root = Path(sidecar_root)
    return SimpleNamespace(
        sidecar_root=sidecar_root,
        config=sidecar_root / "config",
        contracts=sidecar_root / "contracts",
        data=sidecar_root / "data",
        logs=sidecar_root / "logs",
        cache=sidecar_root / "cache",
        exports=sidecar_root / "exports",
        workspaces=sidecar_root / "workspaces",
        snapshots=sidecar_root / "snapshots",
        docs=sidecar_root / "_docs",
        src=sidecar_root / "src",
        contract_file=sidecar_root / "contracts" / "builder_constrant_contract.md",
        db_file=sidecar_root / "data" / "sidecar.db",
    )


def under(root: Path, path: Path) -> bool:
    """True if path is strictly inside root (no escape via ..)."""
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def detect_sidecar_root(start: Path | None = None) -> Path:
    """Walk up from start (default: this file) to find the sidecar root."""
    here = Path(start) if start else Path(__file__).resolve()
    for candidate in [here] + list(here.parents):
        if candidate.name == ".scaffold" or (candidate / "contracts" / "builder_constrant_contract.md").is_file():
            return candidate
    raise RuntimeError(f"could not detect sidecar root from {here}")
