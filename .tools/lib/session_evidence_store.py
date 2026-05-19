"""SQLite-backed Bag of Evidence and Evidence Shelf store."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
WINDOWS_ABSOLUTE_RE = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/](?![\\/nrtbfav0])(?:[^\\/\s\"'<>|]+[\\/])*[^\\/\s\"'<>|]*"
)


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def evidence_root(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".dev-tools" / "runtime" / "local_agent" / "evidence"


def evidence_db_path(project_root: str | Path) -> Path:
    return evidence_root(project_root) / "evidence.sqlite3"


def sanitize_text(text: str, project_root: str | Path | None = None) -> str:
    output = str(text)
    replacements: list[tuple[Path, str]] = []
    if project_root is not None:
        replacements.append((Path(project_root).resolve(), "<project_root>"))
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


def init_store(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = evidence_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        _create_schema(conn, root)
    return status(root)


def status(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = evidence_db_path(root)
    if not db_path.exists():
        return {
            "exists": False,
            "schema_version": "",
            "db_path": _relative(db_path, root),
            "session_count": 0,
            "item_count": 0,
            "blob_count": 0,
        }
    with _connect(db_path) as conn:
        schema_version = _meta(conn, "schema_version") or ""
        session_count = conn.execute("SELECT COUNT(*) FROM evidence_shelves").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM evidence_items").fetchone()[0]
        blob_count = conn.execute("SELECT COUNT(*) FROM evidence_blobs").fetchone()[0]
    return {
        "exists": True,
        "schema_version": schema_version,
        "db_path": _relative(db_path, root),
        "session_count": session_count,
        "item_count": item_count,
        "blob_count": blob_count,
    }


def append_item(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = evidence_db_path(root)
    if not db_path.exists():
        init_store(root)
    session_id = _session_id(payload)
    body = str(payload.get("body", payload.get("verbatim_text", "")))
    summary = _summary(payload.get("summary"), body)
    kind = str(payload.get("kind", "evidence"))
    role = str(payload.get("role", payload.get("source", "")))
    source = str(payload.get("source", "agent"))
    sequence_start = _optional_int(payload.get("sequence_start", payload.get("sequence")))
    sequence_end = _optional_int(payload.get("sequence_end", sequence_start))
    importance = max(0, min(_optional_int(payload.get("importance"), 0) or 0, 10))
    tags = _string_list(payload.get("tags"))
    paths = _string_list(payload.get("paths"))
    tools = _string_list(payload.get("tools"))
    search_text = "\n".join([summary, body, " ".join(tags), " ".join(paths), " ".join(tools)])
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    timestamp = now_stamp()
    with _connect(db_path) as conn:
        _create_schema(conn, root)
        conn.execute(
            "INSERT OR IGNORE INTO evidence_blobs(body_hash, body, created_at) VALUES (?, ?, ?)",
            (body_hash, body, timestamp),
        )
        cursor = conn.execute(
            """
            INSERT INTO evidence_items(
                item_uid, session_id, sequence_start, sequence_end, kind, role, source,
                summary, body_hash, searchable_text, tags_json, paths_json, tools_json,
                importance, created_at, updated_at
            ) VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                sequence_start,
                sequence_end,
                kind,
                role,
                source,
                summary,
                body_hash,
                search_text,
                json.dumps(tags),
                json.dumps(paths),
                json.dumps(tools),
                importance,
                timestamp,
                timestamp,
            ),
        )
        item_uid = f"E{int(cursor.lastrowid):06d}"
        conn.execute("UPDATE evidence_items SET item_uid = ? WHERE id = ?", (item_uid, cursor.lastrowid))
        _refresh_shelf(conn, session_id, payload, timestamp)
        item = _get_item(conn, item_uid)
    return _display_item(item, root, include_body=False, redact_paths=True)


def archive_window(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    turns = payload.get("turns", [])
    if not isinstance(turns, list):
        raise ValueError("turns must be a list")
    window_turns = max(0, _optional_int(payload.get("window_turns"), 8) or 0)
    archive_all = payload.get("archive_all") is True
    to_archive = turns if archive_all else turns[: max(0, len(turns) - window_turns)]
    archived: list[dict[str, Any]] = []
    for index, turn in enumerate(to_archive, start=1):
        if not isinstance(turn, dict):
            continue
        body = turn.get("content", turn.get("body", ""))
        archive_payload = {
            "session_id": payload.get("session_id", turn.get("session_id", "default")),
            "sequence_start": turn.get("sequence", turn.get("sequence_start", index)),
            "sequence_end": turn.get("sequence_end", turn.get("sequence", index)),
            "kind": turn.get("kind", "turn"),
            "role": turn.get("role", ""),
            "source": turn.get("source", "local_sidecar_agent"),
            "summary": turn.get("summary", _summary(None, str(body))),
            "body": json.dumps(turn, indent=2, sort_keys=False) if not isinstance(body, str) else str(body),
            "tags": turn.get("tags", payload.get("tags", ["session-evidence"])),
            "paths": turn.get("paths", []),
            "tools": turn.get("tools", []),
            "importance": turn.get("importance", payload.get("importance", 0)),
            "rolling_summary": payload.get("rolling_summary", ""),
            "open_loops": payload.get("open_loops", []),
            "decisions": payload.get("decisions", []),
        }
        archived.append(append_item(root, archive_payload))
    return {
        "session_id": str(payload.get("session_id", "default")),
        "window_turns": window_turns,
        "input_turn_count": len(turns),
        "archived_count": len(archived),
        "archived_items": archived,
    }


def shelf(project_root: str | Path, session_id: str = "default", *, limit: int = 25, redact_paths: bool = True) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = evidence_db_path(root)
    if not db_path.exists():
        return _empty_shelf(session_id)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT rolling_summary, open_loops_json, decisions_json, last_archived_sequence, updated_at FROM evidence_shelves WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        items = _items_for_session(conn, session_id, limit)
        total = conn.execute("SELECT COUNT(*) FROM evidence_items WHERE session_id = ?", (session_id,)).fetchone()[0]
    if row is None:
        result = _empty_shelf(session_id)
    else:
        result = {
            "session_id": session_id,
            "rolling_summary": row["rolling_summary"] or _rollup_from_items(items),
            "open_loops": _json_list(row["open_loops_json"]),
            "decisions": _json_list(row["decisions_json"]),
            "last_archived_sequence": row["last_archived_sequence"],
            "updated_at": row["updated_at"],
            "item_count": total,
            "item_index": [_display_item(item, root, include_body=False, redact_paths=redact_paths) for item in items],
        }
    return result


def search(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = evidence_db_path(root)
    if not db_path.exists():
        return {"query": str(payload.get("query", "")), "matches": [], "match_count": 0}
    query = str(payload.get("query", "")).strip()
    session_id = str(payload.get("session_id", "")).strip()
    limit = max(1, min(_optional_int(payload.get("limit"), 10) or 10, 100))
    redact_paths = payload.get("redact_paths", True) is not False
    with _connect(db_path) as conn:
        terms = [term for term in re.split(r"\s+", query) if term]
        sql = "SELECT * FROM evidence_items"
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        for term in terms:
            clauses.append("(summary LIKE ? OR searchable_text LIKE ? OR tags_json LIKE ? OR paths_json LIKE ? OR tools_json LIKE ?)")
            like = f"%{term}%"
            params.extend([like, like, like, like, like])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY importance DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    matches = [_display_item(row, root, include_body=False, redact_paths=redact_paths) for row in rows]
    return {"query": query, "matches": matches, "match_count": len(matches)}


def get_item(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    db_path = evidence_db_path(root)
    if not db_path.exists():
        raise ValueError("evidence store has not been initialized")
    item_uid = str(payload.get("item_id", payload.get("item_uid", ""))).strip()
    if not item_uid:
        raise ValueError("item_id is required")
    mode = str(payload.get("mode", "summary"))
    redact_paths = payload.get("redact_paths", True) is not False
    with _connect(db_path) as conn:
        item = _get_item(conn, item_uid)
        if item is None:
            raise ValueError(f"evidence item not found: {item_uid}")
        include_body = mode == "verbatim"
        result = _display_item(item, root, include_body=include_body, redact_paths=redact_paths)
        if include_body:
            body = conn.execute("SELECT body FROM evidence_blobs WHERE body_hash = ?", (item["body_hash"],)).fetchone()
            result["verbatim_text"] = _redact(body["body"], root) if redact_paths and body else (body["body"] if body else "")
    return result


def export_store(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root).resolve()
    fmt = str(payload.get("format", "markdown")).lower()
    session_id = str(payload.get("session_id", "default"))
    redact_paths = payload.get("redact_paths", True) is not False
    export_dir = evidence_root(root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    current_shelf = shelf(root, session_id, limit=max(1, _optional_int(payload.get("limit"), 50) or 50), redact_paths=redact_paths)
    if fmt == "json":
        path = export_dir / f"evidence_export_{file_stamp()}.json"
        path.write_text(json.dumps(current_shelf, indent=2, sort_keys=False), encoding="utf-8")
    else:
        path = export_dir / f"evidence_export_{file_stamp()}.md"
        path.write_text(_shelf_markdown(current_shelf), encoding="utf-8")
    return {"export_path": _relative(path, root), "format": fmt, "session_id": session_id, "item_count": current_shelf.get("item_count", 0)}


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection, project_root: Path) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS evidence_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence_blobs (
            body_hash TEXT PRIMARY KEY,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_uid TEXT UNIQUE NOT NULL,
            session_id TEXT NOT NULL,
            sequence_start INTEGER,
            sequence_end INTEGER,
            kind TEXT NOT NULL,
            role TEXT,
            source TEXT,
            summary TEXT NOT NULL,
            body_hash TEXT NOT NULL,
            searchable_text TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            paths_json TEXT NOT NULL DEFAULT '[]',
            tools_json TEXT NOT NULL DEFAULT '[]',
            importance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(body_hash) REFERENCES evidence_blobs(body_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_items_session ON evidence_items(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_evidence_items_search ON evidence_items(summary, searchable_text);
        CREATE TABLE IF NOT EXISTS evidence_shelves (
            session_id TEXT PRIMARY KEY,
            rolling_summary TEXT NOT NULL DEFAULT '',
            open_loops_json TEXT NOT NULL DEFAULT '[]',
            decisions_json TEXT NOT NULL DEFAULT '[]',
            last_archived_sequence INTEGER,
            item_index_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL
        );
        """
    )
    timestamp = now_stamp()
    conn.execute("INSERT OR REPLACE INTO evidence_meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    conn.execute("INSERT OR REPLACE INTO evidence_meta(key, value) VALUES ('project_root_hint', ?)", (_relative(project_root, project_root),))
    conn.execute("INSERT OR IGNORE INTO evidence_meta(key, value) VALUES ('initialized_at', ?)", (timestamp,))


def _refresh_shelf(conn: sqlite3.Connection, session_id: str, payload: dict[str, Any], timestamp: str) -> None:
    existing = conn.execute("SELECT * FROM evidence_shelves WHERE session_id = ?", (session_id,)).fetchone()
    items = _items_for_session(conn, session_id, 100)
    rolling_summary = str(payload.get("rolling_summary") or (existing["rolling_summary"] if existing else "") or _rollup_from_items(items))
    open_loops = _string_list(payload.get("open_loops")) or (_json_list(existing["open_loops_json"]) if existing else [])
    decisions = _string_list(payload.get("decisions")) or (_json_list(existing["decisions_json"]) if existing else [])
    last_sequence = _max_sequence(items)
    item_index = [
        {
            "item_id": item["item_uid"],
            "summary": item["summary"],
            "kind": item["kind"],
            "created_at": item["created_at"],
        }
        for item in items
    ]
    conn.execute(
        """
        INSERT INTO evidence_shelves(session_id, rolling_summary, open_loops_json, decisions_json, last_archived_sequence, item_index_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            rolling_summary = excluded.rolling_summary,
            open_loops_json = excluded.open_loops_json,
            decisions_json = excluded.decisions_json,
            last_archived_sequence = excluded.last_archived_sequence,
            item_index_json = excluded.item_index_json,
            updated_at = excluded.updated_at
        """,
        (session_id, rolling_summary, json.dumps(open_loops), json.dumps(decisions), last_sequence, json.dumps(item_index), timestamp),
    )


def _items_for_session(conn: sqlite3.Connection, session_id: str, limit: int) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM evidence_items WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall())


def _get_item(conn: sqlite3.Connection, item_uid: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM evidence_items WHERE item_uid = ?", (item_uid,)).fetchone()


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM evidence_meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _display_item(item: sqlite3.Row | dict[str, Any] | None, project_root: Path, *, include_body: bool, redact_paths: bool) -> dict[str, Any]:
    if item is None:
        return {}
    result = {
        "item_id": item["item_uid"],
        "session_id": item["session_id"],
        "sequence_start": item["sequence_start"],
        "sequence_end": item["sequence_end"],
        "kind": item["kind"],
        "role": item["role"],
        "source": item["source"],
        "summary": _redact(item["summary"], project_root) if redact_paths else item["summary"],
        "body_hash": item["body_hash"],
        "tags": _json_list(item["tags_json"]),
        "paths": [_redact(path, project_root) if redact_paths else path for path in _json_list(item["paths_json"])],
        "tools": _json_list(item["tools_json"]),
        "importance": item["importance"],
        "created_at": item["created_at"],
    }
    if include_body:
        result["verbatim_text"] = ""
    return result


def _empty_shelf(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "rolling_summary": "",
        "open_loops": [],
        "decisions": [],
        "last_archived_sequence": None,
        "updated_at": "",
        "item_count": 0,
        "item_index": [],
    }


def _rollup_from_items(items: list[sqlite3.Row]) -> str:
    if not items:
        return ""
    recent = list(reversed(items[:5]))
    return "Recent evidence: " + "; ".join(f"{item['item_uid']} {item['summary']}" for item in recent)


def _shelf_markdown(current_shelf: dict[str, Any]) -> str:
    lines = [
        "# Evidence Shelf",
        "",
        f"- Session: `{current_shelf.get('session_id', '')}`",
        f"- Items: `{current_shelf.get('item_count', 0)}`",
        f"- Updated: `{current_shelf.get('updated_at', '')}`",
        "",
        "## Rolling Summary",
        "",
        current_shelf.get("rolling_summary", "") or "_No summary yet._",
        "",
        "## Open Loops",
        "",
    ]
    loops = current_shelf.get("open_loops", [])
    lines.extend([f"- {item}" for item in loops] or ["- None"])
    lines.extend(["", "## Decisions", ""])
    decisions = current_shelf.get("decisions", [])
    lines.extend([f"- {item}" for item in decisions] or ["- None"])
    lines.extend(["", "## Evidence Index", ""])
    for item in current_shelf.get("item_index", []):
        lines.append(f"- `{item.get('item_id')}` {item.get('kind')}: {item.get('summary')}")
    if not current_shelf.get("item_index"):
        lines.append("- No evidence items.")
    lines.append("")
    return "\n".join(lines)


def _redact(text: str, project_root: Path) -> str:
    return sanitize_text(str(text), project_root)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return sanitize_text(str(path), root)


def _session_id(payload: dict[str, Any]) -> str:
    raw = str(payload.get("session_id", "default")).strip()
    return raw or "default"


def _summary(summary: Any, body: str, limit: int = 220) -> str:
    if summary is not None and str(summary).strip():
        return str(summary).strip()[:limit]
    compact = " ".join(str(body).strip().split())
    return compact[:limit] if compact else "(empty evidence)"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        data = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def _optional_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _max_sequence(items: list[sqlite3.Row]) -> int | None:
    values = [item["sequence_end"] for item in items if item["sequence_end"] is not None]
    return max(values) if values else None
