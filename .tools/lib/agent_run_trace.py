"""Project-scoped local-agent run trace store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.session_evidence_store import sanitize_text


SCHEMA_VERSION = "1.0.0"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def trace_root(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".dev-tools" / "runtime" / "local_agent" / "run_trace"


def trace_db_path(project_root: str | Path) -> Path:
    return trace_root(project_root) / "run_trace.sqlite3"


def init_store(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = trace_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        _create_schema(conn, root)
    return status(root)


def status(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = trace_db_path(root)
    if not db_path.exists():
        return {
            "exists": False,
            "schema_version": "",
            "db_path": _relative(db_path, root),
            "trace_count": 0,
            "latest_run_id": "",
        }
    with _connect(db_path) as conn:
        schema_version = _meta(conn, "schema_version") or ""
        trace_count = conn.execute("SELECT COUNT(*) FROM agent_run_traces").fetchone()[0]
        latest = conn.execute("SELECT run_uid FROM agent_run_traces ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "exists": True,
        "schema_version": schema_version,
        "db_path": _relative(db_path, root),
        "trace_count": trace_count,
        "latest_run_id": latest["run_uid"] if latest else "",
    }


def append_trace(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = trace_db_path(root)
    if not db_path.exists():
        init_store(root)
    timestamp = now_stamp()
    body_json = json.dumps(payload.get("trace", payload), sort_keys=True, default=str)
    body_hash = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    with _connect(db_path) as conn:
        _create_schema(conn, root)
        cursor = conn.execute(
            """
            INSERT INTO agent_run_traces(
                run_uid, session_id, status, recovery_class, recovery_message,
                prompt_summary, selected_models_json, allowed_tools_json,
                tool_calls_json, tool_results_json, approvals_json,
                touched_paths_json, evidence_ids_json, verification_json,
                journal_entry_uid, operator_outcome, duration_ms,
                summary, body_hash, body_json, created_at, updated_at
            ) VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("session_id", "")),
                str(payload.get("status", "unknown")),
                str(payload.get("recovery_class", "")),
                str(payload.get("recovery_message", "")),
                _summary(payload.get("prompt", payload.get("summary", ""))),
                json.dumps(payload.get("selected_models", {}), sort_keys=True),
                json.dumps(payload.get("allowed_tools", []), sort_keys=True),
                json.dumps(payload.get("tool_calls", []), sort_keys=True),
                json.dumps(payload.get("tool_results", []), sort_keys=True),
                json.dumps(payload.get("approvals", {}), sort_keys=True),
                json.dumps(payload.get("touched_paths", []), sort_keys=True),
                json.dumps(payload.get("evidence_ids", []), sort_keys=True),
                json.dumps(payload.get("verification", {}), sort_keys=True),
                str(payload.get("journal_entry_uid", "")),
                str(payload.get("operator_outcome", "")),
                _optional_int(payload.get("duration_ms"), 0) or 0,
                _summary(payload.get("summary", payload.get("prompt", ""))),
                body_hash,
                body_json,
                timestamp,
                timestamp,
            ),
        )
        run_uid = str(payload.get("run_id", "")).strip() or f"R{int(cursor.lastrowid):06d}"
        conn.execute("UPDATE agent_run_traces SET run_uid = ? WHERE id = ?", (run_uid, cursor.lastrowid))
        trace = _get_trace(conn, run_uid)
    return _display_trace(trace, root, include_body=False)


def query_traces(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = trace_db_path(root)
    if not db_path.exists():
        return {"matches": [], "match_count": 0}
    query = str(payload.get("query", "")).strip()
    session_id = str(payload.get("session_id", "")).strip()
    recovery_class = str(payload.get("recovery_class", "")).strip()
    limit = max(1, min(_optional_int(payload.get("limit"), 10) or 10, 100))
    clauses: list[str] = []
    params: list[Any] = []
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if recovery_class:
        clauses.append("recovery_class = ?")
        params.append(recovery_class)
    for term in [item for item in query.split() if item]:
        clauses.append("(prompt_summary LIKE ? OR summary LIKE ? OR body_json LIKE ?)")
        like = f"%{term}%"
        params.extend([like, like, like])
    sql = "SELECT * FROM agent_run_traces"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    matches = [_display_trace(row, root, include_body=False) for row in rows]
    return {"matches": matches, "match_count": len(matches)}


def get_trace(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = trace_db_path(root)
    if not db_path.exists():
        raise ValueError("agent run trace store has not been initialized")
    run_id = str(payload.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("run_id is required")
    mode = str(payload.get("mode", "summary"))
    with _connect(db_path) as conn:
        row = _get_trace(conn, run_id)
    if row is None:
        raise ValueError(f"run trace not found: {run_id}")
    return _display_trace(row, root, include_body=mode == "full")


def export_traces(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    fmt = str(payload.get("format", "markdown")).lower()
    traces = query_traces(root, {"limit": payload.get("limit", 50), "query": payload.get("query", "")})
    export_dir = trace_root(root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path = export_dir / f"agent_run_traces_{file_stamp()}.json"
        path.write_text(json.dumps(traces, indent=2, sort_keys=False), encoding="utf-8")
    else:
        path = export_dir / f"agent_run_traces_{file_stamp()}.md"
        path.write_text(_traces_markdown(traces), encoding="utf-8")
    return {"export_path": _relative(path, root), "format": fmt, "trace_count": traces.get("match_count", 0)}


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection, project_root: Path) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trace_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_run_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uid TEXT UNIQUE NOT NULL,
            session_id TEXT,
            status TEXT NOT NULL,
            recovery_class TEXT,
            recovery_message TEXT,
            prompt_summary TEXT,
            selected_models_json TEXT NOT NULL DEFAULT '{}',
            allowed_tools_json TEXT NOT NULL DEFAULT '[]',
            tool_calls_json TEXT NOT NULL DEFAULT '[]',
            tool_results_json TEXT NOT NULL DEFAULT '[]',
            approvals_json TEXT NOT NULL DEFAULT '{}',
            touched_paths_json TEXT NOT NULL DEFAULT '[]',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            verification_json TEXT NOT NULL DEFAULT '{}',
            journal_entry_uid TEXT,
            operator_outcome TEXT,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            summary TEXT,
            body_hash TEXT NOT NULL,
            body_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_run_traces_session ON agent_run_traces(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_agent_run_traces_recovery ON agent_run_traces(recovery_class, id);
        """
    )
    timestamp = now_stamp()
    conn.execute("INSERT OR REPLACE INTO trace_meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    conn.execute("INSERT OR REPLACE INTO trace_meta(key, value) VALUES ('project_root_hint', ?)", (_relative(project_root, project_root),))
    conn.execute("INSERT OR IGNORE INTO trace_meta(key, value) VALUES ('initialized_at', ?)", (timestamp,))


def _display_trace(row: sqlite3.Row | None, project_root: Path, *, include_body: bool) -> dict[str, Any]:
    if row is None:
        return {}
    result = {
        "run_id": row["run_uid"],
        "session_id": row["session_id"] or "",
        "status": row["status"],
        "recovery_class": row["recovery_class"] or "",
        "recovery_message": sanitize_text(row["recovery_message"] or "", project_root),
        "prompt_summary": sanitize_text(row["prompt_summary"] or "", project_root),
        "selected_models": _json_value(row["selected_models_json"], {}),
        "allowed_tools": _json_value(row["allowed_tools_json"], []),
        "touched_paths": [sanitize_text(str(item), project_root) for item in _json_value(row["touched_paths_json"], [])],
        "evidence_ids": _json_value(row["evidence_ids_json"], []),
        "journal_entry_uid": row["journal_entry_uid"] or "",
        "duration_ms": row["duration_ms"],
        "summary": sanitize_text(row["summary"] or "", project_root),
        "body_hash": row["body_hash"],
        "created_at": row["created_at"],
    }
    if include_body:
        body = _json_value(row["body_json"], {})
        result["trace"] = _sanitize_json(body, project_root)
    return result


def _get_trace(conn: sqlite3.Connection, run_uid: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agent_run_traces WHERE run_uid = ?", (run_uid,)).fetchone()


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM trace_meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _summary(text: Any, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit] if compact else ""


def _optional_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_value(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _sanitize_json(value: Any, project_root: Path) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_json(item, project_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item, project_root) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, project_root)
    return value


def _traces_markdown(traces: dict[str, Any]) -> str:
    lines = ["# Agent Run Traces", "", f"- Matches: `{traces.get('match_count', 0)}`", "", "## Index", ""]
    matches = traces.get("matches", [])
    if not matches:
        lines.append("- No traces.")
    for item in matches:
        lines.append(
            f"- `{item.get('run_id')}` `{item.get('status')}` "
            f"`{item.get('recovery_class') or 'none'}`: {item.get('summary') or item.get('prompt_summary')}"
        )
    lines.append("")
    return "\n".join(lines)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return sanitize_text(str(path), root)
